#!/usr/bin/env python3
"""Quote a status read from a file together with its age, so a stale reading is never passed off as current.

usage: reading.py get FILE [--key K] [--max-age 30m|2h|1d] [--time-key T] [--json]
       reading.py write FILE --key K --value V
       reading.py check-report REPORT [--max-age 30m] [--words w1,w2,...]
                                  [--claim-words w1,w2,...] [--no-claims]

get: prints the value and where its time came from, e.g.
  98% (as of 2026-11-20 14:05 +03:00, 12 min old)          time read from the file's own field
  98% (file modified 2026-11-20 14:05 +03:00, 12 min old)  no time field: the file's mtime, the weaker source
  STALE: 80% (as of 2026-11-20 13:00 +03:00, 1 h 17 min old; limit 30 min)
  FUTURE: 98% (as of 2026-11-20 14:30 +03:00, 13 min ahead of the clock)
A JSON object file needs --key. The time is the first found, strongest source first, of: the time field inside the
key's own object value ({"<key>": {"value": V, "as_of": T}} is what `write` stores; {"<key>": {"pct": 80,
"updated_at": T}} works too; the printed value is its "value" member, else the object without the time field); a
field named for the key (<key>_as_of, <key>_updated_at, <key>_timestamp, <key>_time); then a file-wide field (as_of, updated_at, timestamp, time), which is
the weakest JSON source because it says when the file was stamped, not when this key was. With --time-key T only the
name T is looked for, in the same three places, and it must be found. A time is an ISO 8601 string with an offset
(Z allowed) or epoch seconds; one that is present but unreadable is an error and never falls back. None found: the
file's mtime. --json "source" names the place ("field:quota.as_of",
"field:quota_as_of", "field:as_of"). Any other file is plain text: the whole stripped content, with its mtime. Files over 64 KB are refused. Without --max-age a
reading is never stale. An age equal to --max-age is fresh; one second more is stale. A time up to 2 minutes ahead
of the clock counts as age 0 (clock skew); further ahead it is reported as FUTURE, never fresh, even without
--max-age. Ages are shown whole minutes, rounded down. --json prints one object: value, time, source
("field:<name>" or "file modified"), age_seconds, max_age_seconds (null without a limit), status
(fresh|stale|future).

write: stores {"value": V, "as_of": now (ISO 8601, offset)} under the key, so a watcher job records the time with
the value and writing one key never refreshes another. Every other flat key without its own time is first stamped with the time it has now (its
<key>_<name> field, else the file-wide field, else the file's mtime before this write), so replacing the file never makes an old reading look
new; a file-wide time and <key>_<name> fields stay as they are, and an unreadable one makes the write exit 2,
nothing changed. The file is resolved through symlinks first, so a link stays a link and every spelling shares one
lock; a
missing file is created; a file that is not a JSON object is refused untouched; the names as_of, updated_at,
timestamp and time cannot be keys. The read-modify-write holds an exclusive lock on the sibling file
.<name>.lock (left in place) and the file is replaced atomically; a lock held for 10 s exits 2, nothing written.

check-report: scans a draft report for readings quoted without their age. A line is checked when it has
  1. an "as of" marker: (as of 2026-11-20 14:05 +03:00), (as of 2026-11-20 14:05) in the clock's offset, or
     (as of 14:05) meaning today (use the full date for yesterday); an offset may be +03:00, +0300 or Z. The
     output of `get` can be pasted as it is: text after a comma inside the brackets is ignored, and the
     "(file modified <time>)" form counts as a marker. Every marker is compared with the clock, not with the age
     written beside it: older than --max-age (default 30m) is "STALE line N", ahead of the clock beyond the 2
     minutes of skew is "FUTURE line N", an unreadable time is "BAD-MARKER line N".
  2. a percentage (91%, 97.5 %) or a status word (--words, comma separated, replaces the default
     quota,usage,release,deployed,CI,green,red,passing; whole words, any case, so "reduced" does not match
     "red") that no marker covers: "NO-MARKER line N (<trigger>)". A marker covers the text before it back to the
     previous marker, a semicolon or the line start ("quota 80% (as of T); usage 98%" flags usage). Write a
     reading before its marker: text after a marker is uncovered until the next marker. A line over 4000 characters is not scanned: "TOO-LONG line N" (a finding; split the
     line). Blank lines are skipped; nothing else is guessed, so a prose line that merely contains "red" is flagged too and is fixed by rewording or by the opt-out below.
Opt-out for a line that was read live in this very turn: (live: <command>) naming the command that produced it
(no ")" inside). A bare (live) or an empty command does not opt out. The opt-out only silences NO-MARKER; markers
on the same line are still checked. Prints one line per finding, then "<n> finding(s)", or "ok: ..." when clean.

Claims (on unless --no-claims): another session's word is not a source, so a status claim must cite what this run read.
  A CLAIM is, by default, an inflected form of merge, deploy, release, ship, verify, pass, fix or close, with an
  optional re- or un- prefix: merges merged merging, deploys deployed deploying, releases released releasing, ships
  shipped shipping, verifies verified verifying, passes passed passing, fixes fixed fixing, closes closed closing
  (whole words, any case). The base form ("we will fix") is a plan, not a claim; a hyphen right after the word
  ("fixed-width") is not a claim. Known false positives, the price of the rule: "closed questions", "passed away".
  done, live and green are left to the reading words above. --claim-words w1,w2,... replaces the default with exact
  words (no inflection, no prefix; the hyphen rule is not applied). A negated claim ("not merged") is still a claim
  about state and is flagged like any other. Claim words inside a `code span`, a closed ``` fenced block or a valid
  (source: ...) or (live: ...) marker (`gh pr view 741 -> MERGED`) are not claims; a claim word in the free text of an
  "as of" marker ("(as of 14:05, backend: #741 merged)") is a claim. (Markdown table separator rows hold no words, so
  they need no rule; other rows are checked.) Before matching, format characters (Unicode category Cf: zero-width
  space and joiners, BOM, soft hyphen) are removed and the line is NFKC-normalised, so "Mer<ZWSP>ged" and fullwidth
  letters are caught; homoglyphs beyond NFKC (Cyrillic "e" in "merged") are out of scope.
  A fence line starts with ``` and holds no other ```, so an inline ```x``` is not one. A fence never closed is
  "UNCLOSED-FENCE line N" (N = its opening line, exit 1) and fails closed: the lines after it are checked anyway.
  The ONLY accepted sources are two explicit markers, one example each:
    (source: gh pr view 741 -> MERGED abc1234)    what you read: a URL or a command, with what it showed
    (live: gh pr view 741 --json state)           the command you ran this turn
  Its content must be a URL (http or https) or a command: two or more tokens, the first a word of 2+ letters, digits
  or - . _ / ; placeholders ("-", x, n/a, tbd, todo, ?, none, see above) are not: "NO-SOURCE line N (<word>): source
  is not a command or link". One level of balanced parentheses inside a marker is allowed. A marker covers the claim
  words in its own clause: before it, back to the previous marker (any kind, "as of" included), the line start, or
  any of . ; , ! ? followed by a space or the end of the text before the marker, or any of the fullwidth marks
  U+3002 U+FF1B U+FF0C U+FF01 U+FF1F (these break even without a space). So "merged, verified (source: X)"
  flags merged, and a later unrelated marker never covers an earlier sentence. A bare SHA, URL, run id, date or
  "#741" is never a source: it is the claim's subject or copied text, so the writer puts it inside the marker. An
  "as of" marker does not vouch for a claim. An empty "(source: )" or a bare "(live)" is no marker.
  NO-SOURCE line N (<claim word>): a claim not covered by a valid (source: ...) or (live: ...) marker. This also
  catches forwarded lines in any form ("backend: #741 merged", "> qa: fixed", "per the bus: closed").
  BUS-CLAIM line N (<claim word>): the text of a (source: ...) or (live: ...) marker cites the bus, another session
  or the writer's own say-so instead of a read: it contains ask, session, lane, agent, channel, message, inbox, bus,
  said, says, reported, told, confirmed, confirms, trust, "verified by", "checked by", me, we, they, "per " or
  "according to" (any case; a hyphen counts as a word edge). Rewrite the marker with what you read yourself.
  EVERY marker is validated wherever it sits, with or without a claim on the line; one with no claim word inside is
  named "(marker)". An invalid marker also fails the claims before it in its clause.
  Threat model: this catches honest mistakes (forgetting a source, forwarding a bus line as a fact), not deliberate
  evasion. The marker must hold the actual command or link that was run; a made-up command passes the check.
  One finding per line (the first failing claim), reported next to STALE and NO-MARKER findings of the same line.
  Lines over the length limit are not claim-checked.

READING_NOW (ISO 8601; no offset means local time) fixes the clock for tests. Standard library only.
Exit: 0 fresh or clean, 1 STALE or FUTURE (get) or findings (check-report), 2 unreadable or missing file, key or
time, bad --max-age, unreadable clock, unwritable target, or a usage error.
"""
import argparse
import contextlib
import datetime as dt
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

