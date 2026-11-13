#!/usr/bin/env python3
"""Recognise a destructive shell command for guard.py's PreToolUse hook (Claude Code plugin).

Usage: reason = guard_destructive.destructive(command, cwd)  # "" when the command is not on the list
The command is split into simple commands with shlex (at ; & | ( ) and newlines, quotes removed), wrappers
(sudo, env, timeout, VAR=x ...) are skipped, and the program in command position is matched with its
arguments. So `echo "git push --force"` and a grep for the words are not hits. Text inside quotes is read
in two places only: the script given to `sh -c` / `eval`, and SQL passed to a database client.
Not seen: a command built from variables (an rm operand of `$VAR/` or `$VAR/*` is read as broad, `cd $VAR` is not followed) or run through xargs, find -exec, ssh or a script file, command
substitution inside double quotes, SQL in a file (psql -f), and everything after an unbalanced quote. Here-document bodies are dropped before lexing (read only as SQL).
Time budget: pure string work, no subprocess. A push with --force-with-lease or a branch deletion reads at
most three small files under .git (current branch, origin's default branch); a recursive rm or chmod does a
few stat calls to find the repository root.
"""
import os
import re
import shlex

SEPARATORS = frozenset("();|&\n")
PUNCTUATION = "();<>|&\n"
WRAPPERS = {  # word that may precede the program: its options that take a value
    "sudo": "-u -g -h -p -C -U -D -R -T", "doas": "-u -C", "env": "-u -C", "nice": "-n", "ionice": "-c -n -p",
    "timeout": "-k -s", "stdbuf": "-i -o -e", "command": "", "builtin": "", "exec": "", "time": "", "nohup": "",
    "if": "", "then": "", "else": "", "elif": "", "while": "", "until": "", "do": "", "!": "", "{": ""}
ASSIGNMENT = re.compile(r"^\w+=")
DURATION = re.compile(r"^\d+(\.\d+)?[smhd]?$")
SHELLS = frozenset("sh bash zsh dash ksh".split())
MAX_DEPTH = 2  # sh -c inside sh -c; deeper nesting is not read
PROTECTED_BRANCH = re.compile(r"^(main|master|trunk|develop|development|dev|staging|production|prod|release([/-].*)?)$")
WHOLE_TREE = frozenset((".", "./", ":/", "*", ":/*"))
SQL_CLIENTS = frozenset("psql mysql mariadb sqlcmd sqlite3 sqlite".split())
SQL_CARRIERS = frozenset("docker podman kubectl docker-compose".split())  # docker exec db psql -c ...
DESTRUCTIVE_SQL = re.compile(r"\b(?:drop\s+(?:database|table|schema)|truncate\s+(?:table\s+)?[\w\"`\[])", re.I)
DEVICE = re.compile(r"^/dev/(?!null$|zero$|stdout$|stderr$|stdin$|tty$|fd/|shm/)")
OPEN_MODE = re.compile(r"^(0?777|a?[+=]rwx|ugo[+=]rwx)$")
HOME_FORMS = ("~", "$HOME", "${HOME}")
PIPED_MAX = 4000
REDIRECTION = frozenset("<>&")
VARIABLE_ROOT = re.compile(r"^\$(?:\{\w+\}|\w+)/$")  # "$UNSET"/* expands to /* when the variable is empty
WORKING_DIRECTORY = ("$PWD", "${PWD}", "$(pwd)")


HEREDOC_RE = re.compile(r"<<(?!<)-?\s*(?:'([^'\n]+)'|\"([^\"\n]+)\"|\\?(\w+))")


def split_heredocs(command):
    """(command without here-document bodies, the bodies' text). A body is data (a document, a script, SQL), not
    commands, and its apostrophes must not reach the shell lexer. An operator with no terminator line is left alone."""
    lines, kept, bodies, index = command.split("\n"), [], [], 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        index += 1
        for match in HEREDOC_RE.finditer(line):
            word = next(group for group in match.groups() if group)
            end = next((n for n in range(index, len(lines)) if lines[n].strip() == word), None)
            if end is not None:
                bodies.extend(lines[index:end])
                index = end + 1
                break
    return "\n".join(kept), "\n".join(bodies)


