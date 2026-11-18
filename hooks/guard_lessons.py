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
project entry. A registry that cannot be read or does not follow the format is reported as the reason for
refusing every Bash command until it is fixed (an Edit fixes it), so a typo cannot silently drop a guard.
Words are judged after quotes are removed, so `grep "while pgrep -f"`, commit messages and echo text pass;
here-document bodies are dropped; the script of `sh -c` and `eval` is judged too. Not seen: commands built
from variables, run through xargs, ssh or a script file.
Built-in rules:
  pgrep-wait-loop    while/until pgrep -f: the pattern matches the waiting shell's own command line, so the loop
                     never ends. Wait on a recorded pid ($!), a lock file or a completion notice.
  hook-bypass        git --no-verify, git commit -n, setting core.hooksPath, git run with HUSKY=0 (on the
                     command or exported earlier in the same command line).
  help-probe         a script (a known suffix such as .sh or .py, run directly or through an interpreter, or a
                     command named in `programs`) run with --help, or with -h as its only argument: it may not parse
                     the flag and run for real.
  secret-in-message  a secret-looking value in the arguments of a command named in `programs` (none by default).
  rerun-after-red    off until a registry entry names it. A test, build, lint or check command (the same check as the
                     Stop gate counts: tool and subcommand, flags and wrappers ignored) or a `git push` (same
                     operands) that failed last in this session and has no later pass, run again before a cause note
                     (`lessons.py cause "<assertion or check>: <cause or unknown>"`) was recorded after the failure.
Also not seen: a pgrep inside a quoted "$(...)" in a loop condition or in the loop body (`while true; do pgrep -f x
|| break; done`), and a here-document fed to a shell
(`bash <<EOF`), whose body is dropped as data.
Time budget: string work and at most a few stat calls and two small file reads per Bash call.
"""
import json
import os
import re
from collections import namedtuple

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
    "rerun-after-red": "This check or push failed and was not read. Read the failing lines, state the cause, record it "
                       'with `python3 {lessons} cause "<failing assertion or check>: <cause or unknown>"`, then rerun.',
}
OPT_IN = frozenset(("rerun-after-red",))  # off until a registry entry names it
ENTRY_KEYS = {"rule", "lesson", "reason", "enabled", "programs"}
TAKES_PROGRAMS = ("help-probe", "secret-in-message")
CUSTOM_KEYS = {"lesson", "reason", "program", "subcommand", "args_any", "assignments_any", "in_loop"}


class RegistryError(ValueError):
    """A registry file that cannot be used; the message names the file and the fault."""


Command = namedtuple("Command", "word name args assignments in_loop")


def commands(command, depth=0, inherited=()):
    """Each simple command as (program word, program name, args, its assignments, in a while/until condition);
    assignments include those exported earlier in the line; the script of sh -c and eval is expanded in place.
    Every command between `while`/`until` and `do` is in the condition (`while kill -0 $p && pgrep -f x; do`)."""
    found, exported, condition = [], list(inherited), False
    for argv, _piped, _heredoc in shell.simple_commands(shell.split_heredocs(command)[0]):
        name, args = shell.program(argv)
        prefix = argv[:len(argv) - len(args) - 1] if name else argv
        word = argv[len(prefix)] if name else ""
        if "do" in prefix:
            condition = False
        if any(w in LOOP_WORDS for w in prefix):
            condition = True
        if name == "export":
            exported += [arg for arg in args if shell.ASSIGNMENT.match(arg)]
        assignments = exported + [w for w in prefix if shell.ASSIGNMENT.match(w)]
        found.append(Command(word, name, args, assignments, condition))
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


def help_probe(cmd, entry):
    script, args = script_and_args(cmd)
    probed = "--help" in args or args == ["-h"]  # `-h host` is an option with a value, not a probe
    return probed and bool(script) and is_local_script(script, entry.get("programs") or [])


def secret_in_message(cmd, entry):
    programs = entry.get("programs") or []
    script, args = script_and_args(cmd)
    if not any(p in (script, script.rpartition("/")[2], cmd.name) for p in programs if p):
        return False
    from ledger_store import find_secret  # imported here: most commands never reach it
    return bool(find_secret(" ".join(args)))


BUILT_IN = {"pgrep-wait-loop": pgrep_wait_loop, "hook-bypass": hook_bypass, "help-probe": help_probe,
            "secret-in-message": secret_in_message, "rerun-after-red": rerun_after_red}


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
    if entry.get("rule") not in BUILT_IN or unknown:
        raise RegistryError(f"{where}: rule must be one of {sorted(BUILT_IN)} (or give program for a rule of your "
                            "own)" + (f"; unknown keys {sorted(unknown)}" if unknown else ""))
    if "enabled" in entry and not isinstance(entry["enabled"], bool):
        raise RegistryError(f"{where}: enabled must be true or false")
    if "programs" in entry and (entry["rule"] not in TAKES_PROGRAMS or not text_list(entry["programs"])):
        raise RegistryError(f"{where}: programs is a list of names, for {' and '.join(TAKES_PROGRAMS)} only")


def read_registry(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise RegistryError(f"{path}: {error}") from None
    if not isinstance(data, dict) or not isinstance(data.get("guards"), list) or set(data) - {"guards"}:
        raise RegistryError(f'{path}: expected {{"guards": [...]}}')
    for index, entry in enumerate(data["guards"]):
        validate(entry, f"{path} entry {index + 1}")
    return data["guards"]


def registry_paths(cwd):
    """[global registry, project registry], each only when it exists."""
    found = []
    global_file = os.environ.get(GLOBAL_ENV) or os.path.join(os.path.expanduser("~"), ".agents", "lesson-guards.json")
    if os.path.isfile(global_file):
        found.append(global_file)
    folder = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or cwd)
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
        for entry in read_registry(path):
            if "program" in entry:
                custom.append((entry.get("lesson"), entry, custom_match))
            else:
                built_in[entry["rule"]] = {**built_in.get(entry["rule"], {}), **entry}
    return [(name, entry, BUILT_IN[name]) for name, entry in built_in.items()
            if entry.get("enabled", True)] + custom


def judge(command, cwd, session=None):
    """The first rule the command breaks, as Hit(lesson id or None, rule name, reason); None when it breaks none.
    session: a function returning {"red": failed check and push keys, "keys": the command's check keys}, called only
    by a rule that needs it. Raises RegistryError when a registry file is unusable."""
    if not isinstance(command, str) or not command.strip():
        return None
    active = rules(cwd)
    state = []
    for cmd in commands(command):
        for name, entry, matcher in active:
            if name == "rerun-after-red" and session:
                state = state or [session()]
                entry = {**entry, "session": lambda: state[0]}
            if matcher(cmd, entry):
                return Hit(entry.get("lesson"), name, entry.get("reason") or BUILT_IN_REASONS[name])
    return None
