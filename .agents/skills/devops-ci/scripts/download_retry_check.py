#!/usr/bin/env python3
"""Find CI downloads (curl, wget) that have no retry, so one failed CDN fetch does not turn a run red.

Usage: python3 download_retry_check.py [PATH ...]
PATH is a file or a folder (searched for .yml .yaml .sh .bash .js .mjs .cjs .ts .py). With no PATH the defaults are
.github/workflows and ci/, tools/ci/, scripts/ci/ (those that exist). In .yml/.yaml files only `run:` text is read
(a `run: |` block or a single-line `run:`); other files are read whole. Comment lines are skipped, backslash
continuations are one command, and `&&`, `||` and `;` start a new command.
A command is a download when it is
  curl with -O, -o, -L (also inside a cluster such as -fsSLO), --output, --remote-name or --location, or piped to a
  shell or tar;
  wget with a URL (or a $variable), no --spider, and --tries=1, --tries 1, -t 1 or -t1 (wget tries 20 times by
  default, so a plain wget is fine).
In shell text the tool must stand where a command starts (after sudo, env, VAR=x, if, do, $( ...), so
`apt-get install wget` and `echo "wget $URL"` are not calls. curl with -o/--output /dev/null is a probe, not a download.
It is retried when
  curl has --retry N (or --retry=N) with N >= 2, or a $variable for N (--retry-all-errors alone is not a retry);
  wget is only reported for one try; any other --tries/-t value (2 or more, 0 or inf = infinite, a $variable) is fine;
  in shell text the line sits in a loop that reruns it: until ... done, while ... done (not `while read`), or
  for ... done whose command does not use the loop variable (`for f in a b; do curl -O $f` fetches different files).
Folder scans skip .git, node_modules, vendor, dist, build, virtualenvs and files that are not UTF-8 text; a file named
on the command line must be UTF-8. In JS and Python an argv or call spread over lines (open bracket) is one command.
Output: one line per finding, "path:line: curl needs --retry N" or "path:line: wget needs --tries=N".
Exit codes: 0 none found, 1 findings, 2 bad input (missing path, unreadable or non-UTF-8 file).
Standard library only.
"""
import os
import re
import sys
from pathlib import Path

DEFAULT_PATHS = (".github/workflows", "ci", "tools/ci", "scripts/ci")
SHELL_SUFFIXES = {".yml", ".yaml", ".sh", ".bash"}
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", ".venv", "venv", "__pycache__", ".tox"}
MAX_JOINED_LINES = 12
SUFFIXES = {".yml", ".yaml", ".sh", ".bash", ".js", ".mjs", ".cjs", ".ts", ".py"}
RUN_KEY = re.compile(r"^(\s*)(-\s+)?run:\s*(.*?)\s*$")
COMMAND = re.compile(r"(?:^|[\s(`\"'=])(curl|wget)(?=[\s\"',)]|$)")
SEPARATORS = re.compile(r"&&|\|\||;")
PIPE = re.compile(r"(?<!\|)\|(?!\|)")
LOOP_START = re.compile(r"^\s*(?:for|while|until)\b")
LOOP_END = re.compile(r"^\s*done\b")
LOOP_HEADER = re.compile(r"^\s*(for|while|until)\b(.*?)(?:;?\s*\bdo\b.*)?$")
LOOP_VARIABLE = re.compile(r"^\s*(\w+)\s+in\b")
WORD_READ = re.compile(r"\bread\b")
COMMAND_PREFIX = {"do", "then", "else", "if", "elif", "while", "until", "!", "{", "(", "time", "nohup", "exec", "command"}
WRAPPERS_WITH_FLAGS = {"sudo", "env"}
ASSIGNMENT = re.compile(r"^\w+=\S*$")
ONE_LINE_LOOP = re.compile(r"\bdone\b")
CURL_DOWNLOAD_LONG = {"--output", "--remote-name", "--remote-name-all", "--location"}
PIPE_SINKS = {"sh", "bash", "zsh", "dash", "tar"}
WRAPPERS = {"sudo", "env"}
MIN_TRIES = 2
STRIP = "\"'`[](),"


def retry_count_ok(value):
    value = value.strip(STRIP)
    if value.startswith("$"):
        return True
    return value.isdigit() and int(value) >= MIN_TRIES


def tokens_after(stage, match):
    return [t for t in (x.strip(STRIP) for x in re.split(r"[\s,]+", stage[match.end(1):])) if t]


def curl_retried(args):
    for i, tok in enumerate(args):
        if tok.startswith("--retry="):
            return retry_count_ok(tok.split("=", 1)[1])
        if tok == "--retry":
            return i + 1 < len(args) and retry_count_ok(args[i + 1])
    return False


def wget_single_try(args):
    """True when the last tries option of a wget call is 1 (wget's default is 20; 0 and inf mean unlimited)."""
    tries = None
    for i, tok in enumerate(args):
        short = re.match(r"^-[A-Za-z]*t(\d*)$", tok) if not tok.startswith("--") else None
        if tok.startswith("--tries="):
            tries = tok.split("=", 1)[1]
        elif tok == "--tries" or (short and not short.group(1)):
            tries = args[i + 1] if i + 1 < len(args) else None
        elif short:
            tries = short.group(1)
    return tries is not None and tries.strip(STRIP) == "1"


def curl_downloads(args, piped_to_sink):
    if piped_to_sink:
        return True
    if "/dev/null" in args or any(t.endswith("/dev/null") and t.startswith("-o") for t in args):
        return False
    for tok in args:
        if tok in CURL_DOWNLOAD_LONG:
            return True
        if re.match(r"^-[A-Za-z]+$", tok) and set(tok[1:]) & set("OoL"):
            return True
    return False


