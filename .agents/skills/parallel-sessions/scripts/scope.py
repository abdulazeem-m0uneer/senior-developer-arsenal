#!/usr/bin/env python3
"""Set, show or clear the edit-scope lock that the arsenal PreToolUse hook enforces (hooks/guard_scope.py).

Usage (run from anywhere inside the repository):
  python3 scope.py set <folder>... [--reason TEXT]   # writes .claude/arsenal-scope.json at the repository root
  python3 scope.py show                             # prints the lock, or "no scope lock"
  python3 scope.py clear                            # removes the lock file
Folders are given relative to the current directory and stored relative to the repository root; each must
exist and lie inside the repository. Exit codes: 0 done, 2 usage error, a folder outside the repository or
missing, or no repository. Standard library only.
"""
import json
import os
import subprocess
import sys

LOCK = os.path.join(".claude", "arsenal-scope.json")


def repo_root(cwd):
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True,
                             timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return os.path.realpath(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def fail(message):
    print(f"scope: {message}", file=sys.stderr)
    return 2


def set_lock(root, cwd, args):
    folders, reason = [], ""
    items = iter(args)
    for item in items:
        if item == "--reason":
            reason = next(items, "")
            if not reason.strip():
                return fail("--reason needs a text")
        else:
            folders.append(item)
    if not folders:
        return fail("set needs at least one folder")
    allow = []
    for folder in folders:
        real = os.path.realpath(os.path.join(cwd, folder))
        if os.path.commonpath([real, root]) != root:
            return fail(f"{folder} is outside the repository {root}")
        if not os.path.isdir(real):
            return fail(f"{folder} is not an existing folder")
        relative = os.path.relpath(real, root)
        if relative == ".":
            return fail("locking to the repository root locks nothing; use clear instead")
        allow.append(relative.replace(os.sep, "/"))
    path = os.path.join(root, LOCK)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump({"allow": sorted(set(allow)), "reason": reason.strip()}, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)
    print(f"scope locked to {', '.join(sorted(set(allow)))} ({LOCK})")
    return 0


def main(argv):
    if len(argv) < 2 or argv[1] not in ("set", "show", "clear"):
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    cwd = os.getcwd()
    root = repo_root(cwd)
    if root is None:
        return fail("not inside a git repository")
    path = os.path.join(root, LOCK)
    if argv[1] == "set":
        return set_lock(root, cwd, argv[2:])
    if argv[1] == "clear":
        if os.path.exists(path):
            os.remove(path)
            print("scope lock cleared")
        else:
            print("no scope lock")
        return 0
    try:
        with open(path, encoding="utf-8") as handle:
            print(handle.read().strip())
    except FileNotFoundError:
        print("no scope lock")
    except OSError as error:
        return fail(f"cannot read {LOCK}: {error}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
