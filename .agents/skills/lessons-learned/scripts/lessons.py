#!/usr/bin/env python3
"""Keep a lessons-learned ledger: one line per mistake, capped, deduplicated, safe under parallel writers.

Usage:
  lessons.py add --tags a,b --mistake M --cause C --rule R [--check K] [--global]
  lessons.py active [--hook]         # Active lessons, project then global; --hook emits SessionStart hook JSON
  lessons.py search WORD [WORD...] [--full]  # lessons (Active + Archive, project + global) containing every word
  lessons.py show ID                 # one lesson in full (mistake, cause, rule, check); listings print rules only
  lessons.py bump ID                 # the mistake happened again (an archived lesson returns to Active)
  lessons.py archive ID              # retire a lesson
  lessons.py promote ID              # write a rule stub under <ledger dir>/rules/, mark promoted, stop injecting
  lessons.py promote ID --as test    # print a test stub for the lesson's check (marks nothing)
  lessons.py promote ID --guard PATH # the guard (test, lint, hook, CI step) exists at PATH: mark promoted
  lessons.py promote ID --guard PATH --keep-rule  # the guard covers only part of the rule: also write the rule stub
  lessons.py globalize ID            # move a project lesson to the global ledger
  lessons.py check [--min N]         # validate the file and list promotion candidates (hits >= N)
  lessons.py unguarded [--min N] [LEDGER...]  # lessons seen N+ times with no guard, archive included, most hits first
  lessons.py hits [--since 24h]      # lesson-guard refusals in the window, from the hit log (guard_hits.py)
  lessons.py retro [--days 7] [--project]  # Markdown retrospective: git log, ledger, evidence, guard hits (retro.py)
  lessons.py guards [--registry FILE [--target LIVE]] [--strict]  # registries vs this hook and every cached version
                                     # (exit 1: a referenced version would refuse; --registry: dry run of a file not
                                     # yet in place; --target: judge it as if it sat at LIVE, so relative paths resolve)
  lessons.py exempt ID --reason R    # no mechanical guard fits: record why, so the repeat is no longer flagged
  lessons.py metrics [--days 7] [--lane-tag session:] [--bus DIR] [--json] [--ledger FILE ...]
                                     # per ledger and lane: added/repeated per day, repeats, guarded/unguarded/exempt,
                                     # guard fires per day, and with --bus the ETA accuracy per session (metrics.py)
Options: --file PATH (default: $LESSONS_FILE or .agents/lessons.md); --global on add, bump, archive, promote, exempt
  and check targets the global ledger ($LESSONS_GLOBAL_FILE or ~/.agents/lessons.md), as does an id starting with G.
  The promotion threshold N defaults to $LESSONS_PROMOTE_AT, else 3.
  add and bump also append one line to <ledger stem>.events.jsonl beside the ledger (lesson_events.py), for metrics,
  and globalize appends a move line to both ledgers' logs; a failed log write warns on stderr and never fails
  the command.
Escalation: a repeat (bump, or an add that is a duplicate) that brings a lesson with no guard and no exemption to
  the threshold N or more is saved and printed as usual, then prints "ESCALATE <id> x<hits>: ..." on stderr and exits
  3, on every further repeat until `promote ID --guard PATH` or `exempt ID --reason R`. A first add never escalates;
  a guarded or exempted lesson that recurs keeps its GUARD FAILED / EXEMPT recurred hint and exits 0.
  A guard is a Promoted path other than a rules-only lessons-promoted.md (a rule stub is no guard) and other than an
  exempt@ mark (has_guard); escalation, `unguarded` and the session-start "Repeats without a guard" note share it.
Exit codes: 0 ok, 1 check found problems, 2 usage, refused content, unreadable file or busy lock,
  3 the repeat is recorded and escalated (see Escalation).
Time budget: `active --hook` runs two short git reads (1.5 s timeout each) and never fails the session.
"""
import argparse
import contextlib
import json
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

import guard_hits
import functools
import guard_registry
import lesson_events
import metrics
import promotion
import relevance
import retro
from ledger_store import find_secret, locked, write_atomic

