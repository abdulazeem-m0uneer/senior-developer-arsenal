#!/usr/bin/env python3
"""A command killed by exit 134 or 137, run again before the kernel log was read, for guard_lessons' `oom-first` rule.

Usage: guard_oom.reads_kernel_log(command, error=None, output="")  # True: guard.py track records {"event": "klog"}
       guard_oom.facts(command)  # what guard.py track adds to a 134/137 error event: {"same": digest, "timed": bool}
       failed = guard_oom.armed(command, state)  # None, or (the failed command as recorded, ran under timeout)
Exit 134 is V8's heap out of memory abort, 137 a SIGKILL, usually the kernel's or a cgroup's OOM killer: neither
says the change is wrong. guard.py track records each failed call as {"event": "error", "command": <one line, at
most 300 characters, credentials masked>, "error": "Exit code N ...", "checks": <its check keys>}, plus facts() for
a 134/137 (an interrupted call is not recorded), a successful `lessons.py cause` as {"event": "cause"}, and a call
that reads the kernel log as {"event": "klog"}. A kernel log read is a simple command of the call that is, after
wrappers (sudo, env, timeout, also written as a path) and launchers (systemd-run, unshare):
  journalctl with -k, --dmesg, -t kernel, --identifier=kernel, _TRANSPORT=kernel or SYSLOG_IDENTIFIER=kernel (short
             flags may be combined: -kb, -xk, -kn 50), or with -g/--grep, or piped into a grep, or saved to a file
             (> or >>) that a later grep of the call reads, of a pattern holding "oom", "out of memory" or "killed
             process" (any case);
  dmesg, unless it only clears the buffer or sets the console (-C, -D, -E, -n);
  cat, head, tail, less or a grep (not as its pattern) of a cgroup's memory.events or memory.events.local file (a
             bare name, or a path through a folder named for cgroups);
  systemctl status (--user or not), which prints "oom-kill" for a unit the OOM killer stopped;
and no call with --help or --version. It counts when the call exits 0, and when its last pipeline (a trailing
`&& echo ...` left out) holds the read, or greps a file an earlier step saved it to (a step that surely ran: not
after && or ||), and exits 1 from a grep or a journalctl --grep (nothing matched) or 1 or 3 from systemctl status
(the unit is not running), unless that pipeline followed `&&` (then it may not have run). Any other failure is not
a read, nor a call whose output starts with the kernel's refusal (dmesg's "read kernel buffer failed", journalctl's
"No journal files were opened/found").
A failure arms the rule; a later klog event clears every armed failure, and a later cause event clears the ones
that ran under timeout (`timeout` as the program or a wrapper, also behind systemd-run or unshare): exit 137 is
then as likely `timeout -s KILL` or `timeout -k` ending a command that ran past its limit. Armed, it refuses the
same command (by the digest of what it runs: wrappers and launchers, echo, printf and true left out, sh -c scripts
read, whitespace collapsed, here-document bodies kept) or one that shares a check key with it (also the keys of the
command behind a launcher, when the state gives check_keys). Only the newest MAX_ARMED armed failures are judged.
A call with --help or --version passes. Fails open: a state it cannot read arms nothing.
Not seen: timeout inside an sh -c script, a kernel log read through a script or a pager.
"""
import hashlib
import re

import guard_destructive as shell

