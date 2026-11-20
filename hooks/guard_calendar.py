#!/usr/bin/env python3
"""Calendar mistakes in outbound text, for guard_lessons' built-in `calendar` rule (Claude Code plugin).

Usage: reasons = guard_calendar.problems(text, today, workweek=None, approved=(), exceptions_file=None)
                                                                         # [] when the text is clean
       dates, problems = guard_calendar.read_exceptions(path)            # the approved workdays of an exceptions file
       texts = guard_calendar.outbound_texts(tool_name, tool_input, programs, shell)  # what a tool call sends
Three checks:
  - a weekday next to a date must be that date's weekday ("Wed 11-26" is refused when 2026-11-26 is a Thursday;
    "Thurs", "Weds", MM/DD and YYYY-MM-DD are read), and the date must exist;
  - a clock time with a placeholder digit ("16:4x", "1x:30", "16:xx") is a guess: read the time with `date`;
  - with a workweek (for example "Sun-Thu"), a promised date (after ETA, by, due, until, deadline, on, or next to a
    weekday) that falls on another day is refused unless the date is an approved workday (below) or the text says
    "non-workday".
Workday exceptions: a day outside the workweek that the people in charge approved as a working day is recorded in
an exceptions file, one line per date, `YYYY-MM-DD approved-by <who>: <reason>`. Blank lines and lines starting with
`#` are skipped. The date is four-digit year, two-digit month and day and must exist; <who> is text without a colon
(up to the first colon); the reason after that colon is required. A line that does not match, has an empty approver
or reason, or holds an impossible date (2026-02-30) is reported with its line number and applies nothing; the other
lines still apply. A listed date that is already a workday is fine. A missing, unreadable (a directory, a FIFO or device,
bytes that are not UTF-8) or oversized file gives no exceptions and a problem line; it never raises. The guard_lessons registry
names the file with the calendar entry's "exceptions" key. At most 20 problem lines are kept per file, then one
"<path>: N more problem lines"; any text quoted from the file is cut to 60 characters. guard_lessons also bounds
a whole registry read (20 distinct file and approvers pairs, 50 problem lines). The record is advisory: anyone who can write the file can add a line, so it is no
stronger than the word "non-workday" unless the entry also sets "approvers" (a list of names; a line whose approver
is not in the list, compared exactly and case-sensitively after trimming, is a problem line and applies nothing) and
the file is kept where agents do not write it, for example outside the repository and owned by the person who
approves. Without the file, one agreed word per message
("non-workday") was the only way through, so agents wrote false next-workday ETAs; a recorded approval replaces it.
A month-day without a year is the one nearest today (within 200 days). Single-digit dates ("Fri 11-6") are not
read: they look like hour ranges ("Mon 9-5"); write hours as times ("Mon 10:00-12:00").
What is outbound: a Bash call to a message program the registry names, `gh [-R repo] issue|pr comment|create|
edit|review`, `gh release create|edit`, `git commit` or `git tag` (their arguments, and the here-document bodies of
the call, which is where `-m "$(cat <<'EOF' ...)"` keeps the message); and an MCP tool whose last name part has a
sending word (send, reply, comment, post, draft, create, update, add, forward) and no reading or file word (get,
list, search, read, fetch, file, upload), all its text fields. A date before today is a fact, never judged against
the workweek; "not a date" is reported only next to a weekday or for a full YYYY-MM-DD. Not read: `gh api`, curl
bodies, `git notes`, and forms such as "Wed Nov 26" or "26/11". File edits are never outbound, so fixtures and
tests that hold wrong dates on purpose are not judged. Standard library only.
"""
import datetime as dt
import os
import re
import stat

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DAY = (r"(Mon(?:day)?|Tue(?:s|sday)?|Wed(?:s|nesday)?|Thu(?:r|rs|rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)"
       r"(?![\w-])")
DATE = r"(?:(\d{4})-)?(\d{2})[-/](\d{2})(?![\d:/]|-\d)"
NOT_A_DATE = r"(?!\s*(?:am|pm|h|hrs?|hours?|mins?|minutes?|noon|days?|people|utc|gmt)\b)"
WEEKDAY_DATE = re.compile(r"(?<![-\w])" + DAY + r",?\s+" + DATE + NOT_A_DATE, re.I | re.ASCII)
PROMISED_DATE = re.compile(r"\b(?:ETA:?|by|due|until|deadline:?|on)\s+" + DATE + NOT_A_DATE + r"(?!\s*(?:%|(?:ms|s|x)\b))",
                           re.I | re.ASCII)
