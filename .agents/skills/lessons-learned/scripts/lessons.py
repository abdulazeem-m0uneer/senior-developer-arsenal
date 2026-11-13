#!/usr/bin/env python3
"""Keep a lessons-learned ledger: one line per mistake, capped, deduplicated, safe under parallel writers.

Usage:
  lessons.py add --tags a,b --mistake M --cause C --rule R [--check K] [--global]
  lessons.py active [--hook]         # Active lessons, project then global; --hook emits SessionStart hook JSON
  lessons.py search WORD [WORD...]   # lessons (Active + Archive, project + global) containing every word
  lessons.py bump ID                 # the mistake happened again (an archived lesson returns to Active)
  lessons.py archive ID              # retire a lesson
  lessons.py promote ID              # write a rule stub under <ledger dir>/rules/, mark promoted, stop injecting
  lessons.py promote ID --as test    # print a test stub for the lesson's check (marks nothing)
  lessons.py promote ID --guard PATH # the guard (test, lint, hook, CI step) exists at PATH: mark promoted
  lessons.py globalize ID            # move a project lesson to the global ledger
  lessons.py check                   # validate the file and list promotion candidates
Options: --file PATH (default: $LESSONS_FILE or .agents/lessons.md); --global on add, bump, archive, promote and
  check targets the global ledger ($LESSONS_GLOBAL_FILE or ~/.agents/lessons.md), as does an id starting with G.
Exit codes: 0 ok, 1 check found problems, 2 usage, refused content, unreadable file or busy lock.
Time budget: `active --hook` runs two short git reads (1.5 s timeout each) and never fails the session.
"""
import argparse
import contextlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import promotion
import relevance
from ledger_store import find_secret, locked, write_atomic

ACTIVE_CAP = 15
PROMOTE_AT = 3
SIMILAR_AT = 0.5
FIELD_MAX = 200
TAGS_MAX = 60
SEARCH_MAX = 10
HOOK_MAX = 4000   # characters of additionalContext; the host cap is 10,000
LINE_MAX = 700
MUTATING = ("add", "bump", "archive", "promote", "globalize")
LINE_RE = re.compile(
    r"^- ([LG]\d{3,}) \[([^\]]*)\] hits:(\d+) \| (\d{4}-\d{2}-\d{2}) \| Mistake: (.*?) \| Cause: (.*?) "
    r"\| Rule: (.*?) \| Check: (.*?)(?: \| Promoted: (.*))?$")
LESSON_SHAPED_RE = re.compile(r"^\s*[-*]\s+[LG]\d+\b")
HEADER = ("# Lessons Learned\n\n"
          "<!-- Managed by lessons.py. One line per lesson; Active is loaded every session (cap "
          f"{ACTIVE_CAP}), Archive is searched on demand. Never store secrets or personal data. -->\n")
GLOBAL_LABEL = "Global lessons (every project):"
MORE_LINE = "(+{count} more: lessons.py search <words>)"
HOOK_HEADER = ("Lessons ledger for this project: obey the lessons below. If you catch your own mistake, or repeat one "
               "listed here, verify the cause, then run `python3 {script} add --tags T --mistake M --cause C --rule R "
               "--check K` (a repeat: `bump ID`; a tool or habit lesson that holds in every project: add `--global`). "
               "Self-audit before saying a task is done.")


class Refused(Exception):
    """The request cannot be carried out as given; the message is the user-facing error."""


def today():
    return date.today().isoformat()


