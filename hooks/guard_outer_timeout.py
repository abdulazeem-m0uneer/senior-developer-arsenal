#!/usr/bin/env python3
"""A timeout around a queueing program, for guard_lessons' opt-in `outer-timeout` rule.

Usage: text = guard_outer_timeout.problem(command, entry)  # None, or the refusal text, which names the fix
       ok = guard_outer_timeout.valid_hint(value)          # a registry "hint" value this rule can use
Never raises: any error passes the command.
A queueing program (a gate-slot or lock wrapper that waits for its turn before it runs the job) under an outer
timeout is killed while it waits, so the job never ran and the wait counted against the job's own limit. The fix:
bound the wait with the tool's own wait setting (the entry's "hint") and put the timeout inside, on the command the
queueing program runs.
A queueing program is a simple command, or the script an interpreter runs, whose basename is in the entry's
"programs" (exact, suffix included; none by default, so nothing is judged). An outer timeout is `timeout` (any
duration but 0, .0, 0x0 or inf, which never fire; --help and --version run nothing; a variable duration is read) or `systemd-run` with a RuntimeMaxSec= property (the last one wins)
other than 0 or infinity, at any depth of wrappers between it and the queueing program: sudo, doas, env, watch, runuser -u, nice, ionice,
stdbuf, nohup, setsid, taskset, chrt, command, exec, time, unshare, systemd-run, timeout, npx/pnpm/yarn/npm/deno/bun
launchers, xargs, find -exec, docker/podman exec, env -S, the script of sh -c, su -c and eval, and the remote command
of ssh. Programs that run nothing pass: `command -v`, `gate-slot --help`, `-h` and `status` (as its first argument; a status read does not queue), and the syntax-check or module flags of an
interpreter (`bash -n gate-slot`, `python3 -m gate-slot`). A timeout inside the queueing program (`gate-slot timeout 600
cmd`) and a timeout and a queueing program in separate commands of one line pass.
Variables set earlier on the line (`S=gate-slot; timeout 5 $S x`) are read.
Not seen: a name set outside the command line, a name made by a command substitution (`$(echo gate-slot)`), a
program found through an alias, function or script file, docker run, and wrappers outside the list (flock, chroot, strace,
nsenter, kubectl exec). String work only: no file, process or network access.
Standard library only.
"""
import re
import shlex

import guard_destructive as shell
import guard_dry_run_chain
import guard_oom
import guard_timer

MAX_HINT_CHARS = 200
DEFAULT_HINT = "the tool's own wait setting"
TIMEOUT_VALUES = frozenset(("-k", "-s", "--kill-after", "--signal"))
NO_RUN = frozenset(("--help", "--version"))
QUEUE_NO_RUN = NO_RUN | {"-h", "status"}  # a queueing program asked for its usage or its read-only status
NEVER_FIRES = re.compile(r"(?:0+(?:\.0*)?|\.0+|0x0+|inf(?:inity)?)[smhd]?", re.I)  # GNU timeout: no limit is set
WRAPPERS = {**shell.WRAPPERS, "sudo": shell.WRAPPERS["sudo"] + " -r -t", "watch": "-n --interval", "setsid": "", "taskset": "-c --cpu-list", "chrt": "-T -P -D", "exec": "-a",
            "time": "-f -o --format --output"}
POSITIONALS = {"taskset": 1, "chrt": 1}  # words after the options that are not the command: a mask, a priority
SU_LIKE = frozenset(("su", "runuser"))
CONTAINER_EXEC = frozenset(("docker", "podman"))
EXEC_OPTIONS_WITH_VALUE = frozenset("-e --env -u --user -w --workdir --env-file --detach-keys".split())
FIND_RUNS = frozenset(("-exec", "-execdir", "-ok", "-okdir"))
PYTHON = (frozenset(("-m", "-c")), frozenset(("-W", "-X")))
INTERPRETERS = {  # name: (flags after which no script runs, options that take a value)
    **{name: (frozenset(("-n", "-s")), frozenset(("-o", "-O", "--rcfile", "--init-file"))) for name in shell.SHELLS},
    "python": PYTHON, "python3": PYTHON,
    "node": (frozenset("-c --check -e --eval -p --print -i --interactive".split()),
             frozenset("-r --require --import --loader --experimental-loader -C --conditions --env-file".split())),
    "ruby": (frozenset(("-c", "-e")), frozenset(("-r", "-I", "-C", "-E"))),
    "perl": (frozenset(("-c", "-e", "-E")), frozenset(("-I", "-M", "-m", "-C")))}
