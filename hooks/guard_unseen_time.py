#!/usr/bin/env python3
"""Clock times in outbound text that nothing in the session showed, for guard_lessons' opt-in `unseen-time` rule.

Usage: found = guard_unseen_time.unseen(texts, transcript_path, window_mb=None, agent_id=None, allow=None)
       # [] when all seen; found = ["16:36", ...]
       text = guard_unseen_time.named(found)  # "16:36, 17:36 and 2 more"
       guard_unseen_time.remember(transcript_path, agent_id=None)  # guard.py track: keep the times seen so far
The texts are the ones unseen-hash judges (guard_calendar.outbound_texts with messages_only: gh comments, PRs and
issues, the message of a git commit or tag, the registry entry's `programs` (a script an interpreter runs too, and the text of its --body-file or --file
unless the call writes it), outbound MCP tools, SendMessage). A time
typed from memory or converted by hand is often wrong, so each HH:MM in them (00-23 : 00-59) must have reached the
session from outside the model first: the same transcript entries and window as guard_unseen_hash (tool results, user
text, queued messages and attachments; never the assistant's own text, thinking or tool inputs).
A masked time (16:0x, 16:3X: a minute digit 0-5, then x or X) is judged as one time: it is seen when any of the ten
times 16:00 to 16:09 is, or when a seen entry shows it as written (any case); the refusal names it as written.
Not judged: a time in an "ETA MM-DD HH:MM" or
"ETA HH:MM" clause (a day word, "~" or a date with or without the year may stand between), a time right after "by",
"until", "before" or "at the latest" (the same), a range (09:00-17:00), a duration after took, takes, lasted, elapsed
or duration, a time in a code span, a fenced block or a URL, and the registry entry's "allow" words (exact HH:MM, so
"16:36", or a masked HH:Mx, so "16:3x", in either case). The seconds of a time (16:36:44) are
not judged; the minutes and seconds of a longer one (the 11:12 in 10:11:12, a MAC address) are not times.
Seen: the HH:MM appears in a seen entry, or an ISO timestamp there (2026-11-25T16:36:44Z, 2026-11-25 19:36:44 +0300)
that has a zone gives it: the written time, its UTC time and its time in the machine's own zone on that date (the
daylight saving offset of that day). A timestamp without a zone counts as written only. Finding: the window is searched
for the time, for the times a UTC stamp or a stamp in the machine's zone would show it as (the zone's offsets over the
last and next year), and for no other. A stamp in some other offset (+02:00 on a machine at +03:00) is found by the
time it shows, not by its UTC or local reading. A line that is a refusal by this rule shows nothing.
Cost, fail-open and the budget are guard_unseen_hash's: the last `window_mb` MB (default and most 16), 0.2 s for the
read and the check together, at most MAX_TIMES distinct times per call; a missing or unreadable transcript, a timeout
before a time was judged unseen or any error passes the call. A call with no time reads nothing.
Older text: a time the window does not show still counts as seen when remember() kept it. guard.py track calls it
after each Bash call while the rule is on: it parses the next CHUNK_BYTES of the transcript from where the last call
stopped (from the start on the first call) and keeps the times seen entries show in a small per-transcript cache
($ARSENAL_SEEN_TIMES_DIR, default ~/.cache/arsenal/seen-times). Measured on a 108 MB transcript: about 0.1 s per call
while it catches up (29 calls), 0.05 ms when idle; the judge reads the cache only for a time the window did not show.
Whole-file search instead was measured at 0.07-0.09 s per needle and 108 MB, five needles per time: over the budget.
Not kept: a line longer than a chunk, and the text after the last call (the window holds it).
Standard library and guard_unseen_hash, guard_calendar only.
"""
import hashlib
import json
import os
import re
import stat
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import guard_unseen_hash
from guard_unseen_hash import OutOfTime, agent_transcript, read_tail, seen_texts, window_bytes

MAX_TIMES = 16
BUDGET_SECONDS = guard_unseen_hash.BUDGET_SECONDS
ZONE_WEEKS = 60  # the zone's offsets are sampled weekly this far back and forward from now
HH_MM = r"(?:[01]\d|2[0-3]):[0-5]\d"
HH_MX = r"(?:[01]\d|2[0-3]):[0-5](?:\d|x(?!\w))"  # HH:MM, or HH:Mx with a masked minute (case-insensitive)
DATE_PREFIX = r"(?:(?:\d{4}-)?\d\d-\d\d[t\s]+)?"
TIME = re.compile(rf"(?<![\d:.]){HH_MM}(?!\d|:\d\d:)")
TAIL = re.compile(rb":\d\d:")  # the minute and second of a longer reading
MASKED = re.compile(r"(?<![\d:.])(?:[01]\d|2[0-3]):[0-5]x(?!\w)", re.I)  # TIME's left edge, so 2026-11-25T16:3x is judged
DAY = r"(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*|today|tomorrow|tonight)"
FUTURE = rf"~?\s*(?:{DAY}\s+)?{DATE_PREFIX}~?{HH_MX}(?!\d)"
SPAN_OF_TIME = (rf"(?<![\d:.]){HH_MX}\s*[-\u2013]\s*{HH_MX}(?!\d)"
                rf"|\b(?:took|takes|lasted|elapsed|duration):?\s*{HH_MX}(?!\d)")
