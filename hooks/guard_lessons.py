#!/usr/bin/env python3
"""Refuse a Bash command that repeats a recorded lesson, for guard.py's PreToolUse hook (Claude Code plugin).

Usage: hit = guard_lessons.judge(command, cwd)  # None, or Hit(lesson, rule, reason)
Rules: the built-in rules below, adjusted and extended by registry files. The global registry is
$LESSONS_GUARDS_GLOBAL_FILE or ~/.agents/lesson-guards.json; the project registry is .agents/lesson-guards.json,
searched from $CLAUDE_PROJECT_DIR (else the hook's cwd) upward. Format:
  {"guards": [
    {"rule": "hook-bypass", "lesson": "G027"},                        # tie a built-in rule to a lesson id
    {"rule": "help-probe", "enabled": false},                         # switch a built-in rule off
    {"rule": "secret-in-message", "programs": ["notify.sh"]},          # the commands that send messages
    {"lesson": "L031", "program": "git", "subcommand": "push", "args_any": ["--force", "-f"],
     "reason": "Force-pushed a shared branch. Push a new branch instead."}]}  # a rule of your own
A rule of your own matches a simple command by its program (a name or a list of names, never a path),
optionally its first operand (subcommand; for git, after the values of -C, -c, --git-dir and the like), any of `args_any` (exact words; a single letter such as -f also
matches inside a cluster such as -fq), any of `assignments_any` (VAR=value words before the program), and
`in_loop` (the command is the condition of while/until). A built-in rule named in both registries takes the
project entry. Any entry may carry "min_version": "X.Y.Z", the oldest hook that should apply it; an older hook
skips it, so a registry shared by sessions on different versions stays usable everywhere. The registry fails
safe per entry: an entry this hook cannot use (unknown rule or key, wrong type) is skipped, and a file that does
not parse is skipped whole, but every other entry and every built-in rule still apply and no command is refused
for it. registry_problems(cwd) lists what was skipped; `lessons.py guards` checks the registries against every
installed hook version, and the session-start lessons header reports skipped entries.
Words are judged after quotes are removed, so `grep "while pgrep -f"`, commit messages and echo text pass;
here-document bodies are dropped; the script of `sh -c` and `eval` is judged too. A $NAME or ${NAME} in the
program or script word is read from an assignment earlier in the same command line (`S=x.py; python3 $S -h`).
Not seen: names set outside the command line, commands run through xargs, ssh or a script file.
Built-in rules:
  pgrep-wait-loop    while/until pgrep -f: the pattern matches the waiting shell's own command line, so the loop
                     never ends. Wait on a recorded pid ($!), a lock file or a completion notice.
  hook-bypass        git --no-verify, git commit -n, setting core.hooksPath, git run with HUSKY=0 (on the
                     command or exported earlier in the same command line).
  help-probe         a script (a known suffix such as .sh or .py, run directly or through an interpreter, or a
                     command named in `programs`) run with --help, or with -h as its only argument: it may not parse
                     the flag and run for real. An interpreter run on a variable whose value is not known here
                     (`python3 "$SCRIPT" --help`) counts too: what follows an interpreter is a script.
  secret-in-message  a secret-looking value in the arguments of a command named in `programs` (none by default).
  calendar           in text a call sends (gh comments, PRs and issues, git commit messages, the registry's
                     `programs`, outbound MCP tools): a weekday that does not match its date, a date that does
                     not exist, a guessed time (16:4x), and with "workweek" (Sun-Thu) a promise on another day.
                     See guard_calendar.py.
  pipe-exit          a check (the Stop gate's test, build, lint or CI classifier) or a local script piped into a
                     later command, whose exit status is then acted on (&&, ||, if/while/until/!, or $? read by
                     the next command) without set -o pipefail or ${PIPESTATUS[...]}: the status is the last
                     command's, so a failed check reads as success.
  rerun-after-red    off until a registry entry names it. A test, build, lint or check command (the same check as the
                     Stop gate counts: tool and subcommand, flags and wrappers ignored) or a `git push` (same
                     operands) that failed last in this session and has no later pass, run again before a cause note
                     (`lessons.py cause "<assertion or check>: <cause or unknown>"`) was recorded after the failure.
Also not seen: a pgrep inside a quoted "$(...)" in a loop condition or in the loop body (`while true; do pgrep -f x
|| break; done`), and a here-document fed to a shell
(`bash <<EOF`), whose body is dropped as data.
Time budget: string work and at most a few stat calls and two small file reads per Bash call.
"""
import datetime as dt
import json
import os
import re
from collections import namedtuple
from pathlib import Path

