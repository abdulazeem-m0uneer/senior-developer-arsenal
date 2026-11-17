"""Edit-scope lock for hooks/guard.py pre: deny a file write outside the folders a session was locked to.

Usage: reason = guard_scope.refusal(tool_name, tool_input, cwd)   # "" when the write is allowed or nothing is locked
The lock is `.claude/arsenal-scope.json` in the nearest folder at or above cwd, searched up to the repository root
(the first folder holding .git): {"allow": ["src/billing", "tests/billing"], "reason": "billing refactor"}.
Entries are folders relative to that root. No file means no lock. A file that is not valid JSON, an empty or
non-list "allow", or an entry that is absolute or escapes the root is a fault: every write is denied and the
fault named, so a broken lock never silently allows. Write, Edit, MultiEdit and NotebookEdit are judged by
file_path or notebook_path after realpath (so .. and symlinks resolve); Bash is not covered. The lock file
itself is outside any allowed folder unless listed, so the lock cannot be lifted through an edit tool.
Set, show and clear it with .agents/skills/parallel-sessions/scripts/scope.py. Standard library only.
"""
import json
import os

SCOPE_FILE = os.path.join(".claude", "arsenal-scope.json")
WRITE_TOOLS = frozenset(("Write", "Edit", "MultiEdit", "NotebookEdit"))
MAX_BYTES = 64 * 1024


class ScopeError(Exception):
    pass


def find(cwd):
    """(root, lock file path) of the nearest lock at or above cwd within the repository, or (None, None)."""
    folder = os.path.realpath(cwd or os.getcwd())
    while True:
        candidate = os.path.join(folder, SCOPE_FILE)
        if os.path.isfile(candidate):
            return folder, candidate
        parent = os.path.dirname(folder)
        if os.path.exists(os.path.join(folder, ".git")) or parent == folder:
            return None, None
        folder = parent


def load(root, lock_file):
    """(allowed real folders, reason) from the lock file; raises ScopeError naming the fault."""
    try:
        with open(lock_file, "rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ScopeError(f"larger than {MAX_BYTES} bytes")
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as error:
        raise ScopeError(f"unreadable ({error.__class__.__name__})") from error
    allow = data.get("allow") if isinstance(data, dict) else None
    if not isinstance(allow, list) or not allow or not all(isinstance(entry, str) and entry.strip() for entry in allow):
        raise ScopeError('"allow" must be a non-empty list of folder names')
    real_root = os.path.realpath(root)
    folders = []
    for entry in allow:
        if os.path.isabs(entry):
            raise ScopeError(f"{entry!r} is absolute; list folders relative to {root}")
        folder = os.path.realpath(os.path.join(real_root, entry))
        if not inside(folder, real_root):
            raise ScopeError(f"{entry!r} is outside the repository")
        folders.append(folder)
    reason = data.get("reason")
    return folders, reason.strip() if isinstance(reason, str) else ""


def inside(path, folder):
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:  # different drives on Windows
        return False


def target(tool_input, cwd):
    """The real path the tool would write, or None when the input names none."""
    if not isinstance(tool_input, dict):
        return None
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(path, str) or not path.strip():
        return None
    try:
        return os.path.realpath(os.path.join(cwd or os.getcwd(), os.path.expanduser(path)))
    except ValueError:  # a NUL byte or another unrepresentable path: judged as outside, never skipped
        return ""


INSTRUCTION_FILES = frozenset(("claude.md", "agents.md", "gemini.md", "skill.md", "copilot-instructions.md"))
INSTRUCTION_DIRS = frozenset((".claude", ".agents", ".cursor", ".codex", ".gemini", ".github"))


def is_report(path, root):
    """A Markdown file inside the root that does not instruct an agent: the report a reached run limit allows."""
    if not path.lower().endswith(".md") or not inside(path, root):
        return False
    parts = [part.lower() for part in os.path.relpath(path, root).split(os.sep)]
    return parts[-1] not in INSTRUCTION_FILES and not INSTRUCTION_DIRS.intersection(parts[:-1])


def refusal(tool_name, tool_input, cwd, report_write=False):
    """Why the write breaks the lock, or ''. report_write: a reached run limit allows this Markdown report, which the
    lock then accepts only inside the lock's own root (never ~/.claude or another project)."""
    if tool_name not in WRITE_TOOLS:
        return ""
    root, lock_file = find(cwd)
    if not lock_file:
        return ""
    shown = os.path.relpath(lock_file, root)
    try:
        folders, why = load(root, lock_file)
    except ScopeError as error:
        return (f"arsenal scope lock ({shown}) is malformed: {error}. Every write is denied until the user fixes or "
                "clears it (scope.py clear).")
    path = target(tool_input, cwd)
    if path is None or any(inside(path, folder) for folder in folders):
        return ""
    if report_write and path and is_report(path, os.path.realpath(root)):
        return ""
    names = ", ".join(os.path.relpath(folder, os.path.realpath(root)) for folder in folders)
    because = f" ({why})" if why else ""
    return (f"arsenal scope lock ({shown}): {path} is outside the allowed folders {names}{because}. Stay inside them, "
            "or ask the user to widen or clear the lock (scope.py set/clear).")
