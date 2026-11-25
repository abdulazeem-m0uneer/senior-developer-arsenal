#!/usr/bin/env python3
"""Clock times in outbound text that nothing in the session showed, for guard_lessons' opt-in `unseen-time` rule.

Usage: found = guard_unseen_time.unseen(texts, transcript_path, window_mb=None, agent_id=None, allow=None)
       # [] when all seen; found = ["16:36", ...]
       text = guard_unseen_time.named(found)  # "16:36, 17:36 and 2 more"
The texts are the ones unseen-hash judges (guard_calendar.outbound_texts with messages_only: gh comments, PRs and
issues, the message of a git commit or tag, the registry entry's `programs`, outbound MCP tools, SendMessage). A time
typed from memory or converted by hand is often wrong, so each HH:MM in them (00-23 : 00-59) must have reached the
session from outside the model first: the same transcript entries and window as guard_unseen_hash (tool results, user
text, queued messages and attachments; never the assistant's own text, thinking or tool inputs).
Not judged: a time in an "ETA MM-DD HH:MM" or "ETA HH:MM" clause (a day word, "~" or a date with or without the year
may stand between), a time right after "by", "until", "before" or "at the latest" (the same), a range (09:00-17:00),
a duration after took, takes, lasted, elapsed or duration, a time in a code span, a fenced
block or a URL, and the registry entry's "allow" words (exact HH:MM, so "16:36"). The seconds of a time (16:36:44) are
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
Standard library and guard_unseen_hash, guard_calendar only.
"""
import json
import re
import time
from datetime import datetime, timedelta, timezone

import guard_unseen_hash
from guard_unseen_hash import OutOfTime, agent_transcript, read_tail, seen_texts, window_bytes

MAX_TIMES = 16
BUDGET_SECONDS = guard_unseen_hash.BUDGET_SECONDS
ZONE_WEEKS = 60  # the zone's offsets are sampled weekly this far back and forward from now
HH_MM = r"(?:[01]\d|2[0-3]):[0-5]\d"
DATE_PREFIX = r"(?:(?:\d{4}-)?\d\d-\d\d[t\s]+)?"
TIME = re.compile(rf"(?<![\d:.]){HH_MM}(?!\d|:\d\d:)")
DAY = r"(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*|today|tomorrow|tonight)"
FUTURE = rf"~?\s*(?:{DAY}\s+)?{DATE_PREFIX}~?{HH_MM}(?!\d)"
SPAN_OF_TIME = (rf"(?<![\d:.]){HH_MM}\s*[-\u2013]\s*{HH_MM}(?!\d)"
                rf"|\b(?:took|takes|lasted|elapsed|duration):?\s*{HH_MM}(?!\d)")
CLAUSE = re.compile(rf"\beta\b:?\s*{FUTURE}|\b(?:by|until|before|at the latest)\s+{FUTURE}|{SPAN_OF_TIME}", re.I)
FENCE = re.compile(r"```.*?```", re.S)
SPAN = re.compile(r"`[^`\n]*`")
URL = re.compile(r"https?://\S+", re.I)
STAMP = re.compile(r"(\d{4})-(\d\d)-(\d\d)[t ]([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d)(?:\.\d+)?)?"
                   r"(?:(z(?![a-z])|[+-]\d\d(?::?\d\d)?)|\s([+-]\d{4}))?", re.I)
REFUSAL = re.compile(r"arsenal lesson guard \S+ \(unseen-time\): ")  # guard.refusal_text, lowercased

named = guard_unseen_hash.named


def times(texts, allow=None):
    """The distinct HH:MM in the texts that the rule judges, in order, at most MAX_TIMES."""
    skip = {word.lower() for word in allow or () if isinstance(word, str)}
    found = {}
    for text in texts:
        if not isinstance(text, str):
            continue
        text = URL.sub(" ", SPAN.sub(" ", FENCE.sub(" ", text)))
        text = STAMP.sub(lambda match: f" {match.group(4)}:{match.group(5)} ", CLAUSE.sub(" ", text))
        for match in TIME.finditer(text):
            if match.group() not in skip:
                found[match.group()] = None
    return list(found)[:MAX_TIMES]


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
    shown.update(match.group() for match in TIME.finditer(STAMP.sub(" ", text)))
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

    def seen(self, wanted, candidate):
        """True when a seen entry shows the time; the lines holding any needle are parsed newest first."""
        for needle in wanted:
            end = len(self.data)
            while True:
                pos = self.data.rfind(needle, 0, end)
                if pos < 0:
                    break
                end, shown = self.line_times(pos)
                if candidate in shown:
                    return True
        return False


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
        searched = {candidate: needles(candidate, offsets) for candidate in wanted}
        for candidate in wanted:  # times printed nowhere first: parsing lines must not spend their budget
            window.tick()
            if not window.shows_any(searched[candidate]):
                found.add(candidate)
        for candidate in wanted:
            if candidate not in found and not window.seen(searched[candidate], candidate):
                found.add(candidate)
    except OutOfTime:  # a time judged unseen stays unseen; the ones not judged yet pass
        pass
    except Exception:  # fail open: a broken check never refuses a call
        return []
    return [candidate for candidate in wanted if candidate in found]