KILLED = re.compile(r"Exit code 13[47](?!\d)")
EXIT_CODE = re.compile(r"Exit code (\d+)")
OOM_WORDS = re.compile(r"oom|out of memory|killed process", re.I)
DENIED = re.compile(r"read kernel buffer failed|No journal files were (?:opened|found)")
OUTPUT_CHARS = 4000  # the refusal is printed first; a long log is not searched to its end
JOURNAL_VALUES = "bnutTgpSUoDMFicH"  # journalctl short options that take a value (b and n optionally)
CGROUP_FILE = re.compile(r"(?:^|/)memory\.events(?:\.local)?$")
GREPS = frozenset(("grep", "egrep", "rg"))
FILE_READERS = GREPS | {"cat", "head", "tail", "less"}
GREP_PATTERN_OPTIONS = frozenset(("-e", "-f", "--regexp", "--file"))
KERNEL_MATCHES = frozenset(("_TRANSPORT=kernel", "SYSLOG_IDENTIFIER=kernel"))
DMESG_NO_READ = frozenset(("--clear", "--console-off", "--console-on", "--console-level", "--help", "--version"))
DMESG_NO_READ_LETTERS = frozenset("CDEnhV")  # clear, console off/on/level, help, version: nothing is read
WRITES = frozenset((">", ">>", "&>", "&>>", ">|"))
TRIVIAL = frozenset(("echo", "printf", "true", ":"))  # a step that changes nothing a rerun depends on
LAUNCHERS = {  # programs that run the command after their options: the options that take a value
    "systemd-run": frozenset("-p -u -E -M -H -C --property --unit --setenv --machine --host --capsule --description "
                             "--slice --uid --gid --nice --working-directory --root-directory --service-type "
                             "--on-active --on-boot --on-startup --on-unit-active --on-unit-inactive --on-calendar "
                             "--path-property --socket-property --timer-property --job-mode --background --json "
                             "--expand-environment".split()),
    "unshare": frozenset("-S -G -R -w -l --setuid --setgid --root --wd --load-interp --map-user --map-users "
                         "--map-group --map-groups --owner --propagation --setgroups --monotonic --boottime".split())}
MAX_LAYERS = 4
MAX_ARMED = 32  # the newest armed failures judged: the cost of a call must not grow with the session
DIGEST_CHARS = 16
NOT_A_RUN = frozenset(("--help", "--version"))
READER_WORD = re.compile(r"journalctl|dmesg|systemctl|memory\.events")  # a call without one reads no log


def journal_options(args):
    """[(option, value or None)] of journalctl's arguments: -xk is -x -k, -kn 50 is -k -n50, --grep=x is --grep x."""
    found, index = [], 0
    while index < len(args):
        arg, index = args[index], index + 1
        if arg.startswith("--"):
            name, equals, value = arg.partition("=")
            if not equals and name in ("--grep", "--identifier") and index < len(args):
                value, index = args[index], index + 1
            found.append((name, value or None))
        elif arg.startswith("-"):
            for at, letter in enumerate(arg[1:], 2):
                if letter in JOURNAL_VALUES:
                    value = arg[at:]
                    if not value and letter not in "bn" and index < len(args):
                        value, index = args[index], index + 1
                    found.append(("-" + letter, value or None))
                    break
                found.append(("-" + letter, None))
    return found


def journal_grep(args):
    """journalctl -g/--grep with a pattern for the OOM killer's lines."""
    return any(name in ("-g", "--grep") and value and OOM_WORDS.search(value) for name, value in journal_options(args))


def dmesg_reads(args):
    """False for a dmesg call that prints no log: it clears the buffer, sets the console, or shows help."""
    return not any(arg.partition("=")[0] in DMESG_NO_READ
                   or (arg[:1] == "-" and arg[1:2] != "-" and DMESG_NO_READ_LETTERS & set(arg[1:])) for arg in args)


def cgroup_read(name, args):
    """A file reader given a cgroup's memory.events (a bare name, or a path through a cgroup folder); a grep's first
    operand is its pattern unless -e or -f gave one."""
    if name not in FILE_READERS:
        return False
    operands = [arg for arg in args if not arg.startswith("-")]
    if name in GREPS and not any(arg.partition("=")[0] in GREP_PATTERN_OPTIONS for arg in args):
        operands = [arg for arg in operands if not arg.isdigit()][1:]  # -m 1 oom_kill memory.events
    return any(CGROUP_FILE.search(arg) and ("/" not in arg or "cgroup" in arg) for arg in operands)


def reader(name, args, piped_into):
    """True when one simple command reads the kernel log; piped_into: the args of each grep that reads its output."""
    if NOT_A_RUN & set(args):
        return False
    if name == "journalctl":
        kernel = any(option in ("-k", "--dmesg") or (option in ("-t", "--identifier") and value == "kernel")
                     for option, value in journal_options(args)) or bool(KERNEL_MATCHES & set(args))
        return bool(kernel or journal_grep(args)
                    or any(OOM_WORDS.search(arg) for grep in piped_into for arg in grep))
    if name == "dmesg":
        return dmesg_reads(args)
    if name == "systemctl":
        return "status" in args
    return cgroup_read(name, args)


