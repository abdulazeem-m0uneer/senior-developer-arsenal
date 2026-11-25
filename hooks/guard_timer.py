#!/usr/bin/env python3
"""Timer and oneshot unit mistakes, for guard_lessons' opt-in `timer-safety` rule (Claude Code plugin).

Usage: problem = guard_timer.bash_problem(commands, parse)        # parse: guard_lessons.commands; commands: parse(cmd)
       problem = guard_timer.file_problem(tool_name, tool_input)  # a Write, Edit or MultiEdit call
Each returns the refusal text, which names the fix, or None. Neither raises: any error passes the call.
Bash: a `systemctl` restart verb (restart, try-restart, reload-or-restart, try-reload-or-restart, force-reload, and
the aliases condrestart, reload-or-try-restart, condreload) on a unit named *.timer, or a stop of a timer (`stop`,
`condstop`, `disable --now`, `mask --now`) followed in the same call by a start of the same timer in the same scope
(`start`, `enable --now`, `reenable --now`; --user or not). Restarting a timer, or stopping and starting it, is how a
timer gets "paused", and a Persistent= timer then fires the run it missed at once. The fix: edit the unit and
`systemctl daemon-reload`, or only disable it. A $NAME set earlier on the line is read, and so is each value of a
`for NAME in ...` loop; the remote command of an `ssh` call is judged on its own. A unit named without the .timer
suffix is not a timer (restarting timers.target does not restart the timers it wants).
Files: the content a Write gives, or the file an Edit or MultiEdit would leave (read from disk, at most
MAX_FILE_BYTES; a file that is missing, unreadable, too big or not a regular file, an old_string not in it, or an
empty old_string on a file that exists, passes: the tool refuses that edit itself), of a path ending in .timer or
.service. A leading byte order mark and comment lines (# or ;) are skipped, also inside a continued line, and a line
ending in a backslash continues on the next. In [Timer],
every non-empty OnCalendar= value without a % specifier (at most MAX_VALUES) goes to one `systemd-analyze calendar --
<values>` run (TIMEOUT_SECONDS); a value it names in a "Failed to parse calendar specification" line is refused. A
missing systemd-analyze, a timeout or a failure that names no value passes. In [Service], the last Type= being
oneshot needs a bounding start timeout: the last TimeoutStartSec= or TimeoutSec= value, not empty, 0 or infinity (a
oneshot has no start timeout by default and RuntimeMaxSec= does not bound it). A drop-in folder next to the file
(<name>.service.d) may set it, so its presence passes the oneshot check. Not seen: unit files written through Bash
(`cat > x.timer`), drop-in .conf files.
Standard library only.
"""
import os
import re
import shutil
import stat
import subprocess

import guard_destructive as shell

TIMEOUT_SECONDS = 2.0
MAX_VALUES = 16
MAX_READINGS = 64  # nested loops multiply; the rest are not judged
MAX_FILE_BYTES = 262_144
FILE_TOOLS = frozenset(("Write", "Edit", "MultiEdit"))
RESTARTS = frozenset(("restart", "try-restart", "reload-or-restart", "try-reload-or-restart", "force-reload",
                      "condrestart", "reload-or-try-restart", "condreload"))
STOPS = {"stop": False, "condstop": False, "disable": True, "mask": True}  # True: stops only with --now
STARTS = {"start": False, "enable": True, "reenable": True}  # True: starts only with --now
OPTIONS_WITH_VALUE = frozenset(("-t", "--type", "-s", "--signal", "-p", "--property", "-P", "-H", "--host", "-M",
                                "--machine", "-C", "--capsule", "-n", "--lines", "-o", "--output", "--state",
                                "--kill-whom", "--kill-value", "--root", "--image", "--image-policy", "--job-mode",
                                "--what", "--timestamp", "--boot-loader-entry", "--reboot-argument", "--message",
                                "--drop-in", "--when", "--preset-mode", "--check-inhibitors"))
SSH_OPTIONS_WITH_VALUE = frozenset("BbcDEeFIiJLlmOoPpQRSWw")
UNBOUNDED = re.compile(r"(?:0+(?:\.0*)?\s*[a-z]*|infinity)?", re.I)  # fullmatch: no start timeout
FAILED = "Failed to parse calendar specification '{}'"
FIX = ("To change when it runs, edit the unit and run `systemctl {scope}daemon-reload`; to pause it, only disable "
       "it (`systemctl {scope}disable --now {unit}`, in a call of its own). Then check that `systemctl {scope}"
       "list-timers {unit}` shows the expected next run.")


