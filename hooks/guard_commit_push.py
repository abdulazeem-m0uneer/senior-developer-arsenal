#!/usr/bin/env python3
"""A commit and its push with no status and log read between them, for guard_lessons' opt-in `commit-then-push` rule.

Usage: problem = guard_commit_push.problem(command, entry, parse=None, history=None)  # parse: guard_lessons.commands
       events = guard_commit_push.observe(command, programs, parse=None)  # what the tracker records after a call
Returns the refusal text, which names the fix, or None. Never raises: any error passes the command.
`git commit && git push` pushes whatever the commit left, even when a hook changed it, refused it or left files
unstaged, because nobody read the result. Refused: a `git push` (or a program the entry's "programs" names, such as a
push wrapper; matched by name or path basename, also through a launcher or a shell variable, or the script an
interpreter runs) that follows a `git commit` without BOTH `git status` and `git log` (or `git rev-parse HEAD`, the
same fact) after the commit and before the push, whatever the separators (&&, ||, ;, newlines, if/then blocks) and
inside a $( ) or backticks, bare or in double quotes. The commit may sit in an earlier call: the tracker records
git_commit, git_status, git_log and git_push after each call that ran, failed or not (guard.py track), and `history`
is that session's list. Each push is judged against the last commit before it in the same repository; a push settles
that repository's commit, so it is judged once.
Reads count only when their output is shown: not written to a file or /dev/null (`> f`, `>> f`, `&> f`; stderr
alone may go), not piped into a count (`| wc -l`, `| grep -c x`) or into a stage that writes to a file or /dev/null
(`| cat > /dev/null`; a number spaced from the `>`, as in `git log -n 3 >f`, is an argument, not a descriptor),
not `git log -0`, not `git rev-parse --abbrev-ref HEAD`, not inside a $( ) or backticks (captured; an echo or printf
argument is printed), not in the arm of a `||` (it runs only when the command before it failed), not in a list sent to
the background with `&`. A read in another arm of an if or case than
the push does not count, and a commit in another arm is not before it.
The repository is the call's directory moved by `cd <dir>` and `git -C <dir>` ($VAR, ~ and the like are not known and
match any repository), taken up to the nearest directory holding a .git (so /repo/src and /repo/docs are one
repository); without a .git found, a directory and its subdirectories are one repository (`cd src && git push`
pushes the commit made one level up). A status or log read in a directory above the commit's does not count for it.
A commit, status, log or push of another repository is not told apart from this one only when its directory is not
known.
Passes: `git commit --dry-run`; `git push --dry-run` or -n (in a cluster only before any o: -on is -o n); a push
to a repository on this machine (a path, ./, ../, ~, file://, or a variable set to one earlier in the same call; a
remote name, a host URL, host:path or a variable not known there, such as one a substitution set, still counts); `push_once.py hook` or `check` (the arsenal's pre-push
handler and manual check, which push nothing) and a listed program given --dry-run as a flag (before any `--`, not
right after an option word with no =value, which may take it as its value); any other run of a listed program counts;
a push with no commit before it; a commit with no push after it; a here-document that only writes a script (its body
is dropped, as data); a session with no recorded events (the tracker records only while the rule is on).
String work, plus a check for a .git above each known directory: no process or network access.
Standard library only.
"""

import os
import posixpath
import re
from collections import namedtuple

REASON = ("A git push runs after a git commit with no `git status` and `git log -1` read in between. Run both after "
          "the commit and read them (`git rev-parse HEAD` stands for `git log -1`), then push, as a separate call or "
          "after both in the same script.")