ACTIVE_CAP = 15
PROMOTE_AT = 3   # default; $LESSONS_PROMOTE_AT or --min overrides it
SIMILAR_AT = 0.5
EXIT_ESCALATE = 3  # a repeat was saved and still has no guard: the caller stops until one is attached or exempted
FIELD_MAX = 200
TAGS_MAX = 60
SEARCH_MAX = 10
HOOK_MAX = 2000   # characters of additionalContext (host cap 10,000); brief lines fit about ten lessons
SCRIPT_PATH_BUDGET = 160  # the header's script path, counted at this length whatever its real one (plugin: ~120)
MUTATING = ("add", "bump", "archive", "promote", "globalize", "exempt")
LINE_RE = re.compile(
    r"^- ([LG]\d{3,}) \[([^\]]*)\] hits:(\d+) \| (\d{4}-\d{2}-\d{2}) \| Mistake: (.*?) \| Cause: (.*?) "
    r"\| Rule: (.*?) \| Check: (.*?)(?: \| Promoted: (.*))?$")
LESSON_SHAPED_RE = re.compile(r"^\s*[-*]\s+[LG]\d+\b")
HEADER = ("# Lessons Learned\n\n"
          "<!-- Managed by lessons.py. One line per lesson; Active is loaded every session (cap "
          f"{ACTIVE_CAP}), Archive is searched on demand. Never store secrets or personal data. -->\n")
GLOBAL_LABEL = "Global lessons (every project):"
MORE_LINE = "(+{count} more: lessons.py search <words>)"
HOOK_HEADER = ("Lessons (obey; xN = times seen; full text: `show ID`). If you catch your own mistake, verify the cause, "
               "then `python3 {script} add --tags T --mistake M --cause C --rule R --check K` (repeat: `bump ID`; "
               "holds in any project: `--global`). When a listed lesson changes what you do, say `Applying ID: rule`. "
               "Self-audit before saying done.")


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

    @staticmethod
    def brief(lesson):
        """The rule alone: about a quarter of the full line. `show ID` prints the rest on demand."""
        return (f"- {lesson['id']} [{lesson['tags']}] x{lesson['hits']}: {lesson['rule']}"
                + (f" -> {lesson['promoted']}" if lesson["promoted"] else ""))

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


def promote_at(given=None):
    """The hit count from which a lesson should get a guard: --min, else $LESSONS_PROMOTE_AT, else PROMOTE_AT."""
    value = given if given is not None else os.environ.get("LESSONS_PROMOTE_AT") or PROMOTE_AT
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise Refused(f"promotion threshold {value!r} is not a whole number of 1 or more (--min, LESSONS_PROMOTE_AT)")
    return number


MOVED_MARK = "global "  # `globalize` leaves "Promoted: global <id>" on the project's stub
KEPT_RULE = " + rule "  # promote --guard PATH --keep-rule stores "PATH + rule <rule file>"
EXEMPT_MARK = re.compile(r"^exempt@(\d+): ")  # "exempt@<hits when granted>: <reason>"; never a path promote stores
ESCALATE_SHOWN = 5  # unguarded repeats named in the session-start header; the rest are counted


def exempted_at(lesson):
    """The hit count a written exemption was granted at, or None when the lesson has none."""
    found = EXEMPT_MARK.match(lesson["promoted"])
    return int(found.group(1)) if found else None


def is_exempt(lesson):
    """True while an exemption holds: the lesson has not recurred since it was granted."""
    at = exempted_at(lesson)
    return at is not None and lesson["hits"] <= at


@functools.lru_cache(maxsize=None)
def registry_lessons(cwd):
    """Lesson ids a lesson-guard registry entry guards in cwd, as the installed hook applies them; empty on any
    failure, so an unreadable registry never hides a lesson."""
    try:
        return frozenset(guard_registry.guarded_lessons(cwd))
    except Exception:  # the registry is optional here; has_guard then reads Promoted alone
        return frozenset()


def has_guard(lesson):
    """True when Promoted names a guard (a path other than a rules-only lessons-promoted.md file, an exemption mark
    or a moved-to-global stub; `--guard PATH --keep-rule`, "PATH + rule ...", is guarded by PATH), or when an
    applied lesson-guard registry entry names the lesson (lessons promoted before the registry existed)."""
    promoted = lesson["promoted"]
    if lesson.get("id") and lesson["id"] in registry_lessons(str(relevance.session_cwd())):
        return True
    if not promoted or EXEMPT_MARK.match(promoted) or promoted.startswith(MOVED_MARK):
        return False
    return Path(promoted.split(KEPT_RULE)[0]).name != promotion.RULE_FILE


