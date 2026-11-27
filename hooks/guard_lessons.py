#!/usr/bin/env python3
"""Refuse a Bash command that repeats a recorded lesson, for guard.py's PreToolUse hook (Claude Code plugin).

Usage: hit = guard_lessons.judge(command, cwd)  # None, or Hit(lesson, rule, reason)
       hit = guard_lessons.judge_outbound(tool_name, tool_input, cwd)  # a tool other than Bash that sends text
       Both take transcript=<the hook input's transcript_path> and agent_id=<its agent_id> for the unseen-hash and
       typed-sha rules (default None: without a transcript unseen-hash passes, typed-sha checks short pins only).
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
optionally its first operand (subcommand; for git, after the values of -C, -c, --git-dir and the like; a list such
as ["pr", "merge"] names the leading operands in order, option words and gh's -R/--repo value skipped), any of
`args_any` (exact words; a
single letter such as -f also matches inside a cluster such as -fq), all of `args_all`, none of `args_none` (words
anywhere among the arguments, option values included; a long option also counts when written as --opt=value, but
not with an empty value), any of `assignments_any` (VAR=value words before the program), and `in_loop` (the
command is the condition of while/until). args_all, args_none and a subcommand list need a hook from 1.29.0: give
such an entry "min_version": "1.29.0". Example, merge only a pinned head:
    {"lesson": "G026", "program": "gh", "subcommand": ["pr", "merge"],
     "args_none": ["--match-head-commit", "--disable-auto", "--help", "-h"], "min_version": "1.29.0",
     "reason": "Merge only the head that was reviewed: gh pr merge N --match-head-commit <sha>."}
The shorter form "subcommand": "pr", "args_all": ["merge"] also refuses gh pr list --label merge and
gh pr create --title merge, since args_all reads option values too.
A built-in rule named in both registries takes the project entry. Any entry may carry "min_version": "X.Y.Z", the
oldest hook that should apply it; an older hook skips it, so a registry shared by sessions on different versions
stays usable everywhere. The registry fails
safe per entry: an entry this hook cannot use (unknown rule or key, wrong type) is skipped, and a file that does
not parse is skipped whole, but every other entry and every built-in rule still apply and no command is refused
for it. registry_problems(cwd) lists what was skipped; `lessons.py guards` checks the registries against every
installed hook version, and the session-start lessons header reports skipped entries.
Words are judged after quotes are removed, so `grep "while pgrep -f"`, commit messages and echo text pass;
here-document bodies are dropped; the script of `sh -c` and `eval` is judged too. A $NAME or ${NAME} in the
program or script word is read from an assignment earlier in the same command line (`S=x.py; python3 $S -h`,
`S=./notify.sh; $S team "text"`); a script run by a shell (`bash path/notify.sh`) matches `programs` by its name.
Not seen: names set outside the command line, commands run through xargs, ssh or a script file.
"""
import datetime as dt
import json
import os
import re
from collections import namedtuple
from pathlib import Path

import guard_calendar
import guard_ci_rerun
import guard_container_limits
import guard_destructive as shell
import guard_dry_run_chain
import guard_durable_path
import guard_live_script
import guard_oom
import guard_outer_timeout
import guard_syntax
import guard_timer
import guard_tool_result_read
import guard_typed_sha
import guard_unseen_hash
import guard_unseen_time
import guard_wait_on_text
from guard_lessons_docs import RULES

__doc__ = (__doc__ or "") + RULES  # the per-rule reference lives in guard_lessons_docs.py (file size cap)

Hit = namedtuple("Hit", "lesson rule reason")