def wget_downloads(args):
    if "--spider" in args:
        return False
    return any("://" in t or t.startswith("$") for t in args if not t.startswith("-"))


def at_command_start(stage, match):
    """True when the matched tool is the command of this stage, not an argument or quoted text."""
    skipping_flags = False
    for word in stage[:match.start(1)].split():
        word = word.lstrip("$(`{")
        if not word or word in COMMAND_PREFIX or ASSIGNMENT.match(word):
            skipping_flags = False
        elif word in WRAPPERS_WITH_FLAGS:
            skipping_flags = True
        elif not (skipping_flags and word.startswith("-")):
            return False
    return True


def first_word(stage):
    for word in stage.split():
        word = word.strip(STRIP + "$")
        if word and not word.startswith("-") and word not in WRAPPERS:
            return word
    return ""


def finding_for(command, shell):
    """The tool name when this one command downloads without a retry, else None."""
    stages = PIPE.split(command)
    for index, stage in enumerate(stages):
        match = COMMAND.search(stage)
        if not match or (shell and not at_command_start(stage, match)):
            continue
        tool, args = match.group(1), tokens_after(stage, match)
        if tool == "curl":
            sink = any(first_word(later) in PIPE_SINKS for later in stages[index + 1:])
            if curl_downloads(args, sink) and not curl_retried(args):
                return tool
        elif wget_downloads(args) and wget_single_try(args):
            return tool
    return None


def open_brackets(text):
    return sum(text.count(c) for c in "([") - sum(text.count(c) for c in ")]")


def logical_lines(numbered, shell):
    """Join continuations (a trailing backslash; in JS and Python also an open bracket); each result keeps the
    number of its first line."""
    joined, pending, count = [], None, 0
    for number, text in numbered:
        if pending:
            pending = (pending[0], pending[1] + " " + text.strip())
            count += 1
        else:
            pending, count = (number, text), 1
        if pending[1].rstrip().endswith("\\"):
            pending = (pending[0], pending[1].rstrip()[:-1])
            continue
        if not shell and open_brackets(pending[1]) > 0 and count < MAX_JOINED_LINES:
            continue
        joined.append(pending)
        pending = None
    if pending:
        joined.append(pending)
    return joined


def loop_of(text):
    """(kind, variable, header) of a loop line; the header is the text before `do`."""
    kind, header = LOOP_HEADER.match(text).groups()
    variable = LOOP_VARIABLE.match(header)
    return kind, variable.group(1) if variable else None, header


def reruns(loop, command):
    """True when the loop repeats this command (a retry), not when it feeds it different input."""
    kind, variable, header = loop
    if kind == "while":
        return not WORD_READ.search(header)
    if kind == "for" and variable:
        return not re.search(r"\$\{?" + variable + r"\b", command)
    return True


def scan_block(numbered, shell):
    loops = []
    for number, text in logical_lines(numbered, shell):
        stripped = text.strip()
        if not stripped or stripped.startswith(("#", "//")):
            continue
        active = list(loops)
        if shell and LOOP_START.match(text):
            loop = loop_of(text)
            active.append(loop)
            if not ONE_LINE_LOOP.search(text):
                loops.append(loop)
        elif shell and LOOP_END.match(text) and loops:
            loops.pop()
        for command in SEPARATORS.split(text):
            tool = finding_for(command, shell)
            if tool and not any(reruns(loop, command) for loop in active):
                yield number, tool


def yaml_run_blocks(lines):
    index = 0
    while index < len(lines):
        match = RUN_KEY.match(lines[index])
        index += 1
        if not match:
            continue
        key_indent = len(match.group(1)) + len(match.group(2) or "")
        rest = match.group(3)
        if rest[:1] in ("|", ">"):
            block = []
            while index < len(lines):
                line = lines[index]
                if line.strip() and len(line) - len(line.lstrip()) <= key_indent:
                    break
                block.append((index + 1, line))
                index += 1
            yield block
        elif rest:
            if len(rest) > 1 and rest[0] in "\"'" and rest[-1] == rest[0]:
                rest = rest[1:-1]
            yield [(index, rest)]


def findings_in(path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    shell = path.suffix in SHELL_SUFFIXES
    if path.suffix in (".yml", ".yaml"):
        blocks = yaml_run_blocks(lines)
    else:
        blocks = [list(enumerate(lines, 1))]
    for block in blocks:
        for number, tool in scan_block(block, shell):
            need = "--retry N" if tool == "curl" else "--tries=N"
            yield f"{path}:{number}: {tool} needs {need}"


def folder_files(folder):
    for root, dirs, names in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            if Path(name).suffix in SUFFIXES:
                yield Path(root, name)


def collect_files(paths):
    """(path, named) pairs: a file given on the command line is named, one found in a folder is not."""
    files = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files += [(p, False) for p in folder_files(path)]
        elif path.is_file():
            files.append((path, True))
        else:
            raise FileNotFoundError(f"{raw}: no such file or folder")
    return files


def file_findings(path, named):
    try:
        return list(findings_in(path))
    except UnicodeDecodeError:
        if named:
            raise
        return []


def main(argv):
    paths = argv or [p for p in DEFAULT_PATHS if Path(p).is_dir()]
    try:
        found = [line for path, named in collect_files(paths) for line in file_findings(path, named)]
    except (OSError, UnicodeDecodeError) as err:
        print(f"download_retry_check: {err}", file=sys.stderr)
        return 2
    if found:
        print("\n".join(found))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