MAX_READ = 64 * 1024
MAX_REPORT = 1024 * 1024
SKEW = dt.timedelta(minutes=2)
TIME_KEYS = ("as_of", "updated_at", "timestamp", "time")
RESERVED_KEY = "as_of"
LOCK_WAIT = 10.0
LOCK_POLL = 0.02
DEFAULT_MAX_AGE = "30m"
CLAIM_FORMS = (  # inflected forms only: the base form ("we will fix") is a plan, not a claim
    "merges|merged|merging|deploys|deployed|deploying|releases|released|releasing|ships|shipped|shipping|"
    "verifies|verified|verifying|passes|passed|passing|fixes|fixed|fixing|closes|closed|closing"
)
DEFAULT_WORDS = ("quota", "usage", "release", "deployed", "CI", "green", "red", "passing")
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
SNIPPET = 100
MAX_LINE = 4000  # longer lines are not scanned; every pattern is bounded, so a line costs time linear in its length

AGE_RE = re.compile(r"(\d+)([smhd])")
MARKER_RE = re.compile(r"\((as of|file modified)\s{1,5}([^(),]{0,40}?)\s{0,5}(?:,[^()]{0,200})?\)", re.IGNORECASE)
MARKER_TIME_RE = re.compile(r"(?:(\d{4})-(\d{2})-(\d{2})[ T])?(\d{2}):(\d{2})(?:\s*(Z|[+-]\d{2}:?\d{2}))?", re.IGNORECASE)
LIVE_RE = re.compile(r"\(live:\s{0,5}(?=[^)\s])(?:[^()]|\([^()]{0,100}\)){1,300}\)")
SOURCE_MARK_RE = re.compile(r"\(source:\s{0,5}(?=[^)\s])(?:[^()]|\([^()]{0,100}\)){1,300}\)", re.IGNORECASE)
CODE_SPAN_RE = re.compile(r"`[^`]{0,300}`")
BUS_CUE_RE = re.compile(
    r"(?<!\w)(?:ask|session|lane|agent|channel|message|inbox|bus|said|says|reported|told|confirmed|confirms|trust|"
    r"verified by|checked by|me|we|they|according to)(?!\w)|(?<!\w)per\s",
    re.IGNORECASE,
)
CLAIM_RE = re.compile(r"(?<!\w)(?:re|un)?(?:" + CLAIM_FORMS + r")(?!\w|-\w)", re.IGNORECASE)
COMMAND_WORD_RE = re.compile(r"(?=[^A-Za-z0-9]*[A-Za-z0-9])[A-Za-z0-9._/-]{2,}")
URL_TOKEN_RE = re.compile(r"https?://\S+", re.IGNORECASE)
PLACEHOLDERS = frozenset({"-", "x", "n/a", "tbd", "todo", "?", "none", "see", "above"})
CLAUSE_BREAK_RE = re.compile(r"[.;,!?](?:\s|$)|\u3002")
FENCE = "```"
PERCENT_RE = re.compile(r"\d{1,6}(?:\.\d{1,6})?\s{0,3}%")


