#!/usr/bin/env python3
"""Keep a project's lessons-learned ledger: one line per mistake, capped, deduplicated.

Usage:
  lessons.py add --tags a,b --mistake M --cause C --rule R [--check K]
  lessons.py active [--hook]         # the Active section; --hook emits SessionStart hook JSON (additionalContext)
  lessons.py search WORD [WORD...]   # lessons (Active + Archive) containing every word
  lessons.py bump ID                 # the mistake happened again
  lessons.py archive ID              # retire a lesson (fixed by a test, rule, or tool)
  lessons.py check                   # validate the file and list promotion candidates
Options: --file PATH (default: $LESSONS_FILE or .agents/lessons.md)
Exit codes: 0 ok, 1 check found problems, 2 usage or unreadable file.
"""
import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ACTIVE_CAP = 15
PROMOTE_AT = 3
SIMILAR_AT = 0.5
FIELD_MAX = 200
SEARCH_MAX = 10
LINE_RE = re.compile(
    r"^- (L\d{3,}) \[([^\]]*)\] hits:(\d+) \| (\d{4}-\d{2}-\d{2}) \| Mistake: (.*?) \| Cause: (.*?) "
    r"\| Rule: (.*?) \| Check: (.*)$")
SECRET_RE = re.compile(r"(api[_-]?key|secret|passw(or)?d|token|bearer)\s*[:=]\s*\S+|\b[A-Za-z0-9+/_-]{40,}\b", re.I)
HEADER = ("# Lessons Learned\n\n"
          "<!-- Managed by lessons.py. One line per lesson; Active is loaded every session (cap "
          f"{ACTIVE_CAP}), Archive is searched on demand. Never store secrets or personal data. -->\n")


def today():
    return date.today().isoformat()


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        self.header, self.lessons, self.stray = HEADER, [], []
        if self.path.is_file():
            self._parse(self.path.read_text(encoding="utf-8"))

    def _parse(self, text):
        section, head = None, []
        for line in text.splitlines():
            if line.strip().lower() in ("## active", "## archive"):
                section = line.strip()[3:].lower()
            elif section is None:
                head.append(line)
            elif line.strip():
                match = LINE_RE.match(line)
                if match:
                    i, tags, hits, when, mistake, cause, rule, check = match.groups()
                    self.lessons.append({"id": i, "tags": tags, "hits": int(hits), "date": when, "mistake": mistake,
                                         "cause": cause, "rule": rule, "check": check, "section": section})
                else:
                    self.stray.append(line)
        if head:
            self.header = "\n".join(head).rstrip() + "\n"

    @staticmethod
    def render(lesson):
        return (f"- {lesson['id']} [{lesson['tags']}] hits:{lesson['hits']} | {lesson['date']} | "
                f"Mistake: {lesson['mistake']} | Cause: {lesson['cause']} | Rule: {lesson['rule']} | "
                f"Check: {lesson['check']}")

    def section(self, name):
        return [lesson for lesson in self.lessons if lesson["section"] == name]

    def save(self):
        parts = [self.header]
        for name in ("active", "archive"):
            parts.append(f"\n## {name.capitalize()}\n")
            parts.extend(self.render(lesson) + "\n" for lesson in self.section(name))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(parts), encoding="utf-8")

    def find(self, lesson_id):
        return next((lesson for lesson in self.lessons if lesson["id"] == lesson_id.upper()), None)

    def next_id(self):
        return "L%03d" % (1 + max([int(lesson["id"][1:]) for lesson in self.lessons] or [0]))


def words(lesson):
    return {w for w in re.findall(r"[a-z0-9_.]{3,}", f"{lesson['mistake']} {lesson['rule']}".lower())}


def similarity(a, b):
    wa, wb = words(a), words(b)
    return len(wa & wb) / len(wa | wb) if wa | wb else 0.0


def clean(value):
    return " ".join(value.replace("|", "/").split())[:FIELD_MAX]


