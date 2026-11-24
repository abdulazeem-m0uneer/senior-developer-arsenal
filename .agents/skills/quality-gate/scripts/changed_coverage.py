#!/usr/bin/env python3
"""Coverage of the lines a branch changes, so new code cannot hide behind old tests.

usage: changed_coverage.py --report <lcov.info|cobertura.xml> --base <ref> [--min 90] [--json]

Changed lines: the added and modified lines of `git diff -U0 --no-color <base>...HEAD` (deleted lines do not
count), run at the repository top. Executable lines and their hits come from the report: lcov `DA:<line>,<hits>`
under `SF:<path>`, or Cobertura `<class filename=...><lines><line number=... hits=...>` (format chosen by the
content: an XML report is Cobertura; a UTF-8 byte order mark is skipped). A Cobertura filename is first taken
under each `<sources><source>` folder in turn (a relative one from the report's folder), as coverage.py writes
names relative to its source folder: the first that holds the file names it; when none does, the filename is
matched as below. A changed line is executable when
the report lists it, covered when its hits are above 0 (hits of one line are summed over records; negative
lcov hits count as 0). Only changed files the report lists are measured; the others are named on one "not in
the report" line, so a report from the wrong directory is visible. A path holding a space is read without the
TAB git ends its diff header with. Hunk lines are counted, so an added line that starts with "++ " is content,
not a file header.

Paths: report paths may be absolute or relative to a sub-package. A report path names a file for certain when,
absolute, it lies under the repository top, or, relative and the report lies inside the repository, it joins
the report's folder or one of its parents up to the top into a file of HEAD (`..` resolved: a report in
packages/web/coverage naming ../shared/x.ts is packages/shared/x.ts). Otherwise it is matched, leading `..`
dropped, against every file of HEAD by trailing path components: the shorter path must be a whole suffix of
the longer (src/app.py matches pkg/src/app.py; rc/app.py does not), the longest shared suffix wins, then the
fewest extra components. A tie between files, one of them changed, is reported and skipped (a sub-package
report's src/index.ts in a monorepo with several src/index.ts names no file for sure). A changed file counts
only the report paths that match it best, so an example copy's examples/demo/src/app.py record is not summed
into src/app.py when a src/app.py record exists.

Output: "changed-lines coverage: C/E (P%), minimum M%" and, when under, each file's uncovered changed lines
(at most 20 per file, then "and N more"). --json prints {covered, executable, percent, min, pass, files:
[{path, executable, covered, uncovered}], not_in_report, ambiguous} instead. P is floored (to 0.1 in the text,
0.01 in --json), so a refusal never shows the minimum; pass compares the exact ratio.
Commit first: the diff compares commits, so uncommitted work is not measured.
Exit: 0 at or above --min, or no changed line is executable; 1 under --min; 2 usage error, missing or unreadable
report, or a git error. Standard library only.
"""
import argparse
import json
import os
import posixpath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath

HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
SHOWN_PER_FILE = 20


class Unusable(Exception):
    """The report or git cannot be read: exit 2."""


def git(top, *args):
    try:
        out = subprocess.run(["git", "-C", top, *args], capture_output=True, text=True)
    except OSError as error:
        raise Unusable(f"git: {error}") from error
    if out.returncode:
        raise Unusable(f"git {' '.join(args[:2])} failed: {out.stderr.strip()}")
    return out.stdout


def unquote(path):
    """A path as git prints it in a diff header, with C-style quoting removed."""
    if not (path.startswith('"') and path.endswith('"')):
        return path
    escapes = {"\\\\": "\\", '\\"': '"', "\\t": "\t", "\\n": "\n"}
    return re.sub(r'\\[\\"tn]', lambda match: escapes[match.group(0)], path[1:-1])


def changed_lines(top, base):
    """{repo-relative path: set of added or modified line numbers} of <base>...HEAD."""
    diff = git(top, "-c", "core.quotePath=false", "diff", "-U0", "--no-color", "--no-ext-diff",
               "--src-prefix=a/", "--dst-prefix=b/", f"{base}...HEAD")
    changed, current, hunk_left = {}, None, 0
    for line in diff.splitlines():
        if hunk_left:  # -U0: a hunk is exactly its removed plus added lines ("\ No newline" lines aside)
            hunk_left -= not line.startswith("\\")
        elif line.startswith("+++ "):
            target = unquote(line[4:].removesuffix("\t"))  # git ends a header holding a space with a TAB
            current = target[2:] if target.startswith("b/") else None
        elif match := HUNK.match(line):
            removed, start, count = int(match.group(1) or 1), int(match.group(2)), int(match.group(3) or 1)
            hunk_left = removed + count
            if current and count:
                changed.setdefault(current, set()).update(range(start, start + count))
    return changed