class ReadingError(Exception):
    """Exit 2: unreadable file, key, time, limit or clock."""


def clock():
    value = os.environ.get("READING_NOW")
    if not value:
        return dt.datetime.now().astimezone()
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        raise ReadingError(f"READING_NOW is not ISO 8601: {value!r}") from None
    return parsed if parsed.tzinfo else parsed.astimezone()


def parse_age(text):
    match = AGE_RE.fullmatch(text)
    seconds = int(match.group(1)) * UNITS[match.group(2)] if match else 0
    if seconds <= 0:
        raise ReadingError(f"bad age {text!r}: use a positive whole number and s, m, h or d (30m, 2h, 1d)")
    return dt.timedelta(seconds=seconds)


def format_duration(delta):
    minutes = max(int(delta.total_seconds()), 0) // 60
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    if days:
        return f"{days} d" + (f" {hours} h" if hours else "")
    if hours:
        return f"{hours} h" + (f" {mins} min" if mins else "")
    return f"{mins} min"


def format_time(moment):
    offset = int(moment.utcoffset().total_seconds()) // 60
    sign = "-" if offset < 0 else "+"
    hours, mins = divmod(abs(offset), 60)
    return f"{moment:%Y-%m-%d %H:%M} {sign}{hours:02d}:{mins:02d}"