class Ledger:
    def __init__(self, path, prefix="L"):
        self.path, self.prefix = Path(path), prefix
        self.header, self.lessons, self.stray, self.orphans = HEADER, [], [], []
        self.undecodable = False  # not UTF-8: reading replaces the bad bytes, so writing the ledger would lose them
        if self.path.is_file():
            raw = self.path.read_bytes()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                self.undecodable = True
                text = raw.decode("utf-8", errors="replace")
            self._parse(text)

    def _parse(self, text):
        section, head = None, []
        for line in text.splitlines():
            if line.strip().lower() in ("## active", "## archive"):
                section = line.strip()[3:].lower()
            elif section is None:
                head.append(line)
                if LESSON_SHAPED_RE.match(line):
                    self.orphans.append(line)
            elif line.strip():
                match = LINE_RE.match(line)
                if match:
                    i, tags, hits, when, mistake, cause, rule, check, promoted = match.groups()
                    self.lessons.append({"id": i, "tags": tags, "hits": int(hits), "date": when, "mistake": mistake,
                                         "cause": cause, "rule": rule, "check": check, "promoted": promoted or "",
                                         "section": section})
                else:
                    self.stray.append(line)
        if head:
            self.header = "\n".join(head).rstrip() + "\n"

    @staticmethod
    def render(lesson):
        return (f"- {lesson['id']} [{lesson['tags']}] hits:{lesson['hits']} | {lesson['date']} | "
                f"Mistake: {lesson['mistake']} | Cause: {lesson['cause']} | Rule: {lesson['rule']} | "
                f"Check: {lesson['check']}" + (f" | Promoted: {lesson['promoted']}" if lesson["promoted"] else ""))

    def section(self, name):
        return [lesson for lesson in self.lessons if lesson["section"] == name]

    def save(self):
        parts = [self.header]
        for name in ("active", "archive"):
            parts.append(f"\n## {name.capitalize()}\n")
            parts.extend(self.render(lesson) + "\n" for lesson in self.section(name))
        write_atomic(self.path, "".join(parts))

    def find(self, lesson_id):
        lesson = next((lesson for lesson in self.lessons if lesson["id"] == lesson_id.upper()), None)
        if not lesson:
            raise Refused(f"no lesson {lesson_id} in {self.path}")
        return lesson

    def next_id(self):
        return "%s%03d" % (self.prefix, 1 + max([int(lesson["id"][1:]) for lesson in self.lessons] or [0]))


def global_path():
    return Path(os.environ.get("LESSONS_GLOBAL_FILE") or Path.home() / ".agents" / "lessons.md")


def repository_root(folder):
    folder = Path(folder).resolve()
    return next((parent for parent in (folder, *folder.parents) if (parent / ".git").exists()), None)


def writable_global_path(project_file):
    """The global ledger holds lessons for every project, so it must not live inside the project's repository
    (the one the command runs in, or the one holding the project ledger)."""
    path = global_path().resolve()
    for root in {repository_root(Path.cwd()), repository_root(Path(project_file).resolve().parent)}:
        if root and root in path.parents:
            raise Refused(f"the global ledger {path} is inside this repository; point LESSONS_GLOBAL_FILE outside it")
    return path


def open_global(project_file):
    """The global ledger for reading, or None when it is missing or is the project ledger itself."""
    path = global_path()
    if not path.is_file() or path.resolve() == Path(project_file).resolve():
        return None
    try:
        return Ledger(path, "G")
    except OSError as error:  # an unreadable global ledger must not hide the project's lessons
        print(f"note: global ledger {path} ignored: {error}", file=sys.stderr)
        return None


def words(lesson):
    return {w for w in re.findall(r"[a-z0-9_.]{3,}", f"{lesson['mistake']} {lesson['rule']}".lower())}


def similarity(a, b):
    wa, wb = words(a), words(b)
    return len(wa & wb) / len(wa | wb) if wa | wb else 0.0


def clean(value, limit=FIELD_MAX):
    return " ".join(value.replace("|", "/").split())[:limit]


def promote_hint(lesson):
    if lesson["promoted"]:
        return f"\nGUARD FAILED {lesson['id']}: promoted to {lesson['promoted']} and it happened again. Strengthen it."
    if lesson["hits"] < PROMOTE_AT:
        return ""
    return (f"\nPROMOTE {lesson['id']}: seen {lesson['hits']} times. Run `promote {lesson['id']}` for a rule stub, or "
            f"enforce it mechanically (test, lint, hook, CI) and run `promote {lesson['id']} --guard PATH`.")


def enforce_cap(ledger, keep):
    active = ledger.section("active")
    if len(active) > ACTIVE_CAP:
        evicted = min((lesson for lesson in active if lesson is not keep), key=lambda x: (x["hits"], x["date"]))
        evicted["section"] = "archive"
        print(f"active cap {ACTIVE_CAP} reached: archived {evicted['id']}")


def recur(ledger, lesson, hits=1):
    """Count a repeat; an archived (or promoted) lesson that recurs is loaded again. Returns the note to print."""
    lesson["hits"] += hits
    lesson["date"] = today()
    back = lesson["section"] == "archive"
    if back:
        lesson["section"] = "active"
        enforce_cap(ledger, lesson)
    return (" (back in Active)" if back else "") + promote_hint(lesson)


def record(ledger, new):
    """Add a lesson, or count it as a repeat of the most similar existing one. Returns (stored lesson, message)."""
    twin = max(ledger.lessons, key=lambda lesson: similarity(lesson, new), default=None)
    if twin and similarity(twin, new) >= SIMILAR_AT:
        note = recur(ledger, twin, new["hits"])
        return twin, f"duplicate of {twin['id']}: hits bumped to {twin['hits']}{note}"
    new["id"] = ledger.next_id()
    ledger.lessons.append(new)
    enforce_cap(ledger, new)
    return new, f"added {new['id']}"