def pipelines(command):
    """[(the operator before it, [(program, args)])] for each pipeline of the call, in order."""
    found, stages, argv, opener = [], [], [], ""
    for word in shell.tokens(command) + [";"]:
        if not (word and set(word) <= shell.SEPARATORS):
            argv.append(word)
            continue
        if argv:
            stages.append(shell.program(argv))
            argv = []
        if not (word.startswith("|") and word != "||"):
            if stages:
                found.append((opener, stages))
                stages = []
            opener = word
    return found


def written(args):
    """The files a simple command's output is redirected to."""
    return {args[index + 1] for index in range(len(args) - 1) if args[index] in WRITES}


def decides_as_read(stages, code):
    """True when the failed call's exit code says its last stage read the log: 1 from a grep (nothing matched) or a
    journalctl --grep, 1 or 3 from systemctl status (the unit is not running, as after an OOM kill)."""
    last, args = stages[-1]
    if last in GREPS or (last == "journalctl" and journal_grep(args)):
        return code == 1
    return last == "systemctl" and "status" in args and code in (1, 3)


def candidate(name, args):
    """True for a stage that reader() could count: journalctl, dmesg, systemctl, or a file reader of memory.events."""
    return name in ("journalctl", "dmesg", "systemctl") or (name in FILE_READERS
                                                           and any(CGROUP_FILE.search(arg) for arg in args))


def any_reader(groups, deciding=None):
    """True when a stage reads the kernel log, its output piped into a grep or saved to a file a later grep reads.
    deciding: the index of the pipeline whose exit decided a failed call; then only its stages count, and an earlier
    one that surely ran (not after && or ||) and saved a file a grep of the deciding pipeline reads."""
    stages = [(index, opener, name, args) for index, (opener, group) in enumerate(groups) for name, args in group]
    for at, (index, opener, name, args) in enumerate(stages):
        if not candidate(name, args):  # only these can read the log: the grep lists are built for them alone
            continue
        files = written(args)
        piped = [later_args for later, _, grep, later_args in stages[at + 1:] if later == index and grep in GREPS]
        saved = [later_args for later, _, grep, later_args in stages[at + 1:]
                 if later != index and grep in GREPS and files & set(later_args)
                 and (deciding is None or later == deciding)]
        if deciding is None or index == deciding:
            if reader(name, args, piped + saved):
                return True
        elif saved and not opener.startswith(("&&", "||")) and reader(name, args, saved):
            return True
    return False


def reads_kernel_log(command, error=None, output=""):
    """True when the call read the kernel log; error: the failure text of a call that did not exit 0; output: the
    start of its stdout and stderr (a refused read prints why)."""
    if not READER_WORD.search(command) or DENIED.search(output[:OUTPUT_CHARS]) \
            or (error is not None and DENIED.search(error)):
        return False
    try:
        groups = pipelines(shell.split_heredocs(command)[0])
    except Exception:  # a command the shell parser cannot split reads nothing
        return False
    code = EXIT_CODE.match(error or "")
    if not groups or (error is not None and not code):
        return False
    if error is None:
        return any_reader(groups)
    last = len(groups) - 1  # only the last pipeline decides the exit code; `&& echo found` after it cannot exit 1
    while last and groups[last][0].startswith("&&") and all(name in TRIVIAL for name, _ in groups[last][1]):
        last -= 1
    if groups[last][0].startswith("&&") or not decides_as_read(groups[last][1], int(code.group(1))):
        return False  # after && the deciding pipeline may not have run
    return any_reader(groups[:last + 1], deciding=last)


def launched(args, takes_value):
    """The command a launcher runs: the words after its options (a `--` among them is skipped like one)."""
    index = 0
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in takes_value else 1
    return args[index:]


def layers(argv):
    """[(words before the program, program name, its arguments)] for the program and each one it launches
    (systemd-run, unshare); a wrapper written as a path (/usr/bin/timeout) is read as the wrapper."""
    found = []
    for _ in range(2 * MAX_LAYERS):
        name, args = shell.program(argv)
        prefix = argv[:len(argv) - len(args) - 1] if name else argv
        if name in shell.WRAPPERS:
            argv = [*prefix, name, *args]
            continue
        found.append((prefix, name, args))
        if name not in LAUNCHERS or len(found) == MAX_LAYERS:
            break
        argv = launched(args, LAUNCHERS[name])
    return found