import guard_calendar
import guard_destructive as shell

Hit = namedtuple("Hit", "lesson rule reason")

PROJECT_FILE = os.path.join(".agents", "lesson-guards.json")
GLOBAL_ENV = "LESSONS_GUARDS_GLOBAL_FILE"
LESSON_ID = re.compile(r"[LG]\d{3,}")  # used with fullmatch
LOOP_WORDS = frozenset(("while", "until"))
INTERPRETERS = frozenset("node python python3 bash sh zsh dash ksh ruby perl deno bun".split())
SCRIPT_SUFFIXES = (".sh", ".bash", ".py", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl")
INSTALLED_DIRS = ("node_modules/", ".venv/", "venv/", "site-packages/")
GIT_VALUE_OPTIONS = "mFcCtuS"  # a commit option letter that takes the rest of its cluster as its value (-uno)
GIT_OPTIONS_WITH_VALUE = frozenset(("-m", "-F", "-c", "-C", "-t", "--message", "--file", "--author", "--date",
                                    "--template", "--cleanup", "--fixup", "--squash", "--reuse-message",
                                    "--reedit-message", "--trailer"))
GIT_GLOBAL_WITH_VALUE = frozenset(("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
                                   "--config-env", "--super-prefix"))
CONFIG_READS = frozenset(("--get", "--get-all", "--get-regexp", "--get-urlmatch", "--unset", "--unset-all", "--list",
                          "-l", "--show-origin", "--show-scope", "get", "unset", "list"))
MAX_DEPTH = 2
BUILT_IN_REASONS = {
    "pgrep-wait-loop": "A while/until loop on pgrep -f matches its own shell's command line and never ends. Wait on "
                       "a recorded pid ($!), a lock file or the task-completion notice instead.",
    "hook-bypass": "This skips the git hooks. Fix what the hook reports instead of bypassing it.",
    "help-probe": "Do not probe a local script with --help or -h: it may not parse the flag and run for real. Read "
                  "its usage header or source first.",
    "secret-in-message": "A message must not carry a secret value. Name the file that holds the secret instead.",
    "calendar": "A date or time in this message is wrong: {problems}. Check dates with `date -d YYYY-MM-DD +%a` and the "
                "time with `date +%H:%M` before sending.",
    "pipe-exit": "A pipeline's exit status is its last command's, so `check | tail && next` goes on even when the "
                 "check failed. Use `set -o pipefail;` first, read ${PIPESTATUS[0]}, or run `check > out.log 2>&1; "
                 "echo rc=$?` and read the file.",
    "rerun-after-red": "This check or push failed and was not read. Read the failing lines, state the cause, record it "
                       'with `python3 {lessons} cause "<failing assertion or check>: <cause or unknown>"`, then rerun.',
}
OPT_IN = frozenset(("rerun-after-red",))  # off until a registry entry names it
ENTRY_KEYS = {"rule", "lesson", "reason", "enabled", "programs", "min_version", "workweek"}
TAKES_PROGRAMS = ("help-probe", "secret-in-message", "calendar")
CUSTOM_KEYS = {"lesson", "reason", "program", "subcommand", "args_any", "assignments_any", "in_loop", "min_version"}
VERSION_SHAPE = re.compile(r"\d{1,6}\.\d{1,6}\.\d{1,6}", re.ASCII)
REGISTRY_MAX_BYTES = 1_000_000
VARIABLE = re.compile(r"\$(?:\{(\w+)\}|(\w+))")
CODE_OR_MODULE = frozenset(("-c", "-e", "-m", "-p", "--eval", "--print"))  # the next word is code or a module


def version_tuple(text):
    return tuple(int(part) for part in text.split("."))


def hook_version(folder=None):
    """This hook's arsenal version: VERSION next to the hook (an installer copy ships it there), else at the plugin
    root; a file that is unreadable or not X.Y.Z is passed over. None when neither gives a version."""
    folder = Path(folder or Path(__file__).resolve().parent)
    for candidate in (folder / "VERSION", folder.parent / "VERSION"):
        try:
            text = candidate.read_text(encoding="utf-8").strip().lstrip("\ufeff")
        except (OSError, ValueError):  # ValueError: not UTF-8; this runs at import and must never fail it
            continue
        if VERSION_SHAPE.fullmatch(text):
            return version_tuple(text)
    return None


HOOK_VERSION = hook_version()


class RegistryError(ValueError):
    """A registry file that cannot be used; the message names the file and the fault."""


Command = namedtuple("Command", "word name args assignments in_loop variables", defaults=((),))


def commands(command, depth=0, inherited=()):
    """Each simple command as (program word, program name, args, its assignments, in a while/until condition);
    assignments include those exported earlier in the line; the script of sh -c and eval is expanded in place.
    Every command between `while`/`until` and `do` is in the condition (`while kill -0 $p && pgrep -f x; do`).
    variables: the NAME=value words a command's own words expand from, set earlier by a bare assignment or export
    (a prefix assignment, `X=a cmd $X`, is not: the shell expands $X before it assigns)."""
    found, exported, condition = [], list(inherited), False
    variables = list(inherited)
    for argv, _piped, _heredoc in shell.simple_commands(shell.split_heredocs(command)[0]):
        name, args = shell.program(argv)
        prefix = argv[:len(argv) - len(args) - 1] if name else argv
        word = argv[len(prefix)] if name else ""
        if "do" in prefix:
            condition = False
        if any(w in LOOP_WORDS for w in prefix):
            condition = True
        expands_from = tuple(variables)
        own = [w for w in prefix if shell.ASSIGNMENT.match(w)]
        if name == "export":
            exported += [arg for arg in args if shell.ASSIGNMENT.match(arg)]
            variables += [arg for arg in args if shell.ASSIGNMENT.match(arg)]
        elif not name:
            variables += own  # `S=x.py; ...`: a bare assignment sets a shell variable
        assignments = exported + own
        found.append(Command(word, name, args, assignments, condition, expands_from))
        script = ""
        if name in shell.SHELLS and depth < MAX_DEPTH:
            flag = next((i for i, arg in enumerate(args) if re.match(r"^-[a-z]*c$", arg)), None)
            script = args[flag + 1] if flag is not None and flag + 1 < len(args) else ""
        elif name == "eval" and depth < MAX_DEPTH:
            script = " ".join(args)
        if script:
            found.extend(commands(script, depth + 1, assignments))  # HUSKY=0 bash -c '...'
    return found


def has_option(args, letter, long_name=None):
    """A single-letter option given alone or inside a cluster (-af), or the long option (--full, --full=x)."""
    return any((long_name and (arg == long_name or arg.startswith(long_name + "=")))
               or (re.match(r"^-[A-Za-z]+$", arg) and letter in arg[1:]) for arg in args)


def push_key(cmd):
    """`git push origin feat` for a git push (its operands, no options), else ''."""
    if cmd.name != "git":
        return ""
    index, subcommand = git_subcommand(cmd.args)
    if subcommand != "push":
        return ""
    return " ".join(["git push", *(a for a in cmd.args[index + 1:] if not a.startswith("-"))])


def push_keys(command):
    return [key for key in map(push_key, commands(command)) if key]


def is_cause_command(cmd):
    script, args = script_and_args(cmd)
    return script.rpartition("/")[2] in ("lessons", "lessons.py") and "cause" in args[:3]


def rerun_after_red(cmd, entry):
    """The same check, or the same push, that failed last in this session and has no cause note since."""
    session = entry.get("session")
    if not session or is_cause_command(cmd):
        return False
    state = session()
    return bool((state["keys"] | {push_key(cmd)}) & state["red"])


def pgrep_wait_loop(cmd, _entry):
    return cmd.in_loop and cmd.name == "pgrep" and has_option(cmd.args, "f", "--full")


def git_subcommand(args):
    """(index, subcommand) of a git command line: the first word that is not a global option or its value."""
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in GIT_GLOBAL_WITH_VALUE:
            index += 2
        elif arg.startswith("-"):
            index += 1
        else:
            return index, arg
    return len(args), ""


def git_options(args):
    """The option words of a git subcommand, without option values (-m "--no-verify") and operands after `--`."""
    options, words = [], iter(args)
    for arg in words:
        if arg == "--":
            break
        if arg.startswith("-"):
            options.append(arg)
            if arg in GIT_OPTIONS_WITH_VALUE:
                next(words, None)
    return options


def commit_skips_hooks(options):
    """-n alone or in a cluster, but not inside a value attached to -m, -u and the like (-mn, -uno)."""
    return any(re.match(r"^-[A-Za-z]+$", arg) and "n" in re.split(f"[{GIT_VALUE_OPTIONS}]", arg[1:], maxsplit=1)[0]
               for arg in options)


def sets_hooks_path(args, index, subcommand):
    """-c core.hooksPath=... before the subcommand, or `git config [set] core.hooksPath VALUE`."""
    if any(arg.lower().startswith("core.hookspath=") for arg in args[:index]):
        return True
    if subcommand != "config" or any(arg in CONFIG_READS for arg in args[index + 1:]):
        return False
    operands = [arg for arg in args[index + 1:] if not arg.startswith("-")]
    key = next((i for i, arg in enumerate(operands) if arg.lower() == "core.hookspath"), None)
    return key is not None and key + 1 < len(operands)


def hook_bypass(cmd, _entry):
    if cmd.name != "git":
        return False
    if any(w.upper() == "HUSKY=0" for w in cmd.assignments):
        return True
    index, subcommand = git_subcommand(cmd.args)
    if sets_hooks_path(cmd.args, index, subcommand):
        return True
    options = git_options(cmd.args[index + 1:])
    return "--no-verify" in options or (subcommand == "commit" and commit_skips_hooks(options))


def is_local_script(word, programs):
    if word in programs or word.rpartition("/")[2] in programs:
        return True
    return not any(part in word for part in INSTALLED_DIRS) and word.endswith(SCRIPT_SUFFIXES)


def script_and_args(cmd):
    """(script word, its arguments) for `./x.sh a` and `python3 x.py a`; ('', []) otherwise."""
    if cmd.name in INTERPRETERS:
        index = next((i for i, arg in enumerate(cmd.args) if not arg.startswith("-")), None)
        return (cmd.args[index], cmd.args[index + 1:]) if index is not None else ("", [])
    return cmd.word, cmd.args


def expand(word, variables):
    """The word with each $NAME and ${NAME} replaced by its latest value in `variables`; unknown names stay."""
    values = dict(variable.split("=", 1) for variable in variables)
    return VARIABLE.sub(lambda match: values.get(match.group(1) or match.group(2), match.group(0)), word)


def help_probe(cmd, entry):
    script, args = script_and_args(cmd)
    probed = "--help" in args or args == ["-h"]  # `-h host` is an option with a value, not a probe
    if not (probed and script):
        return False
    resolved = expand(script, cmd.variables)
    if cmd.name in INTERPRETERS and VARIABLE.fullmatch(resolved):
        before = cmd.args[cmd.args.index(script) - 1] if cmd.args.index(script) else ""
        return before not in CODE_OR_MODULE  # an unknown script, unless it is `-c "$CODE"` or `-m "$MODULE"`
    return is_local_script(resolved, entry.get("programs") or [])


def secret_in_message(cmd, entry):
    programs = entry.get("programs") or []
    script, args = script_and_args(cmd)
    if not any(p in (script, script.rpartition("/")[2], cmd.name) for p in programs if p):
        return False
    from ledger_store import find_secret  # imported here: most commands never reach it
    return bool(find_secret(" ".join(args)))


BUILT_IN = {"pgrep-wait-loop": pgrep_wait_loop, "hook-bypass": hook_bypass, "help-probe": help_probe,
            "secret-in-message": secret_in_message, "rerun-after-red": rerun_after_red,
            "pipe-exit": lambda cmd, entry: False,  # judged on the whole command: see pipe_exit
            "calendar": lambda cmd, entry: False}  # judged on the text a call sends: see calendar_hit
WHOLE_COMMAND = frozenset(("pipe-exit", "calendar"))


def custom_match(cmd, entry):
    programs = entry["program"] if isinstance(entry["program"], list) else [entry["program"]]
    if cmd.name not in programs:
        return False
    if "subcommand" in entry:
        found = git_subcommand(cmd.args)[1] if cmd.name == "git" else next(
            (a for a in cmd.args if not a.startswith("-")), None)
        if found != entry["subcommand"]:
            return False
    if entry.get("in_loop") and not cmd.in_loop:
        return False
    wanted = entry.get("args_any")
    if wanted and not any(arg in cmd.args or (re.match(r"^-[A-Za-z]$", arg) and has_option(cmd.args, arg[1]))
                          for arg in wanted):
        return False
    assignments = entry.get("assignments_any")
    return not assignments or any(a in cmd.assignments for a in assignments)


def text_list(value):
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item for item in value)


