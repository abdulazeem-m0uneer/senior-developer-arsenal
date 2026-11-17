#!/usr/bin/env python3
"""Local usage statistics of the arsenal, read from Claude Code session transcripts: what it caught and what it did.

Usage:
  usage_stats.py record                         # SessionEnd hook: hook JSON on stdin; prints nothing, always exits 0
  usage_stats.py backfill [--dir DIR]           # every *.jsonl transcript under DIR (default ~/.claude/projects)
  usage_stats.py report [--days N] [--json | --markdown] [--readme README.md]
  usage_stats.py diagnose <transcript> | --session ID | --last [--dir DIR] [--json]  # missed skills, core gaps
Store: one JSON line per session in $ARSENAL_USAGE_FILE (default ~/.agents/arsenal-usage.jsonl), replaced by
session id with an atomic rewrite under a lock, so record and backfill can run any number of times. A per-machine
random salt beside it (<store>.salt) hashes the working directory into a project id. Only counts, dates, skill
and subagent names, lesson ids and version numbers are stored: never a prompt, command, path, output or code.
ARSENAL_USAGE=off turns off `record` only. Only sessions where the arsenal was active are kept: its SessionStart
hook ran, or one of its skills, subagents or guards appears in the session.
Transcript fields read (observed on Claude Code 2.1.321 to 2.1.325; undocumented): Skill and Agent/Task tool_use
inputs, `<command-name>/arsenal:x</command-name>` in user text, the Stop gate's `isMeta` user line that starts with
"Stop hook feedback:", PreToolUse denials (a tool_result with is_error true on a line that carries toolDenialKind),
Bash tool_use commands paired with their tool_result by id, edit tool file paths, SessionStart hook attachments
and message.usage. Text inside tool outputs is never searched: a session that prints guard source code quotes
every marker. Lines with isSidechain true are skipped, and so are files under a subagents/ folder as sessions of their
own; a session's subagent transcripts (<session>/subagents/*.jsonl) credit only their Skill and Agent use to it.
Exit codes: 0 on success, 2 on a missing directory, a bad argument or a README without exactly one usage block.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # importing the helpers must not leave __pycache__ in the plugin
HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent.parent
# Plugin and repository: <root>/hooks beside <root>/.agents/skills. Installer: <dir>/arsenal-hooks beside <dir>/skills.
HOOK_DIRS = (SKILLS.parent.parent / "hooks", SKILLS.parent / "arsenal-hooks")
SCHEMA = 1

SKILL_PREFIX = "arsenal:"
NAME = re.compile(r"^[\w-]{1,64}$")
LESSON_ID = re.compile(r"^[LG]\d{3,6}$")
COMMAND_NAME = re.compile(r"<command-name>/?arsenal:([\w-]{1,64})</command-name>")
STOP_FEEDBACK, STOP_MARK = "Stop hook feedback:", "arsenal guard (asked once)"
BLOCK_KINDS = (("untested", "no test change"), ("failed", "failed this session"),
               ("dead", "dead code in this session's changes"))
DENIAL_PREFIX = re.compile(r"^(?:PreToolUse:\w+ hook error: )?(?:\[[^\]\n]*\]: )?")
DENIAL_KINDS = (("lesson_guard", "arsenal lesson guard "), ("destructive", "arsenal guard: "),
                ("run_limit", "arsenal run limit"))
GUARDED_LESSON = re.compile(r"^arsenal lesson guard ([LG]\d{3,6})\b")
# What lessons.py prints for the lesson it wrote or counted: "added L012", "duplicate of G003: ...", "L012 hits:3",
# and before 1.5 "PROMOTE L012: seen 3 times". Output without an id (a refusal, a background launch) counts nothing.
LESSON_OUTPUT = re.compile(r"\b(added|duplicate of) ([LG]\d{3,6})\b|^(?:PROMOTE )?([LG]\d{3,6})(?: hits:\d+|: seen \d+ times)",
                           re.M)
# A ledger named on the command line is a test or a manual check (measured: most such adds), not the user's ledger.
CUSTOM_LEDGER = re.compile(r"\bLESSONS_(?:GLOBAL_)?FILE=|\s--file[=\s]")
CORE_MARK = "Arsenal operating core"  # first words of hooks/core.md, injected by the SessionStart hook
VERSION = re.compile(r"/arsenal/(\d+\.\d+\.\d+)/")
EDIT_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
TOKEN_KEYS = ("input", "output", "cache_write", "cache_read")
BEGIN, END = "<!-- BEGIN usage -->", "<!-- END usage -->"


def load_helpers():
    """hooks/guard.py (check_keys, LESSON_COMMAND, kind) and usage_report.py (token lines); None when missing."""
    hooks = next((d for d in HOOK_DIRS if (d / "guard.py").is_file()), None)
    for folder in (SKILLS / "autonomous-run" / "scripts", hooks):
        if folder and str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
    try:
        import guard
    except (Exception, SystemExit):  # guard.py exits 0 on a broken install
        guard = None
    try:
        import usage_report
    except Exception:
        usage_report = None
    return guard, usage_report


GUARD, TOKENS = load_helpers()


def store_path():
    return Path(os.environ.get("ARSENAL_USAGE_FILE") or Path.home() / ".agents" / "arsenal-usage.jsonl").expanduser()


def machine_salt(store):
    """The random salt beside the store, created once (0600); the same salt hashes a folder to the same id."""
    path = store.with_name(store.name + ".salt")

    def stored():
        try:
            value = path.read_text(encoding="utf-8").strip()
        except (OSError, ValueError):
            return None
        return value if re.match(r"^[0-9a-f]{32,}$", value) else None

    value = stored()
    if value:
        return value
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_hex(16)
    try:
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:  # another session created it meanwhile (use it), or it is damaged (replace it)
        if stored():
            return stored()
        write_atomic(path, value + "\n")
        return value
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(value + "\n")
    return value


def write_atomic(path, text):
    """Write text to path through a temp file in the same folder and os.replace (0600)."""
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content
                         if isinstance(part, dict) and isinstance(part.get("text"), str))
    return ""


def day(timestamp):
    """YYYY-MM-DD of an ISO 8601 timestamp, or None."""
    if not isinstance(timestamp, str):
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc).date().isoformat()
    except ValueError:
        return None


def relative(path, cwd):
    """A repo-relative form for guard.kind: relative to cwd when inside it, else the path without its root."""
    if cwd and path.startswith(cwd.rstrip("/") + "/"):
        return path[len(cwd.rstrip("/")) + 1:]
    return path.lstrip("/")


class Summary:
    """One session's counts, built line by line in transcript order."""

    def __init__(self):
        self.session = self.cwd = self.claude = self.arsenal = None
        self.first = self.last = None
        self.active = False
        self.skills, self.subagents = Counter(), Counter()
        self.blocks, self.resolved, self.pending = Counter(), Counter(), Counter()
        self.denials, self.checks, self.edits = Counter(), Counter(), Counter()
        self.recorded, self.repeats = 0, 0
        self.lesson_ids, self.bumped, self.guarded = set(), set(), set()
        self.tokens, self.seen_usage = Counter(), set()
        self.commands, self.red = {}, set()

    def resolve(self, kind):
        self.resolved[kind] += self.pending.pop(kind, 0)

    def feed(self, raw):
        try:
            entry = json.loads(raw)
        except ValueError:
            return
        if not isinstance(entry, dict) or entry.get("isSidechain") is True:
            return
        if self.session is None and isinstance(entry.get("sessionId"), str) and NAME.match(entry["sessionId"]):
            self.session = entry["sessionId"]
        if self.cwd is None and isinstance(entry.get("cwd"), str):
            self.cwd = entry["cwd"]
        if isinstance(entry.get("version"), str) and re.match(r"^[\w.-]{1,32}$", entry["version"]):
            self.claude = entry["version"]
        moment = day(entry.get("timestamp"))
        if moment:
            self.first = min(self.first or moment, moment)
            self.last = max(self.last or moment, moment)
        self.count_tokens(raw)
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        content = message.get("content")
        kind = entry.get("type")
        if kind == "attachment":
            self.attachment(entry.get("attachment"))
        elif kind == "user":
            self.user(entry, content)
        elif kind == "assistant" and isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool_use":
                    self.tool_use(part)

    def feed_subagent(self, raw):
        """A subagent transcript line: its Skill and Agent use is credited to the parent session. Nothing else is
        read from it: tokens stay the main session's (counted once), and guards and checks are the parent's."""
        if '"tool_use"' not in raw:  # most lines; skipped unparsed, so long builder transcripts stay cheap
            return
        try:
            entry = json.loads(raw)
        except ValueError:
            return
        if not isinstance(entry, dict):
            return
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        content = message.get("content")
        if entry.get("type") == "assistant" and isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool_use" and part.get("name") in (
                        "Skill", "Agent", "Task"):
                    self.tool_use(part)

    def count_tokens(self, raw):
        if TOKENS is None or '"usage"' not in raw:
            return
        parsed = TOKENS.parse_line(raw)
        if parsed is None:
            return
        key, _, counts = parsed
        if key is not None and key in self.seen_usage:
            return
        self.seen_usage.add(key)
        for name, value in zip(TOKEN_KEYS, counts):
            self.tokens[name] += value

    def attachment(self, attachment):
        if not isinstance(attachment, dict) or attachment.get("hookEvent") != "SessionStart":
            return
        text = f"{attachment.get('stdout') or ''}\n{attachment.get('content') or ''}"
        if CORE_MARK in text:
            self.active = True
        found = VERSION.search(text)
        if found:
            self.arsenal, self.active = found.group(1), True

    def user(self, entry, content):
        if isinstance(content, str):
            if entry.get("isMeta") is True and content.startswith(STOP_FEEDBACK) and STOP_MARK in content:
                for name, phrase in BLOCK_KINDS:
                    if phrase in content:
                        self.blocks[name] += 1
                        self.pending[name] += 1
            elif entry.get("isMeta") is not True:
                self.skills.update(COMMAND_NAME.findall(content))
            return
        if not isinstance(content, list):
            return
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                self.skills.update(COMMAND_NAME.findall(part["text"]))
            elif part.get("type") == "tool_result":
                self.tool_result(entry, part)

    def tool_use(self, part):
        name, given = part.get("name"), part.get("input")
        given = given if isinstance(given, dict) else {}
        if name == "Skill":
            self.named(self.skills, given.get("skill"))
        elif name in ("Agent", "Task"):
            self.named(self.subagents, given.get("subagent_type"))
        elif name == "Bash" and isinstance(given.get("command"), str) and isinstance(part.get("id"), str):
            self.commands[part["id"]] = given["command"]  # kept in memory to pair with its result, never stored
        elif name in EDIT_TOOLS and GUARD is not None and isinstance(given.get(EDIT_TOOLS[name]), str):
            changed = GUARD.kind(relative(given[EDIT_TOOLS[name]], self.cwd))
            if changed:
                self.edits[changed] += 1
                self.resolve("untested" if changed == "test" else "dead")

    @staticmethod
    def named(counter, value):
        if isinstance(value, str) and value.startswith(SKILL_PREFIX) and NAME.match(value[len(SKILL_PREFIX):]):
            counter[value[len(SKILL_PREFIX):]] += 1

    def tool_result(self, entry, part):
        tool_id = part.get("tool_use_id")
        command = self.commands.pop(tool_id, None) if isinstance(tool_id, str) else None
        failed = part.get("is_error") is True
        if failed and "toolDenialKind" in entry:
            reason = DENIAL_PREFIX.sub("", text_of(part.get("content")).lstrip(), count=1)
            for name, prefix in DENIAL_KINDS:
                if reason.startswith(prefix):
                    self.denials[name] += 1
                    lesson = GUARDED_LESSON.match(reason)
                    if lesson:
                        self.guarded.add(lesson.group(1))
                    break
            return  # a denied command did not run
        result = entry.get("toolUseResult")
        if command is None or GUARD is None or (isinstance(result, dict) and result.get("interrupted") is True):
            return
        if failed:
            keys = GUARD.check_keys(command)
            if keys:
                self.checks["failed"] += 1
                self.red.update(keys)
            return
        keys = GUARD.check_keys(command, decisive=True)  # a pass hidden by `| tail` or `|| true` proves nothing
        if keys:
            self.checks["passed"] += 1
            self.checks["red_to_green"] += len(self.red.intersection(keys))
            self.red.difference_update(keys)
            self.resolve("failed")
        if (GUARD.LESSON_COMMAND.search(GUARD.bounded(command)) and not CUSTOM_LEDGER.search(command)
                and self.lesson(text_of(part.get("content")))):
            self.resolve("failed")

    def lesson(self, output):
        """Count what lessons.py reported; True when it recorded or counted at least one lesson."""
        matches = LESSON_OUTPUT.findall(output)
        for verb, lesson, bumped in matches:
            if verb == "added":
                self.recorded += 1
                self.lesson_ids.add(lesson)
            else:
                self.repeats += 1
                self.bumped.add(lesson or bumped)
        return bool(matches)

    def used_arsenal(self):
        return self.active or bool(self.skills or self.subagents or self.blocks or self.denials)

    def result(self, salt):
        if self.session is None or self.first is None:
            return None
        project = hashlib.sha256((salt + self.cwd).encode("utf-8")).hexdigest()[:12] if self.cwd else None

        def counts(counter, keys):
            return {key: counter.get(key, 0) for key in keys}
        return {
            "schema": SCHEMA, "session": self.session, "first": self.first, "last": self.last, "project": project,
            "claude_version": self.claude, "arsenal_version": self.arsenal,
            "skills": dict(sorted(self.skills.items())), "subagents": dict(sorted(self.subagents.items())),
            "blocks": counts(self.blocks, ("untested", "failed", "dead")),
            "resolved": counts(self.resolved, ("untested", "failed", "dead")),
            "denials": counts(self.denials, ("destructive", "lesson_guard", "run_limit")),
            "checks": counts(self.checks, ("failed", "passed", "red_to_green")),
            "lessons": {"recorded": self.recorded, "repeats": self.repeats, "ids": sorted(self.lesson_ids),
                        "bumped": sorted(self.bumped), "guarded": sorted(self.guarded)},
            "edits": counts(self.edits, ("source", "test")),
            "tokens": counts(self.tokens, TOKEN_KEYS),
        }


