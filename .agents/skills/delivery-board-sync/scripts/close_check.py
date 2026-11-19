#!/usr/bin/env python3
"""Close check: a tracker task is completed only with a comment that proves each of its closing criteria.

Usage:
  close_check.py template --criteria FILE              # print the comment skeleton to fill in
  close_check.py check --criteria FILE --comment FILE  # exit 0 when the comment closes every criterion
  (FILE may be "-" for stdin, once.)
The criteria file holds one closing criterion per line: the task's done line and anything the requester listed.
A line may start with an id ("C1 ", "C1: ", "AC-2 "); "#" lines and blank lines are skipped. Two criteria with the
same id or the same text are refused: one comment line could close both.
The comment starts with "CLOSE CHECK:" and holds one line per criterion, "- <id or the criterion's text>:
<evidence>" (bullets -, *, +, •, "1." or "1)"; an id may be written with or without its dash). Evidence is
something a reader can open or re-run: a commit SHA (7 to 40 hex digits with at least one digit), a pull request or
issue number (#123), a URL, a passing test count ("41 passed", "12/12"), a release tag (v1.4.2) or a run id ("run
123456789"). A line that says the work is not done ("not done", "pending", "TODO", "failed", "unmerged" ...) closes
nothing, and neither does the template's placeholder. A criterion that is not done is not closed: the task stays
open, or the open part becomes its own task. What the script cannot know is whether the SHA or the pull request
exists and holds the work: the reader checks that; the script only makes the claim checkable.
Exit codes: 0 closes; 1 a criterion is missing or has no evidence, or the comment does not start with CLOSE CHECK;
2 usage (no criteria, duplicates, unreadable or undecodable input). Wire it into the board script's completion
call: read the task's newest comment, run `check`, and refuse to set the task done unless it exits 0.
Standard library only.
"""
import argparse
import re
import sys

MARK = re.compile(r"^\s*CLOSE CHECK\s*[:：]", re.I)
CRITERION_ID = re.compile(r"^([^\W\d_]{1,6}-?\d{1,4})(?:[:：]|\s)\s*(.+)$")
BULLET = re.compile(r"^\s*(?:[-*+•]|\d{1,3}[.)])\s+(.*\S)\s*$")
SEPARATOR = re.compile(r"[:：]\s+")
PLACEHOLDER = "<merged commit, #PR, link, passing test count, tag or run id>"
EVIDENCE = re.compile(
    r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b"      # a commit, with at least one digit
    r"|(?<![\w#])#\d+\b"                      # a pull request or issue
    r"|https?://[^\s/]+\.[^\s]+"              # a link to a real host
    r"|\b[1-9]\d*\s+passed\b"                 # a passing test count
    r"|\b([1-9]\d*)/\1\b"                     # all of N passed: 12/12
    r"|\bv\d+\.\d+\.\d+\b"                    # a release tag
    r"|\brun\s+\d{5,}\b",                     # a CI run id
    re.I)
NOT_DONE = re.compile(r"\b(?:not\s+(?:done|yet|merged|deployed|verified|released)|todo|tbd|wip|pending|failed|"
                      r"failing|fails|unmerged|broken)\b", re.I)


class Usage(Exception):
    pass


def words(text):
    """The text as lowercase word characters of any script, joined by spaces: the key a label is matched on."""
    return " ".join(re.findall(r"[^\W_]+", text.casefold()))


def criteria_of(text):
    """[(id or None, text)] from the criteria file's lines; Usage for none, an unnamable or a duplicate one."""
    found, seen = [], set()
    for raw in text.lstrip("﻿").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[-*+•]\s+", "", line)
        matched = CRITERION_ID.match(line)
        criterion_id, body = (matched.group(1).upper(), matched.group(2).strip()) if matched else (None, line)
        if not words(body):
            raise Usage(f"criterion {line!r} has no words to match a comment line on")
        for key in [words(body)] + ([words(criterion_id)] if criterion_id else []):
            if key in seen:
                raise Usage(f"two criteria share {key!r}: one comment line would close both")
            seen.add(key)
        found.append((criterion_id, body))
    if not found:
        raise Usage("no closing criteria: list the task's done line and the requester's close list, one per line")
    return found


def comment_lines(comment):
    """{label key: evidence}: each bullet line read at every ": ", so a label may itself hold a colon."""
    lines = {}
    for raw in comment.lstrip("﻿").splitlines():
        bullet = BULLET.match(raw)
        if not bullet:
            continue
        text = bullet.group(1)
        for separator in SEPARATOR.finditer(text):
            key = words(text[:separator.start()])
            if key:
                lines.setdefault(key, text[separator.end():])
    return lines


def keys_of(criterion_id, text):
    keys = [words(text)]
    if criterion_id:
        keys += [words(criterion_id), words(criterion_id.replace("-", "")), words(f"{criterion_id} {text}")]
    return keys


def problems(criteria, comment):
    """Each reason the comment does not close the task; [] when it does."""
    if not MARK.match(comment.lstrip("﻿")):
        return ['the comment must start with "CLOSE CHECK:"']
    lines = comment_lines(comment)
    found = []
    for criterion_id, text in criteria:
        evidence = next((lines[key] for key in keys_of(criterion_id, text) if key in lines), None)
        name = f"{criterion_id} {text}" if criterion_id else text
        if evidence is None:
            found.append(f"no line for: {name}")
        elif NOT_DONE.search(evidence):
            found.append(f"not done: {name} ({evidence[:80]}); keep the task open or split the open part off")
        elif not EVIDENCE.search(evidence):  # the template's placeholder holds no evidence token
            found.append(f"no evidence for: {name} (give a commit, #PR, link, passing test count, tag or run id)")
    return found


def template(criteria):
    lines = ["CLOSE CHECK:"]
    for criterion_id, text in criteria:
        if criterion_id:
            lines.append(f"{criterion_id} is: {text}")
        lines.append(f"- {criterion_id or text}: {PLACEHOLDER}")
    return "\n".join(lines)


def read(path, stdin_used):
    try:
        if path == "-":
            if stdin_used[0]:
                raise Usage("only one of --criteria and --comment can be read from stdin")
            stdin_used[0] = True
            data = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read().encode("utf-8")
            return data.decode("utf-8-sig")
        with open(path, encoding="utf-8-sig") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError) as error:
        raise Usage(f"cannot read {path}: {error}") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check a CLOSE CHECK comment against a task's closing criteria.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("template", "check"):
        command = sub.add_parser(name)
        command.add_argument("--criteria", required=True)
        if name == "check":
            command.add_argument("--comment", required=True)
    args = parser.parse_args(argv)
    stdin_used = [False]
    try:
        criteria = criteria_of(read(args.criteria, stdin_used))
        if args.command == "template":
            print(template(criteria))
            return 0
        found = problems(criteria, read(args.comment, stdin_used))
    except Usage as error:
        print(f"close_check: {error}", file=sys.stderr)
        return 2
    if found:
        print("not closed:\n" + "\n".join(f"- {problem}" for problem in found))
        return 1
    print(f"closes: {len(criteria)} criteria, each with evidence")
    return 0


if __name__ == "__main__":
    sys.exit(main())