PROJECT_FILE = os.path.join(".agents", "lesson-guards.json")
GLOBAL_ENV = "LESSONS_GUARDS_GLOBAL_FILE"
LESSON_ID = re.compile(r"[LG]\d{3,}")  # used with fullmatch
LOOP_WORDS = frozenset(("while", "until"))
INTERPRETERS = frozenset("node python python3 bash sh zsh dash ksh ruby perl deno bun".split())
SCRIPT_SUFFIXES = (".sh", ".bash", ".py", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl")
INSTALLED_DIRS = ("node_modules/", ".venv/", "venv/", "site-packages/")
GH_REPO_OPTIONS = frozenset(("-R", "--repo"))  # gh options whose value comes before a subcommand
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
    "rerun-after-red": "This check, push or CI run failed and was not read. Read the failing lines, state the cause, record it "
                       'with `python3 {lessons} cause "<failing assertion or check>: <cause or unknown>"`, then rerun.',
    "shell-syntax": "The shell cannot parse this command, so none of it was run: {error}. Put free text in a file with "
                    "the Write tool or in a quoted heredoc (<<'EOF'), never inline in single quotes, then run the "
                    "fixed command.",
    "unseen-hash": "Commit hash {hashes} appears in no tool output of this session. Copy each hash from a git/gh "
                   "output of this turn (run `git log -1 --format=%H <ref>` or `gh pr view N --json mergeCommit`), "
                   'never from memory. A word that is not a commit hash: reword it, or add it to the entry\'s "allow" '
                   "list.",
    "unseen-time": "Time {times} appears in no tool output of this session. Copy each time from `date +%H:%M` or from "
                   "the timestamp the API returned (mergedAt, createdAt), in the zone you state, never from memory or "
                   'by converting by hand. A time that is not a past clock time: reword it, or add it to the entry\'s '
                   '"allow" list.',
    "typed-sha": 'Pass the SHA from git in the same command: --match-head-commit "$(git rev-parse HEAD)" or '
                 '--force-with-lease=<ref>:"$(git rev-parse origin/<ref>)"; a typed SHA is refused when it is short '
                 "or was never printed in this session.",
    "oom-first": "{command} exited 134/137, which is usually the kernel or V8 running out of memory, not the change: "
                 "read the kernel log first (journalctl -k --since '-15 min' | grep -i -E 'oom|killed process'), "
                 "compare peak memory, then rerun{timeout}.",
}
OOM_TIMEOUT = ('; or, if it ran out its timeout limit, confirm that with python3 {lessons} cause '
               '"<command>: timeout"')
# off until a registry entry names it
OPT_IN = frozenset(("rerun-after-red", "shell-syntax", "unseen-hash", "typed-sha", "oom-first", "timer-safety",
                    "live-script", "dry-run-chain", "outer-timeout", "wait-on-text", "durable-path", "tool-result-read",
                    "unseen-time", "container-limits"))
ENTRY_KEYS = {"rule", "lesson", "reason", "enabled", "programs", "min_version", "workweek", "exceptions", "approvers",
              "shell", "window_mb", "allow", "guessed_times", "confirm", "hint", "no_queue_env", "paths", "scratch",
              "compose_project"}
TAKES_PROGRAMS = ("help-probe", "secret-in-message", "calendar", "unseen-hash", "unseen-time", "dry-run-chain",
                  "outer-timeout")
CUSTOM_KEYS = {"lesson", "reason", "program", "subcommand", "args_any", "args_all", "args_none", "assignments_any",
               "in_loop", "min_version"}
VERSION_SHAPE = re.compile(r"\d{1,6}\.\d{1,6}\.\d{1,6}", re.ASCII)
REGISTRY_MAX_BYTES = 1_000_000
APPROVED_KEY, EXCEPTIONS_FILE_KEY = "_approved_workdays", "_exceptions_file"  # set by read_registry, never in a file
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


Command = namedtuple("Command", "word name args assignments in_loop variables branch", defaults=((), ()))