def validate(entry, where):
    """Raise RegistryError when one registry entry does not follow the format."""
    if not isinstance(entry, dict):
        raise RegistryError(f"{where}: an entry is not an object")
    if "min_version" in entry and not valid_min_version(entry["min_version"]):
        raise RegistryError(f"{where}: min_version must be a version such as 1.10.0")
    lesson = entry.get("lesson")
    if lesson is not None and not (isinstance(lesson, str) and LESSON_ID.fullmatch(lesson)):
        raise RegistryError(f"{where}: lesson {lesson!r} is not a lesson id such as L012 or G003")
    reason = entry.get("reason")
    if reason is not None and not (isinstance(reason, str) and reason.strip()):
        raise RegistryError(f"{where}: reason must be non-empty text")
    if "program" in entry:
        unknown = set(entry) - CUSTOM_KEYS
        if unknown or not lesson or not reason:
            raise RegistryError(f"{where}: a rule of your own needs lesson, reason and program"
                                + (f"; unknown keys {sorted(unknown)}" if unknown else ""))
        program = entry["program"]
        names = [program] if isinstance(program, str) else program
        if not text_list(names) or any("/" in name for name in names):
            raise RegistryError(f"{where}: program must be a name or a list of names, without a directory")
        for key in ("args_any", "assignments_any"):
            if key in entry and not text_list(entry[key]):
                raise RegistryError(f"{where}: {key} must be a list of words")
        if "subcommand" in entry and not (isinstance(entry["subcommand"], str) and entry["subcommand"]):
            raise RegistryError(f"{where}: subcommand must be a word")
        if "in_loop" in entry and not isinstance(entry["in_loop"], bool):
            raise RegistryError(f"{where}: in_loop must be true or false")
        return
    unknown = set(entry) - ENTRY_KEYS
    if not isinstance(entry.get("rule"), str) or entry["rule"] not in BUILT_IN or unknown:
        raise RegistryError(f"{where}: rule must be one of {sorted(BUILT_IN)} (or give program for a rule of your "
                            "own)" + (f"; unknown keys {sorted(unknown)}" if unknown else ""))
    if "enabled" in entry and not isinstance(entry["enabled"], bool):
        raise RegistryError(f"{where}: enabled must be true or false")
    if "programs" in entry and (entry["rule"] not in TAKES_PROGRAMS or not text_list(entry["programs"])):
        raise RegistryError(f"{where}: programs is a list of names, for {', '.join(TAKES_PROGRAMS)} only")
    if "workweek" in entry:
        if entry["rule"] != "calendar":
            raise RegistryError(f"{where}: workweek is for the calendar rule only")
        try:
            guard_calendar.parse_workweek(entry["workweek"])
        except ValueError as error:
            raise RegistryError(f"{where}: {error}") from None


