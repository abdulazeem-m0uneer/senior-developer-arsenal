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
Not a chain either, because the real run only happens after the dry run's own result was checked: (1) the dry run's
output is captured (NAME=$(dry ...), also piped inside, also in a loop) and the real run sits only in the branch
of an if/elif whose test ([[ ]], [ ], test, grep) reads $NAME, in a case $NAME arm other than the default `*`, or
after a test of $NAME joined by && or | (`echo "$NAME" | grep -q x && real`); the else or default arm (also among joined patterns, `x|*)`), a `;`, a real
run after `||`, a `||` that has an alternative not testing $NAME, a grep whose pattern is $NAME, another variable and a
variable assigned again after the dry run do not count. (2) After `set -o pipefail` (also -eo, -o errexit -o
pipefail; +o turns it off; a set inside an if or ( ), after && or ||, in a pipeline or in the background does not
count) a dry run in a pipeline (`dry | tail -1 && real`, only && between them) reports its own failure to the &&. A
dry run that is not piped is refused as before.
Confirm flags are the entry's "confirm" list (it replaces the default --yes, --apply, --confirm, --force); a long
flag also counts as --flag=value, a single letter also inside a cluster (-vy). Words after `--` are operands.
Refused: a real run of a program after a dry run of the same program in the same command.
String work only: no file, process or network access.
Standard library only.
"""
import itertools
import re
from collections import namedtuple

import guard_destructive as shell

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
CHAIN_IDS = itertools.count(1)  # one id per && or | list, unique across every command line judged
GREPS = frozenset(("grep", "egrep", "fgrep", "rg"))
TEST_WORDS = frozenset(("[", "[[", "test")) | GREPS  # a command that tests its operands
CAPTURE = re.compile(r"(\w+)=\$")  # the word before the ( of NAME=$(...)
# gates and captures hold (variable name, generation): an assignment starts a new generation
Place = namedtuple("Place", "path gates captures chain and_after staged pipefail",
                   defaults=((), frozenset(), frozenset(), 0, False, False, False))
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


def variables(words):
    return frozenset(match[0] or match[1] for word in words for match in shell.VARIABLE.findall(word))


def fed(argv):
    """The variables a command reads as its input: all of them, but for a grep only those after <<< (its other
    operands are a pattern or a file)."""
    if GREPS & set(argv):
        return variables(argv[argv.index("<<<") + 1:]) if "<<<" in argv else frozenset()
    return variables(argv)


def tested(unit):
    """The variables a unit (the commands of one pipeline) reads, when it has a test command."""
    if not any(TEST_WORDS & set(argv) for argv in unit):
        return frozenset()
    return frozenset().union(*(fed(argv) for argv in unit))


def connector(separators):
    """'&&' or '|' when that alone joins a command to the one before it (a newline after it continues the list)."""
    return {"&&": "&&", "|": "|", "|&": "|"}.get(separators.strip("\n"), "")


class Condition:
    """The pipelines of one if/elif test or one &&, ||, | list. The real run depends on the variables every
    alternative of a || tests, or on those any pipeline of an && list tests."""

    def __init__(self):
        self.units, self.ors = [], False

    def add(self, argv, joiner):
        if not joiner:
            self.units, self.ors = [], False
        if joiner == "|" and self.units:
            self.units[-1].append(argv)
        else:
            self.units.append([argv])
        self.ors = self.ors or joiner == "||"

    def gate(self):
        tests = [tested(unit) for unit in self.units]
        if not tests:
            return frozenset()
        return frozenset.intersection(*tests) if self.ors else frozenset().union(*tests)


def joiner(separators):
    """'&&', '||' or '|' when that alone joins a command to the one before it, else ''."""
    return "||" if separators.strip("\n") == "||" else connector(separators)


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


class Level:
    """One open if or case: its current alternative and the variables that alternative runs only on a test of."""

    def __init__(self, is_case):
        self.id, self.alt, self.gate, self.is_case = next(CONSTRUCT_IDS), 0, frozenset(), is_case
        self.subject, self.condition, self.reading, self.awaiting = frozenset(), Condition(), False, False
        self.default, self.joined = False, False

    def next_alternative(self):
        self.alt, self.gate = self.alt + 1, frozenset()

    def read_condition(self, words):
        self.condition, self.reading = Condition(), True
        self.condition.add(list(words), "")

    def close_condition(self):  # the `then` of an if or elif
        if self.reading:
            self.gate, self.reading = self.condition.gate(), False

    def open_case(self, words, closer):  # the words after `case`: the subject, `in`, the first pattern if on this line
        at = words.index("in") if "in" in words else len(words)
        self.subject, self.awaiting = variables(words[:at]), True
        if words[at + 1:]:
            self.choose(words[at + 1:], closer)

    def choose(self, pattern, closer):
        """A case arm; its patterns may be joined by | (`x|*)`). The default pattern `*` runs on no match, so an
        arm that has it is gated on nothing."""
        self.default = (self.default and self.joined) or "*" in pattern
        self.joined = closer.strip("\n") == "|"
        self.awaiting, self.gate = self.joined, frozenset() if self.default else self.subject


class Branches:
    """Where each command sits: among the if/elif/else and case alternatives of one command line, which variables
    those alternatives (and the && / | list it is in) test, which NAME=$(...) it is inside, which && list it is in
    and whether pipefail is on. Feed it each command in order."""

    def __init__(self, base=None):
        """base: the Place of the script's own command, for the commands of an sh -c, eval or ssh script."""
        self.base = base or Place()
        self.levels, self.stack, self.pending, self.pipefail = [], [], None, False
        self.chain, self.condition, self.saved, self.generation = next(CHAIN_IDS), Condition(), [], {}

    def substitutions(self, opener):
        """Track the open NAME=$( ... ) from the separators before a command; None marks any other parenthesis."""
        for position, char in enumerate(opener):
            if char == "(":
                self.stack.append(self.pending if position == 0 else None)
                self.saved.append(self.pipefail)  # a set inside the parentheses ends with them
            elif char == ")" and self.stack:
                self.stack.pop()
                self.pipefail = self.saved.pop()
        self.pending = None

    def alternatives(self, argv, starts_case_branch, opener, closer):
        top = self.levels[-1] if self.levels else None
        if top and starts_case_branch:
            top.alt += 1
        if top and top.reading and argv[0] != "then":
            top.condition.add(argv, joiner(opener))
        if top and top.is_case and (starts_case_branch or top.awaiting):
            top.choose(argv, closer)
        for index, word in enumerate(argv):
            top = self.levels[-1] if self.levels else None
            if word in ("if", "case"):
                level = Level(word == "case")
                self.levels.append(level)
                if level.is_case:
                    level.open_case(argv[index + 1:], closer)
                else:
                    level.read_condition(argv[index + 1:])
            elif word == "elif" and top:
                top.next_alternative()
                top.read_condition(argv[index + 1:])
            elif word == "else" and top:
                top.next_alternative()
            elif word == "then" and top:
                top.close_condition()
            elif word in ("fi", "esac"):
                if top:
                    self.levels.pop()
            elif word not in LEADING:
                break

    def versioned(self, names):
        return frozenset((name, self.generation.get(name, 0)) for name in names)

    def sets_here(self, opener, closer):
        """True when a `set` runs unconditionally in the shell itself: not in an if or case, not a stage of a
        pipeline, not after && or ||, not sent to the background."""
        return not self.levels and not joiner(opener) and connector(closer) != "|" and closer.strip("\n") != "&"

    def path(self, argv, starts_case_branch, opener="", closer=""):
        """The Place of one command; opener is every separator before it, closer the one that ends it."""
        name, args = shell.program(argv)
        self.substitutions(opener)
        for word in itertools.takewhile(shell.ASSIGNMENT.match, [w for w in argv if w not in LEADING]):
            name = word.partition("=")[0]  # a new value: an earlier capture of the name is gone
            self.generation[name] = self.generation.get(name, 0) + 1
        if not connector(opener):
            self.chain = next(CHAIN_IDS)
        if not joiner(opener):
            self.condition = Condition()
        self.alternatives(argv, starts_case_branch, opener, closer)
        if name == "set" and self.sets_here(opener, closer):
            self.pipefail = set_pipefail([name, *args], self.pipefail)
        after_or = joiner(opener) == "||"  # `test || real` runs when the test failed: no gate
        gated = frozenset().union(frozenset() if after_or else self.condition.gate(), *(lv.gate for lv in self.levels))
        place = Place(self.base.path + tuple((level.id, level.alt) for level in self.levels),
                      self.base.gates | self.versioned(gated), frozenset(filter(None, self.stack)), self.chain,
                      connector(opener) == "&&", "|" in (connector(opener), connector(closer)), self.pipefail)
        self.condition.add(argv, joiner(opener))
        match = CAPTURE.fullmatch(argv[-1]) if closer.startswith("(") else None
        self.pending = (match[1], self.generation[match[1]]) if match else None
        return place


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