def commands(command, depth=0, inherited=(), branches=None):
    """Each simple command as (program word, program name, args, its assignments, in a while/until condition);
    assignments include those exported earlier in the line; the script of sh -c and eval is expanded in place.
    Every command between `while`/`until` and `do` is in the condition (`while kill -0 $p && pgrep -f x; do`).
    variables: the NAME=value words a command's own words expand from, set earlier by a bare assignment or export
    (a prefix assignment, `X=a cmd $X`, is not: the shell expands $X before it assigns).
    branch: the if/case alternatives it sits in (guard_dry_run_chain.Branches)."""
    found, exported, condition = [], list(inherited), False
    variables = list(inherited)
    branches = branches or guard_dry_run_chain.Branches()
    for argv, _piped, _heredoc, *ends in shell.command_runs(shell.split_heredocs(command)[0]):
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
        branch = branches.path(argv, *ends)
        found.append(Command(word, name, args, assignments, condition, expands_from, branch))
        script = ""
        if name in shell.SHELLS and depth < MAX_DEPTH:
            flag = next((i for i, arg in enumerate(args) if re.match(r"^-[a-z]*c$", arg)), None)
            script = args[flag + 1] if flag is not None and flag + 1 < len(args) else ""
        elif name == "eval" and depth < MAX_DEPTH:
            script = " ".join(args)
        if script:
            found.extend(commands(script, depth + 1, assignments, guard_dry_run_chain.Branches(branch)))  # HUSKY=0 bash -c '...'
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
    return bool((state["keys"] | {push_key(cmd)}) & state["red"]) or (
        cmd.name == "gh" and guard_ci_rerun.refused(cmd.args, state.get("events") or []))


def typed_sha(command, transcript, agent_id):
    """A SHA typed into gh pr merge --match-head-commit or a git push lease; see guard_typed_sha."""
    if "--match-head-commit" not in command and "--force-with-lease" not in command:  # no second parse for the rest
        return False
    found = [(cmd.name, leading_operands(cmd), cmd.args, cmd.variables)
             for cmd in commands(guard_typed_sha.plain_quotes(command)) if cmd.name in ("gh", "git")]
    return guard_typed_sha.refused(found, transcript, agent_id)


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


def is_git_commit(cmd):
    """A git commit that commits: a hook may refuse it, and a filtered pipe hides that. --dry-run commits nothing."""
    if cmd.name != "git":
        return False
    index, subcommand = git_subcommand(cmd.args)
    return subcommand == "commit" and "--dry-run" not in git_options(cmd.args[index + 1:])


def is_local_script(word, programs):
    if word in programs or word.rpartition("/")[2] in programs:
        return True
    return not any(part in word for part in INSTALLED_DIRS) and word.endswith(SCRIPT_SUFFIXES)


def script_and_args(cmd):
    """(script word, its arguments) for `./x.sh a`, `python3 x.py a` and `bash -o pipefail x.sh a` (a shell's -o, -O,
    --rcfile value is not the script); ('', []) otherwise."""
    if cmd.name not in INTERPRETERS:
        return cmd.word, cmd.args
    is_shell, index = cmd.name in shell.SHELLS, 0
    while index < len(cmd.args) and (cmd.args[index][:1] in ("-", "+") if is_shell else cmd.args[index][:1] == "-"):
        index += 2 if is_shell and cmd.args[index] in guard_calendar.SHELL_OPTIONS_WITH_VALUE else 1
    return (cmd.args[index], cmd.args[index + 1:]) if index < len(cmd.args) else ("", [])


def run_of(cmd):
    """(program or script basename, its arguments): `./x.sh a`, `python3 x.py a` and `$S a` with S set on the line."""
    behind = guard_dry_run_chain.launched(cmd.name, cmd.args) if cmd.name in guard_dry_run_chain.LAUNCHERS else None
    script, args = behind or script_and_args(cmd)
    return (shell.expand(script, cmd.variables).rpartition("/")[2],
            [shell.expand(arg, cmd.variables) for arg in args], cmd.branch)


def chain_runs(cmds):
    """The runs of a command line for the dry-run-chain rule: the remote command of an ssh call counts as its own."""
    for cmd in cmds:
        remote = guard_timer.ssh_remote(cmd.args) if cmd.name == "ssh" else ""
        if remote:
            yield from map(run_of, commands(remote, MAX_DEPTH - 1, cmd.assignments,
                                            guard_dry_run_chain.Branches(cmd.branch)))
        else:
            yield run_of(cmd)


def help_probe(cmd, entry):
    script, args = script_and_args(cmd)
    probed = "--help" in args or args == ["-h"]  # `-h host` is an option with a value, not a probe
    if not (probed and script):
        return False
    resolved = shell.expand(script, cmd.variables)
    if cmd.name in INTERPRETERS and shell.VARIABLE.fullmatch(resolved):
        before = cmd.args[cmd.args.index(script) - 1] if cmd.args.index(script) else ""
        return before not in CODE_OR_MODULE  # an unknown script, unless it is `-c "$CODE"` or `-m "$MODULE"`
    return is_local_script(resolved, entry.get("programs") or [])


