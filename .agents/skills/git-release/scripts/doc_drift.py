#!/usr/bin/env python3
"""Before a release: find public surface the change added that the docs never mention, and documented surface the
change removed from the code.

Usage:
  python3 doc_drift.py <base-ref> [--docs PATH ...] [--json]
Run inside the repository. Compares the working tree (committed, staged, unstaged and untracked) with <base-ref>.
Prints `undocumented <kind> <name> <file>:<line>` and `stale <kind> <name> <doc>:<line>` lines (or JSON).
Exit codes: 1 drift found, 0 clean, 2 usage or git error (not a repository, unknown ref).

Surface kinds, read from added and removed code lines (docs and test files excluded):
  flag    argparse add_argument, commander and yargs option, System.CommandLine Option, Go flag.String and kin
  env     os.environ / os.getenv, process.env, Environment.GetEnvironmentVariable, os.Getenv, env::var, ENV[], getenv
  route   Express/Fastify app.get and kin, Flask/FastAPI decorators, ASP.NET HttpGet attributes and MapGet,
          Go HandleFunc and gin r.GET
  export  JavaScript/TypeScript `export function|const|class|...` and Python __all__ entries
  config  config.get, settings.get, config[key], Configuration[key], GetValue<T>, viper.Get*
Comment lines (#, //, /*, *) are skipped: an example in a comment is not surface.
Docs: README* and *.md at the root (CHANGELOG* excluded: it records history), docs/**/*.md, and every --docs path.
A route matches docs that write its parameters as :id, {id} or <id>. Standard library only.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

Item = namedtuple("Item", "kind name literal path line")
Drift = namedtuple("Drift", "status kind name path line")

CODE_EXT = frozenset("py js jsx mjs cjs ts tsx mts cts cs go rs java kt rb php".split())
TEST_PATH = re.compile(r"(?:^|/)(?:tests?|__tests__|spec|specs)/|(?:^|/)test_[^/]*$|_test\.\w+$|\.(?:test|spec)\.\w+$"
                       r"|Tests?\.\w+$")
GIT_TIMEOUT = 30

FLAG_PATTERNS = [
    re.compile(r"add_argument\(\s*['\"](-{1,2}[\w-]+)['\"](?:\s*,\s*['\"](--[\w-]+)['\"])?"),
    re.compile(r"\.(?:option|requiredOption)\(\s*['\"](-[^'\"]*)['\"]"),       # commander: "-p, --port <n>"
    re.compile(r"\.option\(\s*['\"]([A-Za-z][\w-]*)['\"]"),                     # yargs: option("port")
    re.compile(r"new\s+Option<[^>]*>\(\s*\"(-{1,2}[\w-]+)\""),
    re.compile(r"\bflag\.(?:String|Int|Int64|Bool|Duration|Float64|Uint|Var)\w*\(\s*(?:&\w+\s*,\s*)?\"([\w-]+)\""),
]
ENV_PATTERNS = [
    re.compile(r"os\.environ(?:\.get)?\s*[\[(]\s*['\"]([A-Z][A-Z0-9_]*)['\"]"),
    re.compile(r"\bgetenv\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]"),
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]*)"),
    re.compile(r"process\.env\[\s*['\"]([A-Z][A-Z0-9_]*)['\"]"),
    re.compile(r"GetEnvironmentVariable\(\s*\"([A-Z][A-Z0-9_]*)\""),
    re.compile(r"os\.(?:Getenv|LookupEnv)\(\s*\"([A-Z][A-Z0-9_]*)\""),
    re.compile(r"env::var(?:_os)?\(\s*\"([A-Z][A-Z0-9_]*)\""),
    re.compile(r"\bENV(?:\.fetch\(|\[)\s*['\"]([A-Z][A-Z0-9_]*)['\"]"),
]
ROUTE_PATTERNS = [
    re.compile(r"\b(?:app|router|server|fastify|api|route)\.(?:get|post|put|patch|delete|all)\(\s*['\"`](/[^'\"`]*)"),
    re.compile(r"@\w+\.(?:route|get|post|put|patch|delete|api_route)\(\s*['\"](/[^'\"]*)"),
    re.compile(r"\[(?:Http(?:Get|Post|Put|Patch|Delete)|Route)\(\s*\"([^\"]+)\""),
    re.compile(r"\bMap(?:Get|Post|Put|Patch|Delete|Methods)\(\s*\"(/[^\"]*)\""),
    re.compile(r"\bHandleFunc\(\s*\"(/[^\"]*)\""),
    re.compile(r"\.(?:GET|POST|PUT|PATCH|DELETE)\(\s*\"(/[^\"]*)\""),
]
EXPORT_PATTERNS = [
    re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function\*?|const|let|var|class|interface|type|enum)"
               r"\s+([A-Za-z_$][\w$]*)"),
]
ALL_LIST = re.compile(r"__all__\s*(?:\+)?=\s*[\[(]([^\])]*)")
CONFIG_PATTERNS = [
    re.compile(r"\b(?:config|settings|conf|cfg)\.get\(\s*['\"]([\w.:-]+)['\"]"),
    re.compile(r"\b(?:config|settings|conf|cfg)\[\s*['\"]([\w.:-]+)['\"]\s*\]"),
    re.compile(r"Configuration\[\s*\"([\w:.-]+)\"\s*\]"),
    re.compile(r"GetValue<[^>]*>\(\s*\"([\w:.-]+)\""),
    re.compile(r"viper\.Get\w*\(\s*\"([\w.-]+)\""),
]
ROUTE_PARAM = re.compile(r"(?::\w+|\{[^}/]+\}|<[^>/]+>)")
COMMENT_LINE = re.compile(r"^\s*(?:#(?!\[)|//|/\*|\*)")
HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class GitError(Exception):
    pass


def git(root, *args, ok=(0,)):
    try:
        out = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=root, capture_output=True,
                             timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as error:
        raise GitError(str(error)) from error
    if out.returncode not in ok:
        raise GitError(os.fsdecode(out.stderr).strip() or f"git {args[0]} exited {out.returncode}")
    return os.fsdecode(out.stdout)


def is_code(path):
    return path.rpartition(".")[2].lower() in CODE_EXT and not TEST_PATH.search(path)


def flags_in(text):
    names = []
    for index, pattern in enumerate(FLAG_PATTERNS):
        for match in pattern.finditer(text):
            if index == 1:
                names += re.findall(r"--?[A-Za-z][\w-]*", match.group(1))
            elif index == 2:
                names.append(f"--{match.group(1)}")
            elif index == 4:
                names.append(f"-{match.group(1)}")
            else:
                names += [group for group in match.groups() if group]
    return names


def items_in(line, path, number):
    if COMMENT_LINE.match(line):
        return []
    found = [Item("flag", name.lstrip("-"), name, path, number) for name in flags_in(line)]
    for kind, patterns in (("env", ENV_PATTERNS), ("route", ROUTE_PATTERNS), ("export", EXPORT_PATTERNS),
                           ("config", CONFIG_PATTERNS)):
        for pattern in patterns:
            found += [Item(kind, match.group(1), match.group(1), path, number) for match in pattern.finditer(line)]
    for match in ALL_LIST.finditer(line):
        found += [Item("export", name, name, path, number) for name in re.findall(r"['\"](\w+)['\"]", match.group(1))]
    return found


def parse_diff(text):
    """(added [(path, line, text)], removed [(path, line, text)]) of code files."""
    added, removed, path, old, new, header = [], [], None, 0, 0, False
    for raw in text.split("\n"):
        if raw.startswith("diff --git "):
            path, header = None, True
        elif header and raw.startswith("--- "):
            source = raw[4:].strip().strip('"')
            path = source[2:] if source.startswith("a/") else None
        elif header and raw.startswith("+++ "):
            target = raw[4:].strip().strip('"')
            path = target[2:] if target.startswith("b/") else path
        elif raw.startswith("@@"):
            header = False
            match = HUNK.match(raw)
            old, new = (int(match.group(1)), int(match.group(2))) if match else (0, 0)
        elif header or path is None or not is_code(path):
            continue
        elif raw.startswith("+"):
            added.append((path, new, raw[1:]))
            new += 1
        elif raw.startswith("-"):
            removed.append((path, old, raw[1:]))
            old += 1
    return added, removed


def doc_paths(root, extra):
    paths = []
    for path in sorted(Path(root).glob("*.md")) + sorted(Path(root).glob("README*")):
        if not path.name.upper().startswith("CHANGELOG") and path.is_file():
            paths.append(path)
    paths += sorted(path for path in (Path(root) / "docs").rglob("*.md") if path.is_file())
    for item in extra:
        target = Path(root) / item
        if not target.exists():
            raise OSError(f"no such docs path: {item}")
        paths += sorted(target.rglob("*.md")) if target.is_dir() else [target]
    return list(dict.fromkeys(paths))


def mention_pattern(item):
    if item.kind == "route":
        parts = ROUTE_PARAM.split(item.name)
        body = r"(?::\w+|\{[^}/\s]+\}|<[^>/\s]+>)".join(re.escape(part) for part in parts)
        return re.compile(rf"(?<!\w){body.rstrip('/') or '/'}(?![\w-])")
    if item.kind == "flag":
        return re.compile(rf"(?<![\w-])--?{re.escape(item.name)}(?![\w-])")
    if item.kind == "env":  # docs write $NAME, ${NAME} and %NAME% as often as the bare name
        return re.compile(rf"(?<![\w.-]){re.escape(item.name)}(?![\w-])")
    return re.compile(rf"(?<![\w$.-]){re.escape(item.name)}(?![\w$-])")


def first_mention(docs, item):
    pattern = mention_pattern(item)
    for path, lines in docs:
        for number, line in enumerate(lines, 1):
            if pattern.search(line):
                return path, number
    return None


def still_in_code(root, item):
    """True when the literal still appears in a code file of the working tree (tracked or untracked)."""
    out = git(root, "grep", "-I", "-l", "-F", "-w", "--untracked", "-e", item.literal, "--", ok=(0, 1))
    return any(is_code(path) for path in out.split("\n") if path)


def drift(root, base, extra_docs=()):
    git(root, "rev-parse", "--verify", f"{base}^{{commit}}")
    diff = git(root, "-c", "core.fileMode=false", "diff", "-U0", "--no-color", "--no-ext-diff", "--src-prefix=a/",
               "--dst-prefix=b/", "-M", base)
    added, removed = parse_diff(diff)
    for path in git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if path and is_code(path):
            try:
                text = (Path(root) / path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            added += [(path, number, line) for number, line in enumerate(text.split("\n"), 1)]
    docs = []
    for path in doc_paths(root, extra_docs):
        try:
            docs.append((os.path.relpath(path, root), path.read_text(encoding="utf-8", errors="replace").split("\n")))
        except OSError:
            continue
    new_items = {}
    for path, number, line in added:
        for item in items_in(line, path, number):
            new_items.setdefault((item.kind, item.name), item)
    old_items = {}
    for path, number, line in removed:
        for item in items_in(line, path, number):
            old_items.setdefault((item.kind, item.name), item)
    found = []
    for key, item in sorted(new_items.items()):
        if key in old_items:
            continue  # a moved or edited line: the surface itself is not new
        if first_mention(docs, item) is None:
            found.append(Drift("undocumented", item.kind, item.literal, item.path, item.line))
    for key, item in sorted(old_items.items()):
        if key in new_items:
            continue
        mention = first_mention(docs, item)
        if mention and not still_in_code(root, item):
            found.append(Drift("stale", item.kind, item.literal, mention[0], mention[1]))
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description="Report doc drift against a base ref.")
    parser.add_argument("base")
    parser.add_argument("--docs", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    try:
        root = git(os.getcwd(), "rev-parse", "--show-toplevel").strip()
        found = drift(root, args.base, args.docs)
    except (GitError, OSError) as error:
        print(f"doc_drift: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([item._asdict() for item in found], indent=2))
    else:
        for item in found:
            print(f"{item.status} {item.kind} {item.name} {item.path}:{item.line}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