def valid_min_version(value):
    return isinstance(value, str) and VERSION_SHAPE.fullmatch(value) is not None


def needs_newer_hook(entry):
    """An entry for a newer hook: skipped quietly, before the rest of it is judged (its rule may not exist here)."""
    value = entry.get("min_version") if isinstance(entry, dict) else None
    return HOOK_VERSION is not None and valid_min_version(value) and version_tuple(value) > HOOK_VERSION


def read_registry(path):
    """(entries this hook applies, problems): a bad entry is skipped with a problem line, a file that does not parse
    gives no entries, and an entry asking for a newer hook (min_version) is skipped without one."""
    try:
        if os.path.getsize(path) > REGISTRY_MAX_BYTES:
            return [], [f"{path}: skipped, larger than {REGISTRY_MAX_BYTES} bytes"]
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, RecursionError) as error:
        return [], [f"{path}: skipped, {type(error).__name__}: {error}"]
    if not isinstance(data, dict) or not isinstance(data.get("guards"), list) or set(data) - {"guards"}:
        return [], [f'{path}: skipped, expected {{"guards": [...]}}']
    entries, problems = [], []
    for index, entry in enumerate(data["guards"]):
        where = f"{path} entry {index + 1}"
        try:
            if needs_newer_hook(entry):
                continue
            validate(entry, where)
        except RegistryError as error:
            problems.append(f"{error} (entry skipped)")
            continue
        except Exception as error:  # any fault in one entry skips that entry only, never the hook
            problems.append(f"{where}: {type(error).__name__}: {error} (entry skipped)")
            continue
        entries.append(entry)
    return entries, problems