def cmd_add(ledger, args):
    fields = {k: clean(getattr(args, k) or "") for k in ("mistake", "cause", "rule", "check")}
    if not (fields["mistake"] and fields["cause"] and fields["rule"]):
        raise Refused("--mistake, --cause and --rule are required")
    tags = ",".join(t.strip().lower() for t in clean(args.tags, TAGS_MAX).replace("]", "").split(",") if t.strip())
    secret = find_secret(" ".join([tags, *fields.values()]))
    if secret:
        raise Refused(f"looks like a secret ({secret}); lessons never store those")
    fields["check"] = fields["check"] or "none yet"
    new = {"tags": tags, "hits": 1, "date": today(), "section": "active", "promoted": "", **fields}
    _, message = record(ledger, new)
    ledger.save()
    print(message)
    return 0


def clip(line):
    return line if len(line) <= LINE_MAX else line[:LINE_MAX - 4] + " ..."


def hook_text(project, shared):
    """Header, then the lessons that matter most for the files in play, within HOOK_MAX characters."""
    header = HOOK_HEADER.format(script=Path(__file__).resolve())
    if not project and not shared:
        return header + "\n(no lessons yet)"
    ranked = relevance.rank(project + shared, relevance.path_tokens(relevance.changed_paths(relevance.session_cwd())))
    lines = [clip(Ledger.render(lesson)) for lesson in ranked]
    budget = HOOK_MAX - len(header) - len(GLOBAL_LABEL) - len(MORE_LINE.format(count=len(lines))) - 3
    kept = relevance.fit(lines, budget)
    is_shared = [any(ranked[index] is lesson for lesson in shared) for index in kept]
    out = [header] + [lines[index] for index, flag in zip(kept, is_shared) if not flag]
    if any(is_shared):
        out += [GLOBAL_LABEL] + [lines[index] for index, flag in zip(kept, is_shared) if flag]
    if len(kept) < len(lines):
        out.append(MORE_LINE.format(count=len(lines) - len(kept)))
    return "\n".join(out)


def cmd_active(ledger, args):
    project = ledger.section("active")
    other = open_global(ledger.path)
    shared = [lesson for lesson in (other.section("active") if other else [])
              if all(similarity(lesson, mine) < SIMILAR_AT for mine in project)]
    if args.hook:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": hook_text(project, shared)}}))
        return 0
    for line in [Ledger.render(x) for x in project] + ([GLOBAL_LABEL] if shared else []) + \
            [Ledger.render(x) for x in shared]:
        print(line)
    return 0


def cmd_search(ledger, args):
    needles = [w.lower() for w in args.words]
    other = open_global(ledger.path)
    found = [(scope + lesson["section"], lesson)
             for scope, source in (("", ledger), ("global ", other)) if source for lesson in source.lessons
             if all(n in Ledger.render(lesson).lower() for n in needles)]
    for label, lesson in sorted(found, key=lambda item: -item[1]["hits"])[:SEARCH_MAX]:
        print(f"[{label}] {Ledger.render(lesson)}")
    return 0


def cmd_bump(ledger, args):
    lesson = ledger.find(args.id)
    note = recur(ledger, lesson)
    ledger.save()
    print(f"{lesson['id']} hits:{lesson['hits']}{note}")
    return 0


def cmd_archive(ledger, args):
    lesson = ledger.find(args.id)
    lesson["section"] = "archive"
    ledger.save()
    print(f"archived {lesson['id']}")
    return 0


def cmd_promote(ledger, args):
    lesson = ledger.find(args.id)
    if args.guard:
        if not Path(args.guard).exists():
            raise Refused(f"guard {args.guard} does not exist; write it first")
        lesson["promoted"] = promotion.shown(args.guard)
    elif args.kind == "test":
        print(promotion.test_stub(lesson))
        print(f"Write it, make it pass, then: promote {lesson['id']} --guard <test file>")
        return 0
    else:
        path, appended = promotion.write_rule_stub(lesson, args.rules_dir or ledger.path.parent / "rules")
        lesson["promoted"] = promotion.shown(path)
        print(f"rule stub {'written to' if appended else 'already present in'} {path}: tighten the wording; "
              "narrow `trigger: always_on` to a glob if it fits one stack; wire the file into agents that do not read this rules directory")
    lesson["section"] = "archive"
    ledger.save()
    print(f"promoted {lesson['id']} to {lesson['promoted']}; it is no longer injected (it returns if it recurs)")
    return 0


