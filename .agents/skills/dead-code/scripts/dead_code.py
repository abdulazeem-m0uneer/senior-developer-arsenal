#!/usr/bin/env python3
"""Find dead code a change adds or leaves behind, in any language, with regexes and git only.

Usage:
  python3 dead_code.py --diff [<ref>]   # default ref: the merge-base of HEAD and origin/HEAD
Prints one `path:line kind name` line per finding. Exit codes: 1 findings, 0 clean, 2 usage or git error.

Library (hooks/guard.py imports it through sys.path, so the Stop gate and the dead-code skill share it):
  findings(root, sha, ignore, is_source) -> [Finding(path, line, kind, name, note)]
reads `git diff -U0 -M <sha>` (the working tree against the commit; "" means no commit yet) plus the full text
of untracked files, keeps the paths `is_source` accepts and `ignore` does not hold, and reports:
  commented-out   an added comment whose body is shaped like code (a run of such lines is one finding)
  debug-leftover  an added debugger statement or breakpoint call (never print or console.log)
  unreferenced    a file-local function or constant defined on an added line whose name occurs once in the
                  repository (`git grep -w`). Never an exported, public or overriding name, a method of self, a
                  class, a field or an annotated definition: frameworks, serializers and other packages call those.
  orphaned        a name called on a removed line that now occurs once in its own file (strings aside), on an
                  import line, or on a definition line whose name also occurs once in the repository
At most MAX_PER_KIND findings per kind, counted after filtering. The scan is skipped (no findings) past MAX_FILES
files, MAX_ADDED added or MAX_REMOVED removed lines, and one time budget covers the git calls and the scan itself.
Any git error, timeout or spent budget means no findings: callers fail open. Standard library only.
"""
import codecs
import os
import re
import subprocess
import sys
import time
from collections import Counter, namedtuple
from pathlib import Path

Finding = namedtuple("Finding", "path line kind name note", defaults=("",))

MAX_PER_KIND = 40
MAX_FILES = 200
MAX_ADDED = 5000
MAX_REMOVED = 5000
MAX_FILE_BYTES = 1_000_000
MAX_LINE = 1000  # a longer line is minified or generated: no pattern runs on it
GIT_TIMEOUT = 2
BUDGET = 1.5
SNIPPET = 40
GREP_CHUNK = 200  # names per `git grep` call
LOOKBACK = 10  # lines above a definition searched for its decorator or attribute
KINDS = ("commented-out", "debug-leftover", "unreferenced", "orphaned")

HASH = frozenset("py rb ex exs".split())
SLASH = frozenset("js jsx mjs cjs ts tsx mts cts vue svelte cs fs go rs java kt kts scala groovy swift dart "
                  "c h cc cpp cxx hpp m mm".split())
DASH = frozenset(("lua",))
PHP = "php"  # // and #
MARKUP = frozenset("vue svelte".split())  # templates also take <!-- -->
JS = frozenset("js jsx mjs cjs ts tsx mts cts vue svelte".split())

# Unrolled string patterns: linear in the line, whatever quotes and backslashes it holds.
QUOTED = re.compile(r"'[^'\\\n]*(?:\\.[^'\\\n]*)*'|\"[^\"\\\n]*(?:\\.[^\"\\\n]*)*\"|`[^`\n]*`")
PRAGMA = re.compile(
    r"noqa|eslint-(?:disable|enable)|type:\s*ignore|pylint:|mypy:|pyright:|isort:|fmt:\s*(?:on|off)|"
    r"prettier-ignore|istanbul|c8\s|ts-(?:ignore|expect-error|nocheck)|nolint|NOSONAR|pragma|coding[:=]|"
    r"licen[cs]e|copyright|SPDX-|all rights reserved|"
    r"^#?\s*(?:end)?region\b|^\s*-\*-|^\s*@|^(?:TODO|FIXME|XXX|HACK|NOTE|BUG)\b", re.I)
