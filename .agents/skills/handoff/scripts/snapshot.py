#!/usr/bin/env python3
"""Keep a deterministic work snapshot across context compaction (no model tokens spent).

Usage:
  snapshot.py write   # PreCompact hook: save branch, status, recent commits, diff stat
  snapshot.py show    # SessionStart hook: after a compaction, print the snapshot as additionalContext
Hook input (JSON on stdin) is optional. Never fails the session: always exits 0.
Snapshot file: $HANDOFF_SNAPSHOT, else <OS temp dir>/arsenal-snapshot-<session_id>.md. It is never written
inside the project, so a consuming repository gets no untracked file.
Time budget: five git reads at 2 s each (10 s worst case); the hook timeout is 20 s.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

GIT_TIMEOUT = 2
MAX_LINES = 30
MAX_CHARS = 2500


def git(*args):
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=GIT_TIMEOUT)
        return out.stdout.strip().splitlines() if out.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        return []


def hook_input():
    try:
        data = json.load(sys.stdin)
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def snapshot_path(data):
    override = os.environ.get("HANDOFF_SNAPSHOT")
    if override:
        return Path(override)
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id", ""))) or "default"
    return Path(tempfile.gettempdir()) / f"arsenal-snapshot-{session}.md"


def section(title, lines):
    lines = lines[:MAX_LINES]
    return f"{title}\n" + ("\n".join(lines) if lines else "(none)")


def write():
    path = snapshot_path(hook_input())
    if not git("rev-parse", "--is-inside-work-tree"):
        return
    body = "\n\n".join([
        "# Snapshot before compaction (auto, from git; the conversation summary may omit these)",
        section("Branch:", git("branch", "--show-current")),
        section("Uncommitted (git status --short):", git("status", "--short")),
        section("Recent commits:", git("log", "--oneline", "-5")),
        section("Diff stat vs HEAD:", git("diff", "--stat", "HEAD")[-15:]),
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body[:MAX_CHARS] + "\n", encoding="utf-8")


def show():
    data = hook_input()
    path = snapshot_path(data)
    if data.get("source") != "compact" or not path.is_file():
        return
    text = path.read_text(encoding="utf-8")[:MAX_CHARS]
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        {"write": write, "show": show}.get(cmd, lambda: None)()
    except Exception:  # a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