def tokens(command):
    """Shell words with quotes removed; an operator (; && | > ...) is a token of its own. Never raises."""
    lexer = shlex.shlex(command.replace("\\\n", " ").replace("`", " ; "), posix=True, punctuation_chars=PUNCTUATION)
    lexer.whitespace, lexer.whitespace_split, lexer.commenters = " \t\r", True, ""
    words = []
    try:
        for word in lexer:
            words.append(word)
    except ValueError:  # an unbalanced quote: what was read before it still counts
        pass
    return words


def simple_commands(command):
    """[(argv, piped_from_previous, has_heredoc)] for each simple command, wrappers still in place."""
    found, argv, piped = [], [], False
    for word in tokens(command) + [";"]:
        if word and set(word) <= SEPARATORS:
            if argv:
                found.append((argv, piped, any(arg.startswith("<<") for arg in argv)))
            argv, piped = [], word.startswith("|") and word != "||"
        else:
            argv.append(word)
    return found


def program(argv):
    """(program name without its directory, its arguments) after assignments and wrappers such as sudo or timeout."""
    index = 0
    while index < len(argv):
        word = argv[index]
        if ASSIGNMENT.match(word):
            index += 1
        elif set(word) <= REDIRECTION:  # `>out git push -f`: the target of a leading redirection is not the program
            index += 2
        elif word.isdigit() and index + 1 < len(argv) and set(argv[index + 1]) <= REDIRECTION:
            index += 3
        elif word in WRAPPERS:
            takes_value = WRAPPERS[word].split()
            index += 1
            while index < len(argv) and (argv[index].startswith("-") or ASSIGNMENT.match(argv[index])
                                         or DURATION.match(argv[index])):
                index += 2 if argv[index] in takes_value else 1
        else:
            return word.rpartition("/")[2], argv[index + 1:]
    return "", []


class Arguments:
    """Options and operands of one command: single-letter flags, long option names, and the other words."""

    def __init__(self, args):
        self.short, self.long, self.words = set(), set(), []
        operands_only = False
        for arg in args:
            if operands_only or not arg.startswith("-") or arg == "-":
                self.words.append(arg)
            elif arg == "--":
                operands_only = True
            elif arg.startswith("--"):
                self.long.add(arg.partition("=")[0])
            else:
                self.short.update(arg[1:])

    def has(self, letter, name):
        return letter in self.short or name in self.long

    def spelled(self, name):
        """True when a long option is given in full or as git abbreviates it (--har for --hard, 3 letters or more)."""
        return any(len(option) >= 5 and name.startswith(option) for option in self.long)


def read_ref(path, prefix):
    """The branch a symbolic ref file points at, without the ref prefix ('' when detached, missing or unreadable)."""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read(300).strip()
    except (OSError, ValueError):
        return ""
    return text[4:].strip().replace(prefix, "", 1) if text.startswith("ref:") else ""


def git_dir(cwd):
    """(working tree root, its git directory) found by walking up from cwd, without running git; ('', '') if none."""
    folder = os.path.abspath(cwd)
    while True:
        marker = os.path.join(folder, ".git")
        if os.path.isdir(marker):
            return folder, marker
        if os.path.isfile(marker):  # a linked worktree or submodule: "gitdir: <path>"
            try:
                with open(marker, encoding="utf-8") as handle:
                    target = handle.read(1000).partition("gitdir:")[2].strip()
            except (OSError, ValueError):
                return folder, ""
            return folder, os.path.join(folder, target) if target else ""
        parent = os.path.dirname(folder)
        if parent == folder:
            return "", ""
        folder = parent