def secret_in_message(cmd, entry):
    programs = entry.get("programs") or []
    script, args = script_and_args(cmd)
    script = shell.expand(script, cmd.variables)  # `S=./notify.sh; $S team "text"`
    if not any(p in (script, script.rpartition("/")[2], cmd.name) for p in programs if p):
        return False
    from ledger_store import find_secret  # imported here: most commands never reach it
    return bool(find_secret(" ".join(args)))


BUILT_IN = {"pgrep-wait-loop": pgrep_wait_loop, "hook-bypass": hook_bypass, "help-probe": help_probe,
            "secret-in-message": secret_in_message, "rerun-after-red": rerun_after_red,
            "pipe-exit": lambda cmd, entry: False,  # judged on the whole command: see pipe_exit
            "calendar": lambda cmd, entry: False,  # judged on the text a call sends: see outbound_hit
            "unseen-hash": lambda cmd, entry: False, "typed-sha": lambda cmd, entry: False,
            "oom-first": lambda cmd, entry: False,  # judged on the whole command against the session: see judge
            "timer-safety": lambda cmd, entry: False,  # judged on the whole command and on unit file writes
            "live-script": lambda cmd, entry: False,  # judged on file writes only: see judge_outbound
            "dry-run-chain": lambda cmd, entry: False,  # judged on the order of the whole command's runs
            "outer-timeout": lambda cmd, entry: False,  # judged on the wrappers of the whole command
            "wait-on-text": lambda cmd, entry: False,  # judged on the conditions of the whole command's loops
            "durable-path": lambda cmd, entry: False,  # judged on the whole command's scheduling and on file writes
            "tool-result-read": lambda cmd, entry: False,  # judged on Read calls only: see judge_outbound
            "unseen-time": lambda cmd, entry: False,  # judged on the text a call sends: see outbound_hit
            "container-limits": lambda cmd, entry: False,  # judged on the whole command's container runs
            "shell-syntax": lambda cmd, entry: False}  # judged on the whole command first: see judge
OUTBOUND = ("calendar", "unseen-hash", "unseen-time")
UNSEEN_RULES = ("unseen-hash", "unseen-time")  # the outbound rules that read the session transcript
WHOLE_COMMAND = frozenset(("pipe-exit", "shell-syntax", "typed-sha", "oom-first", "timer-safety", "live-script",
                           "dry-run-chain", "outer-timeout", "wait-on-text", "durable-path", "tool-result-read", "container-limits") + OUTBOUND)


def has_word(args, word, long_value=False):
    """The exact word, a single letter such as -f inside a cluster (-fq), and with long_value a long option written
    as --opt=value. With long_value, a long option given an empty value (--opt= or --opt "") does not count."""
    if long_value and word.startswith("--"):
        return any((arg == word and args[index + 1:index + 2] != [""])
                   or (arg.startswith(word + "=") and arg != word + "=") for index, arg in enumerate(args))
    return word in args or bool(re.match(r"^-[A-Za-z]$", word) and has_option(args, word[1]))


def leading_operands(cmd):
    """The words that are not options, in order; for git, from the subcommand on (after -C dir and the like); for
    gh, without the value of -R/--repo (gh pr -R o/r merge)."""
    args = cmd.args[git_subcommand(cmd.args)[0]:] if cmd.name == "git" else cmd.args
    takes_value = GH_REPO_OPTIONS if cmd.name == "gh" else ()
    return [arg for index, arg in enumerate(args)
            if not arg.startswith("-") and not (index and args[index - 1] in takes_value)]