def summarize(transcript, salt="", active=False):
    """The session record of one transcript, or None when unreadable, empty, or the arsenal was not active in it."""
    summary = Summary()
    summary.active = active
    try:
        with Path(transcript).open(encoding="utf-8", errors="replace") as lines:
            for raw in lines:
                summary.feed(raw)
    except OSError:
        return None
    for path in subagent_transcripts(Path(transcript)):
        try:
            with path.open(encoding="utf-8", errors="replace") as lines:
                for raw in lines:
                    summary.feed_subagent(raw)
        except OSError:
            continue  # one unreadable subagent file costs only its own credit
    return summary.result(salt) if summary.used_arsenal() else None


def subagent_transcripts(transcript):
    """<project>/<session>/subagents/*.jsonl beside <project>/<session>.jsonl (observed on Claude Code 2.1.325)."""
    folder = transcript.with_suffix("") / "subagents"
    return sorted(folder.glob("*.jsonl")) if folder.is_dir() else []


@contextmanager
def locked(store):
    """An exclusive lock beside the store (POSIX); without fcntl the write is still atomic, only not serialised."""
    store.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
    except ImportError:
        yield
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)  # never through a planted link
    with os.fdopen(os.open(store.with_name(store.name + ".lock"), flags, 0o600), "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def read_store(store):
    """(records by session id, lines that are not records); a missing store reads as empty."""
    records, other = {}, []
    try:
        lines = store.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return records, other
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            record = None
        if isinstance(record, dict) and isinstance(record.get("session"), str):
            records[record["session"]] = record
        elif line.strip():
            other.append(line)  # never written by this script: kept as found, never read as a session
    return records, other


def upsert(store, new_records):
    """Replace or add records by session id with one atomic rewrite; returns the number of records written."""
    with locked(store):
        records, other = read_store(store)
        for record in new_records:
            records[record["session"]] = record
        ordered = sorted(records.values(), key=lambda r: (str(r.get("first")), r["session"]))
        write_atomic(store, "".join(json.dumps(r, sort_keys=True) + "\n" for r in ordered)
                     + "".join(line + "\n" for line in other))
    return len(new_records)


def own_version():
    found = VERSION.search(HERE.as_posix())
    if found:
        return found.group(1)
    try:
        text = (SKILLS.parent.parent / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text if re.match(r"^\d+\.\d+\.\d+$", text) else None


def record_hook(stdin):
    """SessionEnd: hand this session's transcript to a detached process and return at once. Claude Code gives a
    SessionEnd hook little time on exit, and a long transcript takes seconds to read; the detached process outlives
    the hook. ARSENAL_USAGE_SYNC=1 records inline instead. Fails open: prints nothing, returns 0."""
    if os.environ.get("ARSENAL_USAGE", "").strip().lower() == "off":
        return 0
    try:
        data = json.loads(stdin.read() or "{}")
        transcript = data.get("transcript_path") if isinstance(data, dict) else None
        if not isinstance(transcript, str) or not transcript:
            return 0
        if os.environ.get("ARSENAL_USAGE_SYNC", "").strip() == "1":
            return record_transcript(transcript)
        detach = {"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "record", "--transcript", transcript],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True, **detach)
    except Exception:  # a hook must never break the session
        pass
    return 0


def record_transcript(transcript):
    """Summarise one transcript into the store (the detached half of record_hook). Fails open, returns 0."""
    try:
        store = store_path()
        record = summarize(Path(transcript), machine_salt(store), active=True)
        if record is None:
            return 0
        record["arsenal_version"] = record["arsenal_version"] or own_version()
        upsert(store, [record])
    except Exception:  # a hook must never break the session
        pass
    return 0


def transcripts(directory):
    """Main-session transcripts under directory: subagent files are sidechains of a session already counted."""
    for path in sorted(directory.rglob("*.jsonl")):
        if "subagents" not in path.relative_to(directory).parts[:-1] and path.is_file():
            yield path


def backfill(directory):
    store = store_path()
    salt = machine_salt(store)
    found, records = 0, []
    for path in transcripts(directory):
        found += 1
        record = summarize(path, salt)
        if record is not None:
            records.append(record)
    upsert(store, records)
    return found, len(records)


def selected(records, days, today):
    """Records whose last day is on or after today minus `days` days (all of them when days is None)."""
    if days is None:
        return list(records)
    cutoff = (today - timedelta(days=days)).isoformat()
    return [r for r in records if isinstance(r.get("last"), str) and r["last"] >= cutoff]


def section(record, name):
    value = record.get(name)
    return value if isinstance(value, dict) else {}


def number(record, name, key):
    value = section(record, name).get(key, 0)
    return value if type(value) is int and value > 0 else 0


def total(records, name, key):
    return sum(number(r, name, key) for r in records)


def ratio(part, whole):
    return {"count": part, "of": whole, "percent": round(100 * part / whole, 1) if whole else None}


def lesson_key(record, lesson):
    """A project lesson id (L012) names a different lesson in each project; a global one (G003) is one lesson."""
    return lesson if lesson.startswith("G") else f"{record.get('project')}:{lesson}"


def lesson_ids(record, field):
    values = section(record, "lessons").get(field)
    return [v for v in values if isinstance(v, str) and LESSON_ID.match(v)] if isinstance(values, list) else []


def lesson_metrics(records):
    recorded_on = {}
    for r in records:
        for lesson in lesson_ids(r, "ids"):
            key = lesson_key(r, lesson)
            recorded_on[key] = min(recorded_on.get(key, str(r.get("first"))), str(r.get("first")))
    enforced = {key for r in records for field in ("bumped", "guarded") for lesson in lesson_ids(r, field)
                if (key := lesson_key(r, lesson)) in recorded_on and str(r.get("last")) >= recorded_on[key]}
    months, repeats = Counter(), Counter()
    for r in records:
        month = str(r.get("first"))[:7]
        months[month] += 1
        repeats[month] += number(r, "lessons", "repeats")
    trend = [{"month": m, "sessions": months[m], "repeats": repeats[m],
              "per_100_sessions": round(100 * repeats[m] / months[m], 1)} for m in sorted(months)[-6:]]
    return {"recorded": total(records, "lessons", "recorded"), "repeats": total(records, "lessons", "repeats"),
            "recorded_with_id": len(recorded_on), "later_enforced": len(enforced), "repeat_trend": trend}


def metrics(records):
    """The report numbers; every value carries the count it is a share of."""
    code = [r for r in records if number(r, "edits", "source")]
    tokens = [number(r, "tokens", "output") + number(r, "tokens", "input") + number(r, "tokens", "cache_write")
              for r in records]
    skill_sessions, subagent_sessions, skill_calls = Counter(), Counter(), Counter()
    for r in records:
        for name, calls in section(r, "skills").items():
            skill_sessions[name] += 1
            skill_calls[name] += calls if type(calls) is int else 0
        subagent_sessions.update(section(r, "subagents").keys())
    days = {str(r.get(field)) for r in records for field in ("first", "last") if r.get(field)}
    return {
        "sessions": len(records), "code_sessions": len(code),
        "from": min(days) if days else None, "to": max(days) if days else None, "active_days": len(days),
        "projects": len({r.get("project") for r in records if r.get("project")}),
        "arsenal_versions": dict(sorted(Counter(str(r.get("arsenal_version") or "unknown") for r in records).items())),
        "usefulness": {
            "code_sessions_with_test_changes": ratio(sum(1 for r in code if number(r, "edits", "test")), len(code)),
            "missing_test_blocks_resolved": ratio(total(records, "resolved", "untested"),
                                                  total(records, "blocks", "untested")),
            "failed_check_blocks_resolved": ratio(total(records, "resolved", "failed"),
                                                  total(records, "blocks", "failed")),
            "dead_code_blocks_resolved": ratio(total(records, "resolved", "dead"), total(records, "blocks", "dead")),
            "failed_checks_turned_green": total(records, "checks", "red_to_green"),
            "failed_check_runs": total(records, "checks", "failed"),
            "destructive_commands_stopped": total(records, "denials", "destructive"),
            "repeat_mistakes_stopped": total(records, "denials", "lesson_guard"),
            "run_limit_stops": total(records, "denials", "run_limit"),
        },
        "smartness": {
            "code_sessions_with_a_skill": ratio(sum(1 for r in code if section(r, "skills")), len(code)),
            "sessions_with_a_skill_or_subagent": ratio(
                sum(1 for r in records if section(r, "skills") or section(r, "subagents")), len(records)),
            "top_skills": [{"name": n, "sessions": s, "calls": skill_calls[n]} for n, s in skill_sessions.most_common(8)],
            "top_subagents": [{"name": n, "sessions": s} for n, s in subagent_sessions.most_common(5)],
            "lessons": lesson_metrics(records),
        },
        "cost": {"tokens_per_session_median": int(statistics.median(tokens)) if tokens else 0,
                 "tokens_per_session_mean": int(statistics.fmean(tokens)) if tokens else 0},
    }


def share(value):
    if value["percent"] is None:
        return "0 of 0"
    return f"{value['count']} of {value['of']} ({value['percent']}%)"


def render_markdown(m):
    if not m["sessions"]:
        return "# Arsenal usage\n\nNo sessions recorded yet. Run `usage_stats.py backfill`, or wait for a session to end.\n"
    use, smart, lessons = m["usefulness"], m["smartness"], m["smartness"]["lessons"]
    lines = [
        "# Arsenal usage", "",
        f"From {m['sessions']} of my Claude Code sessions with the arsenal active, {m['from']} to {m['to']}"
        f" ({m['active_days']} active days, {m['projects']} projects). Counts of what happened, not proof of cause:"
        " there is no comparison group of sessions without it.", "",
        "## Useful", "",
        f"- Code-changing sessions that also changed tests: {share(use['code_sessions_with_test_changes'])}.",
        f"- Missing-test blocks followed by a test edit: {share(use['missing_test_blocks_resolved'])}.",
        f"- Unresolved-failure blocks followed by a passing check or a lesson: {share(use['failed_check_blocks_resolved'])}.",
        f"- Dead-code blocks followed by a source edit: {share(use['dead_code_blocks_resolved'])}.",
        f"- Failed checks that later passed in the same session: {use['failed_checks_turned_green']}"
        f" (of {use['failed_check_runs']} failed check runs).",
        f"- Destructive commands denied: {use['destructive_commands_stopped']}.",
        f"- Repeat mistakes denied by a lesson guard: {use['repeat_mistakes_stopped']}.", "",
        "## Smart", "",
        f"- Code-changing sessions where an arsenal skill fired: {share(smart['code_sessions_with_a_skill'])}.",
        f"- Sessions with an arsenal skill or subagent: {share(smart['sessions_with_a_skill_or_subagent'])}.",
        f"- Lessons recorded to the project or global ledger (a ledger named on the command line is a test and is"
        f" not counted): {lessons['recorded']}; with an id: {lessons['recorded_with_id']};"
        f" later enforced (a guard denial or a repeat count on or after the day it was recorded): {lessons['later_enforced']}.",
        "- Top skills (sessions, calls): " + (", ".join(f"`{s['name']}` {s['sessions']}/{s['calls']}"
                                                     for s in smart["top_skills"]) or "none") + ".",
        "- Top subagents (sessions): " + (", ".join(f"`{s['name']}` {s['sessions']}"
                                                  for s in smart["top_subagents"]) or "none") + ".", "",
        "Lesson repeats per 100 sessions by month (falling means mistakes stop recurring):", "",
        "| Month | Sessions | Repeats | Per 100 sessions |", "| :--- | ---: | ---: | ---: |",
        *[f"| {t['month']} | {t['sessions']} | {t['repeats']} | {t['per_100_sessions']} |" for t in lessons["repeat_trend"]],
        "", "## Cost", "",
        f"- Tokens per session (input + cache writes + output): median {m['cost']['tokens_per_session_median']:,},"
        f" mean {m['cost']['tokens_per_session_mean']:,}.",
        "- Arsenal versions seen: " + ", ".join(f"{v} ({n})" for v, n in m["arsenal_versions"].items()) + ".", "",
    ]
    return "\n".join(lines)


def render_block(m, today):
    use, smart = m["usefulness"], m["smartness"]
    rows = [
        ("Sessions with the arsenal active", f"{m['sessions']} ({m['from']} to {m['to']})"),
        ("Code-changing sessions that also changed tests", share(use["code_sessions_with_test_changes"])),
        ("Missing-test blocks followed by a test", share(use["missing_test_blocks_resolved"])),
        ("Failed checks that later passed", str(use["failed_checks_turned_green"])),
        ("Destructive commands denied", str(use["destructive_commands_stopped"])),
        ("Repeat mistakes denied by lesson guards", str(use["repeat_mistakes_stopped"])),
        ("Code-changing sessions where a skill fired", share(smart["code_sessions_with_a_skill"])),
        ("Lessons recorded / later enforced", f"{smart['lessons']['recorded']} / {smart['lessons']['later_enforced']}"),
    ] if m["sessions"] else [("Sessions with the arsenal active", "0")]
    return "\n".join([BEGIN, "| Measure | Value |", "| :--- | :--- |", *[f"| {a} | {b} |" for a, b in rows], "",
                      f"_From the maintainer's own sessions, generated {today.isoformat()} by"
                      " `usage_stats.py report --readme`. Counts, not proof of cause._", END])


def update_readme(text, block):
    if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) > text.index(END):
        raise ValueError("README must contain exactly one usage block (BEGIN before END)")
    return text[:text.index(BEGIN)] + block + text[text.index(END) + len(END):]


def main(argv=None, stdin=None, today=None):
    parser = argparse.ArgumentParser(description="Local usage statistics of the arsenal.")
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="SessionEnd hook: hook JSON on stdin")
    record.add_argument("--transcript", help="record this transcript now (what the hook's detached process runs)")
    fill = commands.add_parser("backfill", help="summarise every transcript under --dir")
    fill.add_argument("--dir", default=str(Path.home() / ".claude" / "projects"))
    report = commands.add_parser("report", help="print the numbers")
    report.add_argument("--days", type=int, help="only sessions active in the last N days")
    style = report.add_mutually_exclusive_group()
    style.add_argument("--json", action="store_true")
    style.add_argument("--markdown", action="store_true")
    report.add_argument("--readme", help="rewrite the usage block of this README")
    check = commands.add_parser("diagnose", help="missed skills and operating-core gaps in one session")
    check.add_argument("transcript", nargs="?")
    pick = check.add_mutually_exclusive_group()
    pick.add_argument("--session")
    pick.add_argument("--last", action="store_true")
    check.add_argument("--dir", default=str(Path.home() / ".claude" / "projects"))
    check.add_argument("--json", action="store_true")
    try:
        options = parser.parse_args(argv)
    except SystemExit as stop:
        return 0 if stop.code == 0 else 2
    if options.command == "record":
        return record_transcript(options.transcript) if options.transcript else record_hook(stdin or sys.stdin)
    if options.command == "diagnose":
        import diagnose  # here, not at the top: diagnose imports this module
        return diagnose.run(options.transcript, options.session, options.last, options.dir, options.json)
    if options.command == "backfill":
        directory = Path(options.dir).expanduser()
        if not directory.is_dir():
            print(f"not a directory: {directory}", file=sys.stderr)
            return 2
        found, kept = backfill(directory)
        print(f"read {found} transcripts, kept {kept} sessions with the arsenal active in {store_path()}")
        return 0
    if options.days is not None and options.days < 0:
        print("--days must be 0 or more", file=sys.stderr)
        return 2
    today = today or datetime.now(timezone.utc).date()
    records, _ = read_store(store_path())
    m = metrics(selected(records.values(), options.days, today))
    if options.readme:
        readme = Path(options.readme)
        try:
            readme.write_text(update_readme(readme.read_text(encoding="utf-8"), render_block(m, today)), encoding="utf-8")
        except (OSError, ValueError) as error:
            print(error, file=sys.stderr)
            return 2
    print(json.dumps(m, indent=2) if options.json else render_markdown(m))
    return 0


if __name__ == "__main__":
    sys.exit(main())