def registry_problems(cwd):
    """Every problem line of the registries that apply in cwd; empty when all entries are usable."""
    return [problem for path in registry_paths(cwd) for problem in read_registry(path)[1]]


def registry_paths(cwd, home=None, project=None):
    """[global registry, project registry], each only when it exists. home replaces ~, and project replaces
    $CLAUDE_PROJECT_DIR and cwd as the search start (both for checks run on behalf of another place)."""
    found = []
    global_file = os.environ.get(GLOBAL_ENV) or os.path.join(home or os.path.expanduser("~"), ".agents",
                                                             "lesson-guards.json")
    if os.path.isfile(global_file):
        found.append(global_file)
    folder = os.path.abspath(project or os.environ.get("CLAUDE_PROJECT_DIR") or cwd)
    while True:
        path = os.path.join(folder, PROJECT_FILE)
        if os.path.isfile(path):
            if os.path.abspath(path) != os.path.abspath(global_file):
                found.append(path)
            return found
        parent = os.path.dirname(folder)
        if parent == folder:
            return found
        folder = parent


def rules(cwd):
    """[(rule name, entry, matcher)]: built-in rules merged with the registries (project last, so it wins)."""
    built_in = {name: {"rule": name} for name in BUILT_IN if name not in OPT_IN}
    custom = []
    for path in registry_paths(cwd):
        for entry in read_registry(path)[0]:
            if "program" in entry:
                custom.append((entry.get("lesson"), entry, custom_match))
            else:
                built_in[entry["rule"]] = {**built_in.get(entry["rule"], {}), **entry}
    return [(name, entry, BUILT_IN[name]) for name, entry in built_in.items()
            if entry.get("enabled", True)] + custom


