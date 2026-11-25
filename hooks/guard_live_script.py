#!/usr/bin/env python3
"""A script a shell is running right now, for guard_lessons' opt-in `live-script` rule (Claude Code plugin).

Usage: problem = guard_live_script.file_problem(tool_name, tool_input, cwd)  # a Write, Edit or MultiEdit call
Returns the refusal text, which names the fix, or None. Never raises: any error passes the call.
A shell reads a script a few lines at a time while it runs, so a script changed in place makes the running copy
read the new bytes at the old offset and fail midway. The fix: write a staged copy (<path>.next), test it, then mv
it into place (the running shell keeps the old file open). Only shells: python, node, perl and ruby compile the
whole file before they run it, so changing their script in place does not break the run.
The target is the call's file_path (a relative one is read from the hook's cwd); a path that is not an existing
regular file passes. The scan reads /proc/<pid>/cmdline of this user's processes (the uid that owns /proc/<pid>),
highest pid first (usually the newest; pids wrap), at most MAX_PIDS of them within BUDGET_SECONDS (150 ms; in a daemon
thread, so a blocked /proc read cannot hold the call), never the hook's own process. A process runs the target when
it is a shell (the basename of /proc/<pid>/exe or of argv[0] is bash, sh, zsh, dash, ksh or mksh, a version
suffix allowed: bash-5.2), its script operand (the first word after its options, the value of -o, -O and a cluster ending in them (-euo) skipped; none with -c or -s) names the
target (the same basename, so a script that ran cd still matches, or the same file by device and inode from the
process's cwd), and one of its file descriptors from 10 up is the target by device and inode: a shell keeps the
script it reads there (bash 255, dash 10), so one already replaced by mv (the shell holds the old inode) does not
match. Both are needed: a lock file (`exec {fd}>lock`) or the stdout bash saves during a redirection also sit on 10
and up. Descriptors 0 to 9 (`bash < x.sh`) never count, nor does the shell's executable.
A missing /proc, a process that exits mid-read, a scan past its budget and every error pass.
Not seen: a shell reached through busybox under another name, a script whose name starts with -, or a script
written through Bash (sed -i, cat >).
Standard library only.
"""
import os
import re
import stat
import threading
from time import monotonic

PROC = "/proc"
MAX_PIDS = 2000
BUDGET_SECONDS = 0.15  # a full scan of ~500 pids took 46-91 ms when measured
FILE_TOOLS = frozenset(("Write", "Edit", "MultiEdit"))
SHELL = re.compile(r"(?:bash|sh|zsh|dash|ksh|mksh)(?:-?[0-9][0-9.]*)?")
VALUE_OPTIONS = frozenset(("-o", "+o", "-O", "+O", "--rcfile", "--init-file"))  # the next word is their value
FIRST_SHELL_FD = 10  # shells move the script they read to 10 or above; below are its redirections and stdin


def is_shell(pid, argv0):
    """True when process pid's executable or argv[0] (a name or a path) names a shell."""
    if SHELL.fullmatch(os.path.basename(argv0)):
        return True
    try:
        exe = os.readlink(os.path.join(PROC, str(pid), "exe"))
    except OSError:  # not ours to read, or a kernel thread
        return False
    return SHELL.fullmatch(os.path.basename(exe)) is not None


def script_operand(argv):
    """The script a shell's argv names: the first word after its options; None with -c or -s, or with none."""
    words = iter(argv[1:])
    for word in words:  # `--` is skipped as an option, so a script whose name starts with - is not seen
        if word in VALUE_OPTIONS:
            next(words, None)
        elif word[:1] in "-+" and len(word) > 1:
            if not word.startswith("--") and ("c" in word or "s" in word):
                return None
            if not word.startswith("--") and word[-1] in "oO":  # -eo, -euo: the cluster's last letter takes the next word
                next(words, None)
        else:
            return word
    return None


def names(pid, operand, target, base):
    """True when a script operand of process pid names the target: its basename base, or (device, inode) target."""
    if os.path.basename(operand) == base:
        return True
    try:
        found = os.stat(os.path.join(PROC, str(pid), "cwd", operand))
    except OSError:  # gone, or the cwd is not ours to read
        return False
    return (found.st_dev, found.st_ino) == target


def holds(pid, target):
    """True when process pid has the file whose (device, inode) is target open on a descriptor from 10 up."""
    folder = os.path.join(PROC, str(pid), "fd")
    with os.scandir(folder) as entries:
        for entry in entries:
            if entry.name.isdigit() and int(entry.name) >= FIRST_SHELL_FD:
                try:
                    found = os.stat(os.path.join(folder, entry.name))
                except OSError:  # closed between the listing and the stat
                    continue
                if (found.st_dev, found.st_ino) == target:
                    return True
    return False


def running_pid(target, base):
    """The pid of a shell of this user that reads the file whose (device, inode) is target, named base, as its
    script; None
    when none does, also past the scan's limits.
    The scan runs in a daemon thread joined for BUDGET_SECONDS: a /proc read can block (a process whose memory map
    is locked), and a scan still running then passes."""
    found = []

    def scan():
        try:
            found.append(scan_pids(target, base, monotonic() + BUDGET_SECONDS))
        except Exception:  # judged as not running: this rule must never stop a write it cannot judge
            found.append(None)

    worker = threading.Thread(target=scan, daemon=True)
    worker.start()
    worker.join(BUDGET_SECONDS)
    return found[0] if found else None


def scan_pids(target, base, deadline):
    """running_pid's scan: highest pid first, at most MAX_PIDS of this user's, None once monotonic() passes deadline."""
    pids = sorted((int(entry.name) for entry in os.scandir(PROC) if entry.name.isdigit()), reverse=True)
    uid, own, seen = os.getuid(), os.getpid(), 0
    for pid in pids:
        if seen >= MAX_PIDS or monotonic() > deadline:
            return None
        if pid == own:
            continue
        folder = os.path.join(PROC, str(pid))
        try:
            if os.stat(folder).st_uid != uid:
                continue
            seen += 1
            with open(os.path.join(folder, "cmdline"), "rb") as handle:
                argv = handle.read().decode("utf-8", "surrogateescape").split("\0")
            operand = script_operand(argv)  # cmdline ends in NUL: a last empty word, never an operand
            if operand and is_shell(pid, argv[0]) and names(pid, operand, target, base) and holds(pid, target):
                return pid
        except OSError:  # exited mid-read, or its folder is not ours to read
            continue
    return None


def file_problem(tool_name, tool_input, cwd):
    """The refusal for a Write, Edit or MultiEdit of a script that a shell is running now; None otherwise."""
    try:
        path = tool_input.get("file_path") if tool_name in FILE_TOOLS and isinstance(tool_input, dict) else None
        if not isinstance(path, str) or not path or not os.path.isdir(PROC):
            return None
        found = os.stat(os.path.join(cwd or "", path))
        if not stat.S_ISREG(found.st_mode):  # a FIFO or device is never a script a shell reads from a file
            return None
        pid = running_pid((found.st_dev, found.st_ino), os.path.basename(path))
        if pid is None:
            return None
        return (f"{path} is running now (pid {pid}), and a shell reads its script while it runs, so changing it in "
                f"place breaks that run. Write a staged copy ({path}.next), test it, then mv it into place.")
    except Exception:  # this rule must never stop a write it cannot judge
        return None
