#!/usr/bin/env python3
"""Scheduled work whose script sits in /tmp or a scratchpad, for guard_lessons' opt-in `durable-path` rule.

Usage: text = guard_durable_path.problem(command, entry, parse)         # Bash: None, or the refusal text
       text = guard_durable_path.file_problem(tool_name, tool_input, entry)  # Write, Edit, MultiEdit: the same
       ok = guard_durable_path.valid_scratch(value)                     # a registry "scratch" value this rule can use
Never raises: any error passes the command or the write.
A script, tool or job file kept in /tmp or in a session scratchpad is wiped by cleanup or a reboot, so work that is
scheduled or persistent must not point there. Judged: a Bash command that schedules work to run later (systemd-run
with --on-calendar, --on-active, --on-boot, --on-startup, --on-unit-*, --on-clock-change, --on-timezone-change or
--timer-property; at or batch reading a file or job text; a crontab installed from stdin) and a Write, Edit or
MultiEdit of a .service unit or its .service.d/*.conf drop-in (ExecStart, ExecStartPre,
ExecStartPost), a crontab file (a name that starts with
crontab or ends in .cron or .crontab, a file under /etc/cron.d or /var/spool/cron) or an at job file
(/var/spool/cron/atjobs, /var/spool/at) whose command path is under those places.
For at, batch and crontab only the job text they read is
judged (the echo or printf piped into them, a here-string, a here-document, `< file`, `at -f file`), not other words
of the command line. Paths are normalised (//tmp/x, /tmp/../home/x). The command path is the program,
or for an interpreter (sh, bash, python, node, env ...) the script it runs, also in `bash -c '...'`.
"Under those places" means: a path under /tmp/, a path containing /scratchpad/, or one that matches a glob of the
entry's "scratch" list (shell globs; a glob without a leading / also matches as a path suffix). Running a script now
(`bash /tmp/x.sh`, `systemd-run --scope ... /tmp/x`) passes: only scheduled or persistent work is judged.
Not seen: a path built from a variable ($TMPDIR), a script that sources or starts another one from /tmp, a crontab
installed from a file (`crontab /tmp/lines`: its lines are judged when written), at text read from a variable.
Standard library only.
"""
import fnmatch
import os
import posixpath
import re

import guard_destructive as shell
import guard_timer

TIMER_OPTIONS = frozenset(("--on-calendar", "--on-active", "--on-boot", "--on-startup", "--on-unit-active",
                           "--on-unit-inactive", "--timer-property"))
TIMER_FLAGS = frozenset(("--on-clock-change", "--on-timezone-change"))  # schedule by an event, take no value
SYSTEMD_RUN_VALUE_OPTIONS = frozenset((
    "-p", "--property", "-u", "--unit", "--description", "--slice", "--slice-inherit", "-E", "--setenv", "-M",
    "--machine", "-H", "--host", "--uid", "--gid", "--nice", "--working-directory", "--service-type", "--job-mode",
    "--json", "--pty-late")) | TIMER_OPTIONS
INTERPRETER = re.compile(r"(?:sh|bash|zsh|dash|ksh|python[\d.]*|node|nodejs|perl|ruby|php|bun|deno)")
CRON_FIELD = r"(?:[0-9*/,\-]|sun|mon|tue|wed|thu|fri|sat|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)+"
SCHEDULE = (r"(?:@(?:reboot|hourly|daily|weekly|monthly|yearly|annually|midnight)"
            r"|(?:" + CRON_FIELD + r"[ \t]+){4}" + CRON_FIELD + r")")
CRON_IN_TEXT = re.compile(r"(?:^|[\s\"';(])" + SCHEDULE + r"[ \t]+([^\n]*)", re.I | re.M)
CRON_LINE = re.compile(r"^[ \t]*" + SCHEDULE + r"[ \t]+(.*)$", re.I)
EXEC_LINE = re.compile(r"^[ \t]*Exec(?:Start|StartPre|StartPost)[ \t]*=[ \t]*(.*)$")
SYSTEM_CRONTABS = ("/etc/crontab", "/etc/cron.d/")
AT_DIRECTORIES = ("/var/spool/cron/atjobs/", "/var/spool/at/", "/var/spool/atjobs/")
CRON_DIRECTORIES = ("/etc/cron.d/", "/var/spool/cron/")
AT_READ_ONLY = frozenset("ldrcV")
TEXT_COMMANDS = frozenset(("echo", "printf"))
DOCUMENT_SUFFIXES = (".md", ".markdown", ".txt", ".rst", ".adoc", ".html")
MAX_SCRATCH = 50
MAX_GLOB_CHARS = 200
REASON = ("{path} is kept in /tmp or a session scratchpad, which cleanup or a reboot wipes, so the scheduled job "
          "would find nothing to run. Keep the script in a durable place (the repository, ~/.local/bin) and "
          "schedule that path.")