def unguarded(lesson):
    """No guard (has_guard) and no exemption that holds; a moved stub is counted in the global ledger instead."""
    return not lesson["promoted"].startswith(MOVED_MARK) and not has_guard(lesson) and not is_exempt(lesson)


def promote_hint(lesson):
    if exempted_at(lesson) is not None:
        return (f"\nEXEMPT {lesson['id']} recurred ({lesson['promoted']}): reconsider a mechanical guard, then "
                f"`promote {lesson['id']} --guard PATH`.")
    if lesson["promoted"]:
        return f"\nGUARD FAILED {lesson['id']}: promoted to {lesson['promoted']} and it happened again. Strengthen it."
    if lesson["hits"] < promote_at():
        return ""
    return (f"\nPROMOTE {lesson['id']}: seen {lesson['hits']} times. Run `promote {lesson['id']}` for a rule stub, or "
            f"enforce it mechanically (test, lint, hook, CI) and run `promote {lesson['id']} --guard PATH`.")


def escalation(lesson):
    """The ESCALATE line for a repeat at the threshold with no guard and no exemption, else ''."""
    if has_guard(lesson) or exempted_at(lesson) is not None or lesson["promoted"].startswith(MOVED_MARK) \
            or lesson["hits"] < promote_at():
        return ""
    return (f"ESCALATE {lesson['id']} x{lesson['hits']}: this lesson has repeated without a guard. Attach one (promote "
            f"{lesson['id']} --guard PATH) or record why none fits (exempt {lesson['id']} --reason ...); every further "
            "repeat stops here until then.")


def escalate(lesson):
    """After a saved repeat: print the ESCALATE line and return EXIT_ESCALATE, or return 0."""
    line = escalation(lesson)
    if line:
        print(line, file=sys.stderr)
    return EXIT_ESCALATE if line else 0


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


def log_event(ledger, kind, lesson):
    """Append the change to the events log; the ledger is already saved, so a failed write only warns."""
    try:
        lesson_events.append(ledger.path, kind, lesson, today())
    except (OSError, ValueError) as error:
        print(f"warning: events log {lesson_events.path(ledger.path)} not written ({error}); the lesson is saved, "
              "metrics will miss this change", file=sys.stderr)


def learned(lesson):
    """The line that tells the user which rule was recorded or counted, after add and bump."""
    return f"LEARNED: {lesson['rule']} ({lesson['id']}, x{lesson['hits']})"


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
    stored, message = record(ledger, new)
    ledger.save()
    log_event(ledger, "add" if stored is new else "repeat", stored)
    print(message)
    print(learned(stored))
    return 0 if stored is new else escalate(stored)


def hook_text(project, shared, reserve=0, cwd=None):
    """Header, then the lessons that matter most for the files in play, within HOOK_MAX characters (less reserve,
    the room another header line needs). cwd: the session's folder (read from the hook input when not given)."""
    header = HOOK_HEADER.format(script=Path(__file__).resolve())
    if not project and not shared:
        return header + "\n(no lessons yet)"
    tokens = relevance.path_tokens(relevance.changed_paths(cwd or relevance.session_cwd()))
    # Ranked apart, then alternated: high-hit global lessons must not crowd out every project lesson.
    ranked = relevance.alternate(relevance.rank(project, tokens), relevance.rank(shared, tokens))
    lines = [Ledger.brief(lesson) for lesson in ranked]
    # The script path is budgeted at a fixed length, so where arsenal is installed never changes which lessons show.
    fixed_header = len(HOOK_HEADER.format(script="")) + SCRIPT_PATH_BUDGET
    budget = HOOK_MAX - fixed_header - len(GLOBAL_LABEL) - len(MORE_LINE.format(count=len(lines))) - 3 - reserve
    kept = relevance.fit(lines, budget)
    is_shared = [any(ranked[index] is lesson for lesson in shared) for index in kept]
    out = [header] + [lines[index] for index, flag in zip(kept, is_shared) if not flag]
    if any(is_shared):
        out += [GLOBAL_LABEL] + [lines[index] for index, flag in zip(kept, is_shared) if flag]
    if len(kept) < len(lines):
        out.append(MORE_LINE.format(count=len(lines) - len(kept)))
    return "\n".join(out)


