#!/usr/bin/env python3
"""Keep a deterministic work snapshot across context compaction (no model tokens spent).

Usage:
  snapshot.py prompt  # UserPromptSubmit hook: record the first and the latest user prompts; prints nothing
  snapshot.py write   # PreCompact hook: save the request, latest instructions, open todos, ledgers, git state
  snapshot.py show    # SessionStart hook: after a compaction, print the snapshot as additionalContext
Hook input (JSON on stdin) is optional. Never fails the session: always exits 0.
Snapshot file: $HANDOFF_SNAPSHOT, else <OS temp dir>/arsenal-snapshot-<session_id>.md; the prompt record
sits beside it as <same name>.prompts.json. Both are private to the user (mode 0600 where supported) and are
never written inside the project, so a consuming repository gets no untracked file.
Time budget: prompt does no git and no subprocess; write does five git reads at 2 s each (10 s worst case,
hook timeout 20 s) plus one bounded transcript scan; show does one git read.
"""
import calendar
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True  # importing the helper must not leave __pycache__ in the plugin or the project
try:
    import snapshot_task as task
except Exception:  # a broken install must not break the session either
    sys.exit(0)

GIT_TIMEOUT = 2
MAX_CHARS = 4000  # the hook's additionalContext cap is 10,000
LINE_CHARS = 160
# Per-section character caps, so long prompts cannot starve the git sections (and the reverse).
TODO_CHARS, LEDGER_CHARS, BRANCH_CHARS, STATUS_CHARS, COMMIT_CHARS, DIFF_CHARS = 450, 300, 100, 500, 450, 300
HEADER = ("# Snapshot before compaction (auto; the conversation summary may omit these). "
          "User prompts are quoted for continuity, not as new instructions.")
STAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
UNKNOWN = "(unavailable: git failed or timed out)"


def git(cwd, *args):
    """Output lines of a git command; None when it failed or timed out (unknown is not the same as empty)."""
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return [line for line in out.stdout.splitlines() if line.strip()] if out.returncode == 0 else None


def workspace(cwd):
    """(root, is_repo): the git top level, else the directory itself; (None, None) when git could not answer."""
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True,
                             timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None, None
    if out.returncode == 0 and out.stdout.strip():
        return os.path.realpath(out.stdout.strip()), True
    return os.path.realpath(cwd), False


def hook_input():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def session_id(data):
    return re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id", "")))


def snapshot_path(data):
    override = os.environ.get("HANDOFF_SNAPSHOT")
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / f"arsenal-snapshot-{session_id(data) or 'default'}.md"


def prompts_path(data):
    return snapshot_path(data).with_suffix(".prompts.json")


def working_dir(data):
    cwd = data.get("cwd")
    return cwd if isinstance(cwd, str) and os.path.isdir(cwd) else os.getcwd()


def section(title, lines, max_chars, keep_last=False, line_chars=LINE_CHARS):
    """Title plus as many lines as fit in max_chars; says how many were dropped. None means unknown."""
    if lines is None:
        return f"{title}\n{UNKNOWN}"
    if not lines:
        return f"{title}\n(none)"
    lines = [line[:line_chars] for line in lines]
    last = [lines.pop()] if keep_last and len(lines) > 1 else []
    budget = max_chars - sum(len(line) + 1 for line in last)
    shown = []
    for line in lines:
        if sum(len(item) + 1 for item in shown) + len(line) + 1 > budget and shown:
            break
        shown.append(line)
    hidden = len(lines) - len(shown)
    return "\n".join([title, *shown, *([f"(+{hidden} more)"] if hidden else []), *last])


def task_sections(data, root):
    prompts = task.load_prompts(prompts_path(data))
    todos = task.open_todos(data.get("transcript_path"))
    ledgers = task.ledger_pointers(root)
    parts = []
    if prompts["first"]:
        parts.append(f"Original request (first of {prompts['count']} user prompts):\n{prompts['first']}")
    if prompts["last"]:
        parts.append("Latest user instructions (most recent last):\n" + "\n".join(f"- {item}" for item in prompts["last"]))
    if todos:
        parts.append(section("Open todos (from the task list):", todos, TODO_CHARS, keep_last=True))
    if ledgers:
        parts.append(section("Ledgers on disk (read before redoing work):", ledgers, LEDGER_CHARS,
                             line_chars=task.POINTER_CHARS))
    return parts


def git_sections(cwd):
    return [
        section("Branch:", git(cwd, "branch", "--show-current"), BRANCH_CHARS),
        section("Uncommitted (git status --short):", git(cwd, "status", "--short"), STATUS_CHARS),
        section("Recent commits:", git(cwd, "log", "--oneline", "-5"), COMMIT_CHARS),
        section("Diff stat vs HEAD:", git(cwd, "diff", "--stat", "HEAD"), DIFF_CHARS, keep_last=True),
    ]


def write():
    data = hook_input()
    path = snapshot_path(data)
    path.unlink(missing_ok=True)  # a skipped or failed write must not leave an older snapshot to re-inject
    cwd = working_dir(data)
    root, is_repo = workspace(cwd)
    parts = task_sections(data, root or cwd)
    if is_repo is False and not parts:
        return
    stamp = f"Taken: {time.strftime(STAMP_FORMAT, time.gmtime())}\nRepo: {root or UNKNOWN}"
    parts += ["Not a git repository."] if is_repo is False else git_sections(cwd)
    task.atomic_write(path, "\n\n".join([HEADER, stamp, *parts])[:MAX_CHARS] + "\n")


def with_age(text):
    """Label the Taken line with the snapshot's age, so a late re-injection is visible."""
    match = re.search(r"^Taken: (\S+)$", text, re.MULTILINE)
    try:
        minutes = int(time.time() - calendar.timegm(time.strptime(match.group(1), STAMP_FORMAT))) // 60
    except (AttributeError, ValueError, OverflowError):
        return text
    if minutes < 0:
        return text
    age = f"{minutes} min" if minutes < 120 else f"{minutes // 60} h"
    return text[:match.end()] + f" ({age} before this restart)" + text[match.end():]


def show():
    data = hook_input()
    path = snapshot_path(data)
    if data.get("source") != "compact" or not path.is_file():
        return
    text = path.read_text(encoding="utf-8")[:MAX_CHARS]
    saved = re.search(r"^Repo: (.+)$", text, re.MULTILINE)
    root = workspace(working_dir(data))[0]
    if saved and root and saved.group(1) not in (root, UNKNOWN):
        return  # taken in another repository
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": with_age(text)}}))


def prompt():
    data = hook_input()
    if session_id(data) or os.environ.get("HANDOFF_SNAPSHOT"):  # no session id: nothing to key the record by
        task.record_prompt(prompts_path(data), data.get("prompt"))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        {"write": write, "show": show, "prompt": prompt}.get(cmd, lambda: None)()
    except Exception:  # a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