def valid_scratch(value):
    return (isinstance(value, list) and 0 < len(value) <= MAX_SCRATCH
            and all(isinstance(item, str) and item.strip() and len(item) <= MAX_GLOB_CHARS for item in value))


def globs(entry):
    value = entry.get("scratch") if isinstance(entry, dict) else None
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def volatile(word, patterns):
    """Whether a path word is under /tmp/, a scratchpad, or one of the entry's scratch globs."""
    if "/" not in word:
        return False
    word = posixpath.normpath(re.sub(r"^/+", "/", word))  # //tmp/x and /tmp/../home/x are what the kernel resolves
    return (word.startswith("/tmp/") or "/scratchpad/" in word
            or any(fnmatch.fnmatchcase(word, pattern) or (not pattern.startswith("/")
                                                           and fnmatch.fnmatchcase(word, "*/" + pattern))
                   for pattern in patterns))


def target(argv):
    """The path a command line runs: its program, or the script of an interpreter (also `bash -c '...'`); '' if none."""
    name, args = shell.program(argv)
    if not name:
        return ""
    word = argv[len(argv) - len(args) - 1]
    if name == "env":  # given by path (/usr/bin/env), so shell.program kept it
        return target(next((args[i:] for i, arg in enumerate(args)
                            if not arg.startswith("-") and not shell.ASSIGNMENT.match(arg)), []))
    if not INTERPRETER.fullmatch(name):
        return word
    if name in shell.SHELLS:
        flag = next((i for i, arg in enumerate(args) if re.fullmatch(r"-[a-z]*c", arg)), None)
        if flag is not None and flag + 1 < len(args):
            return target(shell.tokens(args[flag + 1]))
    return next((arg for arg in args if not arg.startswith("-")), "")


def scheduling_target(args):
    """For systemd-run arguments: the command path it would run later, or '' when it schedules nothing."""
    scheduled, index = False, 0
    while index < len(args) and args[index].startswith("-") and args[index] != "--":
        flag, equals, _ = args[index].partition("=")
        scheduled = scheduled or flag in TIMER_OPTIONS or flag in TIMER_FLAGS
        index += 2 if flag in SYSTEMD_RUN_VALUE_OPTIONS and not equals else 1
    index += 1 if index < len(args) and args[index] == "--" else 0
    return target(args[index:]) if scheduled else ""


def installs_crontab(args):
    """`crontab -` (or `crontab` alone) reads the new table from stdin; -l, -r and -e do not."""
    return "-" in args or not any(arg.startswith("-") for arg in args)


def reads_a_job(args):
    """at and batch read a job unless they only list, remove or show jobs (-l, -d, -r, -c, -V)."""
    return not any(re.fullmatch(r"-[a-zA-Z]*", arg) and AT_READ_ONLY & set(arg[1:]) for arg in args)


def cron_targets(rest, system=False):
    """The command path of each command of a crontab line's command (`a && b` has two); the user field of a system
    crontab comes first and is skipped."""
    runs = shell.command_runs(rest.strip())
    argvs = [run[0] for run in runs]
    if system and argvs:
        argvs[0] = argvs[0][1:]
    return [path for path in (target(argv) for argv in argvs) if path]


def text_lines(*sources):
    """The lines of text sources; echo -e and printf write a literal \\n for a line break."""
    return [line for source in sources for line in source.replace("\\n", "\n").splitlines()]


def pipeline_before(runs, index):
    """The runs that feed run `index` through a pipe, also from inside ( ... ) | cmd; stops at ; && || or a newline."""
    found, depth, at = [], 0, index
    while at > 0:
        for char in reversed(runs[at][4].replace("||", ";")):
            if char == ")":
                depth += 1
            elif char == "(":
                depth -= 1
            elif char in ";&\n" and depth <= 0:
                return found
        at -= 1
        found.append(runs[at])
    return found


def stdin_text(runs, index, bodies):
    """(job text, files read) a crontab or at run gets on stdin: echo/printf in its pipeline, a here-string, a
    here-document body, a `< file`."""
    argv = runs[index][0]
    feeders = [run for run in pipeline_before(runs, index)
               if shell.program(run[0])[0] in TEXT_COMMANDS]
    sources = [" ".join(shell.program(run[0])[1]) for run in feeders]
    here = any(run[2] for run in [runs[index]] + pipeline_before(runs, index))
    sources += [bodies] if here else []
    files = []
    for position, word in enumerate(argv[:-1]):
        if word == "<<<":
            sources.append(argv[position + 1])
        elif word == "<":
            files.append(argv[position + 1])
    return text_lines(*sources), files