def read_bounded(path, limit):
    """Return (text, mtime epoch seconds); refuses a file over limit bytes or not UTF-8."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(limit + 1)
            mtime = os.fstat(handle.fileno()).st_mtime
    except OSError as exc:
        raise ReadingError(f"{path}: {exc.strerror or exc}") from None
    if len(data) > limit:
        raise ReadingError(f"{path}: larger than {limit // 1024} KB")
    try:
        return data.decode("utf-8"), mtime
    except UnicodeDecodeError:
        raise ReadingError(f"{path}: not UTF-8 text") from None


def parse_field_time(value, now):
    """A time field: epoch seconds or ISO 8601 with an offset."""
    try:
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, (int, float)):
            return dt.datetime.fromtimestamp(value, dt.timezone.utc).astimezone(now.tzinfo)
        if isinstance(value, str):
            parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00" if value[-1:] in "Zz" else value)
            if parsed.tzinfo:
                return parsed
    except (ValueError, OverflowError, OSError):
        pass
    raise ReadingError(f"time {value!r} is not epoch seconds or ISO 8601 with an offset")


def load_reading(path, key, time_key, now):
    """Return (value, moment, label, source)."""
    text, mtime = read_bounded(path, MAX_READ)
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        if key:
            raise ReadingError(f"{path}: not a JSON object, cannot read key {key!r}")
        value = text.strip()
        if not value:
            raise ReadingError(f"{path}: empty")
        return value, file_moment(mtime, now), "file modified", "file modified"
    if not key:
        raise ReadingError(f"{path}: a JSON object needs --key")
    names = (time_key,) if time_key else TIME_KEYS
    entry = data.get(key)
    own = own_entry(entry, names)
    value = entry_value(entry, own) if own else entry
    if value is None:
        raise ReadingError(f"{path}: no value for key {key!r}")
    found = find_time(data, key, names)
    if found is None:
        if time_key:
            raise ReadingError(f"{path}: no time field {time_key!r} for key {key!r}")
        return value, file_moment(mtime, now), "file modified", "file modified"
    return value, parse_field_time(found[0], now), "as of", f"field:{found[1]}"


def own_entry(entry, names):
    """The time field name inside an object value that carries its own time, else None."""
    return next((n for n in names if entry.get(n) is not None), None) if isinstance(entry, dict) else None


def entry_value(entry, time_name):
    """What an object with its own time stands for: its "value" member, else itself without the time field."""
    return entry["value"] if "value" in entry else {k: v for k, v in entry.items() if k != time_name}


def find_time(data, key, names):
    """(raw time, source label) for a key, strongest first: inside its own object, <key>_<name>, then file-wide."""
    entry, own = data.get(key), own_entry(data.get(key), names)
    lookups = (
        ([(entry, own, f"{key}.{own}")] if own else [])
        + [(data, f"{key}_{n}", f"{key}_{n}") for n in names]
        + [(data, n, n) for n in names]
    )
    return next(((src[field], label) for src, field, label in lookups if src.get(field) is not None), None)


def file_moment(mtime, now):
    return dt.datetime.fromtimestamp(mtime, dt.timezone.utc).astimezone(now.tzinfo)


def render_value(value):
    return value if isinstance(value, str) else json.dumps(value)


def judge(age, limit):
    if age < -SKEW:
        return "future"
    return "stale" if limit is not None and age > limit else "fresh"


def cmd_get(args, out, now):
    limit = parse_age(args.max_age) if args.max_age is not None else None
    value, moment, label, source = load_reading(args.file, args.key, args.time_key, now)
    age = now - moment
    status = judge(age, limit)
    if args.json:
        out(json.dumps({
            "value": value,
            "time": moment.isoformat(timespec="seconds"),
            "source": source,
            "age_seconds": max(int(age.total_seconds()), 0) if status != "future" else int(age.total_seconds()),
            "max_age_seconds": int(limit.total_seconds()) if limit is not None else None,
            "status": status,
        }))
    else:
        where = f"{label} {format_time(moment)}"
        text = render_value(value)
        if status == "future":
            out(f"FUTURE: {text} ({where}, {format_duration(-age)} ahead of the clock)")
        elif status == "stale":
            out(f"STALE: {text} ({where}, {format_duration(age)} old; limit {format_duration(limit)})")
        else:
            out(f"{text} ({where}, {format_duration(age)} old)")
    return 0 if status == "fresh" else 1


def try_lock(handle):
    try:
        if fcntl:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


@contextlib.contextmanager
def locked(target):
    """Exclusive cross-process lock for one read-modify-write; the OS drops it when the holder exits."""
    try:
        handle = open(target.with_name(f".{target.name}.lock"), "a+b")
    except OSError as exc:
        raise ReadingError(f"{target}: {exc.strerror or exc}") from None
    with handle:
        deadline = time.monotonic() + LOCK_WAIT
        while not try_lock(handle):
            if time.monotonic() >= deadline:
                raise ReadingError(f"{target} is locked by another reading.py write; nothing was written, retry")
            time.sleep(LOCK_POLL)
        yield


def cmd_write(args, out, now):
    if args.key in TIME_KEYS:
        raise ReadingError(f"key {args.key!r} is a time field name; choose another key")
    target = Path(os.path.realpath(args.file))  # one spelling for the lock, the read and the replace; a link stays a link
    with locked(target):
        data, mode, mtime = {}, 0o644, 0
        if target.exists():
            text, mtime = read_bounded(target, MAX_READ)
            try:
                data = json.loads(text)
            except ValueError:
                data = None
            if not isinstance(data, dict):
                raise ReadingError(f"{target}: not a JSON object, left untouched")
            mode = target.stat().st_mode & 0o777
            stamp_flat_keys(data, args.key, mtime, now)
        data[args.key] = {"value": args.value, RESERVED_KEY: now.isoformat(timespec="seconds")}
        replace_atomically(target, data, mode)
    out(f"ok {Path(args.file).name} {args.key} as of {format_time(now)}")
    return 0


def stamp_flat_keys(data, skip, mtime, now):
    """Give every flat key its own time from its current source, so replacing the file (new mtime) ages no key back to now."""
    meta = set(TIME_KEYS) | {f"{k}_{n}" for k in data for n in TIME_KEYS}
    for key in list(data):
        if key == skip or key in meta or data[key] is None or own_entry(data[key], TIME_KEYS):
            continue
        found = find_time(data, key, TIME_KEYS)
        moment = parse_field_time(found[0], now) if found else file_moment(mtime, now)
        data[key] = {"value": data[key], RESERVED_KEY: moment.isoformat(timespec="seconds")}


def replace_atomically(target, data, mode):
    try:
        fd, temp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    except OSError as exc:
        raise ReadingError(f"{target}: {exc.strerror or exc}") from None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temp, mode)
        except OSError:
            pass  # mounts without modes
        os.replace(temp, target)
    except OSError as exc:
        remove_quietly(temp)
        raise ReadingError(f"{target}: {exc.strerror or exc}") from None


def remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


def parse_marker_time(text, now):
    """(date) HH:MM (offset) as written in a report; no date means today, no offset the clock's. None if unreadable."""
    match = MARKER_TIME_RE.fullmatch(text)
    if not match:
        return None
    year, month, day, hour, minute, offset = match.groups()
    try:
        if not offset:
            zone = now.tzinfo
        elif offset in "Zz":
            zone = dt.timezone.utc
        else:
            digits = offset[1:].replace(":", "")
            delta = dt.timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
            zone = dt.timezone(-delta if offset[0] == "-" else delta)
        today = now.astimezone(zone).date()
        date = dt.date(int(year), int(month), int(day)) if year else today
        return dt.datetime(date.year, date.month, date.day, int(hour), int(minute), tzinfo=zone)
    except ValueError:
        return None