def registry_note(cwd=None):
    """One header line when the lesson-guard registry has entries this hook skips; '' otherwise or on any failure."""
    try:
        count = len(guard_registry.current_problems(cwd or relevance.session_cwd()))
    except Exception:  # the session-start hook never fails over a report line
        return ""
    if not count:
        return ""
    return (f"Lesson-guard registry: {count} entr{'y' if count == 1 else 'ies'} skipped (not applied); "
            f"run `python3 {Path(__file__).resolve()} guards` and fix them.")


def escalation_note(ledger, shared_ledger):
    """One header line naming the repeats that still have no guard and no exemption that holds; a global lesson that
    repeats a project one is counted once, as in the loaded list. '' when there are none or on any failure (the
    session-start hook never fails over a report line)."""
    try:
        found = unguarded_lessons([ledger] + ([shared_ledger] if shared_ledger else []), promote_at())
    except Exception:
        return ""
    project = [lesson for source, lesson in found if source is ledger]
    found = [(source, lesson) for source, lesson in found
             if source is ledger or all(similarity(lesson, mine) < SIMILAR_AT for mine in project)]
    if not found:
        return ""
    named = ", ".join(f"{lesson['id']} x{lesson['hits']}" for _, lesson in found[:ESCALATE_SHOWN])
    more = f" and {len(found) - ESCALATE_SHOWN} more (`unguarded`)" if len(found) > ESCALATE_SHOWN else ""
    return (f"Repeats without a guard ({len(found)}): {named}{more}. Give each a guard (`promote ID --guard PATH`) or "
            "record why none fits (`exempt ID --reason ...`).")


def cmd_active(ledger, args):
    project = ledger.section("active")
    other = open_global(ledger.path)
    shared = [lesson for lesson in (other.section("active") if other else [])
              if all(similarity(lesson, mine) < SIMILAR_AT for mine in project)]
    if args.hook:
        cwd = relevance.session_cwd()  # the hook input is read once: stdin cannot be read twice
        notes = [note for note in (escalation_note(ledger, other), registry_note(cwd)) if note]
        reserve = sum(len(note) + 1 for note in notes)
        context = "\n".join([hook_text(project, shared, reserve, cwd), *notes])
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}))
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
    shape = Ledger.render if args.full else Ledger.brief
    for label, lesson in sorted(found, key=lambda item: -item[1]["hits"])[:SEARCH_MAX]:
        print(f"[{label}] {shape(lesson)}")
    return 0


def cmd_show(ledger, args):
    print(Ledger.render(ledger.find(args.id)))
    return 0


def cmd_bump(ledger, args):
    lesson = ledger.find(args.id)
    note = recur(ledger, lesson)
    ledger.save()
    log_event(ledger, "repeat", lesson)
    print(f"{lesson['id']} hits:{lesson['hits']}{note}")
    print(learned(lesson))
    return escalate(lesson)


def cmd_exempt(ledger, args):
    lesson = ledger.find(args.id)
    reason = clean(args.reason or "")
    if not reason:
        raise Refused("--reason is required: why no test, lint, hook or CI check can enforce this lesson")
    secret = find_secret(reason)
    if secret:
        raise Refused(f"looks like a secret ({secret}); lessons never store those")
    if has_guard(lesson):
        raise Refused(f"{lesson['id']} already has a guard ({lesson['promoted']}); an exemption would hide it")
    rule = lesson["promoted"] if lesson["promoted"] and exempted_at(lesson) is None else ""  # a rules-only promotion
    lesson["promoted"] = clean(f"exempt@{lesson['hits']}: {reason}" + (f" (rule kept in {rule})" if rule else ""))
    ledger.save()
    print(f"exempted {lesson['id']} at {lesson['hits']} hits: {reason}. It stays in its section and is no longer "
          "flagged as a repeat without a guard, unless it recurs")
    return 0