def under_timeout(argv):
    return any(name == "timeout" or "timeout" in prefix for prefix, name, _ in layers(argv))


def ran_under_timeout(command):
    try:
        return any(under_timeout(argv) for argv, _, _ in shell.simple_commands(shell.split_heredocs(command)[0]))
    except Exception:  # unparsable: only a kernel log read clears it
        return False


def programs(text, depth=0):
    """[(program, args)] the text runs, wrappers and launchers left out, `sh -c` scripts read, echo and true dropped."""
    found = []
    for argv, _, _ in shell.simple_commands(text):
        name, args = layers(argv)[-1][1:]
        if name in shell.SHELLS and "-c" in args[:-1] and depth < shell.MAX_DEPTH:
            found.extend(programs(args[args.index("-c") + 1], depth + 1))
        elif name and name not in TRIVIAL:
            found.append((name, args))
    return found


def core(command):
    """The programs the command runs with their arguments, wrappers and launchers left out, one line."""
    try:
        return " ; ".join(" ".join([name, *args]) for name, args in programs(shell.split_heredocs(command)[0]))
    except Exception:  # unparsable: compared as typed
        return " ".join(command.split())


def digest(command):
    """A short digest of the command's core and its here-document bodies (whitespace collapsed), or None when it runs
    nothing to compare; guard.py track stores it, so the comparison sees the command as it ran, not the one-line,
    cut and masked copy it records."""
    try:
        body = " ".join(shell.split_heredocs(command)[1].split())
    except Exception:
        body = ""
    text = core(command)
    if not text:
        return None
    return hashlib.sha256(f"{text}\n{body}".encode()).hexdigest()[:DIGEST_CHARS]


def facts(command):
    """What guard.py track adds to a 134/137 error event: {"same": its digest, "timed": it ran under timeout}."""
    same = digest(command)
    return {"timed": ran_under_timeout(command), **({"same": same} if same else {})}


def pending(events):
    """[(recorded command, its check keys, ran under timeout, digest or None)] armed and not cleared, oldest first: the
    newest MAX_ARMED."""
    found = []

    def timed(item):  # parsed only for the failures still kept, once each
        if item[2] is None:
            item[2] = ran_under_timeout(item[0])
        return item[2]

    for event in events:
        if not isinstance(event, dict):
            continue
        kind, error, command = event.get("event"), event.get("error"), event.get("command")
        if kind == "error" and isinstance(error, str) and KILLED.match(error) and isinstance(command, str):
            checks, ran, same = event.get("checks"), event.get("timed"), event.get("same")
            keys = {key for key in checks if isinstance(key, str)} if isinstance(checks, list) else set()
            found.append([command, keys, ran if isinstance(ran, bool) else None,
                          same if isinstance(same, str) else None])
            del found[:-MAX_ARMED]
        elif kind == "klog":
            found = []
        elif kind == "cause":
            found = [item for item in found if not timed(item)]
    return [(item[0], item[1], timed(item), item[3]) for item in found]


def armed(command, state):
    """(recorded command, ran under timeout) of the armed failure this command repeats, else None.
    state: {"events": the session's events, "keys": the command's check keys, "check_keys": guard.py's check_keys
    (optional, for the keys of a command behind a launcher)}."""
    try:
        if NOT_A_RUN & set(command.split()):
            return None
        check_keys = state.get("check_keys")

        def with_launched(text, keys):
            return set(keys) | (set(check_keys(core(text))) if callable(check_keys) else set())

        same, keys = digest(command), None
        for failed, failed_keys, timed, failed_same in reversed(pending(state.get("events") or [])):
            keys = with_launched(command, state.get("keys") or ()) if keys is None else keys
            if (same and same == (failed_same or digest(failed))) or with_launched(failed, failed_keys) & keys:
                return failed, timed
    except Exception:  # fail open: a state this rule cannot read never refuses a call
        return None
    return None