def first_trigger(line, word_re):
    hits = [m for m in (PERCENT_RE.search(line), word_re.search(line)) if m]
    return min(hits, key=lambda m: m.start()).group(0) if hits else None


def uncovered_text(line, markers):
    """The line without each marker and the text it covers (back to the previous marker, a semicolon or the start)."""
    kept, cursor = [], 0
    for marker in markers:
        gap = line[cursor:marker.start()]
        kept.append(gap[: gap.rfind(";") + 1])
        cursor = marker.end()
    kept.append(line[cursor:])
    return "".join(kept)


def compile_word_re(raw, option):
    words = [w.strip() for w in raw.split(",") if w.strip()]
    if not words:
        raise ReadingError(f"{option} needs at least one word")
    return re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, words)) + r")(?!\w)", re.IGNORECASE)


def is_command_or_link(content):
    """A URL, or a command: two or more tokens, the first a word of 2+ characters. Placeholders are neither."""
    tokens = content.split()
    if not tokens or all(token.lower() in PLACEHOLDERS for token in tokens):
        return False
    return bool(URL_TOKEN_RE.fullmatch(tokens[0])) or (len(tokens) >= 2 and bool(COMMAND_WORD_RE.fullmatch(tokens[0])))


FULLWIDTH_CLAUSE_ENDS = {0xFF1B: "; ", 0xFF0C: ", ", 0xFF01: "! ", 0xFF1F: "? "}  # NFKC folds them to ASCII, losing the break