KEYWORDS = "return|if|for|const|let|var|def|class|import|function|public|private"
KEYWORD_CODE = re.compile(
    rf"^(?:{KEYWORDS})\b\s*[\w.$]*[(=\[;<{{]"                    # if (x, return foo(, def foo(
    r"|^(?:const|let|var)\s+[\w$]+\s*=[^=]"                       # const x = 1
    r"|^(?:if|elif|while)\b.*[<>=!(\[].*:$"                       # if total > 0:
    r"|^for\s+[\w, ()]+\s+in\s+\S.*:$"                            # for item in items:
    r"|^(?:def|class)\s+\w+\s*(?:\(.*\))?\s*:$"                   # class Foo:
    r"|^(?:class|interface|struct|enum|trait)\s+\w+.*\{$"          # class Foo extends Bar {
    r"|^import\s+[\w.]+(?:\s+as\s+\w+)?;?$"                       # import os
    r"|^import\s+(?:[\w$]+\s*,?\s*)?(?:\{[^}]*\}|\*\s+as\s+\w+)?\s*from\s+['\"][^'\"]+['\"];?$"
    r"|^from\s+[\w.]+\s+import\s+[\w*, ()]+$")
CODE_TOKEN = re.compile(r"[\w$\])]\(|[^=!<>]=[^=]|:=|!=|==|<=|>=|&&|\|\||\w\.[A-Za-z_$]|->|::|\w\[")
ASSIGN_OR_CALL = re.compile(  # one-line code with no terminator: Go, Python, Kotlin, Ruby, Rust
    r"^(?:(?:(?:val|var|let|const|mut|auto|final)\s+)*[\w$.\[\]]+\s*(?::\s*[\w<>?\[\], ]+)?\s*(?::=|[-+*/]?=)"
    r"\s*[\w$\"'(\[{-].*|[\w$.]+\(.*\);?|return\s+[\w$.]+\(.*\);?)$")