def branches(cwd):
    """(current branch, origin's default branch), each '' when unknown."""
    _, directory = git_dir(cwd)
    if not directory:
        return "", ""
    common = directory
    try:
        with open(os.path.join(directory, "commondir"), encoding="utf-8") as handle:  # linked worktree
            common = os.path.join(directory, handle.read(1000).strip())
    except (OSError, ValueError):
        pass
    return (read_ref(os.path.join(directory, "HEAD"), "refs/heads/"),
            read_ref(os.path.join(common, "refs", "remotes", "origin", "HEAD"), "refs/remotes/origin/"))


def push_reason(found, cwd):
    if found.has("n", "--dry-run"):
        return ""
    refspecs = found.words[1:]  # the first operand is the remote
    if found.has("f", "--force") or found.spelled("--mirror") or any(spec.startswith("+") for spec in refspecs):
        return ("a force push overwrites commits on the remote: use --force-with-lease on your own feature "
                "branch, or push a new commit")
    deletes = found.has("d", "--delete") or found.spelled("--delete") or any(spec.startswith(":") for spec in refspecs)
    if "--force-with-lease" not in found.long and not deletes:
        return ""
    current, default = branches(cwd)
    targets = [spec.rpartition(":")[2].replace("refs/heads/", "") for spec in refspecs] or [current]
    targets = [current if target == "HEAD" else target for target in targets]
    if any(target and (target == default or PROTECTED_BRANCH.match(target)) for target in targets):
        return "rewriting or deleting a protected or default branch on the remote: open a pull request instead"
    return ""


def git_reason(args, cwd):
    index = 0
    while index < len(args) and args[index].startswith("-"):  # git -C dir -c key=value <subcommand>
        if args[index] == "-C" and index + 1 < len(args):
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(args[index + 1])))
        index += 2 if args[index] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace") else 1
    command, found = "".join(args[index:index + 1]), Arguments(args[index + 1:])
    whole_tree = any(word in WHOLE_TREE for word in found.words)
    if command == "push":
        return push_reason(found, cwd)
    if command == "reset" and found.spelled("--hard"):
        return "git reset --hard discards uncommitted work: git stash first, or use git reset --keep"
    if command == "clean" and (found.has("f", "--force") or found.spelled("--force")) \
            and not found.has("n", "--dry-run"):
        return "git clean -f deletes untracked files for good: list them with git clean -n, or git stash -u"
    if command == "checkout" and (found.has("f", "--force") or whole_tree):
        return "this checkout discards every uncommitted change: git stash first, or name the files"
    if command == "switch" and (found.has("f", "--force") or found.spelled("--discard-changes")):
        return "this switch discards every uncommitted change: git stash first, or commit"
    if command == "restore" and whole_tree and (found.has("W", "--worktree") or not found.has("S", "--staged")):
        return "git restore of the whole tree discards every uncommitted change: git stash first, or name the files"
    if command == "branch" and ("D" in found.short or found.has("d", "--delete") and found.has("f", "--force")):
        return "git branch -D deletes unmerged commits: use git branch -d, which refuses when work is unmerged"
    return ""


def is_broad(target, cwd):
    """True for /, the home directory, a repository root or its .git, '.', '..', a top-level directory, or a glob of one."""
    target = re.sub(r"/\.?\*$", "/", target)  # dir/* and dir/.* empty the directory itself
    if VARIABLE_ROOT.match(target) or target.rstrip("/") in WORKING_DIRECTORY:
        return True
    if target in ("*", ".*") or target.startswith(HOME_FORMS) and target.rstrip("/") in HOME_FORMS:
        return True
    if target and all(part in (".", "..") for part in target.rstrip("/").split("/")) and target.rstrip("/"):
        return True
    home = os.path.expanduser("~")
    for form in HOME_FORMS:
        if target.startswith(form + "/"):
            target = home + target[len(form):]
    path = os.path.normpath(os.path.join(cwd, target))
    root, parent = git_dir(cwd)[0], os.path.dirname(path)
    if os.path.dirname(parent) == parent or os.path.basename(path) == ".git" or os.path.exists(os.path.join(path, ".git")):
        return True  # a filesystem root, a top-level directory, the root of any repository, or its history
    return any(place and (place == path or place.startswith(path + os.sep)) for place in (home, root))