def normalized(line):
    """The line without format characters (zero-width, soft hyphen, BOM: category Cf), NFKC-normalised."""
    kept = "".join(c for c in line if unicodedata.category(c) != "Cf").translate(FULLWIDTH_CLAUSE_ENDS)
    return unicodedata.normalize("NFKC", kept)


def marker_verdict(text):
    """(kind, note) when a (source: ...) or (live: ...) marker is not a read of this run, else None."""
    content = text.partition(":")[2][:-1].strip()
    if BUS_CUE_RE.search(content):
        return "BUS-CLAIM", ""
    if not is_command_or_link(content):
        return "NO-SOURCE", "source is not a command or link: "
    return None


def claim_finding(line, claim_re):
    """(kind, claim word, note) of the first failing claim or marker on the line, else None."""
    line = normalized(line)
    spans = [m.span() for m in CODE_SPAN_RE.finditer(line)]
    blanked = CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), line)
    markers = sorted(
        (m.start(), m.end(), kind, m.group(0))
        for kind, regex in (("asof", MARKER_RE), ("source", SOURCE_MARK_RE), ("live", LIVE_RE))
        for m in regex.finditer(line)
        if not any(lo <= m.start() < hi for lo, hi in spans)
    )
    verdicts = [marker_verdict(mk[3]) if mk[2] != "asof" else None for mk in markers]
    found = []  # (position, kind, word, note)
    for (start, end, _, _), verdict in zip(markers, verdicts):
        if verdict:
            inner = claim_re.search(blanked, start, end)
            found.append((start, verdict[0], inner.group(0) if inner else "marker", verdict[1]))
    for claim in claim_re.finditer(blanked):
        inside = next((mk for mk in markers if mk[0] <= claim.start() < mk[1]), None)
        if inside:
            if inside[2] == "asof":
                found.append((claim.start(), "NO-SOURCE", claim.group(0), ""))
            continue
        index = next((i for i, mk in enumerate(markers) if mk[0] >= claim.end()), None)
        if index is None or CLAUSE_BREAK_RE.search(blanked, claim.end(), markers[index][0]) or markers[index][2] == "asof":
            found.append((claim.start(), "NO-SOURCE", claim.group(0), ""))
        elif verdicts[index]:
            found.append((claim.start(), verdicts[index][0], claim.group(0), verdicts[index][1]))
    if not found:
        return None
    _, kind, word, note = min(found)
    return kind, word, note