def cmd_globalize(ledger, args):
    lesson = ledger.find(args.id)
    path = writable_global_path(args.file)
    if path == ledger.path.resolve():
        raise Refused(f"{lesson['id']} is already in the global ledger")
    with locked(path):
        shared = Ledger(path, "G")
        refuse_stray(shared)
        stored, message = record(shared, {**lesson, "section": "active", "promoted": ""})
        shared.save()
    lesson["promoted"], lesson["section"] = f"global {stored['id']}", "archive"
    ledger.save()
    print(f"global ledger: {message}\nmoved {lesson['id']} to {path} as {stored['id']}")
    return 0


def cmd_check(ledger, _args):
    problems = ["not valid UTF-8: convert the file; a command that writes it would replace the bad bytes"
                ] if ledger.undecodable else []
    problems += [f"unparsable line: {line[:80]}" for line in ledger.stray]
    problems += [f"lesson outside any section (never loaded; move it under ## Active): {line.strip()[:80]}"
                 for line in ledger.orphans]
    ids = [lesson["id"] for lesson in ledger.lessons]
    problems += [f"duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    if len(ledger.section("active")) > ACTIVE_CAP:
        problems.append(f"Active has {len(ledger.section('active'))} lessons (cap {ACTIVE_CAP})")
    for lesson in ledger.section("active"):
        if lesson["hits"] >= PROMOTE_AT and lesson["promoted"]:
            print(f"candidate {lesson['id']} hits:{lesson['hits']}: recurred after promotion to {lesson['promoted']}; "
                  "strengthen that guard")
        elif lesson["hits"] >= PROMOTE_AT:
            print(f"candidate {lesson['id']} hits:{lesson['hits']}: run `promote {lesson['id']}` (rule stub), or add "
                  "a test, lint, hook or CI guard and `promote --guard`")
    for problem in problems:
        print(f"problem: {problem}")
    print(f"{len(ledger.lessons)} lessons, {len(problems)} problems")
    return 1 if problems else 0


def build_parser():
    parser = argparse.ArgumentParser(description="Lessons-learned ledger (project and global).")
    parser.add_argument("--file", default=os.environ.get("LESSONS_FILE") or ".agents/lessons.md")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--tags", default="")
    for name in ("mistake", "cause", "rule", "check"):
        add.add_argument(f"--{name}")
    sub.add_parser("active").add_argument("--hook", action="store_true")
    sub.add_parser("search").add_argument("words", nargs="+")
    promote = sub.add_parser("promote")
    promote.add_argument("--as", dest="kind", choices=("rule", "test"), default="rule")
    promote.add_argument("--guard")
    promote.add_argument("--rules-dir")
    by_id = [sub.add_parser(name) for name in ("bump", "archive", "globalize")] + [promote]
    for command in by_id:
        command.add_argument("id")
    for command in [add, sub.add_parser("check"), *by_id[:2], promote]:
        command.add_argument("--global", dest="shared", action="store_true")
    return parser


COMMANDS = {"add": cmd_add, "active": cmd_active, "search": cmd_search, "bump": cmd_bump, "archive": cmd_archive,
            "promote": cmd_promote, "globalize": cmd_globalize, "check": cmd_check}


def refuse_stray(ledger):
    if ledger.undecodable:
        raise Refused(f"{ledger.path} is not valid UTF-8; convert it first (writing would destroy the bad bytes)")
    if ledger.stray:
        raise Refused(f"{ledger.path} has unparsable lines; run `check` and fix them first")


def run(args):
    shared = getattr(args, "shared", False) or (args.command != "globalize" and
                                                getattr(args, "id", "").upper().startswith("G"))
    path, prefix = (writable_global_path(args.file), "G") if shared else (Path(args.file), "L")
    if args.command not in MUTATING:
        return COMMANDS[args.command](Ledger(path, prefix), args)
    with locked(path):
        ledger = Ledger(path, prefix)
        refuse_stray(ledger)
        return COMMANDS[args.command](ledger, args)


def main(argv=None):
    args = build_parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # a lesson with a character the console cannot encode still prints
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(errors="replace")
    hook = args.command == "active" and args.hook
    try:
        return run(args)
    except (Refused, OSError, ValueError) as error:  # ValueError includes UnicodeError
        if not hook:
            print(f"error: {error}", file=sys.stderr)
        return 0 if hook else 2
    except Exception:  # a session-start hook never breaks the session
        if not hook:
            raise
        return 0


if __name__ == "__main__":
    sys.exit(main())