def units(args, variables=()):
    """(scope, verb, units) of a systemctl call: scope is "--user " or "", the units are its operands after the verb."""
    words, index, operands, scope = [shell.expand(arg, variables) for arg in args], 0, [], ""
    while index < len(words):
        word = words[index]
        if word == "--":
            operands += words[index + 1:]
            break
        if word == "--user":
            scope = "--user "
        if word.startswith("-"):
            index += 2 if word in OPTIONS_WITH_VALUE else 1
            continue
        operands.append(word)
        index += 1
    return scope, (operands[0] if operands else ""), operands[1:]


def ssh_remote(args):
    """The command an ssh call runs on the remote host (its words after the destination, joined), or ''."""
    return ssh_target(args)[1]


def ssh_target(args):
    """(destination, remote command) of an ssh call; the command is its words after the destination, joined.
    Options may also follow the destination (`ssh host -p 22 cmd`); `--` ends them."""
    index, destination, host = 0, False, ""
    while index < len(args):
        word = args[index]
        if word == "--":
            if not destination:
                host = args[index + 1] if index + 1 < len(args) else ""
            index += 1 if destination else 2  # `ssh -- host cmd`: the word after `--` is the destination
            break
        if word.startswith("-") and word != "-":
            letter = next((i for i, char in enumerate(word[1:], 1) if char in SSH_OPTIONS_WITH_VALUE), None)
            index += 2 if letter == len(word) - 1 else 1  # `-p 22` takes the next word, `-p22` and `-tt` do not
        elif destination:
            break
        else:
            destination, host, index = True, word, index + 1
    return host, " ".join(args[index:])


def readings(cmd, loops):
    """The variables a command's words may expand from: one set per value of each `for NAME in` loop it names."""
    found = [tuple(cmd.variables)]
    for name, values in loops.items():
        if any(f"${name}" in arg or f"${{{name}}}" in arg for arg in cmd.args):
            found = [(*variables, f"{name}={value}") for variables in found for value in values][:MAX_READINGS]
    return found


def bash_problem(commands, parse, stopped=None, host=""):
    """The refusal for a systemctl call that restarts a timer, or stops and then starts one; None otherwise.
    parse: guard_lessons.commands, which splits the remote command of an ssh call. stopped: the (host, scope, timer)
    stops seen so far in the whole call, shared with the remote commands of its ssh calls; host: where these run."""
    try:
        stopped = set() if stopped is None else stopped
        loops = {}
        for cmd in commands:
            if cmd.name == "ssh":
                destination, remote = ssh_target(cmd.args)
                problem = bash_problem(parse(remote), parse, stopped, destination) if remote else None
                if problem:
                    return problem
            elif cmd.name == "for" and cmd.args[1:2] == ["in"]:
                loops[cmd.args[0]] = cmd.args[2:]
            if cmd.name != "systemctl":
                continue
            now = "--now" in cmd.args
            for scope, verb, names in (units(cmd.args, variables) for variables in readings(cmd, loops)):
                timers = [name for name in names if name.endswith(".timer")]
                if verb in RESTARTS and timers:
                    return (f"`systemctl {scope}{verb} {timers[0]}` re-arms the timer, and a Persistent= timer then "
                            "fires its missed run at once. " + FIX.format(scope=scope, unit=timers[0]))
                if verb in STARTS and (now or not STARTS[verb]):
                    again = next((name for name in timers if (host, scope, name) in stopped), None)
                    if again:
                        return (f"Stopping {again} and starting it again in one call re-arms it, and a Persistent= "
                                "timer then fires its missed run at once. " + FIX.format(scope=scope, unit=again))
                if verb in STOPS and (now or not STOPS[verb]):
                    stopped.update((host, scope, name) for name in timers)
    except Exception:  # this rule must never stop a command it cannot judge
        return None
    return None