DEFAULT_VALUE = re.compile(r"\$\{(\w+):?[-=]([^}]*)\}")  # ${NAME:-default}
FIX = ("Bound the wait with {hint}, and put the timeout inside, on the command it runs: "
       "`{program} ... timeout N <command>`.")


def valid_hint(value):
    """A short one-line text the refusal can name: the tool's own wait setting."""
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= MAX_HINT_CHARS
            and "\n" not in value and "\r" not in value)


def skip_leading(argv, variables):
    """argv without leading assignments (added to variables) and redirections."""
    index = 0
    while index < len(argv):
        word = argv[index]
        if shell.ASSIGNMENT.match(word):
            variables.append(word)
            index += 1
        elif word and set(word) <= shell.REDIRECTION:
            index += 2
        elif word.isdigit() and index + 1 < len(argv) and set(argv[index + 1]) <= shell.REDIRECTION:
            index += 3
        else:
            break
    return argv[index:]


def timeout_rest(args, variables):
    """(the command after timeout's options and duration, whether the timeout is set); None when nothing runs."""
    index = 0
    while index < len(args) and args[index].startswith("-") and args[index] != "-":
        word = args[index]
        if word in NO_RUN:
            return None
        index += 2 if word in TIMEOUT_VALUES else 1
    if index >= len(args):
        return None
    return args[index + 1:], NEVER_FIRES.fullmatch(expand(args[index], variables)) is None


def bounded(value):
    """A RuntimeMaxSec value that ends the unit: not empty, 0 or infinity."""
    return guard_timer.UNBOUNDED.fullmatch(value.strip()) is None


def property_value(word, args, index):
    """(the value of a systemd-run property option, the next index); (None, index) for any other option."""
    if word.startswith("--property="):
        return word.partition("=")[2], index
    if word in ("-p", "--property"):
        return (args[index] if index < len(args) else None), index + 1
    if word.startswith("-p") and not word.startswith("--"):
        return word[2:], index  # -pRuntimeMaxSec=60
    return None, index


def launcher_rest(name, args):
    """(the command after the options of systemd-run or unshare, whether a RuntimeMaxSec bound was set)."""
    takes_value, index, runtime = guard_oom.LAUNCHERS[name], 0, False
    while index < len(args) and args[index].startswith("-") and args[index] != "-":
        word, index = args[index], index + 1
        if word == "--":
            break
        value, index = property_value(word, args, index) if name == "systemd-run" else (None, index)
        if value is None and word in takes_value:
            index += 1
        key, _, setting = (value or "").partition("=")
        if key == "RuntimeMaxSec":
            runtime = bounded(setting)  # the last one wins
    return args[index:], runtime


def script_operand(name, args):
    """(the script an interpreter runs, its arguments) for `bash ./x.sh a`, else None: also None when a flag (-n, -m, -e) makes it run
    no script, and the value of an option such as python -W or node -r is skipped."""
    no_script, takes_value = INTERPRETERS[name]
    index = 0
    while index < len(args) and args[index][:1] in ("-", "+"):
        if args[index] in no_script:
            return None
        index += 2 if args[index] in takes_value else 1
    return (args[index], args[index + 1:]) if index < len(args) else None


def shell_script(name, args):
    """The script of `sh -c` or eval, else ''."""
    if name == "eval":
        return " ".join(args)
    if name in shell.SHELLS | SU_LIKE:
        flag = next((i for i, arg in enumerate(args) if re.match(r"^-[a-z]*c$", arg) or arg == "--command"), None)
        script = args[flag + 1:flag + 3] if flag is not None else []
        return script[-1] if script[:1] == ["--"] else (script[0] if script else "")
    return ""


def find_commands(args):
    """The commands after each -exec, -execdir, -ok and -okdir of find, up to their ; or + terminator."""
    found, index = [], 0
    while index < len(args):
        if args[index] in FIND_RUNS:
            end = next((i for i in range(index + 1, len(args)) if args[i] in (";", "+")), len(args))
            found.append(args[index + 1:end])
            index = end
        index += 1
    return found


def container_command(args):
    """The command after `docker exec`'s options and container, else None."""
    if args[:1] != ["exec"]:
        return None
    index = 1
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in EXEC_OPTIONS_WITH_VALUE else 1
    return args[index + 1:]


def user_command(args):
    """The command after `runuser -u USER [--]`, else None (the -c script form is read by shell_script)."""
    for index, word in enumerate(args):
        if word in ("-u", "--user") and index + 1 < len(args):
            rest = args[index + 2:]
            return rest[1:] if rest[:1] == ["--"] else rest
    return None