def cmd_archive(ledger, args):
    lesson = ledger.find(args.id)
    lesson["section"] = "archive"
    ledger.save()
    print(f"archived {lesson['id']}")
    return 0


def cmd_promote(ledger, args):
    lesson = ledger.find(args.id)
    if args.keep_rule and not args.guard:
        raise Refused("--keep-rule goes with --guard PATH: it keeps the rule for what that guard does not cover")
    if args.guard:
        if not Path(args.guard).exists():
            raise Refused(f"guard {args.guard} does not exist; write it first")
        if EXEMPT_MARK.match(promotion.shown(args.guard)):
            raise Refused(f"guard path {args.guard} reads as an exemption mark; rename it")
        lesson["promoted"] = promotion.shown(args.guard)
        if args.keep_rule:  # a partial guard: the rest of the rule stays in force as an always-loaded rule
            path, appended = promotion.write_rule_stub(lesson, args.rules_dir or ledger.path.parent / "rules")
            lesson["promoted"] += f"{KEPT_RULE}{promotion.shown(path)}"
            print(f"rule {'written to' if appended else 'already present in'} {path}: it keeps the part of the rule "
                  "the guard does not cover")
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
        log_event(shared, "move", stored)
    lesson["promoted"], lesson["section"] = f"{MOVED_MARK}{stored['id']}", "archive"
    ledger.save()
    log_event(ledger, "move", lesson)
    print(f"global ledger: {message}\nmoved {lesson['id']} to {path} as {stored['id']}")
    return 0


def cmd_check(ledger, args):
    threshold = promote_at(args.min)
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
        if lesson["hits"] >= threshold and is_exempt(lesson):
            continue  # an exemption that holds: no candidate
        if lesson["hits"] >= threshold and exempted_at(lesson) is not None:
            print(f"candidate {lesson['id']} hits:{lesson['hits']}: recurred after its exemption ({lesson['promoted']}); "
                  "reconsider a guard, or exempt it again with the reason it still holds")
            continue
        if lesson["hits"] >= threshold and lesson["promoted"]:
            print(f"candidate {lesson['id']} hits:{lesson['hits']}: recurred after promotion to {lesson['promoted']}; "
                  "strengthen that guard")
        elif lesson["hits"] >= threshold:
            print(f"candidate {lesson['id']} hits:{lesson['hits']}: run `promote {lesson['id']}` (rule stub), or add "
                  "a test, lint, hook or CI guard and `promote --guard`")
    for problem in problems:
        print(f"problem: {problem}")
    print(f"{len(ledger.lessons)} lessons, {len(problems)} problems")
    return 1 if problems else 0


def ledger_sources(ledger, extra=(), shared=True):
    """This ledger, any ledger named and (unless shared is False) the global one, each once."""
    missing = [path for path in extra if not Path(path).is_file()]
    if missing:
        raise Refused(f"no ledger at {', '.join(missing)}")
    sources = []
    for source in [ledger, *(Ledger(Path(path), "L") for path in extra), open_global(ledger.path) if shared else None]:
        if source and all(source.path.resolve() != seen.path.resolve() for seen in sources):
            sources.append(source)
    return sources


def unguarded_lessons(sources, threshold):
    """(source, lesson) seen threshold+ times with no guard, archive included, most hits first."""
    found = [(source, lesson) for source in sources for lesson in source.lessons
             if lesson["hits"] >= threshold and unguarded(lesson)]
    return sorted(found, key=lambda item: -item[1]["hits"])


def cmd_unguarded(ledger, args):
    """Every lesson seen --min times or more with no guard, archive included, from this ledger, the global one and
    any ledger named; a lesson moved to the global ledger is counted there, not here."""
    threshold = promote_at(args.min)
    found = unguarded_lessons(ledger_sources(ledger, args.ledgers), threshold)
    for source, lesson in found:
        print(f"{lesson['id']} hits:{lesson['hits']} [{lesson['section']}] {source.path}: {lesson['rule']}")
    print(f"{len(found)} lessons seen {threshold}+ times without a guard")
    return 0