def fenced_line_numbers(lines):
    """(line numbers inside closed ``` blocks, fence fences included; line of an unclosed opening fence or 0).

    A fence line starts with ``` and holds no other ```, so an inline ```x``` is not a fence. An unclosed fence hides nothing.
    """
    inside, open_at, opened = set(), 0, 0
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith(FENCE) and FENCE not in stripped[3:]:
            if opened:
                inside.update(range(opened, number + 1))
                opened = 0
            else:
                opened = number
        open_at = opened
    return inside, open_at


def cmd_check_report(args, out, now):
    limit = parse_age(args.max_age)
    word_re = compile_word_re(args.words, "--words")
    claim_re = None
    if not args.no_claims:
        claim_re = CLAIM_RE if args.claim_words is None else compile_word_re(args.claim_words, "--claim-words")
    text, _ = read_bounded(args.report, MAX_REPORT)
    findings = []
    lines = text.splitlines()
    fenced_lines, unclosed = fenced_line_numbers(lines)
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        snippet = line.strip()[:SNIPPET]
        if len(line) > MAX_LINE:
            findings.append(f"TOO-LONG line {number}: {len(line)} characters, line too long to check; split it: {snippet}")
            continue
        markers = list(MARKER_RE.finditer(line))
        for marker in markers:
            written = f"{marker.group(1).lower()} {marker.group(2)}"
            moment = parse_marker_time(marker.group(2), now)
            if moment is None:
                findings.append(f"BAD-MARKER line {number}: cannot read the time in '{written}': {snippet}")
                continue
            age = now - moment
            if age < -SKEW:
                findings.append(f"FUTURE line {number}: {written} is {format_duration(-age)} ahead of the clock: {snippet}")
            elif age > limit:
                findings.append(
                    f"STALE line {number}: {written} is {format_duration(age)} old (limit {format_duration(limit)}): {snippet}"
                )
        if not LIVE_RE.search(line):
            trigger = first_trigger(uncovered_text(line, markers), word_re)
            if trigger:
                findings.append(f"NO-MARKER line {number} ({trigger}): {snippet}")
        found = claim_re and number not in fenced_lines and claim_finding(line, claim_re)
        if found:
            findings.append(f"{found[0]} line {number} ({found[1]}): {found[2]}{snippet}")
    if claim_re and unclosed:
        findings.append(f"UNCLOSED-FENCE line {unclosed}: no closing ``` ; the lines after it were checked anyway")
    for finding in findings:
        out(finding)
    out(f"{len(findings)} finding(s)" if findings else "ok: no unmarked or stale readings")
    return 1 if findings else 0


def build_parser():
    parser = argparse.ArgumentParser(prog="reading.py", description="Quote a file reading with its age.")
    sub = parser.add_subparsers(dest="command", required=True)
    get = sub.add_parser("get", help="print a value with its time and age")
    get.add_argument("file")
    get.add_argument("--key")
    get.add_argument("--max-age")
    get.add_argument("--time-key")
    get.add_argument("--json", action="store_true")
    write = sub.add_parser("write", help="record a value with the time now")
    write.add_argument("file")
    write.add_argument("--key", required=True)
    write.add_argument("--value", required=True)
    check = sub.add_parser("check-report", help="flag stale or unmarked readings in a draft")
    check.add_argument("report")
    check.add_argument("--max-age", default=DEFAULT_MAX_AGE)
    check.add_argument("--words", default=",".join(DEFAULT_WORDS))
    check.add_argument("--claim-words")
    check.add_argument("--no-claims", action="store_true")
    return parser


def main(argv=None, out=print, err=lambda text: print(text, file=sys.stderr)):
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    handlers = {"get": cmd_get, "write": cmd_write, "check-report": cmd_check_report}
    try:
        return handlers[args.command](args, out, clock())
    except ReadingError as exc:
        err(f"reading.py: {exc}")
        return 2
    except RecursionError:  # JSON nested too deep to decode: unreadable, never "stale" (exit 1)
        err("reading.py: the file's JSON is nested too deeply to read")
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")  # a lone surrogate in a value prints escaped
    sys.exit(main())