GUESSED_TIME = re.compile(r"(?<![\w:])(?:\d{1,2}:(?:\d[xX?]|[xX?]{2})|\d[xX?]:\d{2})(?![\w:])", re.ASCII)
ACKNOWLEDGED = re.compile(r"\bnon-workday\b", re.I)
EXCEPTION_LINE = re.compile(r"(\d{4})-(\d{2})-(\d{2}) approved-by ([^:\n]*):(.*)", re.ASCII)
EXCEPTIONS_MAX_BYTES = 100_000
MAX_PATH_CHARS, MAX_PATH_PARTS = 1024, 64  # an exceptions path longer than this is refused unread
ECHO_LIMIT = 60  # characters of any text from the file shown in a message
PROBLEM_LIMIT = 20  # problem lines kept per file; the rest are counted in one line
SPAN_DAYS = 200
SEND_WORDS = frozenset(("send", "reply", "post", "draft", "create", "update", "add", "comment", "forward"))
NOT_SEND_WORDS = frozenset(("get", "list", "search", "read", "fetch", "download", "find", "file", "files", "upload",
                            "attachment"))
GH_WRITES = {"issue": {"comment", "create", "edit", "close", "reopen"}, "pr": {"comment", "create", "edit", "review",
                                                                                 "close", "merge", "ready"},
             "release": {"create", "edit"}}


def parse_workweek(value):
    """The workdays as a set of 0-6 (Monday 0) from "Sun-Thu" or ["Sun", "Mon", ...]; ValueError otherwise."""
    if isinstance(value, str):
        match = re.fullmatch(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)-(Mon|Tue|Wed|Thu|Fri|Sat|Sun)", value.strip())
        if not match:
            raise ValueError(f"workweek {value!r} is not a range such as Sun-Thu")
        start, end = DAYS.index(match.group(1)), DAYS.index(match.group(2))
        return {(start + step) % 7 for step in range((end - start) % 7 + 1)}
    if isinstance(value, list) and value and all(isinstance(day, str) and day in DAYS for day in value):
        return {DAYS.index(day) for day in value}
    raise ValueError("workweek is a range such as Sun-Thu or a list of days such as [\"Sun\", \"Mon\"]")


def clip(text):
    """The text, cut to ECHO_LIMIT characters with an ellipsis, for a message that quotes a file."""
    return text if len(text) <= ECHO_LIMIT else text[:ECHO_LIMIT - 1] + "\u2026"


def scan_exceptions(text):
    """(records, problems, more) of an exceptions file's text: records are (line number, date, approver) for each good
    line; problems are at most PROBLEM_LIMIT lines and more counts the ones left out."""
    records, problems, more = [], [], 0
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = EXCEPTION_LINE.fullmatch(line)
        problem = None
        if not match or not match.group(4).strip() or not match.group(5).strip():
            problem = (f"line {number}: expected `YYYY-MM-DD approved-by <who>: <reason>` with both the approver "
                       "and the reason (line ignored)")
        else:
            try:
                records.append((number, dt.date(*map(int, match.group(1, 2, 3))), match.group(4).strip()))
            except ValueError:
                problem = f"line {number}: {'-'.join(match.group(1, 2, 3))} is not a date (line ignored)"
        if problem and len(problems) < PROBLEM_LIMIT:
            problems.append(problem)
        elif problem:
            more += 1
    return records, problems, more


def apply_approvers(records, problems, more, approvers=None, path=""):
    """(approved dates, problem lines): the records whose approver is one of approvers (exact, case-sensitive,
    after trimming; every record when approvers is None); the others add a problem line and apply nothing."""
    problems = list(problems)
    shown = clip(path)
    prefix = f"{shown} " if path else ""
    dates = set()
    for number, date, who in records:
        if approvers is None or who in approvers:
            dates.add(date)
        elif len(problems) < PROBLEM_LIMIT:
            problems.append(f"{prefix}line {number}: {clip(who)!r} is not one of the registry's approvers (line ignored)")
        else:
            more += 1
    if more:
        problems.append(f"{shown}: {more} more problem lines" if path else f"{more} more problem lines")
    return dates, problems


def parse_exceptions(text, approvers=None):
    """(approved dates as a set, problem lines) from the text of an exceptions file; see the module docstring."""
    records, problems, more = scan_exceptions(text)
    return apply_approvers(records, problems, more, approvers)


def load_exceptions(path):
    """(records, problems, more) of the file at path, read once so that many entries can share it; a file that is
    missing or cannot be read gives no records and one problem line, never an error."""
    shown = clip(path)
    try:
        # O_NONBLOCK: opening a FIFO must not wait for a writer; only a regular file is read, and never past the limit
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return [], [f"{shown}: skipped, not a regular file"], 0
            data = handle.read(EXCEPTIONS_MAX_BYTES + 1)
        if len(data) > EXCEPTIONS_MAX_BYTES:
            return [], [f"{shown}: skipped, larger than {EXCEPTIONS_MAX_BYTES} bytes"], 0
        records, problems, more = scan_exceptions(data.decode("utf-8"))
    except FileNotFoundError:
        return [], [f"{shown}: not found, no workday exceptions apply"], 0
    except Exception as error:  # the hook runs on every command: any fault is a problem line, never an error
        return [], [f"{shown}: skipped, {type(error).__name__}: {clip(str(error))}"], 0
    return records, [f"{shown} {problem}" for problem in problems], more


