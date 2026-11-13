#!/usr/bin/env python3
"""Task state for the compaction snapshot: user prompts, open todos, on-disk ledgers.

Imported by snapshot.py (not a command). Standard library only; no git, no subprocess.
  record_prompt   UserPromptSubmit: keep the first prompt and the last few in a per-session JSON file
  open_todos      best effort: replay the task-list tool calls found in the session transcript
  ledger_pointers plan ledgers, plans and handoff documents that exist on disk, newest first
The transcript format is internal to Claude Code and may change on any release, so open_todos scans
defensively and returns [] on anything it does not recognise; prompts come from the documented hook input.
A list that may be partial (a transcript longer than SCAN_BYTES, or an update to a task never seen) says so.
Time budget: record_prompt is one small read and one atomic write; open_todos streams at most SCAN_BYTES
and parses only the lines that carry a task marker (measured: 144 MB in 0.5 s).
"""
import json
import os
import re
import tempfile
import time
from pathlib import Path

KEEP_LAST = 3
FIRST_CHARS = 600
LAST_CHARS = 250
TODO_CHARS = 120
SCAN_BYTES = 256_000_000
TASK_MARKERS = (b"TaskCreate", b"TaskUpdate", b"TodoWrite", b"created successfully", b'"task"')
INCOMPLETE = "(task list may be incomplete: older tasks were not seen)"
MAX_LEDGERS = 4
POINTER_CHARS = 280
# implementation-plan skill: the ledger with or without a plan-slug directory, and the plans themselves
LEDGER_GLOBS = (".plan-workspace/progress.md", ".plan-workspace/*/progress.md", "docs/plans/*.md")
# handoff skill: handoff-<repo>-<YYYYMMDD-HHMM>.md in the OS temp dir
HANDOFF_STAMP = re.compile(r"-\d{8}-\d{4}\.md")
CREATED = re.compile(r"Task #(\S+) created successfully")
OPEN_STATES = ("in_progress", "pending")


def clip(text, limit):
    """Strip and shorten to at most limit characters, saying how much was dropped."""
    text = text.strip()
    if len(text) <= limit:
        return text
    marker = f" ...(+{len(text) - limit} chars)"
    return text[:max(0, limit - len(marker))] + marker


