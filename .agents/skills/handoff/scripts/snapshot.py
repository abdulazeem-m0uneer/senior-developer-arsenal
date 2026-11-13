#!/usr/bin/env python3
"""Keep a deterministic work snapshot across context compaction (no model tokens spent).

Usage:
  snapshot.py write   # PreCompact hook: save branch, status, recent commits, diff stat
  snapshot.py show    # SessionStart hook: after a compaction, print the snapshot as additionalContext
Hook input (JSON on stdin) is optional. Never fails the session: always exits 0.
Snapshot file: $HANDOFF_SNAPSHOT or .agents/handoff-snapshot.md (git-ignored scratch, not a deliverable).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

PATH = Path(os.environ.get("HANDOFF_SNAPSHOT", ".agents/handoff-snapshot.md"))
MAX_LINES = 30
MAX_CHARS = 2500


def git(*args):
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5)
        return out.stdout.strip().splitlines() if out.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        return []


def section(title, lines):
    lines = lines[:MAX_LINES]
    return f"{title}\n" + ("\n".join(lines) if lines else "(none)")


def write():
    if not git("rev-parse", "--is-inside-work-tree"):
        return
    body = "\n\n".join([
        "# Snapshot before compaction (auto, from git; the conversation summary may omit these)",
        section("Branch:", git("branch", "--show-current")),
        section("Uncommitted (git status --short):", git("status", "--short")),
        section("Recent commits:", git("log", "--oneline", "-5")),
        section("Diff stat vs HEAD:", git("diff", "--stat", "HEAD")[-15:]),
    ])
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(body[:MAX_CHARS] + "\n", encoding="utf-8")


def show():
    try:
        source = json.load(sys.stdin).get("source")
    except (ValueError, OSError):
        source = None
    if source != "compact" or not PATH.is_file():
        return
    text = PATH.read_text(encoding="utf-8")[:MAX_CHARS]
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