CLOSING_CODE = re.compile(r"[\w$\])]\(|[^=!<>]=[^=]|\w\.[A-Za-z_$]")
DEBUG = [
    (re.compile(r"^\s*debugger\s*;?\s*$"), "debugger"),
    (re.compile(r"\bbreakpoint\(\s*\)"), "breakpoint()"),
    (re.compile(r"\b(?:i?pdb)\.set_trace\("), "pdb.set_trace"),
    (re.compile(r"^\s*import\s+i?pdb\b"), "import pdb"),
    (re.compile(r"\bbinding\.pry\b"), "binding.pry"),
    (re.compile(r"^\s*byebug\b"), "byebug"),
    (re.compile(r"\bdbg!\("), "dbg!"),
    (re.compile(r"\bvar_dump\("), "var_dump"),
    (re.compile(r"\bDebugger\.Break\(\s*\)"), "Debugger.Break()"),
    (re.compile(r"\bruntime\.Breakpoint\(\s*\)"), "runtime.Breakpoint()"),
]
PHP_DD = re.compile(r"(?<![\w$>:])dd\(")  # dd() is Laravel's dump-and-die only in PHP
DOCTEST = re.compile(r"^\s*(?:>>>|\.\.\.)\s")
# File-local definitions only, per language family: a name another package, a framework or a serializer can
# reach (exported, public, a class, a field) is never reported as unreferenced.
LOCAL_DEFINITIONS = {
    "py": [re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(")],
    "js": [re.compile(r"(?:^|[\s(=:,])function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\("),
           re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=[^=>]")],
    "go": [re.compile(r"^func\s+(?:\([^)]*\)\s*)?([a-z_]\w*)\s*[(\[]")],
    "rs": [re.compile(r"^\s*(?:async\s+)?(?:const\s+)?(?:unsafe\s+)?fn\s+(\w+)")],
    "kt": [re.compile(r"\bprivate\s+(?:\w+\s+)*fun\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?(\w+)\s*\(")],
    "swift": [re.compile(r"\b(?:private|fileprivate)\s+(?:\w+\s+)*func\s+(\w+)")],
    "java": [re.compile(r"^\s*(?:\w+\s+)*private\s+(?:(?:static|async|final|readonly|unsafe)\s+)*"
                        r"[\w<>\[\],.?]+\s+(\w+)\s*\(")],
    "php": [re.compile(r"^\s*(?:(?:private|static)\s+)*function\s+(\w+)\s*\(")],
    "c": [re.compile(r"^static\s+(?:inline\s+)?[\w\s*]+?\b(\w+)\s*\(")],
    "lua": [re.compile(r"^\s*local\s+function\s+(\w+)")],
    "dart": [re.compile(r"^\s*[\w<>?]+\s+(_\w+)\s*\(")],
    "ex": [re.compile(r"^\s*defp\s+(\w+)")],
}
FAMILY = {**{ext: "js" for ext in JS}, "py": "py", "go": "go", "rs": "rs", "kt": "kt", "kts": "kt",
          "swift": "swift", "cs": "java", "java": "java", "groovy": "java", "scala": "java", "php": "php",
          "c": "c", "h": "c", "cc": "c", "cpp": "c", "cxx": "c", "hpp": "c", "lua": "lua", "dart": "dart",
          "ex": "ex", "exs": "ex"}
EXPORTED = re.compile(r"\b(?:export|public|pub|open|protected|internal|override|abstract|virtual|extern)\b")
SELF_PARAM = re.compile(r"\(\s*(?:&\s*(?:mut\s+)?|\*)?(?:self|cls|this)\b")
ANNOTATION = ("@", "#[", "#![", "[")
# Any definition, for the orphaned check (its repo-wide count of 1 is the evidence there, not the kind).
ANY_DEFINITION = [
    re.compile(r"^\s*(?:async\s+)?def\s+(\w+)"),
    re.compile(r"\bfunction\s*\*?\s*([A-Za-z_$][\w$]*)\s*\("),
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:const|let|var|val)\s+([A-Za-z_$][\w$]*)\s*[=:]"),
    re.compile(r"^\s*(?:export\s+)?(?:\w+\s+)*(?:class|interface|enum|struct|trait|record)\s+(\w+)"),
    re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)"),
    re.compile(r"\bfn\s+(\w+)"),
    re.compile(r"\bfun\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?(\w+)\s*\("),
    re.compile(r"^\s*(?:(?:public|private|protected|internal|static|readonly|override|virtual|abstract|sealed|async|"
               r"final|open|suspend|inline|extern|unsafe|partial|const|new)\s+)+(?:[\w<>\[\],.?]+\s+)?(\w+)\s*[({=;]"),
]
IMPORT_LINE = re.compile(r"^\s*(?:import\b|from\s+\S+\s+import\b|using\s+(?:static\s+)?[\w.]+\s*(?:=\s*[\w.]+\s*)?;"
                         r"|use\s+[\w:{}, ]+;|#include\b|(?:const|let|var)\s+.*=\s*require\s*\()")
IMPORT_OPEN = re.compile(r"^\s*(?:from\s+\S+\s+import\s*\(|import\s*\(|import\s+(?:type\s+)?\{|use\s+[\w:]+::\{)")
IDENT = re.compile(r"[A-Za-z_$][\w$]*")
CALL = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)(?:\s*(?:\.|::|->)\s*[A-Za-z_$][\w$]*)*\s*\(")  # json.dumps( -> json
NOT_CALLS = frozenset("if for while switch catch return function def class new typeof sizeof await yield elif "
                      "with assert lambda not and or in is print super this self base".split())
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class GitError(Exception):
    """A git call failed or timed out, or the scan's time budget is spent: the result is no findings."""


class Clock:
    """One time budget shared by every git call and every scanned line of a scan."""

    def __init__(self, budget, timeout):
        self.deadline, self.timeout = time.monotonic() + budget, timeout

    def check(self):
        if time.monotonic() > self.deadline:
            raise GitError("time budget spent")

    def git(self, root, *args, ok=(0,), stdin=None):
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise GitError("time budget spent")
        try:
            out = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=root, capture_output=True,
                                 input=stdin, timeout=min(self.timeout, left))
        except (OSError, subprocess.SubprocessError) as error:
            raise GitError(str(error)) from error
        if out.returncode not in ok:
            raise GitError(os.fsdecode(out.stderr).strip() or f"git {args[0]} exited {out.returncode}")
        return os.fsdecode(out.stdout)


def extension(path):
    return path.rpartition(".")[2].lower() if "." in path.rpartition("/")[2] else ""


def lines_of(text):
    """Lines as git numbers them: split on newlines only (a form feed inside a line stays in it)."""
    lines = text.split("\n")
    return lines[:-1] if lines and lines[-1] == "" else lines