def cmd_add(ledger, args):
    fields = {k: clean(getattr(args, k) or "") for k in ("mistake", "cause", "rule", "check")}
    if not (fields["mistake"] and fields["cause"] and fields["rule"]):
        print("error: --mistake, --cause and --rule are required", file=sys.stderr)
        return 2
    if SECRET_RE.search(" ".join(fields.values())):
        print("error: looks like a secret or credential; lessons never store those", file=sys.stderr)
        return 2
    fields["check"] = fields["check"] or "none yet"
    tags = ",".join(t.strip().lower() for t in args.tags.split(",") if t.strip())
    new = {"id": ledger.next_id(), "tags": tags, "hits": 1, "date": today(), "section": "active", **fields}
    twin = max(ledger.lessons, key=lambda lesson: similarity(lesson, new), default=None)
    if twin and similarity(twin, new) >= SIMILAR_AT:
        twin["hits"] += 1
        twin["date"] = today()
        ledger.save()
        print(f"duplicate of {twin['id']}: hits bumped to {twin['hits']}" + promote_hint(twin))
        return 0
    ledger.lessons.append(new)
    active = ledger.section("active")
    if len(active) > ACTIVE_CAP:
        evicted = min(active[:-1], key=lambda lesson: (lesson["hits"], lesson["date"]))
        evicted["section"] = "archive"
        print(f"active cap {ACTIVE_CAP} reached: archived {evicted['id']}")
    ledger.save()
    print(f"added {new['id']}")
    return 0


def promote_hint(lesson):
    return (f"\nPROMOTE {lesson['id']}: seen {lesson['hits']} times. Enforce it mechanically (test, lint, hook, CI) "
            f"or move the rule into a rules file, then `archive {lesson['id']}`.") if lesson["hits"] >= PROMOTE_AT else ""


HOOK_HEADER = ("Lessons ledger for this project: obey the lessons below. If you catch your own mistake, or repeat one "
               "listed here, verify the cause, then run `python3 {script} add --tags T --mistake M --cause C --rule R "
               "--check K` (a repeat: `bump ID`). Self-audit before saying a task is done.")


def cmd_active(ledger, args):
    active = ledger.section("active")
    lines = [ledger.render(lesson) for lesson in active]
    if args.hook:
        lines = [HOOK_HEADER.format(script=Path(__file__).resolve())] + (lines or ["(no lessons yet)"])
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": "\n".join(lines)}}))
        return 0
    for line in lines:
        print(line)
    return 0


def cmd_search(ledger, args):
    needles = [w.lower() for w in args.words]
    hits = [lesson for lesson in ledger.lessons if all(n in ledger.render(lesson).lower() for n in needles)]
    for lesson in sorted(hits, key=lambda x: -x["hits"])[:SEARCH_MAX]:
        print(f"[{lesson['section']}] {ledger.render(lesson)}")
    return 0


def cmd_bump(ledger, args):
    lesson = ledger.find(args.id)
    if not lesson:
        print(f"error: no lesson {args.id}", file=sys.stderr)
        return 2
    lesson["hits"] += 1
    lesson["date"] = today()
    ledger.save()
    print(f"{lesson['id']} hits:{lesson['hits']}" + promote_hint(lesson))
    return 0


def cmd_archive(ledger, args):
    lesson = ledger.find(args.id)
    if not lesson:
        print(f"error: no lesson {args.id}", file=sys.stderr)
        return 2
    lesson["section"] = "archive"
    ledger.save()
    print(f"archived {lesson['id']}")
    return 0


def cmd_check(ledger, _args):
    problems = [f"unparsable line: {line[:80]}" for line in ledger.stray]
    ids = [lesson["id"] for lesson in ledger.lessons]
    problems += [f"duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    if len(ledger.section("active")) > ACTIVE_CAP:
        problems.append(f"Active has {len(ledger.section('active'))} lessons (cap {ACTIVE_CAP})")
    for lesson in ledger.section("active"):
        if lesson["hits"] >= PROMOTE_AT:
            print(f"candidate {lesson['id']} hits:{lesson['hits']}: promote to a test, lint, hook or rule")
    for problem in problems:
        print(f"problem: {problem}")
    print(f"{len(ledger.lessons)} lessons, {len(problems)} problems")
    return 1 if problems else 0


def build_parser():
    parser = argparse.ArgumentParser(description="Project lessons-learned ledger.")
    parser.add_argument("--file", default=os.environ.get("LESSONS_FILE", ".agents/lessons.md"))
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--tags", default="")
    for name in ("mistake", "cause", "rule", "check"):
        add.add_argument(f"--{name}")
    sub.add_parser("active").add_argument("--hook", action="store_true")
    sub.add_parser("check")
    sub.add_parser("search").add_argument("words", nargs="+")
    sub.add_parser("bump").add_argument("id")
    sub.add_parser("archive").add_argument("id")
    return parser


COMMANDS = {"add": cmd_add, "active": cmd_active, "search": cmd_search, "bump": cmd_bump,
            "archive": cmd_archive, "check": cmd_check}


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        ledger = Ledger(args.file)
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if ledger.stray and args.command not in ("check", "active", "search"):
        print("error: file has unparsable lines; run `check` and fix them first", file=sys.stderr)
        return 2
    return COMMANDS[args.command](ledger, args)


if __name__ == "__main__":
    sys.exit(main())
