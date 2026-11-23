#!/usr/bin/env python3
"""Shell syntax check of a Bash command, for guard_lessons' built-in `shell-syntax` rule (Claude Code plugin).

Usage: error = guard_syntax.parse_error(command, shell="bash")  # the shell's first error line, or None
A command the shell cannot parse is refused before any part of it runs: free text with an apostrophe inside a
single-quoted argument (`echo 'it's done'`) ends the quote early, and in a multi-line command the lines before the
parse error would already have run. The command goes to `<shell> -n` on stdin: -n reads and parses every line and
executes nothing, not even a command substitution. bash also gets -O extglob so `!(x)` patterns parse as they do
where extglob is on; zsh gets -f so no user startup file is read. The shell runs with only PATH and LC_ALL=C in its
environment (no BASH_ENV, English messages), at most TIMEOUT_SECONDS, on at most MAX_COMMAND_BYTES of command.
Fails open: a shell that is missing or cannot start, a timeout, a longer command, a non-zero exit whose message
is not a parse error, and any other fault give None, so a broken guard never refuses a command.
A here-document whose end word is missing is only a warning to bash (exit 0) and passes. Standard library only.
"""
import os
import re
import subprocess

SHELLS = frozenset(("bash", "sh", "dash", "zsh", "ksh", "mksh"))
SHELL_FLAGS = {"bash": ("-O", "extglob"), "zsh": ("-f",)}
TIMEOUT_SECONDS = 1.0
MAX_COMMAND_BYTES = 200_000  # a longer command is not checked: the parse would cost more than the hook may spend
OUTPUT_LIMIT = 4096  # bytes of the shell's error output read
ERROR_LIMIT = 200  # characters of the error line shown in the refusal
PARSE_ERROR = re.compile(r"syntax error|parse error|unexpected|unmatched|unterminated|bad substitution", re.I)


def clip(text):
    return text if len(text) <= ERROR_LIMIT else text[:ERROR_LIMIT - 1] + "\u2026"


def parse_error(command, shell="bash", run=None, timeout=TIMEOUT_SECONDS):
    """The first error line `<shell> -n` prints for the command, cut to ERROR_LIMIT characters; None when it parses
    or when the check cannot be made (see the module docstring). run replaces subprocess.run for tests."""
    try:
        if shell not in SHELLS or not isinstance(command, str):
            return None
        data = command.encode("utf-8")
        if len(data) > MAX_COMMAND_BYTES:
            return None
        env = {"PATH": os.environ.get("PATH", os.defpath), "LC_ALL": "C"}
        argv = [shell, "-n", *SHELL_FLAGS.get(shell, ())]
        done = (run or subprocess.run)(argv, input=data, capture_output=True, timeout=timeout, env=env, check=False)
        if done.returncode == 0:
            return None
        output = (done.stderr or b"")[:OUTPUT_LIMIT].decode("utf-8", "replace")
        line = next((line.strip() for line in output.splitlines() if PARSE_ERROR.search(line)), None)
        return clip(line) if line else None  # a warning first (an open here-document) is passed over
    except Exception:  # a missing shell, a timeout (run kills the child), bad text: never refuse for the guard's fault
        return None
