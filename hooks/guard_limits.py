#!/usr/bin/env python3
"""Per-run limits for an unattended run, enforced by guard.py's PreToolUse hook (Claude Code plugin).

Usage: the operator or the agent writes the limits file at the start of the run and deletes it at the end:
  <project>/.claude/arsenal-run-limits.json   {"max_tool_calls": 400, "max_minutes": 240, "deadline": "2025-03-05T02:00:00+00:00"}
Every key is optional. max_tool_calls and max_minutes are counted per session, from the first tool call made
while the file exists; deadline is an absolute ISO 8601 time with a UTC offset. When $ARSENAL_RUN_LIMITS
is set only that path is used; otherwise the file is searched from $CLAUDE_PROJECT_DIR (else the hook's cwd) upward. No file: nothing is
read, counted or enforced. A file that is not a JSON object of these keys with usable values counts as a
reached limit, so a typo cannot silently lift the cap.
There is no cost or token limit: hook input carries no cost and no cumulative usage (see the autonomous-run skill).
Time budget: a few stat calls per tool call without a file; one small read with one.
"""
import json
import os

FILE = os.path.join(".claude", "arsenal-run-limits.json")
ENV = "ARSENAL_RUN_LIMITS"
COUNTED = ("max_tool_calls", "max_minutes")
REPORT_TOOLS = ("Write", "Edit", "Read")  # still allowed on a .md file after a limit: the handoff and the end report;
# Read too, because Claude Code refuses to Edit or overwrite an existing file that was not read first


def find(cwd):
    """Path of the limits file that applies, or '' (the usual case)."""
    override = os.environ.get(ENV)
    if override:
        return override if os.path.isfile(override) else ""
    folder = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or cwd)
    while True:
        path = os.path.join(folder, FILE)
        if os.path.isfile(path):
            return path
        parent = os.path.dirname(folder)
        if parent == folder:
            return ""
        folder = parent


def deadline_seconds(text):
    """Epoch seconds of an ISO 8601 time that carries a UTC offset; ValueError otherwise."""
    from datetime import datetime  # only a run with a deadline pays for the import
    moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("no UTC offset")
    return moment.timestamp()


def read(path):
    """(limits, problem): the validated limits with the deadline in epoch seconds, or what is wrong with the file."""
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.loads(handle.read(10000))
    except (OSError, ValueError):
        return {}, "is not readable JSON"
    if not isinstance(raw, dict):
        return {}, "is not a JSON object"
    limits = {}
    for key, value in raw.items():
        if key in COUNTED and type(value) in (int, float) and value > 0:
            limits[key] = value
        elif key == "deadline" and isinstance(value, str):
            try:
                limits[key] = deadline_seconds(value)
            except (ValueError, OverflowError):
                return {}, "has a deadline that is not an ISO 8601 time with a UTC offset"
        else:
            return {}, f"has an unknown key or an unusable value: {str(key)[:40]}"
    return limits, ""


def usage(events):
    """(tool calls counted so far, epoch seconds of the first one or None) from the session's guard events."""
    calls = [event for event in events if event.get("event") in ("call", "run")]
    count = sum(event.get("calls", 1) if isinstance(event.get("calls", 1), int) else 1 for event in calls)
    times = [event["time"] for event in calls if isinstance(event.get("time"), (int, float))]
    return count, min(times) if times else None


def reached(limits, calls, started, now):
    """Which limit is used up, as text; '' while the run may continue."""
    if "max_tool_calls" in limits and calls >= limits["max_tool_calls"]:
        return f"{calls} of {limits['max_tool_calls']} tool calls used"
    if "max_minutes" in limits and started is not None and now - started >= limits["max_minutes"] * 60:
        return f"{limits['max_minutes']} minutes used"
    if "deadline" in limits and now >= limits["deadline"]:
        return "the deadline has passed"
    return ""


def status(path, events, now):
    """(why work must stop under the limits file at path, whether the file itself is the problem); ('', False) to go on."""
    limits, problem = read(path)
    return (f"the limits file {problem}", True) if problem else (reached(limits, *usage(events), now), False)


def is_report_write(data, limits_path, damaged):
    """True for a Write, Edit or Read of a Markdown file, or of a damaged limits file so that it can be repaired."""
    tool_input = data.get("tool_input")
    target = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if data.get("tool_name") not in REPORT_TOOLS or not isinstance(target, str):
        return False
    same = damaged and os.path.abspath(target) == os.path.abspath(limits_path)
    return same or target.lower().endswith(".md")