def head_files(top):
    return {name for name in git(top, "ls-tree", "-r", "-z", "--name-only", "HEAD").split("\0") if name}


def parse_lcov(text):
    hits, current = {}, None
    for line in text.splitlines():
        if line.startswith("SF:"):
            current = hits.setdefault(line[3:].strip(), {})
        elif line.startswith("DA:") and current is not None:
            fields = line[3:].split(",")
            if len(fields) >= 2 and fields[0].strip().isdigit() and fields[1].strip().lstrip("-").isdigit():
                number = int(fields[0])
                current[number] = current.get(number, 0) + max(int(fields[1]), 0)
        elif line.startswith("end_of_record"):
            current = None
    return hits


def under_source(filename, sources, report_dir):
    """The real path of the file `filename` names under one of Cobertura's <source> folders (a relative one taken
    from the report's folder), first one holding it; `filename` itself when none does."""
    for source in sources:
        candidate = os.path.join(report_dir, source, filename)  # join keeps an absolute source or filename
        if os.path.isfile(candidate):
            return os.path.realpath(candidate)
    return filename


def parse_cobertura(text, report_dir):
    root = ET.fromstring(text)
    sources = [source.text.strip() for source in root.iter("source") if source.text and source.text.strip()]
    hits = {}
    for element in root.iter("class"):
        filename = element.get("filename")
        if not filename:
            continue
        filename = under_source(filename, sources, report_dir)
        lines = hits.setdefault(filename, {})
        for row in element.findall("lines/line"):
            number, count = row.get("number", ""), row.get("hits", "")
            if number.isdigit() and count.isdigit():
                lines[int(number)] = lines.get(int(number), 0) + int(count)
    return hits


def read_report(path):
    """{report path: {line: hits}}; Unusable when missing, unreadable or empty."""
    try:
        with open(path, encoding="utf-8-sig") as handle:  # .NET tools write a BOM
            text = handle.read()
    except (OSError, UnicodeDecodeError) as error:
        raise Unusable(f"cannot read report {path}: {error}") from error
    try:
        if text.lstrip().startswith("<"):
            hits = parse_cobertura(text, os.path.dirname(os.path.realpath(path)))
        else:
            hits = parse_lcov(text)
    except ET.ParseError as error:
        raise Unusable(f"cannot parse Cobertura report {path}: {error}") from error
    if not hits:
        raise Unusable(f"no coverage records in {path} (expected lcov SF:/DA: lines or Cobertura <class> elements)")
    return hits


def common_suffix(first, second):
    count = 0
    for left, right in zip(reversed(first), reversed(second)):
        if left != right:
            break
        count += 1
    return count


def resolve_for_certain(path, top, report_dir, files):
    """The file of `files` an absolute path under `top`, or a path relative to the report's folder or a parent
    of it up to `top`, names; None when it names none."""
    if PurePosixPath(path).is_absolute():
        candidates = [path]
    else:
        folders, folder = [], report_dir
        while folder and folder.is_relative_to(top):
            folders.append(folder)
            folder = folder.parent if folder != top else None
        candidates = [str(folder / path) for folder in folders]
    for candidate in candidates:
        candidate = PurePosixPath(posixpath.normpath(candidate))
        if candidate.is_relative_to(top) and str(candidate.relative_to(top)) in files:
            return str(candidate.relative_to(top))
    return None