def wrapper_rest(name, args):
    """The command after a wrapper's own options (sudo -u root, nice -n 5); walk() skips the assignments."""
    takes_value, index = WRAPPERS[name].split(), 0
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in takes_value else 1
    if name == "taskset" and {"-c", "--cpu-list"} & set(args[:index]):
        return args[index:]  # the CPU list was an option value, so no mask comes before the command
    return args[index + POSITIONALS.get(name, 0):]


def split_string(args):
    """env's -S / --split-string text split into words, then the arguments after it; None without that option."""
    index = 0
    while index < len(args):
        word = args[index]
        if word in ("-S", "--split-string"):
            text, after = (args[index + 1] if index + 1 < len(args) else ""), index + 2
        elif word.startswith("--split-string="):
            text, after = word.partition("=")[2], index + 1
        elif word.startswith("-S"):
            text, after = word[2:], index + 1
        elif word.startswith("-"):
            index += 2 if word in ("-u", "-C") else 1
            continue
        else:
            return None
        return shlex.split(text) + args[after:]
    return None


def run_subcommand(args):
    """The script and its arguments after `deno run` or `bun run` and the options around it, else None."""
    words = [word for word in args if not word.startswith("-")]
    return words[1:] if words[:1] == ["run"] else None


def expand(word, variables):
    """The word with $NAME, ${NAME} and ${NAME:-default} resolved from the variables set on this line."""
    values = dict(variable.split("=", 1) for variable in variables)
    return shell.expand(DEFAULT_VALUE.sub(lambda m: values.get(m.group(1), m.group(2)), word), variables)


def walk(argv, queues, timed, variables):
    """The queueing program (as its basename) that runs under a timeout through the wrappers of argv, else None."""
    argv = skip_leading(argv, variables)
    if not argv:
        return None
    word = expand(argv[0], variables)
    name, args = word.rpartition("/")[2], argv[1:]
    if name == "export":
        variables.extend(arg for arg in args if shell.ASSIGNMENT.match(arg))
        return None
    if name == "timeout":
        found = timeout_rest(args, variables)
        return walk(found[0], queues, timed or found[1], variables) if found else None
    if name in guard_oom.LAUNCHERS:
        rest, runtime = launcher_rest(name, args)
        return walk(rest, queues, timed or runtime, variables)
    if name == "command" and args[:1] in (["-v"], ["-V"]):
        return None  # a lookup, nothing runs
    if name == "env" and split_string(args) is not None:
        return walk(split_string(args), queues, timed, variables)
    if name == "runuser" and user_command(args) is not None:
        return walk(user_command(args), queues, timed, variables)
    if name in WRAPPERS:
        return walk(wrapper_rest(name, args), queues, timed, variables)
    if name in ("deno", "bun"):
        rest = run_subcommand(args)
        return walk(rest, queues, timed, variables) if rest else None
    if name in guard_dry_run_chain.LAUNCHERS:
        behind = guard_dry_run_chain.launched(name, args)
        return walk(list(behind[0:1]) + behind[1], queues, timed, variables) if behind else None
    if name == "ssh":
        return walk_script(guard_timer.ssh_remote(args), queues, timed, variables)
    if name == "find":
        return next(filter(None, (walk(run, queues, timed, variables) for run in find_commands(args))), None)
    if name in CONTAINER_EXEC:
        rest = container_command(args)
        return walk(rest, queues, timed, variables) if rest else None
    script = shell_script(name, args)
    if script:
        return walk_script(script, queues, timed, variables)
    operand = script_operand(name, args) if name in INTERPRETERS else None
    if operand:
        operand = (expand(operand[0], variables).rpartition("/")[2], operand[1])
    for candidate, rest in ((name, args), operand or (None, [])):
        if candidate in queues and not set(rest[:1]) & QUEUE_NO_RUN:
            return candidate if timed else None
    return None


def walk_script(script, queues, timed, variables):
    """walk() over each simple command of a script text; variables set in it stay in it."""
    scoped = list(variables)
    for argv, *_ in shell.command_runs(shell.split_heredocs(script)[0]):
        found = walk(argv, queues, timed, scoped)
        if found:
            return found
    return None


def problem(command, entry):
    """The refusal for a queueing program under an outer timeout; None otherwise or on any error."""
    try:
        queues = {name.rpartition("/")[2] for name in entry.get("programs") or ()}
        if not queues or not isinstance(command, str):
            return None
        found = walk_script(command, queues, False, [])
        if found is None:
            return None
        hint = entry.get("hint") or DEFAULT_HINT
        return (f"`{found}` queues for its turn, and a timeout around it kills the job while it waits. "
                + FIX.format(hint=hint, program=found))
    except Exception:  # this rule must never stop a command it cannot judge
        return None
