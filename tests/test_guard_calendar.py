"""Tests for the calendar lesson guard: hooks/guard_calendar.py, its registry entry, and its place in guard.py pre."""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "hooks" / "guard.py"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import guard_calendar  # noqa: E402
import guard_destructive  # noqa: E402
import guard_lessons  # noqa: E402
import hook_env  # noqa: E402

TODAY = dt.date(2026, 11, 19)  # a Thursday
SUN_THU = guard_calendar.parse_workweek("Sun-Thu")


def problems(text, workweek=None):
    return guard_calendar.problems(text, TODAY, workweek)


class ProblemTests(unittest.TestCase):
    def test_a_weekday_must_match_its_date(self):
        for text in ("ships Wed 11-26", "Thurs 11-27", "Tues 11-25", "Weds 11-26", "Mon 11/25", "wed 11-26",
                     "Wednesday 2026-11-26", "Thu, 11-20"):
            [problem] = problems(text)
            self.assertIn("is a", problem, text)
            self.assertIn("date -d", problem, text)
        for text in ("ships Thu 11-26", "Fri 11-27", "Monday 2027-01-04", "Sat 08-01", "Thursday, 11-19"):
            self.assertEqual(problems(text), [], text)

    def test_dates_that_do_not_exist(self):
        self.assertEqual(problems("Mon 02-30"), ["Mon 02-30 is not a date"])
        self.assertEqual(problems("Mon 2027-02-30"), ["Mon 2027-02-30 is not a date"])  # the year is shown
        self.assertEqual(problems("due 2027-02-29"), ["2027-02-29 is not a date"])
        for text in ("ETA 13-40 10:00", "by 10-12 people", "up by 10-12%", "on 30-40 hosts", "until 12-45 ms"):
            self.assertEqual(problems(text), [], text)  # a bare pair that is no date may be a range

    def test_text_that_only_looks_like_a_date(self):
        for text in ("office Mon-Fri 9-5", "Tue 10-12 people", "Wed 10-12:30 slot", "Tue 10-12 hrs", "Fri 11-6",
                     "see you Monday", "Monthly 11-26 renewal", "build 10-12 done", "v1.10.0-12"):
            self.assertEqual(problems(text), [], text)

    def test_guessed_clock_times(self):
        for text in ("deployed at 16:4x", "back 1x:30", "ETA 16:xx", "rolled at 9:5?"):
            [problem] = problems(text)
            self.assertIn("guessed time", problem, text)
        for text in ("deployed at 16:45", "0x1f:30", "10:00-12:00", "ratio 3:2", "build 16:4", "16:45x"):
            self.assertEqual(problems(text), [], text)

    def test_the_nearest_year_is_meant(self):
        self.assertEqual(guard_calendar.problems("Mon 01-04", dt.date(2026, 12, 30)), [])  # 2027-01-04
        self.assertEqual(guard_calendar.problems("Sat 08-01", TODAY), [])  # 2026-08-01, past
        self.assertTrue(guard_calendar.problems("Sat 01-04", dt.date(2026, 12, 30)))

    def test_a_promise_outside_the_workweek(self):
        for text in ("ETA 11-20 10:00", "done by 11-21", "Fri 11-20 release", "due 2026-11-21", "deadline: 11-20",
                     "until 11-20", "on 11-21"):
            [problem] = problems(text, SUN_THU)
            self.assertIn("outside the workweek", problem, text)
        for text in ("ETA 11-22 10:00", "Thu 11-26 release", "ETA 11-20 10:00, a non-workday on purpose",
                     "Fri 11-20 release (Non-Workday)"):
            self.assertEqual(problems(text, SUN_THU), [], text)
        self.assertEqual(problems("ETA 11-20 10:00"), [])  # no workweek: no check
        for text in ("migrated on 11-14", "on 2026-11-13 we shipped", "Fri 11-13 release went out"):
            self.assertEqual(problems(text, SUN_THU), [], text)  # a past date is a fact, not a promise
        self.assertTrue(problems("ETA 11-21 10:00", SUN_THU))  # today's week, Saturday: still a promise
        for text in ("latency down by 11-21%", "p95 until 11-21 ms", "scaled by 11-21x"):  # units, not dates
            self.assertEqual(problems(text, SUN_THU), [], text)

    def test_one_line_per_mistake(self):
        found = problems("Wed 11-26 and Wed 11-26 at 16:4x, ETA 11-21", SUN_THU)
        self.assertEqual(len(found), 3)  # the wrong weekday, the guess, and the non-workday promise