COMMIT, STATUS, LOG, PUSH = "git_commit", "git_status", "git_log", "git_push"  # the events the tracker records
READS = {"status": STATUS, "log": LOG}
NAME_ONLY = frozenset(("--abbrev-ref", "--symbolic", "--symbolic-full-name"))  # rev-parse prints a name, not the commit
DRY_RUN_CLUSTER = re.compile(r"-[A-Za-mp-z]*n[A-Za-z]*")  # git push -n, -un; not -on (-o with the value n)
OPTION_CLUSTER = re.compile(r"-[A-Za-z0-9]*o")  # git push -uo V: -u, then -o with the next word as its value
NO_COMMITS = re.compile(r"-0+|-n0+|--max-count=0+")  # git log -0 prints no commit
STDOUT_REDIRECTS = frozenset((">", ">>", ">|", "&>", "&>>", ">&"))
GREP_COUNT = re.compile(r"-[A-Za-z]*c[A-Za-z]*|--count")  # grep -c prints a number, no line
SUBSTITUTED = "$SUBST"  # the word a substitution leaves behind
CAPTURE_OPEN, CAPTURE_CLOSE = "capture_begin", "capture_end"  # the commands that bracket a substitution's hoisted ones
SHOWS_ARGUMENTS = re.compile(r"(?:\w+=\S*\s+)*(?:echo|printf)\b")  # a command that prints what a substitution gave it
Item = namedtuple("Item", "event path dir")  # dir: the repository's absolute directory, None when not known
SEPARATORS = ";&|\n()"
SPACED_REDIRECT = re.compile(r"(?<=[ \t])(?=>(?!\())")  # `-n 3 >f`: the 3 is an argument, fd 1 is meant
KEYWORDS = re.compile(r"\s*(?:(?:if|then|else|elif|while|until|do|!|\{)\s+)*")  # words before a command's own
NO_PUSH_SUBCOMMANDS = {"push_once.py": frozenset(("hook", "check"))}  # the arsenal's own wrapper: both only judge a push
PUSH_WITH_VALUE = frozenset(("-o", "--push-option", "--receive-pack", "--exec"))
NETWORK_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")  # ssh://, https://, git:// (file:// is local)
VARIABLE_ROUNDS = 4  # O=$T/o.git after T=/tmp/x: each round resolves one level


def valid_programs(value):
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item for item in value)


