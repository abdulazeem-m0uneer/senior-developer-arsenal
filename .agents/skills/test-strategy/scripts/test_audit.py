#!/usr/bin/env python3
"""Audit a test suite for tests that cannot fail, do not run, repeat each other, or only grep the source.

Usage:
  python3 test_audit.py [--json] [--min-dup-chars N] [PATH ...]   # default PATH: the current directory
Prints one `path:line kind name` line per finding (or a JSON list with --json).
Exit codes: 1 findings, 0 clean, 2 usage error (an unreadable path or a bad option).

Kinds:
  no-assertion  a test with no assertion. Counted as an assertion: the language's own forms, and any call whose
                name starts with assert, expect, verify, check, should, must or ensure, or is raises/fail, so a
                custom helper such as verifyInvoice() counts. A helper named otherwise is not seen.
  skipped       an unconditional skip: a skip decorator or attribute, xit/xdescribe, t.Skip, #[ignore],
                markTestSkipped, or pytest.skip/skipTest as the first statement (skipIf-style skips run somewhere)
  focused       .only, fit/fdescribe, focus: true (the rest of the suite silently stops running)
  duplicate     the same normalized body as an earlier test (at least --min-dup-chars characters, default 40)
  source-grep   the test reads a source-code file (the code path is in the read call or on its line), asserts on
                containment, and calls nothing but reads, path and string helpers and assertions
Languages: Python (ast), JavaScript/TypeScript, C#, Java, Kotlin, Go, Rust, PHP, Ruby (regexes). Standard library only.
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

Finding = namedtuple("Finding", "path line kind name")
Test = namedtuple("Test", "line name body skipped focused")

SKIP_DIRS = frozenset("node_modules .git dist build out target bin obj vendor .venv venv __pycache__ coverage "
                      ".next .nuxt .tox .mypy_cache".split())
CODE_EXT = r"(?:py|js|jsx|mjs|cjs|ts|tsx|cs|go|rs|java|kt|kts|rb|php|swift|scala|c|cc|cpp|h|hpp)"
SOURCE_PATH = re.compile(rf"""['"][^'"\n]*\.{CODE_EXT}['"]""")
ASSERT_PREFIX = re.compile(r"(?i)^(?:assert|expect|verify|check|should|must|ensure)|^(?:raises|fail)$")
CALL_NAME = re.compile(r"(?<![\w$])([A-Za-z_$][\w$]*)(?:!\(|\s*\()")  # foo( and Rust macros foo!(
NAMING = [
    (re.compile(r"(?:^|/)(?:test_[^/]*|[^/]*_test)\.py$"), "py"),
    (re.compile(r"(?:\.(?:test|spec)\.[cm]?[jt]sx?$|(?:^|/)__tests__/[^/]+\.[cm]?[jt]sx?$)"), "js"),
    (re.compile(r"Tests?\.cs$"), "cs"),
    (re.compile(r"(?:Tests?|IT)\.java$"), "java"),
    (re.compile(r"Tests?\.kts?$"), "kt"),
    (re.compile(r"_test\.go$"), "go"),
    (re.compile(r"Test\.php$"), "php"),
    (re.compile(r"(?:_spec|_test)\.rb$|(?:^|/)test_[^/]*\.rb$"), "rb"),
    (re.compile(r"\.rs$"), "rs"),  # Rust: any file that holds #[test]
]

# Per language family: test starts, assertion forms, skip and focus markers, file reads, containment checks.
JS_START = re.compile(r"(?<![\w$.])(x|f)?(it|test)(?:\.(only|skip|todo|concurrent|each\s*\([^)]*\)))?\s*\(\s*"
                      r"(['\"`])((?:(?!\4).)*)\4", re.S)
JS_FOCUSED_DESCRIBE = re.compile(r"(?<![\w$.])(?:fdescribe\s*\(|describe\.only\s*\()")
JS_SKIPPED_DESCRIBE = re.compile(r"(?<![\w$.])(?:xdescribe\s*\(|describe\.skip\s*\()")
CS_START = re.compile(r"\[\s*(Fact|Theory|Test|TestMethod|TestCase)\b([^\]]*)\]((?:\s*\[[^\]]*\])*)\s*"
                      r"(?:(?:public|private|internal|async|static|virtual)\s+)*[\w<>\[\],.?]+\s+(\w+)\s*\(")
JVM_START = re.compile(r"@(?:Test|ParameterizedTest|RepeatedTest)\b(?:\([^)]*\))?((?:\s*@[\w.]+(?:\([^)]*\))?)*)\s*"
                       r"(?:(?:public|private|protected|internal|suspend|open)\s+)*(?:void\s+|fun\s+)`?([\w ]+?)`?\s*\(")
GO_START = re.compile(r"^func\s+(Test\w*)\s*\(\s*\w+\s+\*testing\.T\s*\)", re.M)
RS_START = re.compile(r"#\[(?:tokio::)?test(?:\([^)]*\))?\]((?:\s*#\[[^\]]*\])*)\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)")
PHP_START = re.compile(r"((?:#\[Test\]|/\*\*(?:(?!\*/).)*@test(?:(?!\*/).)*\*/)\s*)?"
                       r"(?:public\s+)?(?:static\s+)?function\s+(test\w*|\w+)\s*\(", re.S)
RB_START = re.compile(r"^([ \t]*)(x|f)?(it|specify|scenario|test)\b\s*(?:\(?\s*(['\"])(.*?)\4)?([^\n]*)\bdo\b"
                      r"|^([ \t]*)def\s+(test_\w+)", re.M)
ASSERT_FORMS = {
    "js": re.compile(r"(?<![\w$])(?:expect|assert)\b|\.should\b|\bt\.(?:is|deepEqual|true|false|throws)\b"),
    "cs": re.compile(r"\bAssert\.|\.Should\(|\bVerify\("),
    "jvm": re.compile(r"\bassert\w*\s*\(|\bassertThat\b|\bverify\s*\(|\bshould\w*\b|\bexpect\w*\b"),
    "go": re.compile(r"\bt\.(?:Error|Errorf|Fatal|Fatalf|Fail|FailNow)\b|\b(?:assert|require)\.\w+\("),
    "rs": re.compile(r"\b(?:assert|assert_eq|assert_ne|debug_assert\w*|panic)!|\.unwrap\(\)|\.expect\("),
    "php": re.compile(r"\$this->(?:assert|expect)\w*\(|\bexpect\(|\bself::assert\w*\("),
    "rb": re.compile(r"\b(?:expect|assert\w*|refute\w*|must_\w+|wont_\w+)\b|\.should\b"),
}
SKIP_IN_BODY = {
    "go": re.compile(r"\bt\.(?:Skip|Skipf|SkipNow)\("),
    "php": re.compile(r"\$this->markTest(?:Skipped|Incomplete)\("),
    "rb": re.compile(r"^\s*(?:skip|pending)\b", re.M),
    "cs": re.compile(r"\bAssert\.(?:Ignore|Inconclusive)\("),
}
READS_SOURCE = re.compile(r"readFileSync|readFile\(|File\.ReadAllText|ReadAllLines|os\.ReadFile|ioutil\.ReadFile|"
                          r"fs::read_to_string|include_str!|File\.read|IO\.read|file_get_contents|Files\.read\w*")
CONTAINS = re.compile(r"toContain|toMatch|includes\(|Contains\(|strings\.Contains|\.contains\(|"
                      r"assertStringContainsString|assertMatchesRegularExpression|\binclude\(|\bmatch\b|=~")
PY_READS = frozenset(("open", "read_text", "read_bytes", "getsource", "getsourcelines"))
PY_CONTAINS = frozenset(("assertIn", "assertNotIn", "assertRegex", "assertNotRegex", "search", "findall",
                         "match", "fullmatch", "count"))
# Calls that only read, build paths, handle strings or assert: a test making nothing but these exercises no code.
PLUMBING = frozenset(
    "open read read_text read_bytes getsource getsourcelines readFileSync readFile ReadAllText ReadAllLines ReadFile "
    "read_to_string include_str file_get_contents readString readAllLines Path of join joinpath resolve parent "
    "with_suffix exists str string String format encode decode lower upper strip trim splitlines split replace len "
    "compile search findall match fullmatch count contains Contains includes toContain toMatch include eq to expect "
    "toBe toEqual Equal True False That is require unwrap print Sprintf Errorf Error Fatalf Fatal".split())
PY_SKIP_DECORATORS = re.compile(r"(?:^|\.)skip$")  # skipIf/skipUnless/skipif run somewhere: not reported


def language_of(path):
    for pattern, language in NAMING:
        if pattern.search(path):
            return language
    return None


def list_files(paths):
    """Repository-relative-or-given paths of candidate test files; raises OSError on a missing path."""
    found = []
    for base in paths:
        if os.path.isfile(base):
            found.append(base)
            continue
        if not os.path.isdir(base):
            raise OSError(f"no such file or directory: {base}")
        listed = git_files(base)
        if listed is None:
            listed = []
            for directory, dirs, names in os.walk(base):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
                listed += [os.path.join(directory, name) for name in names]
        found += [path for path in listed if not any(part in SKIP_DIRS for part in Path(path).parts[:-1])]
    return sorted(dict.fromkeys(path for path in found if language_of(path.replace(os.sep, "/"))))


def git_files(base):
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=base,
                             capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return [os.path.join(base, os.fsdecode(name)) for name in out.stdout.split(b"\0") if name]


# ---------- Python (ast) ----------

def call_name(node):
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""


def dotted(node):
    if isinstance(node, ast.Call):
        node = node.func
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def reads_source(call):
    """True when the call reads source code: getsource, or open()/read_text() on a code-file path literal."""
    name = call_name(call)
    if name in ("getsource", "getsourcelines"):
        return True
    if name not in PY_READS:
        return False
    return any(isinstance(n, ast.Constant) and isinstance(n.value, str) and SOURCE_PATH.search(repr(n.value))
               or isinstance(n, ast.Name) and n.id == "__file__" for n in ast.walk(call))


def python_tests(text):
    tree = ast.parse(text)
    tests = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            body = node.body[1:] if node.body and isinstance(node.body[0], ast.Expr) and isinstance(
                getattr(node.body[0], "value", None), ast.Constant) and isinstance(node.body[0].value.value, str) \
                else node.body
            skipped = any(PY_SKIP_DECORATORS.search(dotted(d)) for d in node.decorator_list)
            first = body[0] if body else None  # an unconditional skip is the first statement itself
            skipped = skipped or (isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
                                  and dotted(first.value) in ("pytest.skip", "self.skipTest"))
            tests.append((node, body, skipped))
    return tests


def python_findings(path, text, min_dup):
    found, seen = [], {}
    for node, body, skipped in python_tests(text):
        line, name = node.lineno, node.name
        if skipped:
            found.append(Finding(path, line, "skipped", name))
        nodes = [n for stmt in body for n in ast.walk(stmt)]
        calls = [call_name(n) for n in nodes if isinstance(n, ast.Call)]
        asserts = any(isinstance(n, (ast.Assert, ast.Raise)) for n in nodes) or any(
            ASSERT_PREFIX.search(c) for c in calls if c) or any(  # subprocess.run(..., check=True) raises on failure
            isinstance(n, ast.keyword) and n.arg == "check" and isinstance(n.value, ast.Constant) and n.value.value is True
            for n in nodes)
        if not asserts and not skipped:
            found.append(Finding(path, line, "no-assertion", name))
        reads_code = any(isinstance(n, ast.Call) and reads_source(n) for n in nodes) and all(
            not c or c in PLUMBING or ASSERT_PREFIX.search(c) for c in calls)
        contains = any(isinstance(n, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in n.ops)
                       for n in nodes) or any(c in PY_CONTAINS for c in calls)
        if reads_code and contains:
            found.append(Finding(path, line, "source-grep", name))
        key = "\n".join(ast.dump(stmt, annotate_fields=False) for stmt in body)
        normalized = "\n".join(ast.unparse(stmt) for stmt in body)
        if len(re.sub(r"\s+", "", normalized)) >= min_dup:
            if key in seen:
                found.append(Finding(path, line, "duplicate", f"{name} (same as line {seen[key]})"))
            else:
                seen[key] = line
    return found


# ---------- brace languages ----------

def block_end(text, start, quotes):
    """Index just past the brace block that opens at or after start; -1 when it never closes."""
    open_at = text.find("{", start)
    if open_at < 0:
        return -1, -1
    depth, index, length = 0, open_at, len(text)
    while index < length:
        char = text[index]
        if char in quotes:
            end = index + 1
            while end < length and text[end] != char:
                end += 2 if text[end] == "\\" else 1
            index = end + 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index)
            index = length if newline < 0 else newline
            continue
        if text.startswith("/*", index):
            close = text.find("*/", index + 2)
            index = length if close < 0 else close + 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return open_at, index + 1
        index += 1
    return open_at, -1


def strip_comments(body):
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    return re.sub(r"//[^\n]*$|^\s*#(?![\[!])[^\n]*$", "", body, flags=re.M)


def line_at(text, offset):
    return text.count("\n", 0, offset) + 1


def test_body(text, match_end, language, quotes):
    """(body, found) for the test whose header ends at match_end; a JS test without a braced body gets its call."""
    open_at = text.find("{", match_end)
    segment = text[match_end:open_at] if open_at >= 0 else ""
    braced = open_at >= 0 and ";" not in segment and len(segment) < 400 and (
        language != "js" or "=>" in segment or "function" in segment)
    if braced:
        open_at, end = block_end(text, match_end, quotes)
        if end >= 0:
            return text[open_at + 1:end - 1], True
    if language == "js":
        stop = text.find(";", match_end)
        return text[match_end:stop if 0 <= stop < match_end + 400 else match_end + 400], True
    return "", False


def brace_tests(text, language):
    """Test(line, name, body, skipped, focused) for one brace-delimited language family."""
    quotes = "\"`" if language == "rs" else "'\"`"
    tests = []
    if language == "js":
        for match in JS_START.finditer(text):
            prefix, modifier = match.group(1), match.group(3) or ""
            body, ok = test_body(text, match.end(), language, quotes)
            if not ok:
                continue
            tests.append(Test(line_at(text, match.start()), match.group(5)[:60], body,
                              prefix == "x" or modifier in ("skip", "todo"), prefix == "f" or modifier == "only"))
        return tests
    starts = {"cs": CS_START, "jvm": JVM_START, "go": GO_START, "rs": RS_START, "php": PHP_START}[language]
    for match in starts.finditer(text):
        if language == "php" and not (match.group(1) or match.group(2).startswith("test")):
            continue
        body, ok = test_body(text, match.end(), language, quotes)
        if not ok:
            continue
        if language == "cs":
            name = match.group(4)
            skipped = bool(re.search(r"\bSkip\s*=", match.group(2))) or bool(re.search(r"\[\s*Ignore\b", match.group(3)))
        elif language == "jvm":
            name, skipped = match.group(2).strip(), bool(re.search(r"@(?:Disabled|Ignore)\b", match.group(1)))
            skipped = skipped or bool(re.search(r"@(?:Disabled|Ignore)\b", text[max(0, match.start() - 200):match.start()]
                                                .rsplit("}", 1)[-1]))
        elif language == "go":
            name, skipped = match.group(1), False
        elif language == "rs":
            name, skipped = match.group(2), bool(re.search(r"#\[ignore\b", match.group(1)))
            if re.search(r"#\[should_panic\b", match.group(1)):
                body += "\npanic!()"  # the attribute is the assertion
        else:
            name, skipped = match.group(2), False
        skipped = skipped or bool(SKIP_IN_BODY.get(language, re.compile(r"(?!x)x")).search(body))
        tests.append(Test(line_at(text, match.start()), name, body, skipped, False))
    return tests


def ruby_tests(text):
    tests, lines = [], text.split("\n")
    for match in RB_START.finditer(text):
        indent = match.group(1) if match.group(1) is not None else match.group(7)
        name = match.group(5) or match.group(8) or match.group(3) or "test"
        start = line_at(text, match.start())
        body = []
        for line in lines[start:]:
            if line.strip() == "end" and len(line) - len(line.lstrip()) == len(indent):
                break
            body.append(line)
        else:
            continue
        rest = match.group(6) or ""
        tests.append(Test(start, name, "\n".join(body), match.group(2) == "x" or bool(SKIP_IN_BODY["rb"].search(
            "\n".join(body))), match.group(2) == "f" or "focus: true" in rest or ":focus" in rest))
    return tests


def generic_findings(path, text, language, min_dup):
    family = {"kt": "jvm", "java": "jvm"}.get(language, language)
    if family == "rs" and "#[test]" not in text and "#[tokio::test" not in text:
        return []
    tests = ruby_tests(text) if family == "rb" else brace_tests(text, family)
    found, seen = [], {}
    if family == "js":
        for pattern, kind in ((JS_FOCUSED_DESCRIBE, "focused"), (JS_SKIPPED_DESCRIBE, "skipped")):
            for match in pattern.finditer(text):
                found.append(Finding(path, line_at(text, match.start()), kind, "describe block"))
    for test in tests:
        if test.focused:
            found.append(Finding(path, test.line, "focused", test.name))
        if test.skipped:
            found.append(Finding(path, test.line, "skipped", test.name))
        body = strip_comments(test.body) if family != "rb" else re.sub(r"(?m)#[^\n]*$", "", test.body)
        code = re.sub(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"", '""', body)
        asserts = bool(ASSERT_FORMS[family].search(code)) or any(
            ASSERT_PREFIX.search(name) for name in CALL_NAME.findall(code))
        if not asserts and not test.skipped:
            found.append(Finding(path, test.line, "no-assertion", test.name))
        reads_code = any(READS_SOURCE.search(line) and SOURCE_PATH.search(line) for line in body.split("\n")) and all(
            name in PLUMBING or ASSERT_PREFIX.search(name) for name in CALL_NAME.findall(code))
        if reads_code and CONTAINS.search(body):
            found.append(Finding(path, test.line, "source-grep", test.name))
        key = re.sub(r"\s+", "", body)
        if len(key) >= min_dup:
            if key in seen:
                found.append(Finding(path, test.line, "duplicate", f"{test.name} (same as line {seen[key]})"))
            else:
                seen[key] = test.line
    return found


def audit_file(path, min_dup):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    language = language_of(path.replace(os.sep, "/"))
    if language == "py":
        try:
            return python_findings(path, text, min_dup)
        except (SyntaxError, ValueError, RecursionError):
            return []
    return generic_findings(path, text, language, min_dup)


def audit(paths, min_dup=40):
    found = []
    for path in list_files(paths):
        found += audit_file(path, min_dup)
    return sorted(found, key=lambda f: (f.path, f.line, f.kind))


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=True, description="Audit a test suite.")
    parser.add_argument("paths", nargs="*", default=["."])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--min-dup-chars", type=int, default=40)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    if args.min_dup_chars < 1:
        print("test_audit: --min-dup-chars must be at least 1", file=sys.stderr)
        return 2
    try:
        found = audit(args.paths, args.min_dup_chars)
    except OSError as error:
        print(f"test_audit: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([f._asdict() for f in found], indent=2))
    else:
        for finding in found:
            print(f"{finding.path}:{finding.line} {finding.kind} {finding.name}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