def excused(dry, real):
    """True when the real run only happens after the dry run's own result was checked: the dry run's captured output
    is tested by the branch or && list the real run is in, or pipefail makes the dry run's pipeline status the one
    the && acts on."""
    return bool(dry.captures & real.gates) or (real.pipefail and real.and_after and dry.staged
                                              and dry.chain == real.chain)


def problem(runs, entry):
    """The refusal for a real run that follows a dry run of the same program in one command; None otherwise."""
    try:
        programs = {name.rpartition("/")[2] for name in entry.get("programs") or ()}
        confirm = entry.get("confirm") or CONFIRM
        dry = {}
        for name, args, *branch in runs:
            if name not in programs:
                continue
            flag, place = confirm_flag(args, confirm), branch[0] if branch else Place()
            target = subject(args, set(DRY) | set(confirm))
            if flag is None:
                if not is_info(args):
                    dry.setdefault(name, []).append((target, place))
            elif any(same_subject(earlier, target) and not alternatives(before.path, place.path)
                     and not excused(before, place) for earlier, before in dry.get(name, ())):
                return (f"`{name}` runs as a dry run and then for real ({flag}) in one command, so the real run goes "
                        f"ahead even when the dry run refused. {FIX}")
    except Exception:  # this rule must never stop a command it cannot judge
        return None
    return None
