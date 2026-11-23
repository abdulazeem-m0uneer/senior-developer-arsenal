"""Tests for the calendar lesson guard: hooks/guard_calendar.py, its registry entry, and its place in guard.py pre."""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
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

    def test_the_guessed_time_check_can_be_turned_off(self):
        for text in ("DONE x (checked 14:5x)", "ETA 16:xx", "my 01:0x line"):
            self.assertEqual(guard_calendar.problems(text, TODAY, SUN_THU, guessed_times=False), [], text)
            self.assertTrue(problems(text, SUN_THU), text)  # on by default
        [weekday] = guard_calendar.problems("ships Wed 11-26 at 14:5x", TODAY, guessed_times=False)
        self.assertIn("is a Thursday", weekday)
        [promise] = guard_calendar.problems("ETA 11-20 1x:30", TODAY, SUN_THU, guessed_times=False)
        self.assertIn("outside the workweek", promise)

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


FRI = dt.date(2026, 11, 20)  # the day after TODAY, outside Sun-Thu
GOOD_LINE = "2026-11-20 approved-by A. Lead: release day"


class ExceptionFileTests(unittest.TestCase):
    def test_good_lines_comments_and_blanks(self):
        text = f"# approved days\n\n{GOOD_LINE}\n  2026-11-28 approved-by Ops: inventory: all hands  \n2026-11-22 approved-by X: y\n"
        dates, found = guard_calendar.parse_exceptions(text)
        self.assertEqual(dates, {FRI, dt.date(2026, 11, 28), dt.date(2026, 11, 22)})  # the 22nd is a Sunday: fine
        self.assertEqual(found, [])

    def test_bad_lines_are_reported_with_their_number_and_apply_nothing(self):
        for line in ("2026-11-20", "2026-11-20 approved-by A. Lead", "2026-11-20 approved-by A. Lead:",
                     "2026-11-20 approved-by A. Lead:   ", "2026-11-20 approved-by : release",
                     "2026-11-20 approved-by   : release", "2026-11-20 approved by A: x", "approved-by A: x",
                     "garbage", "11-20 approved-by A: x", "2026-11-2 approved-by A: x"):
            self.assertEqual(guard_calendar.parse_exceptions(line), (set(), [
                "line 1: expected `YYYY-MM-DD approved-by <who>: <reason>` with both the approver and the reason "
                "(line ignored)"]), line)
        dates, found = guard_calendar.parse_exceptions("2026-02-30 approved-by A: x\n" + GOOD_LINE)
        self.assertEqual(dates, {FRI})
        self.assertEqual(found, ["line 1: 2026-02-30 is not a date (line ignored)"])

    def test_non_ascii_digits_are_not_a_date(self):
        dates, found = guard_calendar.parse_exceptions("\u0662\u0660\u0662\u0666-11-20 approved-by A: x")
        self.assertEqual((dates, len(found)), (set(), 1))

    def test_an_approved_friday_passes_and_an_unapproved_one_names_the_file(self):
        self.assertEqual(guard_calendar.problems("ETA Fri 11-20 10:00", TODAY, SUN_THU, {FRI}, "w.txt"), [])
        [problem] = guard_calendar.problems("ETA 11-20 10:00", TODAY, SUN_THU, {dt.date(2026, 11, 27)}, "w.txt")
        self.assertEqual(problem, "2026-11-20 is a Friday, outside the workweek; give a workday, record the approval "
                         "as `2026-11-20 approved-by <who>: <reason>` in w.txt if it was approved as a working day, "
                         "or write \"non-workday\" if it is meant")
        [plain] = guard_calendar.problems("ETA 11-20 10:00", TODAY, SUN_THU)
        self.assertNotIn("approved-by", plain)
        self.assertEqual(guard_calendar.problems("ETA 11-20 non-workday", TODAY, SUN_THU, (), "w.txt"), [])

    def test_read_exceptions_never_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            good = Path(folder, "w.txt")
            good.write_text(GOOD_LINE + "\ngarbage\n", encoding="utf-8")
            dates, found = guard_calendar.read_exceptions(str(good))
            self.assertEqual(dates, {FRI})
            self.assertEqual(len(found), 1)
            self.assertTrue(found[0].startswith(f"{good} line 2:"))
            self.assertEqual(guard_calendar.read_exceptions(str(Path(folder, "none.txt"))),
                             (set(), [f"{Path(folder, 'none.txt')}: not found, no workday exceptions apply"]))
            for name, make in (("dir", lambda p: p.mkdir()), ("bytes", lambda p: p.write_bytes(b"\xff\xfe\x00bad")),
                               ("big", lambda p: p.write_text("#" * (guard_calendar.EXCEPTIONS_MAX_BYTES + 1)))):
                path = Path(folder, name)
                make(path)
                dates, found = guard_calendar.read_exceptions(str(path))
                self.assertEqual((dates, len(found)), (set(), 1), name)
                self.assertIn("skipped", found[0], name)
            self.assertEqual(guard_calendar.read_exceptions("bad\0path")[0], set())

    def test_problem_lines_are_capped_per_file(self):
        dates, found = guard_calendar.parse_exceptions("junk\n" * 1000 + GOOD_LINE)
        self.assertEqual(dates, {FRI})
        self.assertEqual(len(found), 21)
        self.assertEqual(found[0][:7], "line 1:")
        self.assertEqual(found[19][:8], "line 20:")
        self.assertEqual(found[20], "980 more problem lines")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "w.txt")
            path.write_text("junk\n" * 21)
            dates, found = guard_calendar.read_exceptions(str(path))
            self.assertEqual((len(found), found[20]), (21, f"{path}: 1 more problem lines"))
            path.write_text("junk\n" * 20)
            self.assertEqual(len(guard_calendar.read_exceptions(str(path))[1]), 20)  # at the cap: no count line

    def test_approvers_filter_lines_exactly(self):
        text = (GOOD_LINE + "\n2026-11-27 approved-by a. lead: case\n2026-11-28 approved-by Intruder: self\n"
                "2026-11-29 approved-by   Boss  : spaces\n")
        dates, found = guard_calendar.parse_exceptions(text, frozenset(("A. Lead", "Boss")))
        self.assertEqual(dates, {FRI, dt.date(2026, 11, 29)})  # trimmed names match; another case does not
        self.assertEqual(found, ["line 2: 'a. lead' is not one of the registry's approvers (line ignored)",
                                 "line 3: 'Intruder' is not one of the registry's approvers (line ignored)"])
        self.assertEqual(guard_calendar.parse_exceptions(text)[0], {FRI, dt.date(2026, 11, 27), dt.date(2026, 11, 28),
                                                                   dt.date(2026, 11, 29)})  # no list: advisory
        dates, found = guard_calendar.parse_exceptions("2026-11-28 approved-by X: y\n" * 30, frozenset(("Boss",)))
        self.assertEqual((dates, len(found), found[20]), (set(), 21, "10 more problem lines"))

    def assert_refused_fast(self, path):
        started = time.monotonic()
        dates, found = guard_calendar.read_exceptions(str(path))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual((dates, len(found)), (set(), 1), found)
        self.assertEqual(found[0].split(":")[0], str(path))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFOs here")
    def test_a_fifo_is_refused_without_hanging(self):
        with tempfile.TemporaryDirectory() as folder:
            fifo = Path(folder, "w.txt")
            os.mkfifo(fifo)
            self.assert_refused_fast(fifo)

    @unittest.skipUnless(os.path.exists("/dev/zero"), "no /dev/zero")
    def test_a_link_to_an_endless_device_is_refused_without_reading_it(self):
        with tempfile.TemporaryDirectory() as folder:
            link = Path(folder, "w.txt")
            link.symlink_to("/dev/zero")
            self.assert_refused_fast(link)

    def test_a_directory_and_an_over_limit_file_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "d").mkdir()
            self.assert_refused_fast(Path(folder, "d"))
            big = Path(folder, "big")
            big.write_text("#" * (guard_calendar.EXCEPTIONS_MAX_BYTES + 1))
            self.assert_refused_fast(big)
            edge = Path(folder, "edge")
            edge.write_text(GOOD_LINE + "\n" + "#" * (guard_calendar.EXCEPTIONS_MAX_BYTES - len(GOOD_LINE) - 1))
            self.assertEqual(guard_calendar.read_exceptions(str(edge)), ({FRI}, []))  # exactly the limit is fine

    def test_any_fault_is_a_problem_line_never_an_exception(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "w.txt")
            path.write_text(GOOD_LINE)
            for fault in (RuntimeError("boom"), MemoryError()):
                with mock.patch.object(guard_calendar, "scan_exceptions", side_effect=fault):
                    dates, found = guard_calendar.read_exceptions(str(path))
                self.assertEqual((dates, len(found)), (set(), 1))
                self.assertIn(type(fault).__name__, found[0])


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

    def test_message_programs_run_by_a_shell_or_through_a_variable_are_read(self):
        for command in ('bash .agents/bus/send.sh pm dev "ships Wed 11-26"', 'sh /srv/repo/send.sh pm dev "ships Wed 11-26"',
                        'dash -e send.sh pm dev "ships Wed 11-26"', 'ksh -o errexit send.sh pm dev "ships Wed 11-26"',
                        'S=./send.sh; $S pm dev "ships Wed 11-26"', 'S=/srv/repo/send.sh && "$S" pm dev "ships Wed 11-26"',
                        'export S=/srv/repo/send.sh; ${S} pm dev "ships Wed 11-26"', 'S=send.sh; bash $S pm dev "ships Wed 11-26"',
                        '/bin/bash .agents/bus/send.sh pm dev "ships Wed 11-26"', 'bash +x send.sh pm dev "ships Wed 11-26"'):
            self.assertEqual(self.texts(command, ["send.sh"]), ["pm dev ships Wed 11-26"], command)
        # -ec runs the code "send.sh" with no arguments; the words after it are $0 and $1, not the program's
        for command in ("bash -c './send.sh pm dev \"ships Wed 11-26\"'", "bash -ec send.sh pm dev 'ships Wed 11-26'",
                        'bash other.sh pm "ships Wed 11-26"', 'S=./other.sh; $S pm "Wed 11-26"',
                        'S=./send.sh; echo "$S" pm "Wed 11-26"', 'X=./send.sh other.sh pm "Wed 11-26"', "bash"):
            self.assertEqual(self.texts(command, ["send.sh"]), [], command)

    def test_git_reads_stdin_only_for_a_dash_operand(self):
        for args in (["commit", "--file", "-"], ["commit", "--file=-"], ["commit", "-F-"], ["commit", "-aF", "-"]):
            self.assertTrue(guard_calendar.git_reads_stdin(args), args)
        for args in (["commit", "--file", "msg.txt"], ["commit", "--file"], ["commit", "--file=msg"],
                     ["commit", "-F", "msg.txt"], ["commit", "-m", "-"]):
            self.assertFalse(guard_calendar.git_reads_stdin(args), args)

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

    def test_guessed_times_switch_added_beside_an_older_entry(self):
        older = {"rule": "calendar", "lesson": "L187", "workweek": "Sun-Thu", "programs": ["send.sh"]}
        self.registry([older, {"rule": "calendar", "guessed_times": False, "min_version": "1.29.0"}])
        self.assertEqual(guard_lessons.registry_problems(str(self.dir)), [])
        self.assertIsNone(guard_lessons.judge('bash send.sh pm dev "DONE x (checked 14:5x)"', str(self.dir)))
        for command, problem in (('bash send.sh pm dev "START x ETA 11-20 10:00"', "outside the workweek"),
                                 ('S=./send.sh; $S pm dev "ships Wed 11-26"', "is a Thursday")):
            hit = guard_lessons.judge(command, str(self.dir))
            self.assertEqual(hit.lesson, "L187", command)
            self.assertIn(problem, hit.reason, command)
        self.registry([older])
        self.assertIn("14:5x is a guessed time",
                      guard_lessons.judge('bash send.sh pm dev "DONE x (checked 14:5x)"', str(self.dir)).reason)

    def test_registry_validation(self):
        for entry, fault in (({"rule": "calendar", "guessed_times": "no"}, "guessed_times"),
                             ({"rule": "help-probe", "guessed_times": False}, "guessed_times"),
                             ({"rule": "calendar", "workweek": "Sunday-Thursday"}, "workweek"),
                             ({"rule": "help-probe", "workweek": "Sun-Thu"}, "calendar rule only"),
                             ({"rule": "calendar", "programs": "notify.sh"}, "programs")):
            self.registry([entry])
            [problem] = guard_lessons.registry_problems(str(self.dir))
            self.assertIn(fault, problem, entry)
            self.assertEqual(guard_lessons.judge('git commit -m "Wed 11-26"', str(self.dir)).rule, "calendar")

    def exceptions(self, text=GOOD_LINE + "\n", **entry):
        (self.dir / "workdays.txt").write_text(text, encoding="utf-8")
        self.registry([{"rule": "calendar", "workweek": "Sun-Thu", "exceptions": "workdays.txt", **entry}])

    def judge(self, text):
        return guard_lessons.judge(f'gh pr comment 5 --body "{text}"', str(self.dir))

    def test_an_approved_friday_passes_and_an_unapproved_one_is_refused_with_the_hint(self):
        self.exceptions()
        self.assertIsNone(self.judge("ETA Fri 11-20 10:00"))
        self.assertIsNone(self.judge("ETA 11-22 10:00"))  # a Sunday: a workday anyway
        hit = self.judge("ETA 11-27 10:00")  # the next Friday: not approved
        self.assertIn(f"in {self.dir / 'workdays.txt'} if it was approved as a working day", hit.reason)
        self.assertIn("2026-11-27 is a Friday", hit.reason)
        self.assertIsNone(self.judge("ETA 11-27 10:00, non-workday"))  # the word keeps working
        self.assertEqual(guard_lessons.registry_problems(str(self.dir)), [])

    def test_without_the_key_the_refusal_is_as_before(self):
        self.registry([{"rule": "calendar", "workweek": "Sun-Thu"}])
        hit = self.judge("ETA 11-20 10:00")
        self.assertIn("give a workday, or write \"non-workday\" if it is meant", hit.reason)
        self.assertNotIn("approved-by", hit.reason)

    def test_past_dates_and_weekday_mistakes_are_unchanged_with_exceptions(self):
        self.exceptions()
        self.assertIsNone(self.judge("shipped on 11-13"))
        self.assertIn("is a Thursday", self.judge("ETA Wed 11-26").reason)

    def test_a_missing_file_is_no_exception_and_is_reported(self):
        self.exceptions(exceptions="gone.txt")
        self.assertIn("outside the workweek", self.judge("ETA 11-20 10:00").reason)
        self.assertEqual(guard_lessons.registry_problems(str(self.dir)),
                         [f"{self.dir / 'gone.txt'}: not found, no workday exceptions apply"])

    def test_an_unreadable_file_never_blocks_commands_and_is_reported(self):
        for make in (lambda path: path.mkdir(), lambda path: path.write_bytes(b"\xff\xfe bad")):
            self.registry([{"rule": "calendar", "workweek": "Sun-Thu", "exceptions": "workdays.txt"}])
            path = self.dir / "workdays.txt"
            if path.is_dir():
                path.rmdir()
            path.unlink(missing_ok=True)
            make(path)
            self.assertIsNone(guard_lessons.judge("ls -la", str(self.dir)))
            self.assertIsNone(guard_lessons.judge('git commit -m "ETA 11-22"', str(self.dir)))
            self.assertIn("outside the workweek", self.judge("ETA 11-20 10:00").reason)  # no exceptions, still judged
            [problem] = guard_lessons.registry_problems(str(self.dir))
            self.assertIn("skipped", problem)

    def test_a_fault_while_reading_the_file_leaves_every_other_rule_working(self):
        self.exceptions()
        for fault in (RuntimeError("boom"), MemoryError()):
            with mock.patch.object(guard_calendar, "scan_exceptions", side_effect=fault):
                self.assertEqual(guard_lessons.judge("git commit --no-verify -m x", str(self.dir)).rule, "hook-bypass")
                self.assertIn("outside the workweek", self.judge("ETA 11-20 10:00").reason)
                self.assertEqual(len(guard_lessons.registry_problems(str(self.dir))), 1)

    def test_a_disabled_calendar_rule_does_not_read_its_file(self):
        self.exceptions(enabled=False)
        with mock.patch.object(guard_calendar, "load_exceptions", side_effect=AssertionError("read")):
            self.assertIsNone(self.judge("ETA 11-20 10:00"))
            self.assertEqual(guard_lessons.registry_problems(str(self.dir)), [])

    def test_entries_sharing_a_file_read_and_report_it_once(self):
        (self.dir / "workdays.txt").write_text(GOOD_LINE + "\ngarbage\n", encoding="utf-8")
        (self.dir / "alias.txt").symlink_to(self.dir / "workdays.txt")
        entry = {"rule": "calendar", "workweek": "Sun-Thu"}
        self.registry([{**entry, "exceptions": "workdays.txt"}] * 300 + [{**entry, "exceptions": "alias.txt"}] * 300)
        with mock.patch.object(guard_calendar, "load_exceptions", wraps=guard_calendar.load_exceptions) as load:
            problems = guard_lessons.registry_problems(str(self.dir))
        self.assertEqual(load.call_count, 1)
        self.assertEqual(len(problems), 1)  # one bad line, one problem line

    def many_sources(self, count, text):
        (self.dir / "workdays.txt").write_text(text, encoding="utf-8")
        entry = {"rule": "calendar", "workweek": "Sun-Thu", "exceptions": "workdays.txt"}
        self.registry([{**entry, "approvers": [f"N{number}"]} for number in range(count)])

    def test_only_20_distinct_sources_are_processed_per_registry_read(self):
        self.many_sources(100, "2026-11-28 approved-by Intruder: x\n")
        with mock.patch.object(guard_calendar, "load_exceptions", wraps=guard_calendar.load_exceptions) as load:
            problems = guard_lessons.registry_problems(str(self.dir))
        self.assertEqual(load.call_count, 1)  # one file, read once for all its sources
        self.assertEqual(problems[-1], "80 more calendar exception sources ignored (limit 20)")
        self.assertEqual(len(problems), 20 + 1)  # one unlisted-approver line per processed source, one summary
        self.assertEqual(guard_lessons.read_registry(str(self.registry_file))[0][20].get("_approved_workdays"),
                         frozenset())

    def test_exception_problem_lines_are_capped_at_50_per_registry_read(self):
        self.many_sources(20, "junk\n" * 30)  # 21 problem lines per source: 420 in all
        problems = guard_lessons.registry_problems(str(self.dir))
        self.assertEqual(len(problems), 51)
        self.assertEqual(problems[50], "370 more calendar exception problem lines (limit 50)")

    def test_text_echoed_from_the_file_is_clipped_to_60_characters(self):
        self.exceptions("2026-11-20 approved-by " + "x" * 4000 + ": reason\n", approvers=["A. Lead"])
        [problem] = guard_lessons.registry_problems(str(self.dir))
        self.assertIn("'" + "x" * 59 + "\u2026'", problem)
        self.assertLess(len(problem), len(str(self.dir)) * 2 + 200)

    def test_a_path_the_os_rejects_obeys_the_caps_and_shows_no_os_text(self):
        self.registry([{"rule": "calendar", "exceptions": f"bad\0{number}"} for number in range(3000)])
        problems = guard_lessons.registry_problems(str(self.dir))
        self.assertEqual(len(problems), 20 + 1)
        self.assertEqual(problems[-1], "2980 more calendar exception sources ignored (limit 20)")
        self.assertTrue(all(problem.endswith(": ValueError") for problem in problems[:20]), problems[0])

    def test_only_the_first_20_raw_sources_cost_path_work_and_user_homes_are_not_looked_up(self):
        self.registry([{"rule": "calendar", "exceptions": f"~u{number}/x"} for number in range(2000)])
        started = time.monotonic()
        with mock.patch("os.path.expanduser", wraps=os.path.expanduser) as expand:
            problems = guard_lessons.registry_problems(str(self.dir))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(expand.call_count, 0)  # ~user is a problem line, never looked up
        self.assertEqual(len(problems), 20 + 1)
        self.assertEqual(problems[-1], "1980 more calendar exception sources ignored (limit 20)")
        self.registry([{"rule": "calendar", "exceptions": f"~/w{number}.txt"} for number in range(2000)])
        with mock.patch("os.path.expanduser", wraps=os.path.expanduser) as expand, \
                mock.patch.dict(os.environ, {"HOME": str(self.dir)}):
            guard_lessons.registry_problems(str(self.dir))
        self.assertEqual(expand.call_count, 20)

    def test_identical_failing_entries_report_once_and_a_bare_tilde_is_home(self):
        self.registry([{"rule": "calendar", "exceptions": "bad\0"}] * 5)
        self.assertEqual(len(guard_lessons.registry_problems(str(self.dir))), 1)
        self.registry([{"rule": "calendar", "exceptions": "~"}])
        with mock.patch.dict(os.environ, {"HOME": str(self.dir)}):
            [problem] = guard_lessons.registry_problems(str(self.dir))
        self.assertIn(f"{self.dir}: skipped, IsADirectoryError", problem)  # the home folder, not a ~user refusal

    def test_an_overlong_path_costs_no_path_work(self):
        for raw, fault in (("x" * 1025, "longer than 1024 characters"), ("a/" * 513, "longer than 1024 characters"),
                           ("a/" * 64 + "w", "more than 64 components"), ("a/" * 65, "more than 64 components"), ("../" * 65, "more than 64 components")):
            self.registry([{"rule": "calendar", "exceptions": raw}])
            with mock.patch("os.path.realpath") as real, mock.patch("os.path.expanduser") as expand:
                [problem] = guard_lessons.registry_problems(str(self.dir))
            self.assertEqual((real.call_count, expand.call_count), (0, 0), raw[:9])
            self.assertIn(fault, problem)
            self.assertLess(len(problem), len(str(self.dir)) + 120)
        self.registry([{"rule": "calendar", "exceptions": "a/" * 63 + "w"}])  # 64 components, 127 characters: allowed
        self.assertNotIn("components", guard_lessons.registry_problems(str(self.dir))[0])

    def test_huge_paths_do_not_stall_the_registry_read(self):
        for raw in ("a/" * 400000, "/proc/self/fd/../" * 50000):
            self.registry([{"rule": "calendar", "exceptions": raw}])
            started = time.monotonic()
            guard_lessons.rules(str(self.dir))
            self.assertLess(time.monotonic() - started, 0.5)
            self.assertEqual(len(guard_lessons.registry_problems(str(self.dir))), 1)

    def test_paths_are_clipped_in_every_problem_line(self):
        long = self.dir / ("d" * 100)
        long.mkdir()
        self.registry([{"rule": "calendar", "exceptions": f"{'d' * 100}/none.txt"},
                       {"rule": "calendar", "exceptions": f"{'d' * 100}", "approvers": ["A"]},
                       {"rule": "calendar", "exceptions": f"{'d' * 100}/w.txt", "approvers": ["A"]}])
        (long / "w.txt").write_text("2026-11-20 approved-by B: x\n" + "junk\n" * 30, encoding="utf-8")
        problems = guard_lessons.registry_problems(str(self.dir))
        self.assertGreater(len(problems), 3)
        for problem in problems:
            self.assertNotIn("d" * 61, problem)  # the long folder name is cut in every line
            self.assertLess(len(problem), 200, problem)
        self.assertTrue(any("\u2026 line 1:" in problem or "\u2026: not found" in problem for problem in problems))

    def test_a_long_path_is_clipped_for_every_kind_of_refusal(self):
        folder = self.dir / ("e" * 100)
        folder.mkdir()
        refused = {"big": lambda path: path.write_text("#" * (guard_calendar.EXCEPTIONS_MAX_BYTES + 1)),
                   "locked": lambda path: (path.write_text(GOOD_LINE), path.chmod(0))}
        if hasattr(os, "mkfifo"):
            refused["fifo"] = os.mkfifo
        for name, make in refused.items():
            make(folder / name)
            self.registry([{"rule": "calendar", "exceptions": f"{'e' * 100}/{name}"}])
            problems = guard_lessons.registry_problems(str(self.dir))
            if name == "locked" and not problems:  # running as a user who can read anything
                continue
            [problem] = problems
            self.assertNotIn("e" * 61, problem, name)
            self.assertIn("\u2026", problem, name)
        (folder / "many.txt").write_text("2026-11-20 approved-by B: x\n" + "junk\n" * 30, encoding="utf-8")
        self.registry([{"rule": "calendar", "exceptions": f"{'e' * 100}/many.txt", "approvers": ["A"]}])
        problems = guard_lessons.registry_problems(str(self.dir))
        self.assertEqual(len(problems), 21)  # 20 junk lines, then the count line (it includes the unlisted approver)
        for problem in problems:
            self.assertNotIn("e" * 61, problem)
        (folder / "one.txt").write_text("2026-11-20 approved-by B: x\n", encoding="utf-8")
        self.registry([{"rule": "calendar", "exceptions": f"{'e' * 100}/one.txt", "approvers": ["A"]}])
        [problem] = guard_lessons.registry_problems(str(self.dir))
        self.assertIn("\u2026 line 1: 'B' is not one of", problem)

    def test_a_home_path_is_read_from_home(self):
        (self.dir / "w.txt").write_text(GOOD_LINE + "\n", encoding="utf-8")
        self.registry([{"rule": "calendar", "workweek": "Sun-Thu", "exceptions": "~/w.txt"}])
        with mock.patch.dict(os.environ, {"HOME": str(self.dir)}):
            self.assertIsNone(self.judge("ETA 11-20 10:00"))

    def test_a_path_fault_is_one_clipped_problem_line(self):
        self.registry([{"rule": "calendar", "exceptions": "p" * 500}])
        with mock.patch("os.path.realpath", side_effect=RuntimeError("boom")):
            [problem] = guard_lessons.registry_problems(str(self.dir))
        self.assertIn("'" + "p" * 59 + "\u2026': RuntimeError", problem)
        self.assertNotIn("boom", problem)

    def test_approvers_accept_only_listed_names(self):
        self.exceptions("2026-11-20 approved-by A. Lead: ok\n2026-11-27 approved-by Intruder: self\n",
                        approvers=["A. Lead"])
        self.assertIsNone(self.judge("ETA 11-20 10:00"))
        self.assertIn("outside the workweek", self.judge("ETA 11-27 10:00").reason)  # the unlisted approver
        [problem] = guard_lessons.registry_problems(str(self.dir))
        self.assertIn("line 2: 'Intruder' is not one of the registry's approvers", problem)
        self.exceptions("2026-11-20 approved-by a. lead: ok\n", approvers=["A. Lead"])
        self.assertTrue(self.judge("ETA 11-20 10:00"))  # exact, case-sensitive
        self.exceptions(approvers=["Someone", "A. Lead"])
        self.assertIsNone(self.judge("ETA 11-20 10:00"))

    def test_approvers_key_validation(self):
        for entry, fault in (({"rule": "calendar", "approvers": "A. Lead"}, "approvers must be a list"),
                             ({"rule": "calendar", "approvers": []}, "approvers must be a list"),
                             ({"rule": "calendar", "approvers": ["A", 5]}, "approvers must be a list"),
                             ({"rule": "calendar", "approvers": ["A", "  "]}, "approvers must be a list"),
                             ({"rule": "help-probe", "approvers": ["A"]}, "calendar rule only")):
            self.registry([entry])
            [problem] = guard_lessons.registry_problems(str(self.dir))
            self.assertIn(fault, problem, entry)

    def test_a_malformed_file_keeps_its_good_lines_and_reports_the_rest(self):
        self.exceptions(f"{GOOD_LINE}\n2026-02-30 approved-by A: x\nnonsense\n2026-11-21 approved-by A\n")
        self.assertIsNone(self.judge("ETA 11-20 10:00"))
        self.assertTrue(self.judge("ETA 11-21 10:00"))  # its line has no reason: not applied
        self.assertEqual([problem.split(" ", 1)[1].split(":")[0] for problem in
                          guard_lessons.registry_problems(str(self.dir))], ["line 2", "line 3", "line 4"])

    def test_a_relative_path_is_read_from_the_registry_files_folder(self):
        sub = self.dir / "sub"
        sub.mkdir()
        (sub / "w.txt").write_text(GOOD_LINE, encoding="utf-8")
        (self.dir / "w.txt").write_text("# nothing approved here\n", encoding="utf-8")
        self.registry_file = sub / "reg.json"
        self.registry_file.write_text(json.dumps({"guards": [
            {"rule": "calendar", "workweek": "Sun-Thu", "exceptions": "w.txt"}]}), encoding="utf-8")
        with mock.patch.dict(os.environ, {"LESSONS_GUARDS_GLOBAL_FILE": str(self.registry_file)}):
            self.assertIsNone(self.judge("ETA 11-20 10:00"))  # sub/w.txt, not the working or project folder's
            self.registry_file.write_text(json.dumps({"guards": [
                {"rule": "calendar", "workweek": "Sun-Thu", "exceptions": str(self.dir / "w.txt")}]}),
                encoding="utf-8")
            self.assertTrue(self.judge("ETA 11-20 10:00"))  # an absolute path is used as given

    def test_exceptions_key_validation(self):
        for entry, fault in (({"rule": "calendar", "exceptions": 5}, "exceptions must be"),
                             ({"rule": "calendar", "exceptions": ""}, "exceptions must be"),
                             ({"rule": "calendar", "exceptions": ["a.txt"]}, "exceptions must be"),
                             ({"rule": "help-probe", "exceptions": "a.txt"}, "calendar rule only")):
            self.registry([entry])
            [problem] = guard_lessons.registry_problems(str(self.dir))
            self.assertIn(fault, problem, entry)
            self.assertEqual(guard_lessons.judge("ls", str(self.dir)), None)

    def test_the_exception_key_cannot_be_set_in_a_file(self):
        for key in ("_approved_workdays", "_exceptions_file"):
            self.registry([{"rule": "calendar", "workweek": "Sun-Thu", key: ["2026-11-20"]}])
            self.assertIn("unknown keys", guard_lessons.registry_problems(str(self.dir))[0])
            self.assertIsNone(self.judge("ETA 11-20 10:00"))  # the entry is skipped: nothing approved, no workweek

    def test_min_version_skips_an_entry_for_a_newer_hook_without_reading_its_file(self):
        self.exceptions(min_version="99.0.0")
        self.assertEqual(guard_lessons.registry_problems(str(self.dir)), [])
        self.assertIsNone(self.judge("ETA 11-20 10:00"))  # the entry is skipped: no workweek check at all
        self.exceptions(min_version="0.1.0")
        self.assertIsNone(self.judge("ETA 11-20 10:00"))  # applied and approved

    def test_the_project_entry_overrides_the_global_exceptions_file_key_by_key(self):
        self.exceptions()
        project = self.dir / ".agents"
        project.mkdir()
        registry = project / "lesson-guards.json"
        registry.write_text(json.dumps({"guards": [{"rule": "calendar", "lesson": "L1"}]}), encoding="utf-8")
        self.assertIsNone(self.judge("ETA 11-20 10:00"))  # keys merge: the global file still applies
        (project / "own.txt").write_text("2026-11-27 approved-by B: other\n", encoding="utf-8")
        registry.write_text(json.dumps({"guards": [{"rule": "calendar", "exceptions": "own.txt"}]}), encoding="utf-8")
        self.assertTrue(self.judge("ETA 11-20 10:00"))  # the project's file (in .agents/) replaces the global one
        self.assertIsNone(self.judge("ETA 11-27 10:00"))

    def test_outbound_tools_use_the_exceptions(self):
        self.exceptions()
        self.assertIsNone(guard_lessons.judge_outbound("mcp__mail__send_message", {"body": "ETA 11-20"}, str(self.dir)))
        self.assertTrue(guard_lessons.judge_outbound("mcp__mail__send_message", {"body": "ETA 11-27"}, str(self.dir)))

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
