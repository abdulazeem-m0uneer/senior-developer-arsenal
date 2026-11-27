#!/usr/bin/env python3
"""Report Playwright locators that match text loosely (substring), the cause of strict-mode violations and wrong rows.

Usage: python3 locator_check.py [<path> ...]
A path is a file or a folder (walked, node_modules skipped; .ts .tsx .js .jsx .mjs .cjs files). Default: the e2e/ and
tests/e2e/ folders under the current directory (none present: a note on stderr, exit 0).
Reported: getByLabel, getByText, getByPlaceholder, getByTitle and getByAltText whose first argument is a string
literal and whose options lack `exact: true`; getByRole('r', { name: '...' }) with a string literal name and options
lacking `exact: true`. A call may span lines. Fine: a RegExp literal, a variable or `new RegExp(..)` argument (may be an
intentional RegExp), a template literal with `${...}` interpolation (a variable; one without is a literal), `exact` given as `{ exact }` or `exact: flag` (may be true), getByRole without name, getByTestId,
locator('#id') and other CSS locators, and calls inside comments. Files in a walked folder that import
@testing-library are skipped (no strict mode there); a file named on the command line is always checked.
Output: "path:line: <call> needs { exact: true } or a test id" per call (line of the call's start).
Exit codes: 0 nothing loose, 1 loose locators found, 2 bad input (missing path, unreadable or non-UTF-8 file).
Standard library only.
"""
import re
import sys
from pathlib import Path

EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
DEFAULT_DIRS = ("e2e", "tests/e2e")
CALL = re.compile(r"\bgetBy(Label|Text|Placeholder|Title|AltText|Role)\s*\(")
EXACT_NOT_FALSE = re.compile(r"\bexact\b(?!\s*:\s*false\b)")
NAME_OPTION = re.compile(r"\bname\s*:\s*(\S)")
LITERAL_START = "'\"`"
TESTING_LIBRARY = "@testing-library"
REGEX_PREV = "(,:{=[!&|?;"


def blank_comments(text):
    """Replace comment characters with spaces (newlines kept) so offsets and lines stay put; strings are respected."""
    out, i, n, quote, prev = [], 0, len(text), None, ""
    while i < n:
        c = text[i]
        if not quote and c == "/" and prev in REGEX_PREV and not text.startswith(("//", "/*"), i):
            end = skip_regex(text, i)
            out.append(text[i:end])
            i, prev = end, "/"
            continue
        if not quote and not c.isspace():
            prev = c
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
            out.append(c)
        elif text.startswith("//", i) or text.startswith("/*", i):
            end = text.find("\n", i) if text[i + 1] == "/" else text.find("*/", i)
            stop = n if end < 0 else (end if text[i + 1] == "/" else end + 2)
            out.append(re.sub(r"[^\n]", " ", text[i:stop]))
            i = stop - 1
        else:
            out.append(c)
        i += 1
    return "".join(out)


def split_args(text, start):
    """Top-level arguments of the call whose '(' is at start - 1, and the index after ')'; None when unterminated."""
    args, depth, i, n, begin, prev = [], 0, start, len(text), start, "("
    while i < n:
        c = text[i]
        if c in "'\"`":
            i = skip_string(text, i)
            prev = c
            continue
        if c == "/" and prev in REGEX_PREV:
            i = skip_regex(text, i)
            prev = "/"
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                args.append(text[begin:i])
                return args, i + 1
            depth -= 1
        elif c == "," and depth == 0:
            args.append(text[begin:i])
            begin = i + 1
        if not c.isspace():
            prev = c
        i += 1
    return None


def skip_string(text, i):
    quote = text[i]
    i += 1
    while i < len(text) and text[i] != quote:
        i += 2 if text[i] == "\\" else 1
    return i + 1


def skip_regex(text, i):
    i += 1
    in_class = False
    while i < len(text) and text[i] != "\n":
        c = text[i]
        if c == "\\":
            i += 1
        elif c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            break
        i += 1
    return i + 1


def blank_strings(text):
    """`text` with the characters inside string literals replaced by spaces, so a key search sees code only."""
    out, i = list(text), 0
    while i < len(text):
        if text[i] in LITERAL_START:
            end = skip_string(text, i)
            out[i + 1:end - 1] = " " * max(end - i - 2, 0)
            i = end
        else:
            i += 1
    return "".join(out)


def is_literal(arg):
    """A quoted string or a template literal with no `${...}` interpolation."""
    if not arg or arg[0] not in LITERAL_START:
        return False
    return not (arg[0] == "`" and "${" in arg[:skip_string(arg, 0)])


def is_loose(kind, args):
    first = args[0].strip() if args else ""
    options = args[1] if len(args) > 1 else ""
    if EXACT_NOT_FALSE.search(blank_strings(options)):
        return False
    if kind != "Role":
        return is_literal(first)
    name = NAME_OPTION.search(options)
    return bool(name) and is_literal(options[name.start(1):].lstrip())


def check_text(text):
    """[(line, call text)] for each loose locator call in text."""
    found = []
    clean = blank_comments(text)
    for match in CALL.finditer(clean):
        parsed = split_args(clean, match.end())
        if parsed is None:
            continue
        args, end = parsed
        if is_loose(match.group(1), args):
            call = " ".join(clean[match.start():end].split())
            found.append((clean.count("\n", 0, match.start()) + 1, call))
    return found


def source_files(path):
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*")
                  if p.suffix in EXTENSIONS and p.is_file() and "node_modules" not in p.parts)


def main(argv):
    if argv:
        paths = [Path(a) for a in argv]
    else:
        paths = [Path(d) for d in DEFAULT_DIRS if Path(d).is_dir()]
    for path in paths:
        if not path.exists():
            print(f"locator_check: no such path: {path}", file=sys.stderr)
            return 2
    findings = []
    if not paths:
        print("locator_check: no e2e/ or tests/e2e/ folder here, nothing to check", file=sys.stderr)
    for path in paths:
        for file in source_files(path):
            try:
                text = file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                print(f"locator_check: cannot read {file}: {exc}", file=sys.stderr)
                return 2
            if path.is_dir() and TESTING_LIBRARY in text:
                continue
            findings += [f"{file}:{line}: {call} needs {{ exact: true }} or a test id"
                         for line, call in check_text(text)]
    if findings:
        print("\n".join(findings))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
