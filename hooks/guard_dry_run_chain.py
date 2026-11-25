#!/usr/bin/env python3
"""A dry run and its real run chained in one Bash command, for guard_lessons' opt-in `dry-run-chain` rule.

Usage: problem = guard_dry_run_chain.problem(runs, entry)  # runs: (program or script basename, arguments[, branch])
       ok = guard_dry_run_chain.valid_confirm(value)       # a registry "confirm" value this rule can use
Returns the refusal text, which names the fix, or None. Never raises: any error passes the command.
A dry run and the real run chained with ;, && or || in one call run back to back, so the real run goes ahead even
when the dry run refused or printed a problem nobody read. The fix: run the dry run alone, read its line, then the
real run as a separate call.
A run is one simple command whose program, or the script an interpreter runs, has a basename in the entry's
"programs" (exact, suffix included; none by default, so nothing is judged). It is a dry run when it carries a
dry-run flag (--dry-run, --check; --dry-run=false is not one, and a confirm flag set to false, --apply=false, is not a confirm) or no confirm flag, and a real run when it carries a
confirm flag and no dry-run flag. A lone -n never turns a run that carries a confirm flag into a dry run (-n often
means a namespace or a name); a status, list, wait, view or help call is neither.
Runs behind npx, pnpm/yarn/npm (exec, run or a script name), xargs, `.`/source and the remote command of ssh are
read as the program they launch. A dry run and a real run that name different operands or --option=value targets
(merge 1 --dry-run; merge 2 --yes) are different subjects and pass; an operand that is a variable not set on the
line may be the same subject and does not.
Runs in different alternatives of one if/elif/else or case never run together and are not a chain.
Confirm flags are the entry's "confirm" list (it replaces the default --yes, --apply, --confirm, --force); a long
flag also counts as --flag=value, a single letter also inside a cluster (-vy). Words after `--` are operands.
Refused: a real run of a program after a dry run of the same program in the same command.
String work only: no file, process or network access.
Standard library only.
"""
import itertools
import re

CONFIRM = ("--yes", "--apply", "--confirm", "--force")
DRY = ("--dry-run", "-n", "--check")
CLUSTER = re.compile(r"-[A-Za-z]{2,3}")  # single-letter options written together: -vy (-name is a word, not a cluster)
FALSE_VALUES = ("false", "0", "no", "off")
INFO_FLAGS = ("--help", "-h", "--version", "--list", "--status")
INFO_WORDS = ("status", "list", "help", "show", "version", "wait", "view", "watch", "get", "describe", "logs", "info")
RUN_MODES = ("run", "run-script")
LAUNCHERS = {  # launcher: (words before the program that name its mode, its options that take a value, a bare word is
    # the program)
    "npx": (None, ("-p", "--package", "-c"), False), "bunx": (None, (), False),
    "pnpm": (("exec", "dlx", "x") + RUN_MODES, ("-C", "--dir", "--filter", "-F"), True),
    "yarn": (("exec", "dlx", "run"), ("--cwd",), True),
    "npm": (("exec", "x") + RUN_MODES, ("--prefix", "-C", "-w", "--workspace"), False),
    "xargs": (None, ("-n", "-I", "-P", "-L", "-d", "-E", "-s", "-a", "-l", "-i"), False),
    "source": (None, (), False), ".": (None, (), False)}
LEADING = ("then", "do", "while", "until", "!", "{")  # words that may sit before a command or after if/else
CONSTRUCT_IDS = itertools.count(1)  # one id per if or case, unique across every command line judged
FIX = "Run the dry run alone, read its line, then the real run as a separate call."


def skip_options(words, takes_value):
    while words and words[0].startswith("-"):
        words = words[2:] if words[0] in takes_value else words[1:]
    return words


def launched(name, args):
    """(program basename, its arguments) behind npx, pnpm exec/run, xargs or source; None when no program follows."""
    modes, takes_value, bare = LAUNCHERS[name]
    words, mode = skip_options(list(args), takes_value), None
    if modes:
        if words and words[0] in modes:
            mode, words = words[0], skip_options(words[1:], takes_value)
        elif not bare:
            return None
    if not words:
        return None
    rest = words[1:]
    if mode in RUN_MODES and rest[:1] == ["--"]:
        rest = rest[1:]  # `npm run deploy -- --dry-run`: the options after -- are the script's
    return words[0].rpartition("/")[2], rest