def comment_body(text, ext, in_block):
    """(body or None, block state) for one line; body None: not a comment; "" for documentation, never code.

    The block state is False outside a block comment, "code" inside /* */ or <!-- -->, "doc" inside /** */,
    whose examples are documentation."""
    stripped = text.strip()
    slash = ext in SLASH or ext == PHP
    if in_block:
        end = stripped.find("*/") if slash else stripped.find("-->")
        body = stripped[:end] if end >= 0 else stripped
        state = in_block if end < 0 else False
        return ("" if in_block == "doc" else body.lstrip("*").strip()), state
    if slash and stripped.startswith("/*"):
        end = stripped.find("*/", 2)
        doc = stripped.startswith("/**") and not stripped.startswith("/**/")
        state = ("doc" if doc else "code") if end < 0 else False
        return ("" if doc else stripped[2:end if end >= 0 else None].lstrip("*").strip()), state
    if ext in MARKUP and stripped.startswith("<!--"):
        end = stripped.find("-->", 4)
        return stripped[4:end if end >= 0 else None].strip(), "code" if end < 0 else False
    if slash and stripped.startswith(("///", "//!")):
        return "", False  # Rust, C# and Swift documentation comments: their examples are not dead code
    if slash and stripped.startswith("//"):
        return stripped[2:].strip(), False
    if (ext in HASH or ext == PHP) and stripped.startswith("#") and not stripped.startswith(("#!", "#[")):
        return stripped.lstrip("#").strip(), False
    if ext in DASH and stripped.startswith("--"):
        return stripped.lstrip("-").strip(), False
    return None, False


def code_text(text):
    """The line with string literals blanked: a pattern inside a string is data, not code."""
    return QUOTED.sub('""', text)


def prose_or_pragma(body):
    return not body or "://" in body or bool(PRAGMA.search(body))


def is_code_shaped(body):
    if prose_or_pragma(body):
        return False
    code = code_text(body)
    if KEYWORD_CODE.search(body) or ASSIGN_OR_CALL.search(code):
        return True
    return code.endswith((";", "{")) and bool(CODE_TOKEN.search(code))


def closes_code(body):
    return not prose_or_pragma(body) and body.endswith((")", "}", "):")) and bool(CLOSING_CODE.search(code_text(body)))


def local_definition(text, ext):
    """The name a line defines when nothing outside the file can call it by convention, else None."""
    if EXPORTED.search(text) or SELF_PARAM.search(text):
        return None
    for pattern in LOCAL_DEFINITIONS.get(FAMILY.get(ext, ""), ()):
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def any_definition(text):
    for pattern in ANY_DEFINITION:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def skipped_name(name):
    return (len(name) <= 3 or name in ("main", "Main") or name.startswith(("test", "Test"))
            or name.startswith("__") and name.endswith("__"))


def annotated(lines, number):
    """True when a decorator or attribute (possibly spanning several lines) sits above the definition."""
    for index in range(number - 2, max(number - 2 - LOOKBACK, -1), -1):
        above = lines[index].strip() if index < len(lines) else ""
        if not above:
            return False
        if above.startswith(ANNOTATION):
            return True
        if above.endswith((";", "{", "}")) or any_definition(above):
            return False
    return False


def unquote(path):
    """A diff header path, with git's C-style quoting undone; None when it cannot be decoded."""
    if len(path) >= 2 and path[0] == path[-1] == '"':
        try:
            return codecs.escape_decode(path[1:-1].encode("utf-8"))[0].decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
    return path


def parse_diff(text):
    """{path: {"added": [(line, text)], "removed": [text]}} from `git diff -U0 --dst-prefix=b/` output."""
    files, current, header, new_line = {}, None, False, 0
    for raw in text.split("\n"):
        if raw.startswith("diff --git "):
            current, header = None, True
        elif header and raw.startswith("+++ "):
            target = unquote(raw[4:].rstrip("\t"))
            current = None if target in (None, "/dev/null") or not target.startswith("b/") else files.setdefault(
                target[2:], {"added": [], "removed": []})
        elif raw.startswith("@@") and (header or current is not None):
            header = False
            match = HUNK.match(raw)
            new_line = int(match.group(1)) if match else 0
        elif header or current is None:
            continue  # file headers: only between `diff --git` and the first hunk, so a removed "-- x" is content
        elif raw.startswith("+"):
            current["added"].append((new_line, raw[1:]))
            new_line += 1
        elif raw.startswith("-"):
            current["removed"].append(raw[1:])
    return files


def read_text(root, path):
    """The file's text, or None when it is missing, too large or binary."""
    try:
        data = (Path(root) / path).read_bytes()
    except OSError:
        return None
    if len(data) > MAX_FILE_BYTES or b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def commented_out(clock, path, ext, added):
    """One finding per run of consecutive added comment lines that look like code."""
    found, run, in_block, last = [], [], False, None

    def flush():
        shaped = [index for index, (_, body) in enumerate(run) if is_code_shaped(body)]
        closing = [index for index, (_, body) in enumerate(run) if closes_code(body)]
        code = shaped + (closing if len(closing) >= 2 else [])
        if code:
            first = min(code)
            found.append(Finding(path, run[first][0], "commented-out", " ".join(run[first][1].split())[:SNIPPET]))
        run.clear()

    for number, text in added:
        clock.check()
        if last is not None and number != last + 1:
            flush()
            in_block = False
        last = number
        if len(text) > MAX_LINE:
            flush()
            continue
        body, in_block = comment_body(text, ext, in_block)
        if body is None:
            flush()
        else:
            run.append((number, body))
    flush()
    return found


