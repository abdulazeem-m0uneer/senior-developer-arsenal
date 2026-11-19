#!/usr/bin/env python3
"""Calendar mistakes in outbound text, for guard_lessons' built-in `calendar` rule (Claude Code plugin).

Usage: reasons = guard_calendar.problems(text, today, workweek=None)   # [] when the text is clean
       texts = guard_calendar.outbound_texts(tool_name, tool_input, programs, shell)  # what a tool call sends
Three checks:
  - a weekday next to a date must be that date's weekday ("Wed 11-26" is refused when 2026-11-26 is a Thursday;
    "Thurs", "Weds", MM/DD and YYYY-MM-DD are read), and the date must exist;
  - a clock time with a placeholder digit ("16:4x", "1x:30", "16:xx") is a guess: read the time with `date`;
  - with a workweek (for example "Sun-Thu"), a promised date (after ETA, by, due, until, deadline, on, or next to a
    weekday) that falls on another day is refused unless the text says "non-workday".
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
import re

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


def problems(text, today, workweek=None):
    """Each calendar mistake in the text, as one line with the fix."""
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
            if date >= today and date.weekday() not in workweek:  # a past date is a fact, not a promise
                found.append(f"{date} is a {date.strftime('%A')}, outside the workweek; give a workday, or write "
                             "\"non-workday\" if it is meant")
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