def utc(seconds):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def atomic_write(path, text):
    """Write through a private temp file (mode 0600 where the OS supports it), then rename.

    Text that cannot be encoded (a lone surrogate from a prompt) is written as "?", never an error.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", errors="replace") as out:
            out.write(text)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def load_prompts(path):
    """Return {"first": str, "last": [str], "count": int}; a missing or damaged file reads as empty."""
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        first, last, count = state["first"], state["last"], state["count"]
        if isinstance(first, str) and isinstance(count, int) and isinstance(last, list) \
                and all(isinstance(item, str) for item in last):
            return {"first": first, "last": last[-KEEP_LAST:], "count": count}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {"first": "", "last": [], "count": 0}


def record_prompt(path, prompt):
    if not isinstance(prompt, str) or not prompt.strip():
        return
    state = load_prompts(path)
    if state["first"]:
        state["last"] = (state["last"] + [clip(prompt, LAST_CHARS)])[-KEEP_LAST:]
    else:
        state["first"] = clip(prompt, FIRST_CHARS)
    state["count"] += 1
    atomic_write(path, json.dumps(state))


def task_lines(path):
    """(raw lines that carry a task marker, truncated): streams the last SCAN_BYTES of a regular file.

    The line a truncating cut lands in is no longer valid JSON, so the replay skips it like any damaged line.
    """
    if not path.is_file():
        return [], False
    with open(path, "rb") as source:
        size = source.seek(0, os.SEEK_END)
        truncated = size > SCAN_BYTES
        source.seek(size - SCAN_BYTES if truncated else 0)
        return [raw for raw in source if any(marker in raw for marker in TASK_MARKERS)], truncated


def tool_blocks(lines):
    """Yield (block, entry) for each tool_use / tool_result block of the main conversation."""
    for raw in lines:
        try:
            entry = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("isSidechain") is True:
            continue
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict):
                yield block, entry


def created_id(block, entry):
    """The id a TaskCreate result announces: 'Task #<id> created successfully', else toolUseResult.task.id."""
    content = block.get("content")
    parts = content if isinstance(content, list) else [{"text": content}]
    text = " ".join(part["text"] for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str))
    match = CREATED.search(text)
    if match:
        return match.group(1)
    result = entry.get("toolUseResult")
    task = result.get("task") if isinstance(result, dict) else None
    return str(task["id"]) if isinstance(task, dict) and task.get("id") is not None else None


def replay(lines, truncated=False):
    """Rebuild the task list: ({key: [subject, status]} in creation order, whether tasks may be missing).

    TodoWrite carries the whole list in input.todos; TaskCreate adds one task whose id arrives in its
    tool_result; TaskUpdate changes status or subject by input.taskId. Tasks may be missing when an update
    names a task this scan never saw created, or when a truncated scan found tasks one by one.
    """
    tasks, key_of, unseen, whole = {}, {}, False, False
    for block, entry in tool_blocks(lines):
        kind, name = block.get("type"), block.get("name")
        args = block.get("input") if isinstance(block.get("input"), dict) else {}
        if kind == "tool_result":
            use_id = block.get("tool_use_id")
            task_id = created_id(block, entry) if isinstance(use_id, str) and use_id in tasks else None
            if task_id:
                key_of[task_id] = use_id
        elif kind != "tool_use":
            continue
        elif name == "TodoWrite" and isinstance(args.get("todos"), list):
            todos = [todo for todo in args["todos"] if isinstance(todo, dict) and isinstance(todo.get("content"), str)]
            tasks = {f"todo-{index}": [todo["content"], todo.get("status")] for index, todo in enumerate(todos)}
            key_of, unseen, whole = {}, False, True  # the whole list: nothing older is missing
        elif name == "TaskCreate" and isinstance(args.get("subject"), str) and isinstance(block.get("id"), str):
            tasks[block["id"]] = [args["subject"], "pending"]
        elif name == "TaskUpdate" and args.get("taskId") is not None:
            task = tasks.get(key_of.get(str(args["taskId"])))
            if task is None:
                unseen = True
                continue
            if isinstance(args.get("subject"), str):
                task[0] = args["subject"]
            if isinstance(args.get("status"), str):
                task[1] = args["status"]
    return tasks, unseen or (truncated and bool(tasks) and not whole)


def open_todos(transcript_path):
    """Lines for the tasks still open, or [] when no task list is found or the file is unreadable."""
    if not isinstance(transcript_path, str) or not transcript_path:
        return []
    try:
        tasks, incomplete = replay(*task_lines(Path(transcript_path)))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, MemoryError):
        return []
    live = [(subject, status) for subject, status in tasks.values() if status != "deleted"]
    lines = [f"[{status}] {clip(subject, TODO_CHARS)}" for subject, status in live if status in OPEN_STATES]
    done = len(live) - len(lines)
    if done:
        lines.append(f"({done} completed or other, not listed)")
    return lines + [INCOMPLETE] if incomplete else lines


def handoff_files(repo):
    """Handoff documents of exactly this repository name (not of a repository whose name extends it)."""
    prefix = f"handoff-{repo}"
    return [path for path in Path(tempfile.gettempdir()).glob("handoff-*.md")
            if path.name.startswith(prefix) and HANDOFF_STAMP.fullmatch(path.name[len(prefix):])]


def pointer(path, root, modified):
    """'path (modified <UTC time>)', at most POINTER_CHARS: an over-long path keeps its end, cut marked."""
    shown = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    suffix = f" (modified {utc(modified)})"
    room = POINTER_CHARS - len(suffix)
    return (shown if len(shown) <= room else "..." + shown[len(shown) - room + 3:]) + suffix


def ledger_pointers(root):
    """A pointer line for each ledger, plan or handoff document on disk, newest first."""
    root = Path(root)
    found = []
    for path in [hit for pattern in LEDGER_GLOBS for hit in root.glob(pattern)] + handoff_files(root.name):
        try:
            if path.is_file():
                found.append((path.stat().st_mtime, path))
        except OSError:
            continue
    found.sort(key=lambda item: item[0], reverse=True)
    return [pointer(path, root, modified) for modified, path in found[:MAX_LEDGERS]]
