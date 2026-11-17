"""Unit tests for the usage-stats skill: transcript parsing, the local store, the SessionEnd hook and the report."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "usage-stats" / "scripts" / "usage_stats.py"
sys.path.insert(0, str(SCRIPT.parent))

import usage_stats  # noqa: E402

SESSION = "11111111-2222-3333-4444-555555555555"
CWD = "/work/secret-project"
SECRET_COMMAND = "pytest tests/test_hidden_name.py"
GUARD_STOP = ("Stop hook feedback:\narsenal guard (asked once): source changed this session with no test change: "
              "app/secret_module.py. Add or update a test and run it. Then stop again.")


def line(kind, content=None, ts="2026-11-10T10:00:00.000Z", **extra):
    entry = {"type": kind, "sessionId": SESSION, "cwd": CWD, "version": "2.1.325", "timestamp": ts, **extra}
    if content is not None:
        entry["message"] = {"role": kind, "content": content}
    return json.dumps(entry)


def use(tool_id, name, **given):
    return line("assistant", [{"type": "tool_use", "id": tool_id, "name": name, "input": given}])


def result(tool_id, text="", error=False, **extra):
    return line("user", [{"type": "tool_result", "tool_use_id": tool_id, "content": text, "is_error": error}], **extra)


def start(version="1.5.0"):
    stdout = json.dumps({"hookSpecificOutput": {"additionalContext": (
        "Arsenal operating core (senior engineer defaults) ... python3 /home/u/.claude/plugins/cache/"
        f"senior-developer-arsenal/arsenal/{version}/.agents/skills/lessons-learned/scripts/lessons.py add")}})
    return json.dumps({"type": "attachment", "sessionId": SESSION, "cwd": CWD, "timestamp": "2026-11-10T09:59:00Z",
                       "attachment": {"type": "hook_success", "hookEvent": "SessionStart", "stdout": stdout}})


def stop_block(text=GUARD_STOP, meta=True):
    return line("user", text, isMeta=meta)


def denial(tool_id, reason):
    return result(tool_id, f"PreToolUse:Bash hook error: {reason}", error=True, toolDenialKind="permission-rule")


class Case(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.store = self.dir / "store" / "usage.jsonl"
        patcher = mock.patch.dict(os.environ, {"ARSENAL_USAGE_FILE": str(self.store)})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("ARSENAL_USAGE", None)

    def transcript(self, *lines, name=SESSION, folder="proj"):
        path = self.dir / "projects" / folder / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def summary(self, *lines, active=False):
        return usage_stats.summarize(self.transcript(*lines), "salt", active=active)


class ParsingTest(Case):
    def test_skills_subagents_and_slash_commands_are_counted_by_name(self):
        record = self.summary(
            start(), use("t1", "Skill", skill="arsenal:investigate"), use("t2", "Skill", skill="arsenal:investigate"),
            use("t3", "Skill", skill="other:thing"), use("t4", "Agent", subagent_type="arsenal:code-reviewer"),
            use("t5", "Task", subagent_type="general-purpose"),
            line("user", "<command-name>/arsenal:code-review</command-name>"))
        self.assertEqual(record["skills"], {"code-review": 1, "investigate": 2})
        self.assertEqual(record["subagents"], {"code-reviewer": 1})
        self.assertEqual(record["arsenal_version"], "1.5.0")

    def test_a_session_without_the_arsenal_is_not_kept(self):
        self.assertIsNone(self.summary(use("t1", "Skill", skill="other:thing"), line("user", "hello")))

    def test_live_record_counts_the_session_even_without_events(self):
        record = self.summary(line("user", "hello"), active=True)
        self.assertEqual(record["session"], SESSION)

    def test_stop_block_counts_only_the_meta_feedback_line(self):
        record = self.summary(start(), stop_block())
        self.assertEqual(record["blocks"], {"untested": 1, "failed": 0, "dead": 0})

    def test_quoted_guard_text_in_a_tool_output_or_user_text_is_not_a_block(self):
        record = self.summary(start(), use("t1", "Bash", command="cat hooks/guard.py"),
                              result("t1", GUARD_STOP + " arsenal guard: git reset --hard"),
                              stop_block(meta=False), line("user", "arsenal guard (asked once): quoted", isMeta=True))
        self.assertEqual(record["blocks"], {"untested": 0, "failed": 0, "dead": 0})
        self.assertEqual(record["denials"], {"destructive": 0, "lesson_guard": 0, "run_limit": 0})

    def test_block_kinds_and_their_resolution(self):
        text = ("Stop hook feedback:\narsenal guard (asked once): source changed this session with no test change: a.py."
                " Also: 1 test/build/lint command(s) failed this session (last: pytest). Also: dead code in this "
                "session's changes: a.py:3 commented-out.")
        record = self.summary(start(), stop_block(text),
                              use("t1", "Edit", file_path=f"{CWD}/tests/test_a.py"),
                              use("t2", "Edit", file_path=f"{CWD}/a.py"),
                              use("t3", "Bash", command="pytest -q"), result("t3", "1 passed"))
        self.assertEqual(record["blocks"], {"untested": 1, "failed": 1, "dead": 1})
        self.assertEqual(record["resolved"], {"untested": 1, "failed": 1, "dead": 1})

    def test_an_edit_before_the_block_does_not_resolve_it(self):
        record = self.summary(start(), use("t1", "Edit", file_path=f"{CWD}/tests/test_a.py"), stop_block())
        self.assertEqual(record["resolved"]["untested"], 0)
        self.assertEqual(record["edits"], {"source": 0, "test": 1})

    def test_denials_by_kind_and_the_guarded_lesson_id(self):
        record = self.summary(
            start(),
            use("t1", "Bash", command="git reset --hard"), denial("t1", "arsenal guard: git reset --hard discards work"),
            use("t2", "Bash", command="x"), denial("t2", "arsenal lesson guard G002 (pgrep-wait): wait on a pid"),
            use("t3", "Bash", command="y"), denial("t3", "arsenal run limit (/tmp/x): max calls"),
            use("t4", "Bash", command="z"), denial("t4", "[/home/u/other-hook]: blocked by policy"),
            use("t5", "Bash", command="w"), result("t5", "Permission to use Bash has been denied.", error=True,
                                                   toolDenialKind="permission-rule"))
        self.assertEqual(record["denials"], {"destructive": 1, "lesson_guard": 1, "run_limit": 1})
        self.assertEqual(record["lessons"]["guarded"], ["G002"])

    def test_an_error_without_a_denial_kind_is_not_a_denial(self):
        record = self.summary(start(), use("t1", "Bash", command="ls"),
                              result("t1", "PreToolUse:Bash hook error: arsenal guard: x", error=True))
        self.assertEqual(record["denials"]["destructive"], 0)

    def test_checks_fail_pass_and_red_to_green(self):
        record = self.summary(
            start(),
            use("t1", "Bash", command="pytest -x"), result("t1", "1 failed", error=True),
            use("t2", "Bash", command="echo hi"), result("t2", "hi"),
            use("t3", "Bash", command="pytest -q | tail"), result("t3", "1 passed"),
            use("t4", "Bash", command="cd x && pytest"), result("t4", "1 passed"),
            use("t5", "Bash", command="pytest"), result("t5", "", error=True,
                                                        toolUseResult={"interrupted": True}))
        self.assertEqual(record["checks"], {"failed": 1, "passed": 1, "red_to_green": 1})

    def test_a_pass_without_an_earlier_failure_is_not_red_to_green(self):
        record = self.summary(start(), use("t1", "Bash", command="npm test"), result("t1", "ok"))
        self.assertEqual(record["checks"], {"failed": 0, "passed": 1, "red_to_green": 0})

    def test_lessons_recorded_repeated_and_quoted(self):
        lessons = "python3 /x/lessons.py"
        record = self.summary(
            start(),
            use("t1", "Bash", command=f"{lessons} add --tags a --mistake m"), result("t1", "added L012"),
            use("t2", "Bash", command=f"{lessons} add --tags a"), result("t2", "duplicate of G003: rule"),
            use("t3", "Bash", command=f"{lessons} bump L007"), result("t3", "L007 hits:3"),
            use("t4", "Bash", command=f"{lessons} add --tags b"), result("t4", "failed", error=True),
            use("t5", "Bash", command='grep -n "lessons.py add" README.md'), result("t5", "added L099"),
            use("t6", "Bash", command=f"{lessons} add --tags c"), result("t6", ""),
            use("t7", "Bash", command=f"{lessons} add --tags d"), result("t7", "error: looks like a secret"),
            use("t8", "Bash", command=f"{lessons} bump G004"), result("t8", "PROMOTE G004: seen 5 times"),
            use("t9", "Bash", command=f"LESSONS_FILE=/tmp/l.md {lessons} add --tags e"), result("t9", "added L001"),
            use("t10", "Bash", command=f"{lessons} --file /tmp/l.md bump L001"), result("t10", "L001 hits:2"))
        self.assertEqual(record["lessons"], {"recorded": 1, "repeats": 3, "ids": ["L012"],
                                             "bumped": ["G003", "G004", "L007"], "guarded": []})

    def test_a_refused_lesson_does_not_resolve_a_failure_block(self):
        text = "Stop hook feedback:\narsenal guard (asked once): 1 test/build/lint command(s) failed this session."
        record = self.summary(start(), stop_block(text), use("t1", "Bash", command="python3 lessons.py add --x y"),
                              result("t1", "error: --mistake, --cause and --rule are required"))
        self.assertEqual(record["resolved"]["failed"], 0)

    def test_edits_are_classified_and_vendored_files_ignored(self):
        record = self.summary(start(), use("t1", "Write", file_path=f"{CWD}/src/app.ts"),
                              use("t2", "Edit", file_path=f"{CWD}/src/app.test.ts"),
                              use("t3", "Edit", file_path=f"{CWD}/node_modules/x/index.js"),
                              use("t4", "Edit", file_path=f"{CWD}/README.md"),
                              use("t5", "NotebookEdit", notebook_path=f"{CWD}/nb.ipynb"))
        self.assertEqual(record["edits"], {"source": 1, "test": 1})

    def test_sidechain_lines_are_skipped(self):
        record = self.summary(start(), line("assistant", [{"type": "tool_use", "id": "t1", "name": "Skill",
                                                           "input": {"skill": "arsenal:investigate"}}],
                                            isSidechain=True))
        self.assertEqual(record["skills"], {})

    def test_subagent_skill_and_agent_use_is_credited_to_the_parent_without_its_tokens(self):
        main = self.transcript(start(), use("t1", "Agent", subagent_type="arsenal:node-specialist"))
        usage = {"input_tokens": 1000, "output_tokens": 1000, "cache_creation_input_tokens": 0,
                 "cache_read_input_tokens": 0}
        heavy = json.loads(line("assistant", [{"type": "text", "text": "x"}], isSidechain=True, requestId="r9"))
        heavy["message"].update({"id": "m9", "usage": usage})
        sub = [line("assistant", [{"type": "tool_use", "id": "s1", "name": "Skill",
                                   "input": {"skill": "arsenal:test-every-change"}}], isSidechain=True),
               line("assistant", [{"type": "tool_use", "id": "s2", "name": "Agent",
                                   "input": {"subagent_type": "arsenal:code-explorer"}}], isSidechain=True),
               line("assistant", [{"type": "tool_use", "id": "s3", "name": "Bash",
                                   "input": {"command": "pytest -q"}}], isSidechain=True),
               json.dumps(heavy), "not json", "[1]"]
        folder = main.with_suffix("") / "subagents"
        folder.mkdir(parents=True)
        (folder / "agent-a1.jsonl").write_text("\n".join(sub) + "\n")
        (folder / "agent-broken.jsonl").mkdir()  # an unreadable entry costs only its own credit
        record = usage_stats.summarize(main, "salt")
        self.assertEqual(record["skills"], {"test-every-change": 1})
        self.assertEqual(record["subagents"], {"code-explorer": 1, "node-specialist": 1})
        self.assertEqual(record["tokens"]["input"], 0)  # the subagent's tokens are not added to the session
        self.assertEqual(record["checks"]["passed"], 0)

    def test_a_session_whose_only_arsenal_use_is_in_a_subagent_is_kept(self):
        main = self.transcript(line("user", "hello"))
        folder = main.with_suffix("") / "subagents"
        folder.mkdir(parents=True)
        (folder / "agent-a1.jsonl").write_text(line("assistant", [{"type": "tool_use", "id": "s1", "name": "Skill",
                                                                   "input": {"skill": "arsenal:investigate"}}],
                                                    isSidechain=True) + "\n")
        self.assertEqual(usage_stats.summarize(main, "salt")["skills"], {"investigate": 1})

    def test_tokens_are_summed_once_per_message(self):
        usage = {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 3, "cache_read_input_tokens": 7}
        message = line("assistant", [{"type": "text", "text": "x"}], requestId="r1")
        entry = json.loads(message)
        entry["message"].update({"id": "m1", "usage": usage})
        record = self.summary(start(), json.dumps(entry), json.dumps(entry))
        self.assertEqual(record["tokens"], {"input": 10, "output": 5, "cache_write": 3, "cache_read": 7})

    def test_dates_and_versions(self):
        record = self.summary(start(), line("user", "a", ts="2026-11-09T23:00:00-02:00"),
                              line("user", "b", ts="not a time"), line("user", "c", ts="2026-11-12T01:00:00Z"))
        self.assertEqual((record["first"], record["last"]), ("2026-11-10", "2026-11-12"))
        self.assertEqual(record["claude_version"], "2.1.325")

    def test_malformed_tool_parts_do_not_break_the_session(self):
        record = self.summary(start(), line("user", [{"type": "tool_result", "tool_use_id": ["x"], "is_error": True}]),
                              line("assistant", [{"type": "tool_use", "id": 7, "name": "Bash", "input": "ls"}]),
                              line("assistant", "plain text"), use("t1", "Skill", skill="arsenal:investigate"))
        self.assertEqual(record["skills"], {"investigate": 1})

    def test_missing_empty_and_garbage_transcripts(self):
        self.assertIsNone(usage_stats.summarize(self.dir / "missing.jsonl", "salt", active=True))
        self.assertIsNone(self.summary("", active=True))
        self.assertIsNone(self.summary("{not json", "[1, 2]", "null", active=True))

    def test_the_project_is_a_salted_hash(self):
        first = self.summary(start())["project"]
        self.assertRegex(first, r"^[0-9a-f]{12}$")
        self.assertNotEqual(first, usage_stats.summarize(self.transcript(start()), "other", active=False)["project"])


class StoreTest(Case):
    def secret_session(self):
        return self.transcript(
            start(), line("user", "please fix the secret_function in app"),
            use("t1", "Bash", command=SECRET_COMMAND), result("t1", "secret output text", error=True),
            use("t2", "Edit", file_path=f"{CWD}/secret_module.py", old_string="old_code", new_string="new_code"),
            stop_block())

    def test_backfill_is_idempotent_and_skips_subagent_files(self):
        self.secret_session()
        self.transcript(start(), use("t1", "Skill", skill="arsenal:investigate"), name="agent-1",
                        folder=f"proj/{SESSION}/subagents")
        self.assertEqual(usage_stats.backfill(self.dir / "projects"), (1, 1))
        first = self.store.read_bytes()
        self.assertEqual(usage_stats.backfill(self.dir / "projects"), (1, 1))
        self.assertEqual(self.store.read_bytes(), first)
        self.assertEqual(len(first.splitlines()), 1)

    def test_no_prompt_command_path_or_output_reaches_the_store(self):
        self.secret_session()
        usage_stats.backfill(self.dir / "projects")
        stored = self.store.read_text(encoding="utf-8")
        for secret in ("secret", "test_hidden_name", "old_code", "new_code", "/work", "pytest", "please"):
            self.assertNotIn(secret, stored)

    def test_the_salt_is_created_once_and_reused(self):
        salt = usage_stats.machine_salt(self.store)
        self.assertRegex(salt, r"^[0-9a-f]{32}$")
        self.assertEqual(usage_stats.machine_salt(self.store), salt)
        if os.name == "posix":
            self.assertEqual(self.store.with_name(self.store.name + ".salt").stat().st_mode & 0o777, 0o600)

    def test_a_damaged_salt_is_replaced(self):
        path = self.store.with_name(self.store.name + ".salt")
        path.parent.mkdir(parents=True)
        path.write_text("short\n")
        salt = usage_stats.machine_salt(self.store)
        self.assertRegex(salt, r"^[0-9a-f]{32}$")
        self.assertEqual(path.read_text().strip(), salt)

    def test_a_corrupt_store_line_is_kept_and_never_read_as_a_session(self):
        self.store.parent.mkdir(parents=True)
        self.store.write_text("{broken\n" + json.dumps({"session": "old", "first": "2026-01-01"}) + "\n")
        usage_stats.upsert(self.store, [{"session": "new", "first": "2026-02-01"}])
        records, other = usage_stats.read_store(self.store)
        self.assertEqual(sorted(records), ["new", "old"])
        self.assertEqual(other, ["{broken"])

    def test_upsert_replaces_by_session(self):
        usage_stats.upsert(self.store, [{"session": "a", "first": "2026-01-01", "n": 1}])
        usage_stats.upsert(self.store, [{"session": "a", "first": "2026-01-01", "n": 2}])
        self.assertEqual(usage_stats.read_store(self.store)[0], {"a": {"session": "a", "first": "2026-01-01", "n": 2}})

    def test_backfill_cli_rejects_a_missing_directory(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(usage_stats.main(["backfill", "--dir", str(self.dir / "nope")]), 2)


class HookTest(Case):
    def run_hook(self, payload, env=None):
        environment = {**os.environ, **(env or {})}
        done = subprocess.run([sys.executable, str(SCRIPT), "record"], input=payload, capture_output=True,
                              text=True, env=environment, timeout=60)
        return done

    def test_record_writes_one_session_and_prints_nothing(self):
        path = self.transcript(line("user", "hi"), use("t1", "Skill", skill="arsenal:investigate"))
        done = self.run_hook(json.dumps({"session_id": SESSION, "transcript_path": str(path)}))
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))
        records, _ = usage_stats.read_store(self.store)
        self.assertEqual(records[SESSION]["skills"], {"investigate": 1})
        self.assertRegex(records[SESSION]["arsenal_version"], r"^\d+\.\d+\.\d+$")

    def test_record_fails_open_on_bad_input(self):
        for payload in ("", "not json", "[]", json.dumps({"transcript_path": 5}),
                        json.dumps({"transcript_path": str(self.dir / "missing.jsonl")})):
            done = self.run_hook(payload)
            self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""), payload)
        self.assertFalse(self.store.exists())

    def test_record_fails_open_when_the_store_cannot_be_written(self):
        path = self.transcript(line("user", "hi"))
        blocker = self.dir / "file"
        blocker.write_text("x")
        done = self.run_hook(json.dumps({"transcript_path": str(path)}),
                             {"ARSENAL_USAGE_FILE": str(blocker / "usage.jsonl")})
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))

    def test_switched_off(self):
        path = self.transcript(line("user", "hi"))
        done = self.run_hook(json.dumps({"transcript_path": str(path)}), {"ARSENAL_USAGE": "OFF"})
        self.assertEqual(done.returncode, 0)
        self.assertFalse(self.store.exists())

    def test_wired_as_a_session_end_hook(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["SessionEnd"]
        command = hooks[0]["hooks"][0]
        self.assertIn('"${CLAUDE_PLUGIN_ROOT}/.agents/skills/usage-stats/scripts/usage_stats.py" record || python ',
                      command["command"])
        self.assertLessEqual(command["timeout"], 10)

    def test_core_marker_matches_the_injected_core(self):
        self.assertTrue((ROOT / "hooks" / "core.md").read_text(encoding="utf-8").startswith(usage_stats.CORE_MARK))


def record(session, first, last=None, project="p1", **fields):
    base = {"session": session, "first": first, "last": last or first, "project": project, "arsenal_version": "1.5.0",
            "skills": {}, "subagents": {}, "blocks": {}, "resolved": {}, "denials": {}, "checks": {},
            "lessons": {"recorded": 0, "repeats": 0, "ids": [], "bumped": [], "guarded": []},
            "edits": {}, "tokens": {}}
    base.update(fields)
    return base


class ReportTest(Case):
    TODAY = date(2026, 11, 17)

    def report(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = usage_stats.main(["report", *args], today=self.TODAY)
        return code, out.getvalue()

    def test_zero_sessions(self):
        code, text = self.report("--markdown")
        self.assertEqual(code, 0)
        self.assertIn("No sessions recorded yet", text)
        code, text = self.report("--json")
        self.assertEqual(json.loads(text)["sessions"], 0)
        self.assertIsNone(json.loads(text)["usefulness"]["missing_test_blocks_resolved"]["percent"])

    def test_numbers_and_their_bases(self):
        usage_stats.upsert(self.store, [
            record("a", "2026-11-01", edits={"source": 2, "test": 1}, skills={"investigate": 2},
                   blocks={"untested": 1}, resolved={"untested": 1}, checks={"red_to_green": 2, "failed": 3},
                   denials={"destructive": 1}, lessons={"recorded": 1, "repeats": 0, "ids": ["L001"], "bumped": [],
                                                        "guarded": []}),
            record("b", "2026-11-05", edits={"source": 1}, blocks={"untested": 1},
                   lessons={"recorded": 0, "repeats": 1, "ids": [], "bumped": ["L001"], "guarded": ["G002"]}),
            record("c", "2026-11-06", project="p2",
                   lessons={"recorded": 0, "repeats": 0, "ids": [], "bumped": [], "guarded": ["L001"]}),
        ])
        m = json.loads(self.report("--json")[1])
        self.assertEqual((m["sessions"], m["code_sessions"], m["projects"]), (3, 2, 2))
        self.assertEqual(m["usefulness"]["code_sessions_with_test_changes"], {"count": 1, "of": 2, "percent": 50.0})
        self.assertEqual(m["usefulness"]["missing_test_blocks_resolved"]["percent"], 50.0)
        self.assertEqual(m["usefulness"]["failed_checks_turned_green"], 2)
        self.assertEqual(m["smartness"]["code_sessions_with_a_skill"]["count"], 1)
        self.assertEqual(m["smartness"]["top_skills"], [{"name": "investigate", "sessions": 1, "calls": 2}])
        # L001 of project p1 was repeated in p1 later; the L001 guarded in p2 is another project's lesson.
        self.assertEqual(m["smartness"]["lessons"]["later_enforced"], 1)
        self.assertEqual(m["smartness"]["lessons"]["repeat_trend"],
                         [{"month": "2026-11", "sessions": 3, "repeats": 1, "per_100_sessions": 33.3}])

    def test_days_filter_boundary(self):
        usage_stats.upsert(self.store, [record("in", "2026-11-07"), record("out", "2026-11-06"),
                                        record("spans", "2026-10-01", last="2026-11-10"),
                                        {**record("undated", "2026-11-10"), "last": None}])
        self.assertEqual(json.loads(self.report("--days", "10", "--json")[1])["sessions"], 2)
        self.assertEqual(json.loads(self.report("--json")[1])["sessions"], 4)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.report("--days", "-1")[0], 2)

    def test_bad_numbers_in_a_record_count_as_zero(self):
        usage_stats.upsert(self.store, [record("a", "2026-11-01", edits={"source": "many", "test": -4},
                                               skills=["not", "a", "dict"], lessons=None)])
        m = json.loads(self.report("--json")[1])
        self.assertEqual((m["sessions"], m["code_sessions"]), (1, 0))

    def test_readme_block_is_replaced_and_nothing_else(self):
        usage_stats.upsert(self.store, [record("a", "2026-11-01", edits={"source": 1, "test": 1})])
        readme = self.dir / "README.md"
        readme.write_text(f"intro\n{usage_stats.BEGIN}\nold\n{usage_stats.END}\noutro\n")
        self.assertEqual(self.report("--readme", str(readme))[0], 0)
        text = readme.read_text()
        self.assertTrue(text.startswith(f"intro\n{usage_stats.BEGIN}\n| Measure | Value |"))
        self.assertTrue(text.endswith(f"{usage_stats.END}\noutro\n"))
        self.assertIn("1 of 1 (100.0%)", text)
        self.assertIn("2026-11-17", text)
        self.assertNotIn("old", text)

    def test_readme_without_exactly_one_block(self):
        readme = self.dir / "README.md"
        for text in ("no block", usage_stats.END + usage_stats.BEGIN, (usage_stats.BEGIN + usage_stats.END) * 2):
            readme.write_text(text)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.report("--readme", str(readme))[0], 2)
            self.assertEqual(readme.read_text(), text)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.report("--readme", str(self.dir / "missing.md"))[0], 2)

    def test_markdown_states_definitions_and_no_causal_claim(self):
        usage_stats.upsert(self.store, [record("a", "2026-11-01", blocks={"untested": 2}, resolved={"untested": 1})])
        text = self.report("--markdown")[1]
        self.assertIn("Missing-test blocks followed by a test edit: 1 of 2 (50.0%)", text)
        self.assertIn("not proof of cause", text)

    def test_usage_errors_exit_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(usage_stats.main([]), 2)
            self.assertEqual(usage_stats.main(["report", "--json", "--markdown"]), 2)


if __name__ == "__main__":
    unittest.main()