def cmd_cause(_ledger, args):
    """Accept a cause note, `<check or assertion>: <cause or unknown>`; writes nothing: the guard hook records that this
    command ran, which lifts the rerun-after-red refusal for the failed check."""
    what, _, cause = " ".join(args.note).partition(":")
    if not what.strip() or not cause.strip():
        raise Refused('a cause note reads "<check or assertion>: <cause or unknown>"')
    print("cause noted; rerun the failed command now")
    return 0


def cmd_hits(_ledger, args):
    try:
        seconds = guard_hits.window_seconds(args.since)
    except ValueError as error:
        raise Refused(str(error)) from None
    found, damaged = guard_hits.counts(seconds)
    for (lesson, rule), count in found.most_common():
        print(f"{lesson} ({rule}) x{count}")
    print(f"{sum(found.values())} guard refusals in the last {args.since} ({guard_hits.path()})"
          + (f"; {damaged} damaged lines skipped" if damaged else ""))
    return 0


def cmd_retro(ledger, args):
    if args.days < 1:
        raise Refused("--days must be 1 or more")
    sources = ledger_sources(ledger, shared=not args.project)
    print(retro.report(sources, unguarded_lessons(sources, promote_at()), args.days, date.fromisoformat(today()),
                       Path.cwd(), has_guard))
    return 0


def guard_state(lesson):
    """"moved" (a stub `globalize` left; the global ledger holds the lesson), else "exempt", "unguarded" or "guarded",
    by the same rules as `unguarded` and `exempt`."""
    if lesson["promoted"].startswith(MOVED_MARK):
        return "moved"
    if is_exempt(lesson):
        return "exempt"
    return "unguarded" if unguarded(lesson) else "guarded"


def cmd_metrics(ledger, args):
    if not 1 <= args.days <= metrics.MAX_DAYS:
        raise Refused(f"--days must be 1 to {metrics.MAX_DAYS}")
    prefix = args.lane_tag.strip().lower()
    if not prefix:
        raise Refused("--lane-tag must not be empty (default session:)")
    prefix += "" if prefix.endswith(":") else ":"  # `session` must not match `sessions:x` or keep the colon
    sources = ledger_sources(ledger, args.ledgers)
    threshold = promote_at()
    data = metrics.collect(sources, guard_state, unguarded_lessons(sources, threshold), threshold, args.days,
                           date.fromisoformat(today()), prefix, args.bus)
    print(json.dumps(data, indent=2) if args.json else metrics.markdown(data))
    return 0


def cmd_guards(_ledger, args):
    """Every registry problem, as this hook and as each cached hook version sees it. Exit 1 when this hook or a
    version an install references has one; a cached version no install references only warns (--strict: counts).
    --registry judges the given files instead of the ones in place: a dry run before writing a change. --target
    LIVE judges the one candidate as if it sat at LIVE (relative paths such as "exceptions" resolve there): it is
    copied to a temporary file beside LIVE, judged, and removed; running hooks read only lesson-guards.json."""
    if args.target:
        if len(dict.fromkeys(args.registry or [])) != 1:
            raise Refused("--target needs exactly one --registry candidate")
        target = Path(args.target)
        if not target.parent.is_dir():
            raise Refused(f"no folder for --target at {target.parent}")
        candidate = Path(args.registry[0])
        if not candidate.is_file():
            raise Refused(f"no registry file at {candidate}")
        handle = tempfile.NamedTemporaryFile("wb", dir=target.parent, prefix=".lesson-guards.candidate-",
                                             suffix=".json", delete=False)
        try:
            with handle:
                handle.write(candidate.read_bytes())
            print(f"candidate {candidate} judged as {target} (temporary copy {handle.name})")
            return judge_registries([Path(handle.name)], args, "candidate registries: ")
        finally:
            os.unlink(handle.name)
    if args.registry:
        missing = [path for path in args.registry if not Path(path).is_file()]
        if missing:
            raise Refused(f"no registry file at {', '.join(missing)}")
        paths = [Path(path) for path in dict.fromkeys(args.registry)]
    else:
        paths = guard_registry.registry_paths(relevance.session_cwd())
    if not paths:
        print("no lesson-guard registry applies here (.agents/lesson-guards.json, ~/.agents/lesson-guards.json)")
        return 0
    return judge_registries(paths, args, "candidate registries: " if args.registry else "registries: ")