def resulting_text(tool_name, tool_input, path):
    """The file's text after the call, or None when it cannot be known (the tool then refuses or it is too big)."""
    if tool_name == "Write":
        return tool_input.get("content") if isinstance(tool_input.get("content"), str) else None
    edits = [tool_input] if tool_name == "Edit" else tool_input.get("edits")
    if not isinstance(edits, list):
        return None
    try:
        # O_NONBLOCK: opening a FIFO must not wait for a writer; only a regular file is read
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)), "rb") as handle:
            status = os.fstat(handle.fileno())
            if not stat.S_ISREG(status.st_mode) or status.st_size > MAX_FILE_BYTES:
                return None
            text = handle.read(MAX_FILE_BYTES + 1).decode("utf-8")
    except FileNotFoundError:
        text = None
    except (OSError, ValueError):
        return None
    for edit in edits:
        old, new = (edit.get("old_string"), edit.get("new_string")) if isinstance(edit, dict) else (None, None)
        if not isinstance(old, str) or not isinstance(new, str):
            return None
        if text is None:  # a missing file: only an empty old_string creates it
            if old:
                return None
            text = new
        elif not old or old not in text:
            return None
        else:
            text = text.replace(old, new) if edit.get("replace_all") else text.replace(old, new, 1)
    return text


def sections(text):
    """{section name: [(key, value), ...]} of a unit file's text, in file order."""
    found, current, lines = {}, None, iter(text.removeprefix("\ufeff").split("\n"))
    for raw in lines:
        line = raw.strip()
        if not line or line[0] in "#;":  # before continuation: systemd never continues a comment line
            continue
        while line.endswith("\\"):
            following = next(lines, "").strip()
            if not following.startswith(("#", ";")):  # a comment inside a continued line is skipped
                line = line[:-1] + " " + following
        if line.startswith("[") and line.endswith("]"):
            current = found.setdefault(line[1:-1], [])
        elif "=" in line and current is not None:
            key, _, value = line.partition("=")
            current.append((key.strip(), value.strip()))
    return found


def unparsable(values):
    """The values systemd-analyze calendar refuses; [] when it is missing, slow or names none of them."""
    program = shutil.which("systemd-analyze")
    if not program or not values:
        return []
    try:
        result = subprocess.run([program, "calendar", "--", *values], capture_output=True, text=True,
                                errors="replace", timeout=TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
                                env={**os.environ, "LC_ALL": "C", "SYSTEMD_COLORS": "0", "SYSTEMD_PAGER": ""})
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    output = result.stdout + result.stderr
    return [] if result.returncode == 0 else [value for value in values if FAILED.format(value) in output]


def timer_problem(found):
    values = [value for key, value in found.get("Timer", []) if key == "OnCalendar" and value and "%" not in value]
    bad = unparsable(list(dict.fromkeys(values))[:MAX_VALUES])
    if not bad:
        return None
    shown = "; ".join(f"OnCalendar={value}" for value in bad)
    return (f"{shown}: systemd-analyze calendar cannot parse it, so the timer would never run when meant. Fix the "
            "value and check it with `systemd-analyze calendar '<value>'` before writing; after daemon-reload, "
            "`systemctl --user list-timers` must show the expected next run.")


def service_problem(found, path):
    entries = found.get("Service", [])
    types = [value for key, value in entries if key == "Type"]
    if not types or types[-1] != "oneshot" or os.path.isdir(path + ".d"):
        return None
    timeouts = [value for key, value in entries if key in ("TimeoutStartSec", "TimeoutSec")]
    if timeouts and not UNBOUNDED.fullmatch(timeouts[-1]):
        return None
    return (f"{os.path.basename(path)} is Type=oneshot with no bounding TimeoutStartSec=: a oneshot unit has no start "
            "timeout by default and RuntimeMaxSec= does not bound it, so a hung run blocks every later one. Add "
            "TimeoutStartSec= (for example TimeoutStartSec=15min) under [Service].")


def file_problem(tool_name, tool_input):
    """The refusal for a Write, Edit or MultiEdit that leaves a bad .timer or .service file; None otherwise."""
    try:
        path = tool_input.get("file_path") if tool_name in FILE_TOOLS and isinstance(tool_input, dict) else None
        if not isinstance(path, str) or not path.endswith((".timer", ".service")):
            return None
        text = resulting_text(tool_name, tool_input, path)
        if text is None:
            return None
        found = sections(text)
        return timer_problem(found) if path.endswith(".timer") else service_problem(found, path)
    except Exception:  # this rule must never stop a write it cannot judge
        return None