CONDITION_WORDS = frozenset(("if", "elif", "while", "until", "!"))
GROUP_WORDS = frozenset(("then", "do", "else", "{", "}"))
CHAIN_OPERATORS = frozenset(("&&", "||"))
LIST_ENDS = frozenset((";", "\n", "&", ";;"))
OPERATOR = re.compile(r"\|\||&&|\|&|;;|\||;|&|\(|\)|\n")
STATUS_READ = re.compile(r"\$(?:\?|\{\?\})")
PIPESTATUS_READ = re.compile(r"\$\{?PIPESTATUS\b")


def operators(word):
    """The shell operators a token holds ('&&\n' is && then a newline), or None for an ordinary word."""
    if word.strip(" \t") and set(word) <= set("|&;()\n \t"):
        return OPERATOR.findall(word)
    return None


def list_items(command):
    """The command as an ordered list of items, each {"stages": [word lists], "op": the operator after it,
    "condition": the item is the condition of if/elif/while/until/!}. An item with no stages is an empty list entry,
    such as the `&&` after a `{ ...; }` group or a `( ... )` subshell."""
    items, stages, current, condition, depth = [], [], [], False, 0

    def close(op):
        nonlocal stages, current, condition
        if current:
            stages.append(current)
        items.append({"stages": stages, "op": op, "condition": condition})
        stages, current, condition = [], [], False

    for word in shell.tokens(shell.split_heredocs(command)[0]) + [";"]:
        ops = operators(word)
        if ops is None:
            if word in ("{", "}") and not stages:
                current = []  # a group or function body opens or closes: what came before is not this command
                continue
            if not stages and not current and word in CONDITION_WORDS:
                condition = True
            elif not stages and not current and word in GROUP_WORDS:
                condition = False
            else:
                current.append(word)
            continue
        for op in ops:
            if op in ("|", "|&"):
                if current:
                    stages.append(current)
                current = []
            elif op == "\n" and (stages and not current):
                continue  # a newline after a pipe continues the pipeline
            elif op == "(":
                depth += 1
            elif op == ")":
                if depth:
                    depth -= 1  # the end of a subshell or of $(...): its words stay in this item
                else:
                    current = []  # the end of a case pattern: the pattern is not a command
            else:
                close(op)
    return items