def read_exceptions(path, approvers=None):
    """(approved dates, problem lines) of the file at path; see load_exceptions and apply_approvers."""
    records, problems, more = load_exceptions(path)
    return apply_approvers(records, problems, more, approvers, path)


def nearest(year, month, day, today):
    """The date meant: the given year, else the one within SPAN_DAYS of today nearest to it; None if none exists."""
    candidates = [int(year)] if year else [today.year - 1, today.year, today.year + 1]
    found = []
    for candidate in candidates:
        try:
            found.append(dt.date(candidate, int(month), int(day)))
        except ValueError:
            continue
    if not year:
        found = [date for date in found if abs((date - today).days) <= SPAN_DAYS]
    return min(found, key=lambda date: abs((date - today).days)) if found else None


def problems(text, today, workweek=None, approved=(), exceptions_file=None):
    """Each calendar mistake in the text, as one line with the fix. approved: dates that count as workdays;
    exceptions_file: where an approval is recorded, named in the refusal."""
    found = []
    promised = []
    for name, year, month, day in WEEKDAY_DATE.findall(text):
        date = nearest(year, month, day, today)
        if date is None:
            found.append(f"{name} {year + '-' if year else ''}{month}-{day} is not a date")
        elif date.strftime("%a").lower() != name[:3].lower():
            found.append(f"{name} {date} is a {date.strftime('%A')} (check with `date -d {date} +%a`)")
        else:
            promised.append(date)
    for year, month, day in PROMISED_DATE.findall(text):
        date = nearest(year, month, day, today)
        if date is not None:
            promised.append(date)
        elif year:  # a full YYYY-MM-DD that does not exist; a bare pair may be a range ("by 10-12 people")
            found.append(f"{year}-{month}-{day} is not a date")
    for guess in GUESSED_TIME.findall(text):
        found.append(f"{guess} is a guessed time: read the clock with `date +%H:%M`")
    if workweek is not None and not ACKNOWLEDGED.search(text):
        for date in sorted(set(promised)):
            if date >= today and date.weekday() not in workweek and date not in approved:  # past: a fact
                way = (f"record the approval as `{date} approved-by <who>: <reason>` in {exceptions_file} if it was "
                       "approved as a working day, or write \"non-workday\" if it is meant" if exceptions_file
                       else "or write \"non-workday\" if it is meant")
                found.append(f"{date} is a {date.strftime('%A')}, outside the workweek; give a workday, {way}")
    return list(dict.fromkeys(found))  # one line per distinct mistake, in order


def string_values(value):
    """Every string inside a tool input (dicts and lists walked), in order."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from string_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from string_values(item)


GH_FLAGS_WITH_VALUE = frozenset(("-R", "--repo", "--hostname"))


def gh_words(args):
    """gh's own words with its global flags removed: `gh -R o/r pr comment` is `pr comment`."""
    words, index = [], 0
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in GH_FLAGS_WITH_VALUE else 1
    return args[index:]


def spoken(args):
    """The arguments as one text, with a value glued to a short option split off (-m'text' -> -m text)."""
    return " ".join(f"{arg[:2]} {arg[2:]}" if re.match(r"^-[A-Za-z]\S", arg) else arg for arg in args)


def bash_texts(command, programs, shell):
    """The arguments of the message commands in a Bash call (quotes removed), and the here-document bodies of a
    call that sends: `git commit -F - <<EOF` and `-m "$(cat <<'EOF' ... EOF)"` carry the message there."""
    texts = []
    command_part, heredoc = shell.split_heredocs(command)
    for argv, _piped, _has_heredoc in shell.simple_commands(command_part):
        name, args = shell.program(argv)
        word = argv[len(argv) - len(args) - 1] if name else ""
        sends = name in programs or word in programs or word.rpartition("/")[2] in programs
        gh = gh_words(args) if name == "gh" else []
        if len(gh) >= 2 and gh[1] in GH_WRITES.get(gh[0], ()):
            sends = True
        if name == "git" and ("commit" in args or "tag" in args):
            sends = True
        if sends:
            texts.append(spoken(args))
    if texts and heredoc:
        texts.append(heredoc)
    return texts


def sends_text(tool_name):
    """True for an MCP tool whose name says it sends or writes text for people (send_message, create_task_comment,
    reply, post, draft), not one that reads (get_message, list_comments) or writes files (create_or_update_file)."""
    if not tool_name.startswith("mcp__"):
        return False
    words = set(re.split(r"[_\W]+", tool_name.rpartition("__")[2].lower()))
    return bool(words & SEND_WORDS) and not words & NOT_SEND_WORDS


def outbound_texts(tool_name, tool_input, programs, shell):
    """The text a tool call sends to people; [] for anything else (file edits, reads, plain commands)."""
    if tool_name == "Bash":
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        return bash_texts(command, programs, shell) if isinstance(command, str) else []
    if isinstance(tool_name, str) and sends_text(tool_name):
        return list(string_values(tool_input))
    return []