def debug_leftovers(clock, path, ext, added):
    found = []
    for number, text in added:
        clock.check()
        if len(text) > MAX_LINE or DOCTEST.match(text) or comment_body(text, ext, False)[0] is not None:
            continue
        code = code_text(text)
        for pattern, name in DEBUG + ([(PHP_DD, "dd()")] if ext == PHP else []):
            if pattern.search(code):
                found.append(Finding(path, number, "debug-leftover", name))
                break
    return found


def definitions_added(clock, path, ext, added, lines):
    """(path, line, name) for file-local definitions on added lines."""
    found, in_block = [], False
    for number, line in added:
        clock.check()
        if len(line) > MAX_LINE:
            continue
        body, in_block = comment_body(line, ext, in_block)
        if body is not None or in_block:
            continue
        name = local_definition(code_text(line), ext)
        if name and not skipped_name(name) and not annotated(lines, number):
            found.append((path, number, name))
    return found


def identifier_index(clock, lines):
    """{name: (occurrences outside strings, line numbers holding it anywhere)} and the import line numbers."""
    counts, where, imports, open_import = Counter(), {}, set(), False
    for number, line in enumerate(lines, 1):
        clock.check()
        if len(line) > MAX_LINE:
            continue
        is_import = open_import or bool(IMPORT_LINE.search(line))
        if open_import:
            open_import = not re.search(r"[)}]", line)
        elif is_import and IMPORT_OPEN.search(line):
            open_import = not re.search(r"[)}]\s*(?:from\b.*)?;?\s*$", line)
        if is_import:
            imports.add(number)
        raw = IDENT.findall(line)
        # an import line counts each name once: `import axios from 'axios'`, Go's `import "strings"`
        counts.update(set(raw) if is_import else IDENT.findall(code_text(line)))
        for name in set(raw):
            where.setdefault(name, set()).add(number)
    return counts, where, imports


def orphaned_candidates(clock, path, ext, removed, lines):
    """(path, line, name, 'import'|'definition') for names a removed call leaves on exactly one line of the file."""
    called = {}
    for text in removed:
        clock.check()
        if len(text) > MAX_LINE or comment_body(text, ext, False)[0] is not None:
            continue
        for name in CALL.findall(code_text(text)):
            if name not in NOT_CALLS and not (name.startswith("__") and name.endswith("__")):
                called[name] = True
    if not called:
        return []
    counts, where, imports = identifier_index(clock, lines)
    candidates = []
    for name in called:
        if counts[name] != 1 or len(where.get(name, ())) != 1:
            continue
        (number,) = where[name]
        if number in imports:
            candidates.append((path, number, name, "import"))
        elif any_definition(code_text(lines[number - 1])) == name:
            candidates.append((path, number, name, "definition"))
    return candidates


def repo_counts(clock, root, names):
    """Whole-word occurrences of each name across tracked and untracked files (strings included: conservative)."""
    counts = Counter()
    ordered = sorted(names)
    for start in range(0, len(ordered), GREP_CHUNK):
        args = ["grep", "-I", "-w", "-o", "-h", "-F", "--untracked"]
        for name in ordered[start:start + GREP_CHUNK]:
            args += ["-e", name]
        out = clock.git(root, *args, "--", ok=(0, 1))
        counts.update(line.strip() for line in out.split("\n") if line.strip())
    return counts


def changed_files(clock, root, sha, ignore, is_source):
    """{path: change} for the source files the working tree adds or changes against the commit."""
    base = sha or clock.git(root, "hash-object", "-t", "tree", "--stdin", stdin=b"").strip()
    diff = clock.git(root, "-c", "core.fileMode=false", "diff", "-U0", "-M", "--no-color", "--no-ext-diff",
                     "--src-prefix=a/", "--dst-prefix=b/", "--ignore-submodules", "--diff-filter=AMR", base)
    files = parse_diff(diff)
    for path in clock.git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if path:
            files.setdefault(path, {"added": [], "removed": [], "new": True})
    skip = set(ignore)
    return {path: change for path, change in files.items() if path not in skip and is_source(path)}