class WorkweekTests(unittest.TestCase):
    def test_ranges_and_lists(self):
        self.assertEqual(guard_calendar.parse_workweek("Sun-Thu"), {6, 0, 1, 2, 3})
        self.assertEqual(guard_calendar.parse_workweek("Mon-Fri"), {0, 1, 2, 3, 4})
        self.assertEqual(guard_calendar.parse_workweek("Fri-Mon"), {4, 5, 6, 0})
        self.assertEqual(guard_calendar.parse_workweek("Wed-Wed"), {2})
        self.assertEqual(guard_calendar.parse_workweek(["Sat", "Sun"]), {5, 6})

    def test_bad_values(self):
        for bad in ("sun-thu", "Sun to Thu", "Sun-", "", [], ["Sunday"], [1], 5, None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                guard_calendar.parse_workweek(bad)


class OutboundTests(unittest.TestCase):
    def texts(self, command, programs=()):
        return guard_calendar.outbound_texts("Bash", {"command": command}, list(programs), guard_destructive)

    def test_message_commands_are_read(self):
        for command in ('gh pr comment 5 --body "x"', 'gh pr create -t x -b "y"', 'gh pr review 5 -b x',
                        'gh issue comment 9 -b x', 'gh issue edit 9 --body x', 'gh release create v1 -n x',
                        'git commit -m "x"', 'git -C repo commit -am x', "cd a && git commit -m x"):
            self.assertTrue(self.texts(command), command)
        self.assertEqual(self.texts("./notify.sh team 'hello'", ["notify.sh"]), ["team hello"])
        self.assertTrue(self.texts("bus/notify.sh team x", ["notify.sh"]))

    def test_heredoc_bodies_of_message_commands_are_read(self):
        for command in ("git commit -F - <<'EOF'\nfix: ships Wed 11-26\nEOF",
                        "git commit -m \"$(cat <<'EOF'\nfix: ships Wed 11-26\nEOF\n)\"",
                        "gh pr create -t x --body \"$(cat <<'EOF'\nships Wed 11-26\nEOF\n)\""):
            self.assertIn("ships Wed 11-26", "\n".join(self.texts(command)), command)
        self.assertEqual(self.texts("python3 - <<'EOF'\nprint('Wed 11-26')\nEOF"), [])

    def test_gh_global_flags_tags_and_glued_values(self):
        for command in ("gh -R owner/repo pr comment 5 -b x", "gh --repo o/r issue comment 9 -b x",
                        "gh --hostname h.example -R o/r pr create -t x -b y", "git tag -a v1 -m x"):
            self.assertTrue(self.texts(command), command)
        self.assertIn("-m Wed 11-26", self.texts("git commit -m'Wed 11-26'")[0])

    def test_other_commands_are_not(self):
        for command in ('echo "Wed 11-26"', "cat notes.md", "gh pr view 5", "gh pr list", "git log -5",
                        "python3 - <<'EOF'\nprint('Wed 11-26')\nEOF", "gh api repos/x/y", "ls"):
            self.assertEqual(self.texts(command), [], command)

    def test_mcp_tools_that_send(self):
        tool_input = {"to": "a@b.c", "body": "Wed 11-26", "meta": {"notes": ["x", {"y": "z"}]}, "count": 3}
        texts = guard_calendar.outbound_texts("mcp__mail__send_message", tool_input, [], guard_destructive)
        self.assertEqual(texts, ["a@b.c", "Wed 11-26", "x", "z"])
        for name in ("mcp__tracker__create_task_comment", "mcp__chat__post", "mcp__mail__create_draft",
                     "mcp__tracker__update_task", "mcp__slack__reply"):
            self.assertTrue(guard_calendar.outbound_texts(name, {"t": "x"}, [], guard_destructive), name)
        for name in ("mcp__tracker__tracker_create_task_comment", "mcp__chat_app__chat_send_message",
                     "mcp__mail_app__create_draft", "mcp__mail__forward", "mcp__docs__add_comment"):
            self.assertTrue(guard_calendar.outbound_texts(name, {"t": "x"}, [], guard_destructive), name)
        for name in ("mcp__tracker__get_task", "mcp__mail__search_threads", "mcp__mail__get_message",
                     "mcp__tracker__get_task_comments", "mcp__chat__get_chat_channel_messages",
                     "mcp__github__create_or_update_file", "mcp__drive__upload_file", "mcp__x__send_file",
                     "Write", "Edit", "Read", "Agent", None, "send_message"):
            self.assertEqual(guard_calendar.outbound_texts(name, {"t": "x"}, [], guard_destructive), [], name)


class CalendarRuleTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.registry_file = self.dir / "lesson-guards.json"
        env = {"LESSONS_GUARDS_GLOBAL_FILE": str(self.registry_file), "CLAUDE_PROJECT_DIR": str(self.dir),
               "ARSENAL_NOW": "2026-11-19T11:00:00"}
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)

    def registry(self, guards):
        self.registry_file.write_text(json.dumps({"guards": guards}), encoding="utf-8")

    def test_on_by_default_for_messages(self):
        hit = guard_lessons.judge('gh pr comment 5 --body "ships Wed 11-26"', str(self.dir))
        self.assertEqual((hit.rule, hit.lesson), ("calendar", None))
        self.assertIn("Wed 2026-11-26 is a Thursday", hit.reason)
        self.assertIsNone(guard_lessons.judge('gh pr comment 5 --body "ships Thu 11-26"', str(self.dir)))
        self.assertIsNone(guard_lessons.judge('echo "Wed 11-26"', str(self.dir)))

    def test_registry_entry(self):
        self.registry([{"rule": "calendar", "lesson": "L187", "workweek": "Sun-Thu", "programs": ["notify.sh"]}])
        hit = guard_lessons.judge("./notify.sh pm 'ETA 11-20 10:00'", str(self.dir))
        self.assertEqual(hit.lesson, "L187")
        self.assertIn("outside the workweek", hit.reason)
        self.registry([{"rule": "calendar", "reason": "Check the date first."}])
        self.assertEqual(guard_lessons.judge('git commit -m "Wed 11-26"', str(self.dir)).reason,
                         "Check the date first.")
        self.registry([{"rule": "calendar", "enabled": False}])
        self.assertIsNone(guard_lessons.judge('git commit -m "Wed 11-26"', str(self.dir)))

    def test_registry_validation(self):
        for entry, fault in (({"rule": "calendar", "workweek": "Sunday-Thursday"}, "workweek"),
                             ({"rule": "help-probe", "workweek": "Sun-Thu"}, "calendar rule only"),
                             ({"rule": "calendar", "programs": "notify.sh"}, "programs")):
            self.registry([entry])
            [problem] = guard_lessons.registry_problems(str(self.dir))
            self.assertIn(fault, problem, entry)
            self.assertEqual(guard_lessons.judge('git commit -m "Wed 11-26"', str(self.dir)).rule, "calendar")

    def test_outbound_tools(self):
        hit = guard_lessons.judge_outbound("mcp__mail__send_message", {"body": "see you Wed 11-26"}, str(self.dir))
        self.assertEqual(hit.rule, "calendar")
        self.assertIsNone(guard_lessons.judge_outbound("mcp__mail__send_message", {"body": "Thu 11-26"},
                                                       str(self.dir)))
        self.assertIsNone(guard_lessons.judge_outbound("Write", {"content": "Wed 11-26"}, str(self.dir)))
        self.registry([{"rule": "calendar", "enabled": False}])
        self.assertIsNone(guard_lessons.judge_outbound("mcp__mail__send_message", {"body": "Wed 11-26"},
                                                       str(self.dir)))

    def test_the_clock_override(self):
        with mock.patch.dict(os.environ, {"ARSENAL_NOW": "2031-03-05T09:00:00"}):  # not today, whenever this runs
            self.assertEqual(guard_lessons.today(), dt.date(2031, 3, 5))
            self.assertIsNone(guard_lessons.judge('git commit -m "Wed 2031-03-05"', str(self.dir)))
        with mock.patch.dict(os.environ, {"ARSENAL_NOW": "not-a-date"}):
            self.assertEqual(guard_lessons.today(), dt.date.today())