def judge_registries(paths, args, header):
    """Print each registry problem as this hook and every cached version sees it; 1 when one blocks."""
    print(header + ", ".join(map(str, paths)))
    referenced = guard_registry.referenced_versions()
    if referenced is None:
        print("note: installed_plugins.json not readable: every cached version counts")
    found = guard_registry.report(paths, referenced=referenced)
    effects = {"refuses": ", REFUSES every Bash command", "fails-open": ", runs NO lesson guard (fails open)"}
    for label, problems, effect, _ in found:
        state = "ok" if not problems else f"{len(problems)} problem(s)" + effects.get(effect, "")
        print(f"{label}: {state}")
        for problem in problems:
            print(f"  - {problem}")
    blocking = any(problems for _, problems, _, counts in found if counts or args.strict)
    if not blocking and any(problems for _, problems, _, _ in found):
        print("warning: only cached versions no install references have problems; a session started before the last "
              "update may still run one: restart those sessions first, or use --strict")
    if blocking:
        print('fix the entries, or give a new rule "min_version" so older hooks skip it')
        return 1
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Lessons-learned ledger (project and global).")
    parser.add_argument("--file", default=os.environ.get("LESSONS_FILE") or ".agents/lessons.md")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--tags", default="")
    for name in ("mistake", "cause", "rule", "check"):
        add.add_argument(f"--{name}")
    sub.add_parser("active").add_argument("--hook", action="store_true")
    search = sub.add_parser("search")
    search.add_argument("words", nargs="+")
    search.add_argument("--full", action="store_true")
    sub.add_parser("show").add_argument("id")
    promote = sub.add_parser("promote")
    promote.add_argument("--as", dest="kind", choices=("rule", "test"), default="rule")
    promote.add_argument("--guard")
    promote.add_argument("--rules-dir")
    promote.add_argument("--keep-rule", action="store_true")
    unguarded = sub.add_parser("unguarded")
    unguarded.add_argument("ledgers", nargs="*")
    sub.add_parser("cause").add_argument("note", nargs="*")
    sub.add_parser("hits").add_argument("--since", default="24h")
    guards = sub.add_parser("guards")
    guards.add_argument("--registry", action="append", help="judge this file instead of the registries in place")
    guards.add_argument("--target", help="with one --registry: judge it as if it were this registry file")
    guards.add_argument("--strict", action="store_true", help="cached versions no install references count too")
    exempt = sub.add_parser("exempt")
    exempt.add_argument("--reason")
    retrospective = sub.add_parser("retro")
    retrospective.add_argument("--days", type=int, default=7)
    retrospective.add_argument("--project", action="store_true")
    report = sub.add_parser("metrics")
    report.add_argument("--days", type=int, default=7)
    report.add_argument("--lane-tag", default="session:",
                        help="tag prefix naming a lane (default session:; a missing : is added)")
    report.add_argument("--bus", help="bus folder holding open-items.tsv: adds the ETA accuracy per session")
    report.add_argument("--json", action="store_true")
    report.add_argument("--ledger", dest="ledgers", action="extend", nargs="+", default=[], metavar="FILE")
    by_id = [sub.add_parser(name) for name in ("bump", "archive", "globalize")] + [promote, exempt]
    for command in by_id:
        command.add_argument("id")
    check = sub.add_parser("check")
    for command in [add, check, *by_id[:2], promote, exempt]:
        command.add_argument("--global", dest="shared", action="store_true")
    for command in (check, unguarded):
        command.add_argument("--min", type=int)
    return parser


COMMANDS = {"add": cmd_add, "active": cmd_active, "search": cmd_search, "bump": cmd_bump, "archive": cmd_archive,
            "promote": cmd_promote, "globalize": cmd_globalize, "check": cmd_check, "show": cmd_show,
            "unguarded": cmd_unguarded, "cause": cmd_cause, "hits": cmd_hits, "retro": cmd_retro,
            "guards": cmd_guards, "exempt": cmd_exempt, "metrics": cmd_metrics}


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


def tolerate_unencodable_output():
    """A lesson with a character the console cannot encode still prints (as '?') instead of raising."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(errors="replace")


def main(argv=None):
    args = build_parser().parse_args(argv)
    tolerate_unencodable_output()
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