def scan(root, sha, ignore=(), is_source=lambda path: True, budget=BUDGET, git_timeout=GIT_TIMEOUT,
         max_files=MAX_FILES, max_added=MAX_ADDED, max_removed=MAX_REMOVED):
    """Findings for the working tree against the commit; raises GitError. A max of None: no size skip."""
    clock = Clock(budget, git_timeout)
    files = changed_files(clock, root, sha, ignore, is_source)
    if max_files is not None and len(files) > max_files:
        return []  # before any file is read: a huge untracked tree must cost nothing
    contents = {path: read_text(root, path) for path in files}
    for path, change in files.items():
        if change.get("new"):
            text = contents[path]
            change["added"] = list(enumerate(lines_of(text), 1)) if text is not None else []
    if max_added is not None and sum(len(change["added"]) for change in files.values()) > max_added:
        return []
    if max_removed is not None and sum(len(change["removed"]) for change in files.values()) > max_removed:
        return []
    found = {kind: [] for kind in KINDS}
    definitions, orphans = [], []
    for path, change in sorted(files.items()):
        ext, text = extension(path), contents[path]
        if text is None:
            continue
        lines = lines_of(text)
        found["commented-out"] += commented_out(clock, path, ext, change["added"])
        found["debug-leftover"] += debug_leftovers(clock, path, ext, change["added"])
        definitions += definitions_added(clock, path, ext, change["added"], lines)
        orphans += orphaned_candidates(clock, path, ext, change["removed"], lines)
    counts = repo_counts(clock, root, {name for _, _, name in definitions}
                         | {name for _, _, name, note in orphans if note == "definition"})
    found["unreferenced"] = [Finding(path, line, "unreferenced", name)
                             for path, line, name in definitions if counts[name] <= 1]
    found["orphaned"] = [Finding(path, line, "orphaned", name, note) for path, line, name, note in orphans
                         if note == "import" or counts[name] <= 1]
    return [finding for kind in KINDS for finding in found[kind][:MAX_PER_KIND]]


def findings(root, sha, ignore=(), is_source=lambda path: True, budget=BUDGET, git_timeout=GIT_TIMEOUT):
    """scan() that fails open: any git error, timeout, spent budget or unreadable input means no findings."""
    try:
        return scan(root, sha, ignore, is_source, budget, git_timeout)
    except (GitError, OSError, ValueError):
        return []


def describe(finding):
    """`a.py:12 commented-out`, `b.ts:40 orphaned import foo`, `c.go:3 unreferenced helper`."""
    if finding.kind == "commented-out":
        return f"{finding.path}:{finding.line} commented-out"
    note = f" {finding.note}" if finding.note else ""
    return f"{finding.path}:{finding.line} {finding.kind}{note} {finding.name}"


def key(finding):
    return f"{finding.path}:{finding.kind}:{finding.name}"


def source_filter():
    """guard.kind from the hooks shipped beside the skills (plugin: <root>/hooks; installer: <dir>/arsenal-hooks)."""
    here = Path(__file__).resolve().parents
    for hooks in (here[4] / "hooks" if len(here) > 4 else None, here[3] / "arsenal-hooks"):
        if hooks and (hooks / "guard.py").is_file():
            sys.path.insert(0, str(hooks))
            try:
                import guard
            except (Exception, SystemExit):  # guard exits 0 on a broken install
                return None
            return lambda path: guard.kind(path) == "source"
    return None


def main(argv):
    args = argv[1:]
    if not args or args[0] != "--diff" or len(args) > 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    is_source = source_filter()
    if is_source is None:
        print("dead_code: hooks/guard.py not found beside the skills", file=sys.stderr)
        return 2
    try:
        top = Clock(10, 10).git(os.getcwd(), "rev-parse", "--show-toplevel").strip()
        ref = args[1] if len(args) == 2 else Clock(10, 10).git(top, "merge-base", "HEAD", "origin/HEAD").strip()
        sha = Clock(10, 10).git(top, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()
        result = scan(top, sha, (), is_source, budget=120, git_timeout=60,
                      max_files=None, max_added=None, max_removed=None)
    except GitError as error:
        print(f"dead_code: {error}", file=sys.stderr)
        return 2
    for finding in result:
        print(describe(finding))
    return 1 if result else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