CLAUSE = re.compile(rf"\beta\b:?\s*{FUTURE}|\b(?:by|until|before|at the latest)\s+{FUTURE}|{SPAN_OF_TIME}", re.I)
FENCE = re.compile(r"```.*?```", re.S)
SPAN = re.compile(r"`[^`\n]*`")
URL = re.compile(r"https?://\S+", re.I)
STAMP = re.compile(r"(\d{4})-(\d\d)-(\d\d)[t ]([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d)(?:\.\d+)?)?"
                   r"(?:(z(?![a-z])|[+-]\d\d(?::?\d\d)?)|\s([+-]\d{4}))?", re.I)
REFUSAL = re.compile(r"arsenal lesson guard \S+ \(unseen-time\): ")  # guard.refusal_text, lowercased
CHUNK_BYTES = 4 * 1024 * 1024  # one remember() parses at most this much: about 90 ms on a real transcript
CACHE_DIR_ENV = "ARSENAL_SEEN_TIMES_DIR"
CACHE_DAYS = 30  # a cache file not written for this long is removed when another one is created
MAX_PRUNED = 1000  # cache files looked at per prune
SKIPS_PER_TICK = 4096  # needle hits that are no time, passed between two reads of the clock
HEX = b"0123456789abcdef"

named = guard_unseen_hash.named


def times(texts, allow=None):
    """The distinct HH:MM, and HH:Mx with a masked minute (as first written), in the texts that the rule judges, in
    order, at most MAX_TIMES."""
    skip = {word.lower() for word in allow or () if isinstance(word, str)}
    found = {}
    for text in texts:
        if not isinstance(text, str):
            continue
        text = URL.sub(" ", SPAN.sub(" ", FENCE.sub(" ", text)))
        text = STAMP.sub(lambda match: f" {match.group(4)}:{match.group(5)} ", CLAUSE.sub(" ", text))
        matches = sorted((match.start(), match.group()) for rule in (TIME, MASKED) for match in rule.finditer(text))
        for _, written in matches:
            if written.lower() not in skip:
                found.setdefault(written.lower(), written)
    return list(found.values())[:MAX_TIMES]


def readings(candidate):
    """The times a candidate stands for: itself, or the ten times its masked minute could be."""
    return [f"{candidate[:-1]}{digit}" for digit in range(10)] if candidate[-1] in "xX" else [candidate]


def clock_time(moment):
    return f"{moment.hour:02d}:{moment.minute:02d}"


def stamp_times(match):
    """The readings of one ISO timestamp: its written time, and with a zone its UTC and machine-zone times."""
    written = f"{match.group(4)}:{match.group(5)}"
    zone = match.group(7) or match.group(8)
    if not zone:
        return {written}
    try:
        if zone.lower() == "z":
            offset = timedelta(0)
        else:
            digits = zone[1:].replace(":", "")
            offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:] or 0))
            offset = -offset if zone[0] == "-" else offset
        moment = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4)),
                          int(match.group(5)), tzinfo=timezone(offset))
        return {written, clock_time(moment.astimezone(timezone.utc)), clock_time(moment.astimezone())}
    except (ValueError, OverflowError, OSError):  # a date that does not exist, or one the zone cannot convert
        return {written}


def entry_times(text):
    """Every HH:MM a seen text shows (see the module text)."""
    shown = set()
    for match in STAMP.finditer(text):
        shown |= stamp_times(match)
    plain = STAMP.sub(" ", text)
    shown.update(match.group() for match in TIME.finditer(plain))
    shown.update(match.group().lower() for match in MASKED.finditer(plain))  # a masked time as written
    return shown