def scheduled_stdin_path(command, patterns, depth=0):
    """The first volatile path in the stdin of a crontab install or an at/batch job, in any sh -c text; or ''."""
    text, bodies = shell.split_heredocs(command)
    runs = shell.command_runs(text)
    for index, run in enumerate(runs):
        name, args = shell.program(run[0])
        if name in shell.SHELLS and depth < shell.MAX_DEPTH:
            flag = next((i for i, arg in enumerate(args) if re.fullmatch(r"-[a-z]*c", arg)), None)
            nested = scheduled_stdin_path(args[flag + 1], patterns, depth + 1) \
                if flag is not None and flag + 1 < len(args) else ""
            if nested:
                return nested
        installs = (name == "crontab" and installs_crontab(args)) or (name in ("at", "batch") and reads_a_job(args))
        if not installs:
            continue
        lines, files = stdin_text(runs, index, bodies)
        if name == "crontab":
            found = [path for line in lines for match in CRON_IN_TEXT.finditer(line)
                     for path in cron_targets(match.group(1))]
        else:
            files += [args[i + 1] for i, arg in enumerate(args[:-1]) if arg == "-f"]
            found = [target(shell.tokens(line)) for line in lines]
        path = next((word for word in files + found if volatile(word, patterns)), "")
        if path:
            return path
    return ""


def problem_paths(command, patterns, parse):
    """The first volatile path a scheduling command of the Bash text points at, or ''."""
    for cmd in parse(command):
        if cmd.name == "systemd-run":
            path = scheduling_target(cmd.args)
            if volatile(path, patterns):
                return path
    return scheduled_stdin_path(command, patterns)


def problem(command, entry, parse=None):
    """The refusal text for scheduled work that points into /tmp or a scratchpad, or None."""
    try:
        if not isinstance(command, str) or not isinstance(entry, dict):
            return None
        if not re.search(r"systemd-run|crontab|\bat\b|\bbatch\b", command):
            return None
        if parse is None:
            import guard_lessons  # imported here: guard_lessons imports this module
            parse = guard_lessons.commands
        path = problem_paths(command, globs(entry), parse)
        return REASON.format(path=path) if path else None
    except Exception:  # a guard never refuses for its own fault
        return None


def file_kind(path):
    if path.endswith(".service") or (".service.d/" in path and path.endswith(".conf")):
        return "service"
    if path.startswith(AT_DIRECTORIES) or path.endswith((".at", ".atjob")):
        return "at"
    name = os.path.basename(path)
    if ((name.startswith("crontab") and not name.endswith(DOCUMENT_SUFFIXES)) or name.endswith((".cron", ".crontab"))
            or path.startswith(CRON_DIRECTORIES)):
        return "cron"
    return ""


def file_path_in(kind, path, text, patterns):
    """The first volatile command path in the text of a unit, crontab or at job file, or ''."""
    system = path.startswith(SYSTEM_CRONTABS)
    for line in (text.replace("\\\n", " ") if kind == "service" else text).splitlines():  # \ continues a unit line
        if kind == "service":
            match = EXEC_LINE.match(line)
            found = [target(shell.tokens(match.group(1).lstrip("@-+!: \t")))] if match else []
        elif kind == "cron":
            match = CRON_LINE.match(line)
            found = cron_targets(match.group(1), system) if match else []
        else:
            found = [target(shell.tokens(line))] if line.strip() else []
        hit = next((word for word in found if volatile(word, patterns)), "")
        if hit:
            return hit
    return ""


def file_problem(tool_name, tool_input, entry):
    """The refusal for a Write, Edit or MultiEdit that leaves a unit, crontab or at job file pointing into /tmp or a
    scratchpad; None otherwise."""
    try:
        path = tool_input.get("file_path") if tool_name in guard_timer.FILE_TOOLS and isinstance(tool_input, dict) \
            else None
        kind = file_kind(path) if isinstance(path, str) else ""
        if not kind or not isinstance(entry, dict):
            return None
        text = guard_timer.resulting_text(tool_name, tool_input, path)
        found = file_path_in(kind, path, text, globs(entry)) if text else ""
        return REASON.format(path=found) if found else None
    except Exception:  # this rule must never stop a write it cannot judge
        return None
