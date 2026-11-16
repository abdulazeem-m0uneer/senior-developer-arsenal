"""The lesson-guard hit log: one JSON line per command a lesson guard refused (time, lesson, rule, cwd).

Imported by lessons.py (`hits`) and by the plugin's PreToolUse hook; not a command. Standard library only.
The command itself is never logged: it may hold the very secret a guard refused.
Path: $LESSONS_GUARD_HITS_FILE or ~/.agents/lesson-guard-hits.jsonl.
"""
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

ENV = "LESSONS_GUARD_HITS_FILE"
WINDOW_RE = re.compile(r"^(\d+)([mhd])$")
UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400}


def path():
    return Path(os.environ.get(ENV) or Path.home() / ".agents" / "lesson-guard-hits.jsonl")


def append(lesson, rule, cwd, now=None):
    """Add one hit (O_APPEND, owner-only file, so parallel hooks cannot lose each other's lines)."""
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"time": int(time.time() if now is None else now), "lesson": lesson, "rule": rule, "cwd": cwd})
    handle = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(handle, (line + "\n").encode("utf-8"))
    finally:
        os.close(handle)


def window_seconds(text):
    """'30m', '24h' or '7d' in seconds; ValueError otherwise."""
    match = WINDOW_RE.match(text.strip())
    if not match or int(match.group(1)) == 0:
        raise ValueError(f"window {text!r} is not a positive number followed by m, h or d (for example 24h)")
    return int(match.group(1)) * UNIT_SECONDS[match.group(2)]


def counts(since_seconds, now=None):
    """(Counter of (lesson, rule) -> hits within the window, damaged lines skipped). No log reads as no hits."""
    now = time.time() if now is None else now
    found, damaged = Counter(), 0
    try:
        lines = path().read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return found, 0
    for line in lines:
        try:
            hit = json.loads(line)
            when, rule = float(hit["time"]), str(hit["rule"])
        except (ValueError, KeyError, TypeError):
            damaged += 1
            continue
        if now - since_seconds <= when <= now:
            found[(hit.get("lesson") or "-", rule)] += 1
    return found, damaged
