#!/usr/bin/env python3
"""A wait loop on message text, for guard_lessons' opt-in `wait-on-text` rule.

Usage: text = guard_wait_on_text.problem(command, entry, parse=None)  # None, or the refusal text
       ok = guard_wait_on_text.valid_paths(value)                      # a registry "paths" value this rule can use
Never raises: any error passes the command.
A `while` or `until` loop whose CONDITION reads one of the entry's "paths" with grep, rg, awk, sed, tail or cat (so
also `cat f | grep x`) waits on text that may only quote the event it waits for (a message that says "MERGED #741"
without the merge). "paths" is a list of shell globs, such as ".agents/bus/inbox-*.md". A glob with a "/" matches
as a path suffix of an argument (`inbox-pm.md` under the same directories, absolute, `./` or `$VAR/` spellings
too); a glob without a "/" matches the argument's basename. Without "paths" nothing is judged. A grep of those files
outside a loop condition, a loop whose condition reads other files, and a loop body that reads them pass.
A read inside a command substitution of the condition, `git grep`, a wildcard (`.agents/bus/*`) and a recursive
grep or rg of the directory count; the search pattern itself is not a file. Not seen: a redirect (`grep x < file`),
a function, a relative path after `cd` or a variable-built path (register the basename glob, `inbox-*.md`, for
those: it matches the file name wherever it sits), a read in the loop body or one that feeds the loop (`tail -f f | while`).
Standard library only.
"""
import fnmatch
import posixpath
import re

READERS = frozenset(("grep", "egrep", "fgrep", "rg", "awk", "gawk", "sed", "tail", "cat"))
PATTERN_FIRST = frozenset(("grep", "egrep", "fgrep", "rg", "awk", "gawk", "sed"))
SUBSTITUTION = re.compile(r"\$\(|\)|`")
LOOP_WORD = re.compile(r"\b(while|until)\b")
MAX_PATHS = 50
MAX_GLOB_CHARS = 200
REASON = ("A wait loop that reads message text matches lines that only quote the event. Wait on the authoritative "
          "state, e.g. gh pr view N --json state, never on message text.")


def valid_paths(value):
    return (isinstance(value, list) and 0 < len(value) <= MAX_PATHS
            and all(isinstance(item, str) and item.strip() and len(item) <= MAX_GLOB_CHARS for item in value))


def names(argument, pattern):
    """Whether a command argument is a file the glob names (see the module text)."""
    if "/" not in pattern:
        return fnmatch.fnmatchcase(posixpath.basename(argument), pattern)
    pattern = pattern[2:] if pattern.startswith("./") else pattern
    return fnmatch.fnmatchcase(argument, pattern) or fnmatch.fnmatchcase(argument, "*/" + pattern)


def covers(argument, pattern):
    """A wildcard argument that can expand to the glob's files (`.agents/bus/*` for `.agents/bus/inbox-*.md`):
    the same directory, and the glob's own text matches the argument's last part read as a pattern."""
    head, _, tail = argument.rpartition("/")
    if not any(char in tail for char in "*?[") or not fnmatch.fnmatchcase(pattern.rpartition("/")[2], tail):
        return False
    return not head or names(head + "/" + posixpath.basename(pattern), pattern)


def include_values(args):
    """The file filters of a recursive search: --include=X, --include X, -g X, --glob X, --glob=X."""
    values = []
    for index, arg in enumerate(args):
        flag, equals, value = arg.partition("=")
        if flag in ("--include", "--glob") and equals:
            values.append(value)
        elif arg in ("--include", "--glob", "-g") and index + 1 < len(args):
            values.append(args[index + 1])
    return values


def searches_directory(cmd, argument, pattern):
    """A recursive grep or rg of the glob's directory, unless its file filter leaves the glob's files out."""
    recursive = cmd.name == "rg" or any(arg in ("--recursive", "-r", "-R") or re.match(r"^-[A-Za-z]*[rR]", arg)
                                        for arg in cmd.args if not arg.startswith("--") or arg == "--recursive")
    folder, _, base = pattern.removeprefix("./").rpartition("/")
    if not recursive or not folder or not names(argument.rstrip("/") + "/" + base, pattern):
        return False
    filters = include_values(cmd.args)
    return not filters or any(fnmatch.fnmatchcase(base, f) or fnmatch.fnmatchcase(f, base) for f in filters)


def file_arguments(cmd):
    """The arguments of a reader that can be files: not the search pattern of grep, rg, awk and sed."""
    args = list(cmd.args)
    if cmd.name in PATTERN_FIRST and not any(re.match(r"^(-e|-f|--regexp|--file)", arg) for arg in args):
        first = next((i for i, arg in enumerate(args) if not arg.startswith("-")), None)
        if first is not None:
            del args[first]
    return args


def reader(cmd):
    """The command when it reads files (`git grep` as grep), else None."""
    if cmd.name == "git" and cmd.args[:1] == ["grep"]:
        return cmd._replace(name="grep", args=cmd.args[1:])
    return cmd if cmd.name in READERS else None


def reads(cmd, paths):
    cmd = reader(cmd)
    return cmd is not None and any(names(arg, glob) or covers(arg, glob) or searches_directory(cmd, arg, glob)
                                   for arg in file_arguments(cmd) for glob in paths)


def reads_in_condition(commands, paths, parse):
    for cmd in commands:
        if not cmd.in_loop:
            continue
        if reads(cmd, paths):
            return True
        for arg in cmd.args:  # "$(grep X file)" is one argument of the test command; the parser turns a backtick body into " ; body ; "
            body = SUBSTITUTION.sub(" ; ", arg)
            if ";" in body and any(reads(inner, paths) for inner in parse(body)):
                return True
    return False


def problem(command, entry, parse=None):
    """The refusal text for a wait loop on the entry's paths, or None."""
    try:
        paths = entry.get("paths") if isinstance(entry, dict) else None
        if not valid_paths(paths) or not isinstance(command, str) or not LOOP_WORD.search(command):
            return None
        if parse is None:
            import guard_lessons  # imported here: guard_lessons imports this module
            parse = guard_lessons.commands
        return REASON if reads_in_condition(parse(command), paths, parse) else None
    except Exception:  # a guard never refuses for its own fault
        return None