class Branches:
    """Where each command sits among the if/elif/else and case alternatives of one command line: a path of
    (construct id, alternative number) pairs, outermost first. Feed it each command in order."""

    def __init__(self, base=()):
        """base: the path of the script's own command, for the commands of an sh -c, eval or ssh script."""
        self.base, self.levels = tuple(base), []

    def path(self, argv, starts_case_branch):
        if starts_case_branch and self.levels:
            self.levels[-1][1] += 1
        for word in argv:
            if word in ("if", "case"):
                self.levels.append([next(CONSTRUCT_IDS), 0])
            elif word in ("elif", "else"):
                if self.levels:
                    self.levels[-1][1] += 1
            elif word in ("fi", "esac"):
                if self.levels:
                    self.levels.pop()
            elif word not in LEADING:
                break
        return self.base + tuple(map(tuple, self.levels))


def alternatives(first, second):
    """True when two branch paths take different alternatives of the same if or case."""
    for (one, one_alt), (other, other_alt) in zip(first, second):
        if one != other:
            return False
        if one_alt != other_alt:
            return True
    return False


def carries(args, flag):
    """True when the options before `--` hold flag: alone, as --flag=value (not a false value), or a single letter
    inside a cluster."""
    for arg in args:
        if arg == "--":
            return False
        if arg == flag:
            return True
        if flag.startswith("--") and arg.startswith(flag + "="):
            if arg[len(flag) + 1:].lower() not in FALSE_VALUES:
                return True
        if len(flag) == 2 and flag[1] != "-" and CLUSTER.fullmatch(arg) and flag[1] in arg[1:]:
            return True
    return False


def dry_flag(arg):
    """True for --dry-run or --check, alone or set to a value that is not false."""
    if arg in ("--dry-run", "--check"):
        return True
    for long in ("--dry-run=", "--check="):
        if arg.startswith(long):
            return arg[len(long):].lower() not in FALSE_VALUES
    return False


def is_dry(args):
    for arg in args:
        if arg == "--":
            return False
        if dry_flag(arg):
            return True
    return False


def is_info(args):
    """A status, list, wait or help call: it neither dry-runs nor does the work."""
    operands = [arg for arg in args if not arg.startswith("-")]
    return any(arg in INFO_FLAGS for arg in args) or bool(operands) and operands[0] in INFO_WORDS


def confirm_flag(args, confirm):
    """The first confirm flag a real run carries; None for a dry run."""
    if is_dry(args):
        return None
    return next((flag for flag in confirm if carries(args, flag)), None)


def subject(args, flags):
    """What a run works on: its operands and its --option=value targets (not the dry-run and confirm flags).
    The word after a --option (`--env prod`) is read as that option's value and left out, unless it is the run's
    only operand (`--pr 12` names the target): leaving it out of the subject refuses less."""
    words, values, operands_only, option = set(), set(), False, False
    for arg in args:
        if operands_only or not arg.startswith("-"):
            (values if option else words).add(arg)
        elif arg == "--":
            operands_only = True
        elif arg.startswith("--") and "=" in arg and arg.partition("=")[0] not in flags:
            words.add(arg)
        option = not operands_only and arg.startswith("--") and "=" not in arg and arg not in flags and arg != "--"
    return words or values


def same_subject(first, second):
    """False only when both name targets and none is shared; no target, or a variable, may be anything."""
    unknown = any("$" in word or "`" in word for word in first | second)
    return unknown or not (first and second) or bool(first & second)


def valid_confirm(value):
    """A non-empty list of options (such as --yes or -y) that are not dry-run flags."""
    return isinstance(value, list) and bool(value) and all(
        isinstance(flag, str) and flag.startswith("-") and flag.strip("-") and flag == flag.strip()
        and flag not in DRY for flag in value)


def problem(runs, entry):
    """The refusal for a real run that follows a dry run of the same program in one command; None otherwise."""
    try:
        programs = {name.rpartition("/")[2] for name in entry.get("programs") or ()}
        confirm = entry.get("confirm") or CONFIRM
        dry = {}
        for name, args, *branch in runs:
            if name not in programs:
                continue
            flag, path = confirm_flag(args, confirm), tuple(branch[0]) if branch else ()
            target = subject(args, set(DRY) | set(confirm))
            if flag is None:
                if not is_info(args):
                    dry.setdefault(name, []).append((target, path))
            elif any(same_subject(earlier, target) and not alternatives(before, path)
                     for earlier, before in dry.get(name, ())):
                return (f"`{name}` runs as a dry run and then for real ({flag}) in one command, so the real run goes "
                        f"ahead even when the dry run refused. {FIX}")
    except Exception:  # this rule must never stop a command it cannot judge
        return None
    return None
