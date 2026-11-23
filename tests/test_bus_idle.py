"""Tests for the bus idle check, idle.py: lanes holding only future ETAs with no sign of work past a threshold."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".agents" / "skills" / "multi-session-delivery"
NOW = "2026-11-18T16:00:00+00:00"
FUTURE = "2026-11-20 12:00"  # far enough from NOW that the local time zone cannot move it into the past
PAST = "2026-11-17 12:00"


class IdleTests(unittest.TestCase):
    """The clock is fixed at 2026-11-18 16:00 UTC through $BUS_NOW; the threshold is the default 30 minutes."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.bus = Path(directory.name)
        for name in ("idle.py", "overdue.py"):
            shutil.copy(SKILL / "templates" / "bus" / name, self.bus / name)
        self.lanes("pm", "backend")
        self.items = self.bus / "open-items.tsv"
        self.items.write_text("", encoding="utf-8")

    def lanes(self, *names):
        (self.bus / "lanes.txt").write_text("".join(f"{name}\n" for name in names), encoding="utf-8")

    def open_item(self, sender, key, eta=FUTURE):
        with self.items.open("a", encoding="utf-8") as out:
            out.write(f"2026-11-18T09:00:00+00:00\t{sender}\t{key}\t{eta}\tSTART {key} work - ETA {eta}\n")

    def bus_line(self, sender, at, to="pm"):
        with (self.bus / f"inbox-{to}.md").open("a", encoding="utf-8") as out:
            out.write(f"{at} | from {sender} | note\n")

    def write(self, name, text):
        path = self.bus / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def idle(self, *args, now=NOW, stdin=None):
        env = {key: value for key, value in os.environ.items() if not key.startswith("BUS_")}
        done = subprocess.run([sys.executable, "-I", str(self.bus / "idle.py"), *args], capture_output=True,
                              text=True, check=False, input=stdin, timeout=30, env={**env, "BUS_NOW": now})
        return done.returncode, done.stdout.strip(), done.stderr

    # IDLE and the threshold
    def test_a_lane_with_only_future_etas_and_old_activity_is_idle(self):
        self.lanes("backend", "web")
        self.open_item("backend", "t-1")
        self.open_item("web", "w-1")
        self.bus_line("backend", "2026-11-18T15:29:00Z")
        self.bus_line("web", "2026-11-18T15:59:00Z")
        code, out, _ = self.idle()
        self.assertEqual(code, 1)
        self.assertEqual(out, "IDLE backend | last bus 2026-11-18T15:29:00+00:00 (31m ago) | status unknown | "
                              f"open t-1 ETA {FUTURE} | why no activity for over 30m; only future ETAs")

    def test_activity_exactly_at_the_threshold_is_not_idle(self):
        self.open_item("backend", "t-1")
        self.bus_line("backend", "2026-11-18T15:30:00Z")
        self.assertEqual(self.idle(), (0, "none", ""))
        self.assertEqual(self.idle(now="2026-11-18T16:00:01+00:00")[0], 1)  # one second past it
        self.assertEqual(self.idle("--threshold", "1h", now="2026-11-18T16:20:00+00:00")[:2], (0, "none"))

    def test_a_lane_with_no_activity_at_all_is_idle(self):
        self.open_item("backend", "t-1")
        self.bus_line("pm", "2026-11-18T15:59:00Z", to="backend")  # the coordinator's lines are not the lane's work
        code, out, _ = self.idle()
        self.assertEqual(code, 1)
        self.assertIn("IDLE backend | last none | status unknown |", out)
        self.assertTrue(out.endswith("why no activity; only future ETAs"), out)
        self.assertNotIn(" pm ", out)

    def test_the_newest_line_in_any_inbox_counts(self):
        self.open_item("backend", "t-1")
        self.bus_line("backend", "2026-11-18T14:00:00Z", to="pm")
        self.bus_line("backend", "2026-11-18T15:50:00Z", to="web")
        self.assertEqual(self.idle()[:2], (0, "none"))

    def test_a_recent_commit_counts_as_activity_and_is_named_as_the_source(self):
        self.open_item("backend", "t-1")
        self.bus_line("backend", "2026-11-18T12:00:00Z")
        commits = self.write("commits.tsv", "backend\t2026-11-18T15:45:00Z\n")
        self.assertEqual(self.idle("--activity", commits)[:2], (0, "none"))
        old = self.write("old.tsv", "backend\t2026-11-18T13:00:00Z\nbackend\t2026-11-18T14:00:00Z\n")
        self.assertIn("| last commit 2026-11-18T14:00:00+00:00 (120m ago) |", self.idle("--activity", old)[1])
        self.assertEqual(self.idle("--activity", "-", stdin="backend\t2026-11-18T15:45:00Z\n")[:2], (0, "none"))

    def test_a_lane_with_an_overdue_or_unreadable_item_is_left_to_overdue_py(self):
        self.lanes("backend", "web")
        self.open_item("backend", "t-1")
        self.open_item("backend", "t-2", eta=PAST)
        self.open_item("web", "w-1", eta="soon")
        self.assertEqual(self.idle()[:2], (0, "none"))

    def test_open_items_are_listed_in_key_order_with_their_etas(self):
        self.open_item("backend", "t-2", eta="2026-11-21 09:00")
        self.open_item("backend", "t-1")
        self.assertIn(f"| open t-1 ETA {FUTURE}, t-2 ETA 2026-11-21 09:00 |", self.idle()[1])

    # status: busy wins only when fresh
    def test_a_fresh_busy_status_overrides_old_activity(self):
        self.open_item("backend", "t-1")
        self.bus_line("backend", "2026-11-18T12:00:00Z")
        for as_of in ("2026-11-18T15:59:00Z", "2026-11-18T15:30:00Z"):  # inside, then exactly at the threshold
            with self.subTest(as_of=as_of):
                status = self.write("status.tsv", f"backend\tbusy\t{as_of}\n")
                self.assertEqual(self.idle("--status", status)[:2], (0, "none"))

    def test_a_stale_or_future_busy_status_is_not_trusted(self):
        self.open_item("backend", "t-1")
        self.bus_line("backend", "2026-11-18T12:00:00Z")
        stale = self.write("stale.tsv", "backend\tbusy\t2026-11-18T15:29:00Z\n")
        code, out, _ = self.idle("--status", stale)
        self.assertEqual(code, 1)
        self.assertIn("| status stale busy (as of 2026-11-18T15:29:00+00:00, 31m old) |", out)
        future = self.write("future.tsv", "backend\tbusy\t2026-11-18T16:05:00Z\n")
        code, out, _ = self.idle("--status", future)
        self.assertEqual(code, 1)
        self.assertIn("| status future busy (as of 2026-11-18T16:05:00+00:00) |", out)

    def test_a_future_status_line_does_not_hide_a_fresh_one(self):
        self.open_item("backend", "t-1")
        status = self.write("status.tsv", "backend\tbusy\t2026-11-18T16:00:00Z\nbackend\tidle\t2026-11-18T16:10:00Z\n")
        self.assertEqual(self.idle("--status", status)[:2], (0, "none"))
        status = self.write("status.tsv", "backend\tidle\t2026-11-18T15:58:00Z\nbackend\tbusy\t2026-11-18T16:05:00Z\n")
        code, out, _ = self.idle("--status", status)
        self.assertEqual(code, 1)
        self.assertIn("| status idle (as of 2026-11-18T15:58:00+00:00) |", out)

    # activity in the future is not a sign of work
    def test_a_future_commit_time_does_not_hide_an_idle_lane(self):
        self.open_item("backend", "t-1")
        self.bus_line("backend", "2026-11-18T12:00:00Z")
        commits = self.write("commits.tsv", "backend\t2026-11-19T12:00:00Z\n")
        code, out, err = self.idle("--activity", commits)
        self.assertEqual(code, 1)
        self.assertIn("| last bus 2026-11-18T12:00:00+00:00 (240m ago; future commit 2026-11-19T12:00:00+00:00 "
                      "ignored) |", out)
        self.assertIn("why no activity for over 30m; only future ETAs", out)
        self.assertIn("backend commit time 2026-11-19T12:00:00+00:00 is in the future: ignored", err)

    def test_a_future_bus_line_does_not_hide_an_idle_lane_or_a_real_one(self):
        self.open_item("backend", "t-1")
        self.bus_line("backend", "2027-01-01T00:00:00Z")
        code, out, err = self.idle()
        self.assertEqual(code, 1)
        self.assertIn("IDLE backend | last none (future bus 2027-01-01T00:00:00+00:00 ignored) |", out)
        self.assertTrue(out.endswith("why no activity; only future ETAs"), out)
        self.assertIn("backend bus time 2027-01-01T00:00:00+00:00 is in the future: ignored", err)
        self.bus_line("backend", "2026-11-18T15:50:00Z", to="web")  # a real line next to the future one still counts
        self.assertEqual(self.idle()[:2], (0, "none"))

    def test_a_fresh_idle_status_makes_an_active_lane_idle(self):
        self.open_item("backend", "t-1")
        self.bus_line("backend", "2026-11-18T15:55:00Z")
        status = self.write("status.tsv", "backend\tbusy\t2026-11-18T15:40:00Z\nbackend\tIDLE\t2026-11-18T15:58:00Z\n")
        code, out, _ = self.idle("--status", status)
        self.assertEqual(code, 1)
        self.assertEqual(out, "IDLE backend | last bus 2026-11-18T15:55:00+00:00 (5m ago) | status idle (as of "
                              f"2026-11-18T15:58:00+00:00) | open t-1 ETA {FUTURE} | why status idle; only future ETAs")

    def test_a_missing_or_bad_status_file_is_reported_and_busy_is_not_trusted(self):
        self.lanes("backend", "web")
        self.open_item("backend", "t-1")
        self.bus_line("backend", "2026-11-18T12:00:00Z")
        bad = self.write("bad.tsv", "backend\tbusy\t2026-11-18T15:59:00Z\nweb\tworking\t2026-11-18T15:59:00Z\n")
        for path, reason in ((str(self.bus / "missing.tsv"), "missing.tsv"), (bad, "--status line 2")):
            with self.subTest(reason=reason):
                code, out, _ = self.idle("--status", path)
                self.assertEqual(code, 2)
                first, *rest = out.splitlines()
                self.assertTrue(first.startswith("STATUS unavailable | "), first)
                self.assertIn(reason, first)
                self.assertTrue(first.endswith(" | busy not trusted for any lane"), first)
                self.assertEqual([row.split(" | ")[0] for row in rest], ["IDLE backend", "EMPTY-QUEUE web"])
                self.assertIn("| status unavailable |", rest[0])

    def test_a_name_that_is_not_a_lane_is_ignored_with_a_note(self):
        self.open_item("backend", "t-1")
        self.bus_line("backend", "2026-11-18T15:55:00Z")
        status = self.write("status.tsv", "ghost\tbusy\t2026-11-18T15:59:00Z\n")
        code, out, err = self.idle("--status", status)
        self.assertEqual((code, out), (0, "none"))
        self.assertIn("ghost is not a lane", err)

    # EMPTY-QUEUE
    def test_a_lane_with_no_open_item_is_an_empty_queue_not_an_error(self):
        self.lanes("pm", "backend", "web")
        self.open_item("backend", "t-1")
        with self.items.open("a", encoding="utf-8") as out:
            out.write("2026-11-18T10:00:00+00:00\tbackend\tt-1\tDONE\tDONE t-1 merged abc1234\n")
        self.bus_line("backend", "2026-11-18T15:59:00Z")
        code, out, _ = self.idle()
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "EMPTY-QUEUE backend | last bus 2026-11-18T15:59:00+00:00 (1m ago) | status unknown",
            "EMPTY-QUEUE web | last none | status unknown"])

    # unreadable input
    def test_bad_usage_and_unreadable_input_exit_2(self):
        self.assertEqual(self.idle("--threshold", "30")[0], 2)
        self.assertEqual(self.idle("--threshold", "0m")[0], 2)
        self.assertEqual(self.idle(now="not-a-time")[0], 2)
        self.assertEqual(self.idle("--activity", "-", "--status", "-")[0], 2)
        self.assertEqual(self.idle("--activity", str(self.bus / "missing.tsv"))[0], 2)
        code, _, err = self.idle("--activity", self.write("a.tsv", "backend 2026-11-18T15:00:00Z\n"))
        self.assertEqual(code, 2)
        self.assertIn("--activity line 1", err)
        self.assertEqual(self.idle("--activity", self.write("b.tsv", "backend\tyesterday\n"))[0], 2)
        (self.bus / "lanes.txt").unlink()
        self.assertEqual(self.idle()[0], 2)

    def test_missing_overdue_py_or_named_items_file_exit_2(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith("BUS_")}
        done = subprocess.run([sys.executable, "-I", str(self.bus / "idle.py")], capture_output=True, text=True,
                              check=False, timeout=30,
                              env={**env, "BUS_NOW": NOW, "BUS_OPEN_ITEMS": str(self.bus / "nope.tsv")})
        self.assertEqual(done.returncode, 2)
        self.assertIn("no open-items file", done.stderr)
        (self.bus / "overdue.py").unlink()
        self.assertEqual(self.idle()[0], 2)

    def test_a_broken_or_older_overdue_py_exits_2_not_1(self):
        self.open_item("backend", "t-1")
        overdue = self.bus / "overdue.py"
        source = overdue.read_text(encoding="utf-8")
        overdue.write_text(source.replace("def record_lines(", "def renamed_record_lines("), encoding="utf-8")
        code, _, err = self.idle()
        self.assertEqual(code, 2)
        self.assertIn("overdue.py too old or broken: no record_lines", err)
        self.assertNotIn("Traceback", err)
        for broken in ("def x(:\n", 'raise RuntimeError("boom")\n', 'raise ValueError("bad at import")\n',
                       "raise SystemExit(1)\n"):
            with self.subTest(broken=broken):
                overdue.write_text(broken, encoding="utf-8")
                code, _, err = self.idle()
                self.assertEqual(code, 2)
                self.assertIn("cannot load overdue.py", err)
                self.assertNotIn("Traceback", err)

    def test_an_eta_due_exactly_now_is_idle_here_and_not_yet_overdue_there(self):
        self.open_item("backend", "t-1")
        self.bus_line("backend", "2026-11-18T12:00:00Z")
        at_eta = FUTURE.replace(" ", "T") + ":00"  # no offset: read in local time, as the ETA is
        code, out, _ = self.idle(now=at_eta)
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("IDLE backend |"), out)
        env = {key: value for key, value in os.environ.items() if not key.startswith("BUS_")}
        listed = subprocess.run([sys.executable, "-I", str(self.bus / "overdue.py")], capture_output=True, text=True,
                                check=False, timeout=30, env={**env, "BUS_NOW": at_eta})
        self.assertEqual((listed.returncode, listed.stdout.strip()), (0, "none"))  # no lane falls between the tools

    def test_a_damaged_inbox_line_is_skipped_and_counted(self):
        self.open_item("backend", "t-1")
        self.bus_line("backend", "2026-11-18T15:55:00Z")
        with (self.bus / "inbox-pm.md").open("a", encoding="utf-8") as out:
            out.write("garbage\nlater | from backend | x\n\n")
        code, out, err = self.idle()
        self.assertEqual((code, out), (0, "none"))
        self.assertIn("2 damaged line(s) in the inbox files", err)


class IdleDocsTests(unittest.TestCase):
    def test_the_coordinator_tick_and_the_quick_check_name_idle_py(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        tick = skill.split("**Nothing stays unsolved unseen**", 1)[1].split("\n", 1)[0]
        self.assertIn("idle.py", tick)
        self.assertIn("python3 .agents/bus/idle.py", skill.split("## 3. Verification Protocol", 1)[1])
        self.assertIn("idle.py", (SKILL / "templates" / "bus" / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