def custom_match(cmd, entry):
    programs = entry["program"] if isinstance(entry["program"], list) else [entry["program"]]
    if cmd.name not in programs:
        return False
    if "subcommand" in entry:
        wanted = entry["subcommand"] if isinstance(entry["subcommand"], list) else [entry["subcommand"]]
        if leading_operands(cmd)[:len(wanted)] != wanted:
            return False
    if entry.get("in_loop") and not cmd.in_loop:
        return False
    wanted = entry.get("args_any")
    if wanted and not any(has_word(cmd.args, word) for word in wanted):
        return False
    if not all(has_word(cmd.args, word, True) for word in entry.get("args_all", ())):
        return False
    if any(has_word(cmd.args, word, True) for word in entry.get("args_none", ())):
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
        for key in ("args_any", "args_all", "args_none", "assignments_any"):
            if key in entry and not text_list(entry[key]):
                raise RegistryError(f"{where}: {key} must be a list of words")
        subcommand = entry.get("subcommand")
        if "subcommand" in entry and not ((isinstance(subcommand, str) and subcommand) or text_list(subcommand)):
            raise RegistryError(f"{where}: subcommand must be a word or a list of words")
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
    if "exceptions" in entry:
        if entry["rule"] != "calendar":
            raise RegistryError(f"{where}: exceptions is for the calendar rule only")
        if not (isinstance(entry["exceptions"], str) and entry["exceptions"].strip()):
            raise RegistryError(f"{where}: exceptions must be the path of a workday exceptions file")
    if "approvers" in entry:
        if entry["rule"] != "calendar":
            raise RegistryError(f"{where}: approvers is for the calendar rule only")
        if not (text_list(entry["approvers"]) and all(item.strip() for item in entry["approvers"])):
            raise RegistryError(f"{where}: approvers must be a list of names")
    if "guessed_times" in entry and (entry["rule"] != "calendar" or not isinstance(entry["guessed_times"], bool)):
        raise RegistryError(f"{where}: guessed_times is true or false, for the calendar rule only")
    if "shell" in entry and (entry["rule"] != "shell-syntax" or not isinstance(entry["shell"], str)
                             or entry["shell"] not in guard_syntax.SHELLS):
        raise RegistryError(f"{where}: shell is for the shell-syntax rule only, one of {sorted(guard_syntax.SHELLS)}")
    if "window_mb" in entry:
        if entry["rule"] not in UNSEEN_RULES:
            raise RegistryError(f"{where}: window_mb is for the unseen-hash and unseen-time rules only")
        value = entry["window_mb"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not \
                0 < value <= guard_unseen_hash.MAX_WINDOW_MB:
            raise RegistryError(f"{where}: window_mb must be a number of megabytes above 0, at most "
                                f"{guard_unseen_hash.MAX_WINDOW_MB}")
    if "confirm" in entry and (entry["rule"] != "dry-run-chain" or not guard_dry_run_chain.valid_confirm(
            entry["confirm"])):
        raise RegistryError(f"{where}: confirm is a list of options such as --yes that are not dry-run flags, for "
                            "the dry-run-chain rule only")
    if "hint" in entry and (entry["rule"] != "outer-timeout" or not guard_outer_timeout.valid_hint(entry["hint"])):
        raise RegistryError(f"{where}: hint is one line of text (200 characters at most) naming the tool's own wait "
                            "setting, for the outer-timeout rule only")
    if "no_queue_env" in entry and (entry["rule"] != "outer-timeout"
                                    or not guard_outer_timeout.valid_no_queue_env(entry["no_queue_env"])):
        raise RegistryError(f"{where}: no_queue_env is a list of at most {guard_outer_timeout.MAX_NO_QUEUE_ENV} "
                            "variable names, for the outer-timeout rule only")
    if "paths" in entry and (entry["rule"] not in ("wait-on-text", "tool-result-read")
                             or not guard_wait_on_text.valid_paths(entry["paths"])):
        raise RegistryError(f"{where}: paths is a list of shell globs such as .agents/bus/inbox-*.md, for the "
                            "wait-on-text and tool-result-read rules only")
    if "scratch" in entry and (entry["rule"] != "durable-path" or not guard_durable_path.valid_scratch(entry["scratch"])):
        raise RegistryError(f"{where}: scratch is a list of shell globs for folders that are wiped, such as "
                            "/var/work/tmp-*/**, for the durable-path rule only")
    if "compose_project" in entry and (entry["rule"] != "container-limits"
                                       or not isinstance(entry["compose_project"], bool)):
        raise RegistryError(f"{where}: compose_project is true or false, for the container-limits rule only")
    if "allow" in entry:
        if entry["rule"] not in UNSEEN_RULES + ("container-limits",):
            raise RegistryError(f"{where}: allow is for the unseen-hash, unseen-time and container-limits rules only")
        if not (text_list(entry["allow"]) and all(item.strip() for item in entry["allow"])):
            raise RegistryError(f"{where}: allow must be a list of words that are not commit hashes (unseen-hash), "
                                "times such as 16:36 (unseen-time) or image names (container-limits)")


def valid_min_version(value):
    return isinstance(value, str) and VERSION_SHAPE.fullmatch(value) is not None


def needs_newer_hook(entry):
    """An entry for a newer hook: skipped quietly, before the rest of it is judged (its rule may not exist here)."""
    value = entry.get("min_version") if isinstance(entry, dict) else None
    return HOOK_VERSION is not None and valid_min_version(value) and version_tuple(value) > HOOK_VERSION


class PathTooLong(ValueError):
    """An exceptions path too long to resolve; its message is safe to show."""


class ExceptionSources:
    """The workday exception files read during one read_registry call. Work and output are bounded whatever the
    registry holds: only the first SOURCE_LIMIT distinct raw (exceptions text, approvers) pairs get any path work
    (the others get no exceptions and are counted), and at most PROBLEM_LINE_LIMIT problem lines come from them."""
    SOURCE_LIMIT, PROBLEM_LINE_LIMIT = 20, 50

    def __init__(self):
        self.raw, self.pairs, self.files, self.ignored, self.shown, self.more = {}, {}, {}, set(), 0, 0

    def emit(self, lines, problems):
        """Add problem lines within the limit; count the rest."""
        room = max(self.PROBLEM_LINE_LIMIT - self.shown, 0)
        problems.extend(lines[:room])
        self.shown += min(len(lines), room)
        self.more += max(len(lines) - room, 0)

    @staticmethod
    def path(raw, registry):
        """The file a registry entry names: relative to the registry file's folder; only a leading ~ or ~/ is
        expanded (from $HOME), and ~user is refused rather than looked up."""
        if raw.startswith("~") and raw != "~" and not raw.startswith("~/"):
            raise ValueError("~user paths are not supported")
        return os.path.join(os.path.dirname(os.path.abspath(registry)), os.path.expanduser(raw))

    def approved(self, raw, approvers, registry, problems):
        """(approved dates, file) for one entry; the file's problem lines go to problems, within the limit."""
        key = (raw, approvers)
        if key in self.raw:
            return self.raw[key]
        if len(self.raw) >= self.SOURCE_LIMIT:
            self.ignored.add(key)
            return frozenset(), ""
        try:
            if len(raw) > guard_calendar.MAX_PATH_CHARS:  # realpath is quadratic in a long path: refuse it unread
                raise PathTooLong(f"exceptions path longer than {guard_calendar.MAX_PATH_CHARS} characters")
            if raw.count("/") >= guard_calendar.MAX_PATH_PARTS:
                raise PathTooLong(f"exceptions path has more than {guard_calendar.MAX_PATH_PARTS} components")
            file = self.path(raw, registry)
            real = os.path.realpath(file)
            if (real, approvers) not in self.pairs:  # another spelling of the same file reports it once
                if real not in self.files:
                    self.files[real] = guard_calendar.load_exceptions(file)
                dates, found = guard_calendar.apply_approvers(*self.files[real], approvers, file)
                self.pairs[(real, approvers)] = frozenset(dates)
                self.emit(found, problems)
            result = (self.pairs[(real, approvers)], file)
        except PathTooLong as error:
            self.emit([f"{registry}: {error} (no exceptions apply)"], problems)
            result = (frozenset(), "")
        except Exception as error:  # never lets a bad path fail the registry read; the class name only
            self.emit([f"{registry}: exceptions {repr(guard_calendar.clip(raw))}: {type(error).__name__}"], problems)
            result = (frozenset(), "")
        self.raw[key] = result
        return result

    def summary(self):
        """The lines that say what was left out."""
        lines = []
        if self.ignored:
            lines.append(f"{len(self.ignored)} more calendar exception sources ignored (limit {self.SOURCE_LIMIT})")
        if self.more:
            lines.append(f"{self.more} more calendar exception problem lines (limit {self.PROBLEM_LINE_LIMIT})")
        return lines


def with_exceptions(entry, registry, problems, sources):
    """The calendar entry with its approved workdays read from the exceptions file (a relative path is read from the
    registry file's folder); a bad file adds problem lines and never raises. sources is the call's ExceptionSources:
    entries that share a file and approvers read and report it once."""
    if "exceptions" not in entry or entry.get("enabled") is False:  # a switched-off rule reads nothing
        return entry
    approvers = frozenset(item.strip() for item in entry["approvers"]) if "approvers" in entry else None
    dates, file = sources.approved(entry["exceptions"], approvers, registry, problems)
    return {**entry, APPROVED_KEY: dates, EXCEPTIONS_FILE_KEY: file}


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
    entries, problems, sources = [], [], ExceptionSources()
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
        entries.append(with_exceptions(entry, path, problems, sources))
    return entries, problems + sources.summary()


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


def pipe_exit(command, is_check, depth=0):
    """True when a check or a local script feeds a later command and the pipeline's exit status is acted on (&&, ||,
    if/elif/while/until/!, a group or subshell ending in it that is acted on, or $? read by the next command), with
    no pipefail turned on earlier in the same shell and no ${PIPESTATUS[...]} read after it. The script of sh -c and
    eval is judged as its own shell."""
    def runs_check(stage):
        text = " ".join(stage)
        parsed = commands(text)
        script = script_and_args(parsed[0])[0] if parsed else ""
        return (bool(is_check and is_check(text)) or (bool(script) and is_local_script(script, []))
                or bool(parsed) and is_git_commit(parsed[0]))

    items = list_items(command)
    status_read_after = [False] * len(items)  # a ${PIPESTATUS[...]} read in any later item, found in one pass
    for index in range(len(items) - 2, -1, -1):
        status_read_after[index] = status_read_after[index + 1] or any(
            PIPESTATUS_READ.search(word) for stage in items[index + 1]["stages"] for word in stage)
    pipefail, pending = False, None
    for index, item in enumerate(items):
        stages = item["stages"]
        if pending is not None:  # the pipeline before this item, ended by ; or a newline or &
            if (stages and any(STATUS_READ.search(word) for word in stages[0])) or \
                    (not stages and item["op"] in CHAIN_OPERATORS):
                return True
            if stages:
                pending = None
        if len(stages) == 1:
            pipefail = guard_dry_run_chain.set_pipefail(stages[0], pipefail)
        if len(stages) < 2 or pipefail or status_read_after[index]:
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
    found = [problem for text in texts for problem in guard_calendar.problems(text, today(), workweek, entry.get(APPROVED_KEY, ()),
                                                                  entry.get(EXCEPTIONS_FILE_KEY),
                                                                  entry.get("guessed_times", True))]
    if not found:
        return None
    reason = entry.get("reason") or BUILT_IN_REASONS["calendar"].replace("{problems}", "; ".join(dict.fromkeys(found)))
    return Hit(entry.get("lesson"), "calendar", reason)


def outbound_hit(name, entry, tool_name, tool_input, transcript, agent_id=None):
    """Hit for an outbound rule (calendar, unseen-hash) on the text this call sends; None when it is clean."""
    texts = guard_calendar.outbound_texts(tool_name, tool_input, entry.get("programs") or [], shell,
                                          messages_only=name in UNSEEN_RULES)
    if name == "calendar":
        return calendar_hit(entry, texts)
    check = guard_unseen_time if name == "unseen-time" else guard_unseen_hash
    found = check.unseen(texts, transcript, entry.get("window_mb"), agent_id=agent_id, allow=entry.get("allow"))
    if not found:
        return None
    reason = entry.get("reason") or BUILT_IN_REASONS[name].replace("{hashes}", check.named(found)).replace(
        "{times}", check.named(found))
    return Hit(entry.get("lesson"), name, reason)


def judge_outbound(tool_name, tool_input, cwd, transcript=None, agent_id=None):
    """The outbound rules for a tool other than Bash that sends text to people (SendMessage, or an MCP send, reply,
    comment, post, draft, create or update), timer-safety for a Write, Edit or MultiEdit of a unit file and
    live-script for one of a script a shell runs; None for every other tool or when it is clean or switched off.
    transcript, agent_id: the session transcript path and the subagent id, read by unseen-hash."""
    for name, entry, _ in rules(cwd):
        if name in ("timer-safety", "live-script", "durable-path", "tool-result-read"):
            problem = (guard_timer.file_problem(tool_name, tool_input) if name == "timer-safety"
                       else guard_tool_result_read.problem(tool_name, tool_input, entry) if name == "tool-result-read"
                       else guard_durable_path.file_problem(tool_name, tool_input, entry) if name == "durable-path"
                       else guard_live_script.file_problem(tool_name, tool_input, cwd))
            hit = Hit(entry.get("lesson"), name, entry.get("reason") or problem) if problem else None
        else:
            hit = outbound_hit(name, entry, tool_name, tool_input, transcript, agent_id) if name in OUTBOUND else None
        if hit:
            return hit
    return None


def judge(command, cwd, session=None, is_check=None, transcript=None, agent_id=None):
    """The first rule the command breaks, as Hit(lesson id or None, rule name, reason); None when it breaks none.
    session: a function returning {"red": failed check and push keys, "keys": the command's check keys, "events": the
    session's recorded events and "check_keys": guard.py's check_keys function (oom-first)}, called only by a rule
    that needs it. is_check: a function telling whether a command text runs a test, build, lint or CI check (guard.py
    passes its own); without it only local scripts count as checks for pipe-exit. transcript, agent_id: the session
    transcript path and the subagent id, read by unseen-hash (without a transcript it passes) and typed-sha (without
    one it checks short merge pins only).
    A registry problem never raises: the entry is skipped (registry_problems lists it)."""
    if not isinstance(command, str) or not command.strip():
        return None
    active = rules(cwd)
    syntax = next((entry for name, entry, _ in active if name == "shell-syntax"), None)
    error = guard_syntax.parse_error(command, syntax.get("shell", "bash")) if syntax else None
    if error:  # first: the other rules read the words of a command the shell would split another way
        return Hit(syntax.get("lesson"), "shell-syntax",
                   syntax.get("reason") or BUILT_IN_REASONS["shell-syntax"].replace("{error}", error))
    state = []
    for name, entry, _ in active:
        if name == "oom-first" and session:
            state = state or [session()]
            failed = guard_oom.armed(command, state[0])
            if failed:
                return Hit(entry.get("lesson"), name, entry.get("reason") or BUILT_IN_REASONS[name].replace(
                    "{timeout}", OOM_TIMEOUT if failed[1] else "").replace("{command}", failed[0]))
        if name in ("timer-safety", "dry-run-chain", "outer-timeout"):
            problem = (guard_timer.bash_problem(commands(command), commands) if name == "timer-safety"
                       else guard_outer_timeout.problem(command, entry) if name == "outer-timeout"
                       else guard_dry_run_chain.problem(chain_runs(commands(command)), entry))
            if problem:
                return Hit(entry.get("lesson"), name, entry.get("reason") or problem)
        if name in ("wait-on-text", "durable-path", "container-limits"):
            problem = {"wait-on-text": guard_wait_on_text, "durable-path": guard_durable_path,
                       "container-limits": guard_container_limits}[name].problem(command, entry, commands)
            if problem:
                return Hit(entry.get("lesson"), name, entry.get("reason") or problem)
        if ((name == "pipe-exit" and pipe_exit(command, is_check))
                or (name == "typed-sha" and typed_sha(command, transcript, agent_id))):
            return Hit(entry.get("lesson"), name, entry.get("reason") or BUILT_IN_REASONS[name])
        if name in OUTBOUND:
            hit = outbound_hit(name, entry, "Bash", {"command": command}, transcript, agent_id)
            if hit:
                return hit
    active = [rule for rule in active if rule[0] not in WHOLE_COMMAND]
    for cmd in commands(command):
        for name, entry, matcher in active:
            if name == "rerun-after-red" and session:
                state = state or [session()]
                entry = {**entry, "session": lambda: state[0]}
            if matcher(cmd, entry):
                return Hit(entry.get("lesson"), name, entry.get("reason") or BUILT_IN_REASONS[name])
    return None