def set_pipefail(words, state):
    """The pipefail state after a `set` command (set -o pipefail, set -euo pipefail, set +o pipefail)."""
    if not words or words[0] != "set" or "pipefail" not in words:
        return state
    at = words.index("pipefail")
    flag = words[at - 1] if at else ""
    if re.fullmatch(r"-[a-zA-Z]*o", flag):
        return True
    if re.fullmatch(r"\+[a-zA-Z]*o", flag):
        return False
    return state


def pipe_exit(command, is_check, depth=0):
    """True when a check or a local script feeds a later command and the pipeline's exit status is acted on (&&, ||,
    if/elif/while/until/!, a group or subshell ending in it that is acted on, or $? read by the next command), with
    no pipefail turned on earlier in the same shell and no ${PIPESTATUS[...]} read after it. The script of sh -c and
    eval is judged as its own shell."""
    def runs_check(stage):
        text = " ".join(stage)
        parsed = commands(text)
        script = script_and_args(parsed[0])[0] if parsed else ""
        return bool(is_check and is_check(text)) or (bool(script) and is_local_script(script, []))

    items = list_items(command)
    pipefail, pending = False, None
    for index, item in enumerate(items):
        stages = item["stages"]
        later = [word for rest in items[index + 1:] for stage in rest["stages"] for word in stage]
        if pending is not None:  # the pipeline before this item, ended by ; or a newline or &
            if (stages and any(STATUS_READ.search(word) for word in stages[0])) or \
                    (not stages and item["op"] in CHAIN_OPERATORS):
                return True
            if stages:
                pending = None
        if len(stages) == 1:
            pipefail = set_pipefail(stages[0], pipefail)
        if len(stages) < 2 or pipefail or any(PIPESTATUS_READ.search(word) for word in later):
            continue
        if not (any(runs_check(stage) for stage in stages[:-1]) and not runs_check(stages[-1])):
            continue
        if item["op"] in CHAIN_OPERATORS or item["condition"]:
            return True
        if item["op"] in LIST_ENDS:
            pending = item
    if depth < MAX_DEPTH:
        for argv, _piped, _heredoc in shell.simple_commands(shell.split_heredocs(command)[0]):
            name, args = shell.program(argv)
            script = ""
            if name in shell.SHELLS:
                flag = next((i for i, arg in enumerate(args) if re.match(r"^-[a-z]*c$", arg)), None)
                script = args[flag + 1] if flag is not None and flag + 1 < len(args) else ""
            elif name == "eval":
                script = " ".join(args)
            if script and pipe_exit(script, is_check, depth + 1):
                return True
    return False