def match_paths(report_paths, changed_paths, files, top, report_dir):
    """({changed path: [report paths]}, [ambiguous report paths]); see "Paths" above."""
    top, report_dir = PurePosixPath(top), PurePosixPath(report_dir)
    by_name = {}
    for path in set(files) | set(changed_paths):
        by_name.setdefault(PurePosixPath(path).name, []).append(PurePosixPath(path).parts)
    scored, ambiguous = {}, []  # scored: {changed path: [(score, report path)]}
    for report_path in report_paths:
        path = report_path.replace("\\", "/")
        certain = resolve_for_certain(path, top, report_dir, files)
        if certain:
            if certain in changed_paths:
                scored.setdefault(certain, []).append(((len(PurePosixPath(certain).parts), 0), report_path))
            continue
        parts = tuple(part for part in PurePosixPath(posixpath.normpath(path)).parts if part not in ("..", "/"))
        candidates = []
        for own in by_name.get(parts[-1] if parts else "", []):
            shared = common_suffix(parts, own)
            if shared == min(len(parts), len(own)):
                candidates.append(((shared, 2 * shared - len(parts) - len(own)), "/".join(own)))
        if not candidates:
            continue
        best = max(score for score, _ in candidates)
        winners = [own for score, own in candidates if score == best]
        if len(winners) > 1:
            if any(own in changed_paths for own in winners):
                ambiguous.append(report_path)
        elif winners[0] in changed_paths:
            scored.setdefault(winners[0], []).append((best, report_path))
    matched = {}
    for path, pairs in scored.items():
        best = max(score for score, _ in pairs)
        matched[path] = [report_path for score, report_path in pairs if score == best]
    return matched, ambiguous


def measure(changed, report, head, top, report_dir):
    matched, ambiguous = match_paths(report, changed, head, top, report_dir)
    files = []
    for path in sorted(matched):
        line_hits = {}
        for report_path in matched[path]:
            for number, count in report[report_path].items():
                line_hits[number] = line_hits.get(number, 0) + count
        executable = sorted(changed[path] & line_hits.keys())
        if executable:
            uncovered = [number for number in executable if line_hits[number] <= 0]
            files.append({"path": path, "executable": len(executable),
                          "covered": len(executable) - len(uncovered), "uncovered": uncovered})
    return files, sorted(set(changed) - set(matched)), sorted(ambiguous)


def render(result):
    lines = []
    if result["not_in_report"]:
        lines.append("changed files not in the report: " + ", ".join(result["not_in_report"]))
    if result["ambiguous"]:
        lines.append("report paths matching several files (skipped): " + ", ".join(result["ambiguous"]))
    if not result["executable"]:
        lines.append("changed-lines coverage: no changed line is executable; pass")
        return "\n".join(lines)
    tenths = 1000 * result["covered"] // result["executable"]  # floored, like percent
    lines.append(f"changed-lines coverage: {result['covered']}/{result['executable']} ({tenths / 10:.1f}%), "
                 f"minimum {result['min']:g}%")
    if not result["pass"]:
        for item in result["files"]:
            if item["uncovered"]:
                shown = ", ".join(str(number) for number in item["uncovered"][:SHOWN_PER_FILE])
                more = len(item["uncovered"]) - SHOWN_PER_FILE
                lines.append(f"  {item['path']}: {shown}" + (f", and {more} more" if more > 0 else ""))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Coverage of the lines a branch changes.")
    parser.add_argument("--report", required=True, help="lcov.info or Cobertura XML")
    parser.add_argument("--base", required=True, help="the ref the branch is compared with (<base>...HEAD)")
    parser.add_argument("--min", type=float, default=90.0, help="minimum percent of changed lines covered")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.min <= 100:
        parser.error("--min must be between 0 and 100")
    try:
        report = read_report(args.report)
        top = os.path.realpath(git(".", "rev-parse", "--show-toplevel").strip())  # compared with the report's folder
        report_dir = os.path.dirname(os.path.realpath(args.report))
        files, not_in_report, ambiguous = measure(changed_lines(top, args.base), report, head_files(top), top,
                                                  report_dir)
    except Unusable as error:
        print(f"changed_coverage: {error}", file=sys.stderr)
        return 2
    covered, executable = sum(f["covered"] for f in files), sum(f["executable"] for f in files)
    percent = 100.0 * covered / executable if executable else 100.0
    floored = 10000 * covered // executable / 100 if executable else 100.0  # never shows the minimum when under
    result = {"covered": covered, "executable": executable, "percent": floored, "min": args.min,
              "pass": not executable or percent >= args.min, "files": files, "not_in_report": not_in_report,
              "ambiguous": ambiguous}
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