class HookTests(unittest.TestCase):
    """guard.py pre run as Claude Code runs it."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)

    def pre(self, tool, tool_input, **env):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
                   "cwd": str(self.dir), "permission_mode": "default"}
        base = {k: v for k, v in os.environ.items() if not k.startswith(("ARSENAL_", "LESSONS_"))
                and k != "CLAUDE_PROJECT_DIR"}
        base.update(hook_env.lesson_guard_files(self.dir), HANDOFF_SNAPSHOT=str(self.dir / "snap.md"),
                    ARSENAL_NOW="2026-11-19T11:00:00", CLAUDE_PROJECT_DIR=str(self.dir), **env)
        done = subprocess.run([sys.executable, str(SCRIPT), "pre"], input=json.dumps(payload), capture_output=True,
                              text=True, cwd=self.dir, env=base)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["hookSpecificOutput"] if done.stdout.strip() else None

    def test_an_mcp_send_with_a_wrong_weekday_is_denied_and_logged(self):
        out = self.pre("mcp__mail__send_message", {"body": "ships Wed 11-26"})
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("(calendar)", out["permissionDecisionReason"])
        hits = (self.dir / "lesson-guard-hits.jsonl").read_text()
        self.assertIn('"rule": "calendar"', hits)
        self.assertNotIn("ships", hits)

    def test_bash_messages_and_switches(self):
        self.assertEqual(self.pre("Bash", {"command": 'gh pr comment 5 --body "Wed 11-26"'})["permissionDecision"],
                         "deny")
        self.assertIsNone(self.pre("Bash", {"command": 'gh pr comment 5 --body "Wed 11-26"'},
                                   ARSENAL_LESSON_GUARDS="off"))
        self.assertIsNone(self.pre("mcp__mail__send_message", {"body": "ships Thu 11-26"}))
        self.assertIsNone(self.pre("Write", {"file_path": str(self.dir / "t.py"), "content": "Wed 11-26"}))

    def test_odd_tool_input_never_breaks_the_hook(self):
        for tool_input in (None, "text", [1, 2], {"body": None}, {"deep": [[["Thu 11-26"]]]}):
            self.assertIsNone(self.pre("mcp__mail__send_message", tool_input), repr(tool_input))


if __name__ == "__main__":
    unittest.main()