def today():
    """Today's date; $ARSENAL_NOW (an ISO date or time) replaces the clock for tests."""
    value = os.environ.get("ARSENAL_NOW")
    try:
        return dt.datetime.fromisoformat(value).date() if value else dt.date.today()
    except ValueError:
        return dt.date.today()


def calendar_hit(entry, texts):
    """Hit for the calendar rule when the outbound texts hold a calendar mistake; None otherwise."""
    if not texts:
        return None
    workweek = guard_calendar.parse_workweek(entry["workweek"]) if "workweek" in entry else None
    found = [problem for text in texts for problem in guard_calendar.problems(text, today(), workweek)]
    if not found:
        return None
    reason = entry.get("reason") or BUILT_IN_REASONS["calendar"].replace("{problems}", "; ".join(dict.fromkeys(found)))
    return Hit(entry.get("lesson"), "calendar", reason)


def judge_outbound(tool_name, tool_input, cwd):
    """The calendar rule for a tool other than Bash that sends text to people (an MCP send, reply, comment, post,
    draft, create or update); None for every other tool or when it is clean or switched off."""
    entry = next((entry for name, entry, _ in rules(cwd) if name == "calendar"), None)
    if entry is None:
        return None
    return calendar_hit(entry, guard_calendar.outbound_texts(tool_name, tool_input, entry.get("programs") or [],
                                                            shell))


def judge(command, cwd, session=None, is_check=None):
    """The first rule the command breaks, as Hit(lesson id or None, rule name, reason); None when it breaks none.
    session: a function returning {"red": failed check and push keys, "keys": the command's check keys}, called only
    by a rule that needs it. is_check: a function telling whether a command text runs a test, build, lint or CI
    check (guard.py passes its own); without it only local scripts count as checks for pipe-exit. A registry problem
    never raises: the entry is skipped (registry_problems lists it)."""
    if not isinstance(command, str) or not command.strip():
        return None
    active = rules(cwd)
    for name, entry, _ in active:
        if name == "pipe-exit" and pipe_exit(command, is_check):
            return Hit(entry.get("lesson"), name, entry.get("reason") or BUILT_IN_REASONS[name])
        if name == "calendar":
            hit = calendar_hit(entry, guard_calendar.outbound_texts("Bash", {"command": command},
                                                                    entry.get("programs") or [], shell))
            if hit:
                return hit
    active = [rule for rule in active if rule[0] not in WHOLE_COMMAND]
    state = []
    for cmd in commands(command):
        for name, entry, matcher in active:
            if name == "rerun-after-red" and session:
                state = state or [session()]
                entry = {**entry, "session": lambda: state[0]}
            if matcher(cmd, entry):
                return Hit(entry.get("lesson"), name, entry.get("reason") or BUILT_IN_REASONS[name])
    return None