def closing(text, start):
    """The index after the `)` or backtick that closes the $( ... ) or backtick substitution at start, or -1."""
    if text[start] == "`":
        end = text.find("`", start + 1)
        return end + 1 if end >= 0 else -1
    depth, index, quote = 1, start + 2, ""
    while index < len(text):
        char = text[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return -1


def unwrap_substitutions(command):
    """The command with each $( ... ) and backtick substitution (in double quotes or bare) replaced by a word and its
    commands put in front of the simple command that holds it, where the shell runs them: `git -C "$(pwd)" push`
    becomes `capture_begin ; pwd ; capture_end ; git -C "$SUBST" push`, so the words of the outer command keep their
    places. The commands between the two markers have their output captured, not shown (unless the outer command is
    an echo or printf, which prints it)."""
    out, index, quote, start = "", 0, "", 0
    while index < len(command):
        char = command[index]
        if char == "\\" and quote != "'":
            out += command[index:index + 2]
            index += 2
        elif quote != "'" and (char == "`" or command.startswith("$(", index)):
            end = closing(command, index)
            if end < 0:
                out += command[index:]
                break
            inner = command[index + (2 if char == "$" else 1):end - 1]
            at = KEYWORDS.match(out, start).end()
            body = unwrap_substitutions(inner) + " ; "
            if not SHOWS_ARGUMENTS.match(out, at):
                body = f"{CAPTURE_OPEN} ; {body}{CAPTURE_CLOSE} ; "
            out = out[:at] + body + out[at:] + SUBSTITUTED
            index = end
        else:
            if quote:
                quote = "" if char == quote else quote
            elif char in "'\"":
                quote = char
            elif char in SEPARATORS:
                start = len(out) + 1
            out += char
            index += 1
    return out


def feeds_a_shell(line, parse, lessons):
    """True when a command on the line runs the here-document as its script: a shell with no -c and no script file."""
    return any(cmd.name in lessons.shell.SHELLS and not lessons.script_and_args(cmd)[0]
               and not any(re.match(r"^-[a-z]*c$", arg) for arg in cmd.args)
               for cmd in parse(lessons.shell.HEREDOC_RE.sub("", line)))


def heredoc_scripts(command, parse, lessons):
    """The command with the body of each here-document a shell runs left in as lines of commands, and the bodies
    that are only data (a file written, text read) dropped."""
    lines, kept, index = command.split("\n"), [], 0
    while index < len(lines):
        line = lines[index]
        index += 1
        end = next((next((n for n in range(index, len(lines)) if lines[n].strip() == word), None)
                    for word in (next(group for group in match.groups() if group)
                                 for match in lessons.shell.HEREDOC_RE.finditer(line))), None)
        if end is None:
            kept.append(line)
            continue
        kept.append(lessons.shell.HEREDOC_RE.sub("", line))
        if feeds_a_shell(line, parse, lessons):
            kept.extend(lines[index:end])
        index = end + 1
    return "\n".join(kept)


def discards_output(args):
    """True when stdout goes to a file or /dev/null: `> f`, `>> f`, `1> f`, `&> f`, `>& f` (stderr alone, `>&2` and
    `2>&1` still show)."""
    for index, arg in enumerate(args[:-1]):
        target = args[index + 1]
        if arg in STDOUT_REDIRECTS and not (arg == ">&" and (target.isdigit() or target == "-")):
            fd = args[index - 1] if index and args[index - 1].isdigit() else "1"
            if arg.startswith("&") or fd == "1":
                return True
    return False


def shows_no_commit(args):
    """True for a log limited to no commits: -0, -n 0, -n0, --max-count=0, --max-count 0."""
    return any(NO_COMMITS.fullmatch(arg) or arg in ("-n", "--max-count") and index + 1 < len(args)
               and re.fullmatch(r"0+", args[index + 1]) for index, arg in enumerate(args))


def pipe_stages_after(cmds, at):
    """The commands the one at cmds[at] pipes into, in order (`a | b | c` gives b and c)."""
    stages = []
    for before, after in zip(cmds[at:], cmds[at + 1:]):
        if not (before.branch.staged and after.branch.staged) or after.branch.chain != before.branch.chain:
            break
        if after.branch.and_after or after.branch.or_arm:
            break  # joined by && or ||, not by the pipe
        stages.append(after)
    return stages


def counts_away(cmds, at):
    """True when the command at cmds[at] pipes into a count (`| wc -l`, `| grep -c x`) or into a stage whose stdout
    goes to a file or /dev/null (`| cat > /dev/null`), which shows no line of what it read. `| grep -q` is still a
    read: as an if or while test it decides what runs next on what the status showed."""
    return any(stage.name == "wc" or discards_output(stage.args) or stage.name in ("grep", "egrep", "fgrep", "rg")
               and any(GREP_COUNT.fullmatch(arg) for arg in stage.args) for stage in pipe_stages_after(cmds, at))


def is_dry_run(options):
    return any(option == "--dry-run" or DRY_RUN_CLUSTER.fullmatch(option) for option in options)


def push_remote(args):
    """The repository a `git push` names (its first operand, else --repo), or None for the configured default; git
    sends to the operand when both are given (`git push --repo /tmp/b.git origin x` reaches origin)."""
    words, repo = iter(args), None
    for arg in words:
        if arg == "--":
            return next(words, repo)
        if arg.startswith("--repo="):
            repo = arg.partition("=")[2]
        elif arg in PUSH_WITH_VALUE or arg == "--repo" or OPTION_CLUSTER.fullmatch(arg):
            value = next(words, None)
            if arg == "--repo":
                repo = value
        elif not arg.startswith("-"):
            return arg
    return repo


def is_local_repository(remote, variables, lessons):
    """True for a remote on this machine: a path (absolute, ./, ../, ~, or one with a / and no host: before it) or a
    file:// URL, also through variables set earlier in the call. A remote name, a host URL, scp-style host:path or a
    variable that is not known (unset here, or set by a substitution) is not: it may reach a shared remote."""
    for _ in range(VARIABLE_ROUNDS):
        expanded = lessons.shell.expand(remote, variables)
        if expanded == remote:
            break
        remote = expanded
    if not remote or any(char in remote for char in "$`"):
        return False
    if remote.startswith("file://"):
        return True
    if NETWORK_URL.match(remote):
        return False
    if remote in (".", "..") or remote.startswith(("/", "./", "../", "~")):
        return True
    return "/" in remote and ":" not in remote.partition("/")[0]


def git_event(cmd, lessons):
    """The event of a git command: commit, push, or the status or log it prints; '' for any other."""
    index, subcommand = lessons.git_subcommand(cmd.args)
    rest = cmd.args[index + 1:]
    if subcommand == "commit":
        return COMMIT if lessons.is_git_commit(cmd) else ""
    if subcommand == "push":
        remote = push_remote(rest)
        local = remote is not None and is_local_repository(remote, cmd.variables, lessons)
        return "" if local or is_dry_run(lessons.git_options(rest)) else PUSH
    if subcommand == "rev-parse":
        names_only = any(arg.partition("=")[0] in NAME_ONLY for arg in rest)
        subcommand = LOG if "HEAD" in rest and not names_only else ""  # the same fact as `git log -1`
    else:
        subcommand = READS.get(subcommand, "")
        if subcommand == LOG and shows_no_commit(rest):
            return ""
    return "" if discards_output(rest) else subcommand


def dry_run_flag(args):
    """True for --dry-run as a flag: before any `--`, and not right after an option word with no =value, which may
    take it as its value (`ship.sh --note --dry-run`)."""
    for index, arg in enumerate(args):
        if arg == "--":
            return False
        if arg == "--dry-run" and not (index and args[index - 1].startswith("-") and "=" not in args[index - 1]):
            return True
    return False


def event_of(cmd, names, lessons):
    if cmd.name == "git":
        return git_event(cmd, lessons)
    program, args, _branch = lessons.run_of(cmd)
    if program not in names or dry_run_flag(args):
        return ""
    return "" if args and args[0] in NO_PUSH_SUBCOMMANDS.get(program, ()) else PUSH


def where(place):
    """The if/case path a command surely runs on: the test of an if runs on every way past it, so its path is the
    construct's outer one (an elif test runs only when the first failed)."""
    path = place.path
    return path[:-1] if place.reading and path and path[-1][1] == 0 else path


def resolve(path, here):
    """The absolute directory `path` names from `here`, or None when it is not known here ($VAR, ~, `-`)."""
    if not path or path == "-" or path[0] in "~" or any(char in path for char in "$`*?"):
        return None
    if path.startswith("/"):
        return posixpath.normpath(path)
    return posixpath.normpath(posixpath.join(here, path)) if here else None


def repo_dir(cmd, here, lessons):
    """The directory a git command works in: `here` moved by each -C <dir> before its subcommand (None for --git-dir)."""
    if cmd.name != "git":
        return here
    stop, index = lessons.git_subcommand(cmd.args)[0], 0
    while index < stop:
        if cmd.args[index] == "-C" and index + 1 < stop:
            here = resolve(cmd.args[index + 1], here)
        elif cmd.args[index].partition("=")[0] in ("--git-dir", "--work-tree"):
            here = None  # a repository named by its git directory: matched with any
        index += 2 if cmd.args[index] in lessons.GIT_GLOBAL_WITH_VALUE else 1
    return here


def repository_top(directory):
    """The nearest directory at or above `directory` that holds a .git (a directory, or the file of a worktree or
    submodule), else `directory` itself; None stays None."""
    probe = directory
    while probe:
        if os.path.exists(os.path.join(probe, ".git")):
            return probe
        parent = posixpath.dirname(probe)
        probe = parent if parent != probe else None
    return directory


def after_cd(args, here):
    operands = [arg for arg in args if arg == "-" or not arg.startswith("-")]
    return resolve(operands[0], here) if operands else None


def shown(cmd, captured, backgrounded):
    """False for a read whose output the session does not see: captured by a substitution, in the arm of a || (it
    runs only when the command before it failed), or in a list sent to the background (it runs beside what follows)."""
    return not (captured or cmd.branch.or_arm or cmd.branch.chain in backgrounded)


def events_of(command, names, parse, lessons, cwd=None):
    """[Item(event, if/case path, directory)] of each commit, push and read in the command, in order."""
    text = SPACED_REDIRECT.sub("1", unwrap_substitutions(heredoc_scripts(command, parse, lessons)))
    cmds = list(lessons.with_remote_commands(parse(text)))
    backgrounded = {cmd.branch.chain for cmd in cmds if cmd.branch.background}
    found, captured, here = [], 0, resolve(cwd, None) if cwd else None
    for at, cmd in enumerate(cmds):
        if cmd.name in (CAPTURE_OPEN, CAPTURE_CLOSE):
            captured = max(0, captured + (1 if cmd.name == CAPTURE_OPEN else -1))
        elif cmd.name == "cd":
            here = after_cd(cmd.args, here)
        else:
            event = event_of(cmd, names, lessons)
            seen = shown(cmd, captured, backgrounded) and not counts_away(cmds, at)
            if event and (event in (COMMIT, PUSH) or seen):
                found.append(Item(event, where(cmd.branch), repository_top(repo_dir(cmd, here, lessons))))
    return found


def alternatives(first, second, lessons):
    return lessons.guard_dry_run_chain.alternatives(first, second)


def within(inner, outer):
    """True when either directory is not known or `inner` is `outer` or below it."""
    if not inner or not outer:
        return True
    inner, outer = inner.rstrip("/") or "/", outer.rstrip("/") or "/"
    return inner == outer or inner.startswith(outer if outer == "/" else outer + "/")


def same_repo(first, second):
    """True when either directory is not known or one holds the other (a subdirectory is in the same repository)."""
    return within(first, second) or within(second, first)


def settled(history, agent_id=None):
    """The commit left unpushed by this agent's earlier calls in each directory and the reads since, as Items.
    Events of another agent are another flow's; an event with no recorded directory counts for every directory."""
    pending = []
    for event in history if isinstance(history, list) else []:
        if not isinstance(event, dict) or event.get("agent") != agent_id:
            continue
        kind, repo = event.get("event"), repository_top(event.get("cwd") or None)
        if kind in (COMMIT, PUSH):
            pending = [item for item in pending if not same_repo(item.dir, repo)]
        if kind == COMMIT:
            pending.append(Item(COMMIT, (), repo))
        elif kind in (STATUS, LOG) and any(item.event == COMMIT and same_repo(item.dir, repo) for item in pending):
            pending.append(Item(kind, (), repo))
    return pending


def unread_push(chain, index, lessons):
    """True when the push at chain[index] follows a commit that status and log were not both read after."""
    push = chain[index]
    before = [item for item in chain[:index]
              if same_repo(item.dir, push.dir) and not alternatives(item.path, push.path, lessons)]
    commits = [at for at, item in enumerate(before) if item.event == COMMIT]
    if not commits:
        return False
    # a read counts when it runs on every way to this push (its path is a prefix of the push's) and reads the
    # commit's repository, not a directory above it
    commit = before[commits[-1]]
    shown_reads = {item.event for item in before[commits[-1] + 1:] if item.event != COMMIT
                   and push.path[:len(item.path)] == item.path and within(item.dir, commit.dir)}
    return shown_reads != {STATUS, LOG}


def judged(command, entry, parse, pending, cwd):
    import guard_lessons  # imported here: guard_lessons imports this module
    parse = parse or guard_lessons.commands
    names = entry.get("programs") if valid_programs(entry.get("programs")) else []
    chain = pending + events_of(command, names, parse, guard_lessons, cwd)
    if any(item.event == PUSH and unread_push(chain, at, guard_lessons) for at, item in enumerate(chain)):
        return REASON
    return None


def observe(command, programs, parse=None):
    """The events (git_commit, git_status, git_log, git_push) a call ran, in order; [] on any error."""
    return [event for event, _ in observed(command, programs, parse)]


def observed(command, programs, parse=None, cwd=None):
    """[(event, directory)] of a call, for the tracker; directory is None when not known. A call that failed is
    taken as having run all its commands: which step failed is not known, and a read counts only after a commit."""
    try:
        import guard_lessons
        names = programs if valid_programs(programs) else []
        if "git" not in command and not any(name in command for name in names):
            return []  # no parse for a call that names neither git nor a push wrapper
        return [(item.event, item.dir) for item in
                events_of(command, names, parse or guard_lessons.commands, guard_lessons, cwd)]
    except Exception:  # the tracker must never break a session
        return []


def problem(command, entry, parse=None, history=None, cwd=None, agent_id=None):
    """The refusal text for a push after a commit with no status and log read between, or None. history: the
    session's recorded events; cwd, agent_id: where and by whom this call runs (only that flow's events count)."""
    try:
        if not isinstance(command, str) or not isinstance(entry, dict):
            return None
        pending = settled(history, agent_id)
        if "commit" not in command and not pending:
            return None
        return judged(command, entry, parse, pending, cwd)
    except Exception:  # a guard never refuses for its own fault
        return None