def rm_reason(args, cwd):
    found = Arguments(args)
    recursive = found.has("r", "--recursive") or "R" in found.short
    if "--no-preserve-root" in found.long or recursive and any(is_broad(word, cwd) for word in found.words):
        return "rm -r on a root, home, repository or wildcard path: name the exact directories to remove"
    return ""


def chmod_reason(args, cwd):
    found = Arguments(args)
    if found.has("R", "--recursive") and found.words and OPEN_MODE.match(found.words[0]) \
            and any(is_broad(word, cwd) for word in found.words[1:]):
        return "chmod -R 777 on a broad path: set the mode on the one file or directory that needs it"
    return ""


def infrastructure_reason(name, args):
    found = Arguments(args)
    words = found.words
    if name in ("terraform", "tofu", "terragrunt"):
        if words[:1] == ["destroy"] or words[:1] == ["apply"] and "-destroy" in args:
            return f"{name} destroy removes real infrastructure: run {name} plan -destroy and leave the apply to a human"
    elif name in ("kubectl", "oc"):
        after = words[words.index("delete") + 1:][:1] if "delete" in words else []  # the type, not the value of -n
        resources = [word for word in after if word.split("/")[0] in ("namespace", "namespaces", "ns")]
        if "delete" in words and not any(arg.startswith("--dry-run") for arg in args) \
                and (resources or "--all" in found.long or "--all-namespaces" in found.long):
            return "kubectl delete of a namespace or of --all resources: delete one named resource, or use --dry-run=client"
    elif name in ("docker", "podman"):
        if words[:2] == ["system", "prune"] and "--volumes" in found.long:
            return "docker system prune --volumes deletes every unused volume and its data: prune without --volumes"
    elif name == "dd":
        if any(arg.startswith("of=") and DEVICE.match(arg[3:]) for arg in args):
            return "dd onto a device overwrites it: write to a file, and leave devices to a human"
    elif name.startswith("mkfs") or name in ("mke2fs", "wipefs"):
        if any(DEVICE.match(word) for word in words):
            return f"{name} on a device erases it: leave formatting to a human"
    return ""


def sql_reason(name, args, piped_text, raw):
    if name == "dropdb" or name == "mysqladmin" and "drop" in args:
        return "dropping a database: take a backup and leave the drop to a human"
    client = name in SQL_CLIENTS or name in SQL_CARRIERS and any(arg.rpartition("/")[2] in SQL_CLIENTS for arg in args)
    if client and DESTRUCTIVE_SQL.search(" ".join(args) + " " + piped_text + " " + raw):
        return "DROP or TRUNCATE through a database client: write a reviewed migration, or run it on a disposable copy"
    return ""


def destructive(command, cwd, depth=0):
    """One line saying why the command is destructive and what to do instead; '' when it is not on the list."""
    piped_text = ""
    command, heredoc_text = split_heredocs(command)
    for argv, piped, heredoc in simple_commands(command):
        name, args = program(argv)
        if name == "cd" and args and not args[0].startswith(("-", "$")):  # later commands run in that directory
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(args[0])))
        piped_text = (piped_text + " " if piped else "") + " ".join(argv)  # what flows into this command's stdin
        piped_text = piped_text[-PIPED_MAX:]  # bounded: a pipeline of thousands of stages stays linear
        script = ""
        if name in SHELLS and depth < MAX_DEPTH:
            flag = next((i for i, arg in enumerate(args) if re.match(r"^-[a-z]*c$", arg)), None)
            script = "".join(args[flag + 1:flag + 2]) if flag is not None else ""
        elif name == "eval" and depth < MAX_DEPTH:
            script = " ".join(args)
        reason = (destructive(script, cwd, depth + 1) if script
                  else git_reason(args, cwd) if name == "git"
                  else rm_reason(args, cwd) if name == "rm"
                  else chmod_reason(args, cwd) if name == "chmod"
                  else infrastructure_reason(name, args)
                  or sql_reason(name, args, piped_text if piped else "", heredoc_text if heredoc else ""))
        if reason:
            return reason
    return ""