def zone_offsets(now=None):
    """The machine zone's UTC offsets, in minutes, sampled weekly over the last and next year."""
    now = time.time() if now is None else now
    return {time.localtime(now + week * 7 * 86400).tm_gmtoff // 60 for week in range(-ZONE_WEEKS, ZONE_WEEKS + 1)}


def needles(clock_value, offsets):
    """The times whose appearance in the window could show this time: itself, and it moved by each zone offset."""
    hours, minutes = clock_value.split(":")
    minute = int(hours) * 60 + int(minutes)
    moved = {(minute + sign * offset) % 1440 for offset in offsets for sign in (-1, 1)} | {minute}
    return [f"{value // 60:02d}:{value % 60:02d}".encode() for value in sorted(moved)]


def accepted(candidate):
    """The texts of a seen entry that make a candidate seen: its readings, and a masked one as written."""
    return [*readings(candidate), candidate.lower()]


def search_terms(candidate, offsets):
    """What the window is searched for: the needles of a time, and for a masked one their shared HH:M prefixes
    (ten times in one search each, so a masked time costs about what a plain one does) and itself as written."""
    found = {needle for reading in readings(candidate) for needle in needles(reading, offsets)}
    if candidate[-1] not in "xX":
        return sorted(found)
    return sorted({needle[:-1] for needle in found} | {candidate.lower().encode()})


class Window:
    """One lowercased transcript window and the times found so far in the lines parsed."""

    def __init__(self, data, deadline, clock):
        self.data, self.deadline, self.clock, self.parsed = data, deadline, clock, {}

    def tick(self):
        if self.clock() > self.deadline:
            raise OutOfTime()

    def shows_any(self, wanted):
        return any(needle in self.data for needle in wanted)

    def line_times(self, pos):
        start = self.data.rfind(b"\n", 0, pos) + 1
        if start not in self.parsed:
            self.tick()
            end = self.data.find(b"\n", pos)
            self.parsed[start] = self.read_line(start, len(self.data) if end < 0 else end)
        return start, self.parsed[start]

    def read_line(self, start, end):
        try:
            entry = json.loads(self.data[start:end])
        except ValueError:  # a line cut by the window or a partial write
            return set()
        shown = set()
        for text in seen_texts(entry) if isinstance(entry, dict) else []:
            for line in text.splitlines():
                if not REFUSAL.search(line):
                    shown |= entry_times(line)
        return shown

    def after_unicode_escape(self, pos):
        """Whether the digit before pos ends a JSON \\uXXXX escape: the decoded text has a non-digit there."""
        return (pos >= 6 and self.data[pos - 6:pos - 4] == b"\\u"
                and all(byte in HEX for byte in self.data[pos - 4:pos]))

    def is_time_at(self, pos, needle):
        """Whether the needle found at pos is a time, by the edges TIME uses: no digit, ":" or "." before it, and after
        it (a masked minute's prefix needs its digit first) no digit and no ":SS:"."""
        after = pos + len(needle)
        if pos and self.data[pos - 1:pos] in b"0123456789:." and not self.after_unicode_escape(pos):
            return False
        if needle.endswith(b"x"):  # a masked time as written
            return not re.match(rb"\w", self.data[after:after + 1])
        if len(needle) < len(b"HH:MM"):  # the HH:M prefix of a masked time
            if not self.data[after:after + 1].isdigit():
                return False
            after += 1
        return not self.data[after:after + 1].isdigit() and not TAIL.match(self.data, after)

    def seen(self, wanted, candidates):
        """True when a seen entry shows one of the times; the lines holding any needle are parsed newest first."""
        skipped = 0
        for needle in wanted:
            end = len(self.data)
            while True:
                pos = self.data.rfind(needle, 0, end)
                if pos < 0:
                    break
                end = pos
                if not self.is_time_at(pos, needle):
                    skipped += 1
                    if skipped % SKIPS_PER_TICK == 0:
                        self.tick()
                    continue
                end, shown = self.line_times(pos)
                if shown.intersection(candidates):
                    return True
        return False


def cache_path(transcript_path):
    """The cache file of one transcript, under $ARSENAL_SEEN_TIMES_DIR or ~/.cache/arsenal/seen-times."""
    folder = os.environ.get(CACHE_DIR_ENV) or os.path.join(os.path.expanduser("~"), ".cache", "arsenal", "seen-times")
    key = hashlib.sha256(os.path.realpath(transcript_path).encode("utf-8", "surrogateescape")).hexdigest()[:32]
    return Path(folder) / f"{key}.json"


def load_cache(path):
    """{"size": bytes read, "cut": inside a line longer than a chunk, "times": [...]}, or None when missing or bad."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    size, times_seen, cut = data.get("size"), data.get("times"), data.get("cut", False)
    valid = (isinstance(size, int) and not isinstance(size, bool) and size >= 0 and isinstance(cut, bool)
             and isinstance(times_seen, list)
             and all(isinstance(t, str) and re.fullmatch(HH_MX, t, re.I) for t in times_seen))
    return {"size": size, "cut": cut, "times": times_seen} if valid else None


def remembered(transcript_path):
    """The times remember() kept for this transcript; set() when there are none or on any error."""
    try:
        if not isinstance(transcript_path, str) or not transcript_path:
            return set()
        data = load_cache(cache_path(transcript_path))
        return set(data["times"]) if data else set()
    except Exception:
        return set()


def prune(folder, now):
    """Remove cache files not written for CACHE_DAYS (a session's cache outlives it otherwise)."""
    with os.scandir(folder) as entries:
        for count, entry in enumerate(entries):
            if count >= MAX_PRUNED:
                break
            if (entry.name.endswith((".json", ".tmp")) and entry.is_file()
                    and now - entry.stat().st_mtime > CACHE_DAYS * 86400):  # .tmp: a write that crashed midway
                os.unlink(entry.path)


def save_cache(path, data):
    created = not path.exists()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        scratch.write_text(json.dumps(data), encoding="utf-8")
        os.replace(scratch, path)  # parallel writers each leave a whole file; a lost one is reread from its size
    finally:
        if scratch.exists():  # the replace did not happen: no scratch file is left behind
            scratch.unlink()
    if created:
        prune(path.parent, time.time())


def remember(transcript_path, agent_id=None):
    """Add the times the next transcript lines (at most CHUNK_BYTES) show to the transcript's cache, so a time stays
    seen after it left the window. guard.py track calls it after each Bash call while the rule is on. A line longer
    than a chunk is skipped; a line still being written waits for the next call. Never raises."""
    try:
        if not isinstance(transcript_path, str) or not transcript_path:
            return
        if agent_id:
            transcript_path = agent_transcript(transcript_path, agent_id)
            if transcript_path is None:
                return
        if not stat.S_ISREG(os.stat(transcript_path).st_mode):
            return
        cache = cache_path(transcript_path)
        data = load_cache(cache) or {"size": 0, "cut": False, "times": []}
        with open(transcript_path, "rb") as handle:
            if os.fstat(handle.fileno()).st_size < data["size"]:  # rewritten: what it showed before is gone
                data = {"size": 0, "cut": False, "times": []}
            handle.seek(data["size"])
            chunk = handle.read(CHUNK_BYTES).lower()
        whole = chunk.rfind(b"\n") + 1  # the bytes up to the last whole line
        if not whole:
            if len(chunk) < CHUNK_BYTES:
                return  # nothing new, or a line still being written
            data.update(size=data["size"] + len(chunk), cut=True)  # inside a line longer than a chunk
        else:
            start = chunk.find(b"\n") + 1 if data["cut"] else 0  # the rest of a skipped long line
            window, shown = Window(chunk, float("inf"), time.monotonic), set(data["times"])
            while start < whole:
                end = chunk.find(b"\n", start)
                shown |= window.read_line(start, end)
                start = end + 1
            data.update(size=data["size"] + whole, cut=False, times=sorted(shown))
        save_cache(cache, data)
    except Exception:  # the tracker must never break a session
        return


def unseen(texts, transcript_path, window_mb=None, clock=time.monotonic, budget=BUDGET_SECONDS, agent_id=None,
           allow=None):
    """The times in the texts that no seen entry of the transcript window showed; [] on any failure, and only the
    ones judged before the budget ran out on a timeout."""
    found = set()
    try:
        wanted = times(texts or [], allow)
        if not wanted or not isinstance(transcript_path, str) or not transcript_path:
            return []
        deadline = clock() + budget
        if agent_id:  # inside a subagent; absent or empty in the main session
            transcript_path = agent_transcript(transcript_path, agent_id)
            if transcript_path is None:
                return []
        window = Window(read_tail(transcript_path, window_bytes(window_mb)), deadline, clock)
        offsets = zone_offsets()
        searched = {candidate: search_terms(candidate, offsets) for candidate in wanted}
        for candidate in wanted:  # times printed nowhere first: parsing lines must not spend their budget
            window.tick()
            if not window.shows_any(searched[candidate]):
                found.add(candidate)
        for candidate in wanted:
            if candidate not in found and not window.seen(searched[candidate], accepted(candidate)):
                found.add(candidate)
    except OutOfTime:  # a time judged unseen stays unseen; the ones not judged yet pass
        pass
    except Exception:  # fail open: a broken check never refuses a call
        return []
    if found:  # older text: the times remember() kept before it left the window
        kept = remembered(transcript_path)
        found = {candidate for candidate in found if kept.isdisjoint(accepted(candidate))}
    return [candidate for candidate in wanted if candidate in found]
