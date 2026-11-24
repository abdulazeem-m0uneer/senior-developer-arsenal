"""Tests for `usage_stats.py ci`: one CI-cost line per day, from the runs gh lists and ci_learn's classifier.

`gh` is a fake executable on PATH (fake_gh.py) serving synthetic run lists, runs and failed logs. Ledgers are
synthetic files in a temp folder; nothing is written to them.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import resource
except ImportError:  # not on Windows
    resource = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_gh import FakeGh  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "usage-stats" / "scripts" / "usage_stats.py"
TODAY = "2026-03-10"
LEDGER_HEADER = "# Lessons\n\n## Active\n\n"
LIMIT_NOTE = "; partial: gh listed its 200-run limit, older runs not counted"


def listed(run_id, conclusion, created=f"{TODAY}T09:00:00Z", status="completed", branch="feature/x", attempt=1):
    return {"databaseId": run_id, "conclusion": conclusion, "status": status, "createdAt": created,
            "headBranch": branch, "attempt": attempt}


def job(conclusion="failure", minutes=2, name="tests", seconds=0):
    return {"name": name, "conclusion": conclusion, "startedAt": "2026-03-10T09:00:00Z",
            "completedAt": f"2026-03-10T09:{minutes:02d}:{seconds:02d}Z", "steps": []}


def run_view(jobs, conclusion="failure", run_id=1):
    return {"jobs": jobs, "conclusion": conclusion, "headBranch": "feature/x", "headSha": "c" * 40, "event": "push",
            "url": f"https://github.com/acme/app/actions/runs/{run_id}", "workflowName": "ci"}


def log(*lines):
    return "".join(f"tests\tRun tests\t2026-03-10T09:00:{i:02d}.1234567Z {text}\n" for i, text in enumerate(lines))


def lesson_line(lesson_id, hits, promoted=""):
    mark = f" | Promoted: {promoted}" if promoted else ""
    return (f"- {lesson_id} [ci-test] hits:{hits} | 2026-03-01 | Mistake: m{lesson_id} | Cause: c | "
            f"Rule: r{lesson_id} | Check: k{mark}\n")


class CiCostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.gh = FakeGh(self.tmp / "bin")
        self.ledger = self.tmp / "lessons.md"
        self.global_ledger = self.tmp / "global" / "lessons.md"
        patch = mock.patch.dict(os.environ, {"LESSONS_GUARDS_GLOBAL_FILE": str(self.tmp / "no-registry.json")})
        patch.start()  # never this machine's lesson-guard registry
        self.addCleanup(patch.stop)

    def serve(self, runs, details=(), list_rc=0):
        """`runs`: what gh run list prints; `details`: (id, run view JSON, failed log[, attempt]) per red attempt;
        a failed log of None makes `--log-failed` exit 1, as gh does for a job that never started."""
        rules = [{"match": ["run list"], "stdout": runs, "rc": list_rc}]
        for run_id, view, text, *attempt in details:
            only = [f"--attempt {attempt[0]}"] if attempt else []
            rules.append({"match": [f"run view {run_id} ", "--log-failed", *only], "stdout": text or "",
                          "rc": 1 if text is None else 0})
            rules.append({"match": [f"run view {run_id} ", "--json", *only], "stdout": view})
        self.gh.rules(rules)

    def ci(self, *args):
        env = {**self.gh.env(), "LESSONS_FILE": str(self.ledger), "LESSONS_GLOBAL_FILE": str(self.global_ledger)}
        done = subprocess.run([sys.executable, str(SCRIPT), "ci", "--repo", "acme/app", "--today", TODAY, *args],
                              capture_output=True, text=True, cwd=self.tmp, env=env, timeout=120)
        return done.returncode, done.stdout, done.stderr

    def test_a_time_limit_cancel_told_only_by_annotations_counts_as_timeout(self):
        view = run_view([{**job(minutes=28, conclusion="cancelled"), "databaseId": 77}], conclusion="cancelled")
        self.serve([listed(1, "cancelled")], [(1, view, "")])
        rules = json.loads((self.gh.dir / "rules.json").read_text())
        rules.append({"match": ["api repos/acme/app/check-runs/77/annotations"], "stdout": json.dumps(
            [{"annotation_level": "failure", "title": "",
              "message": "The job has exceeded the maximum execution time of 28m0s"}])})
        (self.gh.dir / "rules.json").write_text(json.dumps(rules))
        code, out, err = self.ci("--json")
        self.assertEqual(code, 0, err)
        day = json.loads(out)["days"][-1]
        self.assertEqual((day["minutes"]["timeout"], day["minutes"]["superseded"]), (28.0, 0.0))

    def test_counts_and_minutes_per_class(self):
        self.serve([listed(1, "failure"), listed(2, "failure"), listed(3, "cancelled"), listed(4, "timed_out"),
                    listed(5, "failure"), listed(6, "failure"), listed(7, "failure"), listed(8, "failure"),
                    listed(9, "success"), listed(10, "skipped"), listed(11, None, status="in_progress"),
                    listed(12, "failure", status="in_progress")], [
            (1, run_view([job(minutes=3)]), log("FAIL src/a.test.ts", "Tests: 1 failed")),
            (2, run_view([job(minutes=4)]), log("Jest: coverage threshold for lines (90%) not met")),
            (3, run_view([job("cancelled", 5), job("success", 1, "lint")], "cancelled"), ""),
            (4, run_view([job("timed_out", 6)], "timed_out"), log("still running")),
            (5, run_view([job(minutes=7)]), log("src/a.ts(3,1): error TS2304: Cannot find name 'x'.")),
            (6, run_view([job(minutes=8)]), log("Error: connect ECONNRESET 10.0.0.1:443")),
            (7, run_view([job(minutes=9)]), log("something odd happened")),
            (8, run_view([job(minutes=1)]), log("FAIL src/b.test.ts")),
        ])
        code, out, err = self.ci()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), f"{TODAY} runs 12, red 8, wasted 44 min (timeout 6, coverage 4, test 4, "
                                      "lint/type 7, superseded 6, outside 8, unknown 9); repeats without a guard 0")
        calls = self.gh.calls()
        self.assertIn("run list -R acme/app --created >=2026-03-10 --json "
                      "databaseId,conclusion,status,createdAt,headBranch,attempt -L 200", calls)
        self.assertFalse([call for call in calls if any(f"run view {i} " in call for i in (9, 10, 11, 12))])

    def test_repeats_without_a_guard_count_both_ledgers(self):
        self.ledger.write_text(LEDGER_HEADER + lesson_line("L001", 2) + lesson_line("L002", 5, "tests/t.py")
                               + lesson_line("L003", 1) + lesson_line("L004", 2, "exempt@2: no check fits"),
                               encoding="utf-8")
        self.global_ledger.parent.mkdir()
        self.global_ledger.write_text(LEDGER_HEADER + lesson_line("G001", 3) +
                                      lesson_line("G002", 4, "exempt@2: none"), encoding="utf-8")
        self.serve([])
        code, out, err = self.ci()
        self.assertEqual(code, 0, err)
        self.assertTrue(out.strip().endswith("; repeats without a guard 3"), out)  # L001, G001, G002 (outgrown)

    def test_a_lesson_promoted_only_to_a_rule_stub_repeats_without_a_guard(self):
        self.ledger.write_text(
            LEDGER_HEADER + lesson_line("L001", 3, ".agents/lessons/rules/lessons-promoted.md")
            + lesson_line("L002", 4, "/home/u/.agents/rules/lessons-promoted.md")
            + lesson_line("L003", 3, "tests/test_x.py + rule .agents/lessons/rules/lessons-promoted.md")
            + lesson_line("L004", 3, "hooks/guard.py") + lesson_line("L005", 2, "exempt@2: no check fits"),
            encoding="utf-8")
        self.serve([])
        code, out, err = self.ci()
        self.assertEqual(code, 0, err)
        self.assertTrue(out.strip().endswith("; repeats without a guard 2"), out)  # L001, L002: rule stubs only

    def test_runs_over_max_runs_are_skipped_and_said(self):
        self.serve([listed(1, "failure", f"{TODAY}T10:00:00Z"), listed(3, "failure", f"{TODAY}T12:00:00Z"),
                    listed(2, "failure", f"{TODAY}T11:00:00Z")], [  # out of order: the newest are read first
            (3, run_view([job(minutes=2)]), log("FAIL a")), (2, run_view([job(minutes=3)]), log("FAIL b"))])
        code, out, err = self.ci("--max-runs", "2")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), f"{TODAY} runs 3, red 3, wasted 5 min (timeout 0, coverage 0, test 5, "
                                      "lint/type 0, superseded 0, outside 0, unknown 0); repeats without a guard 0; "
                                      "skipped 1 attempt over --max-runs 2 (not in the minutes)")
        self.assertFalse([call for call in self.gh.calls() if "run view 1 " in call])

    def test_an_empty_day_still_prints_its_line(self):
        self.serve([listed(1, "failure", "2026-03-08T23:59:00Z"), listed(2, "success", "2026-03-09T01:00:00+03:00")],
                   [(1, run_view([job(minutes=2)]), log("FAIL a"))])  # run 2 is 2026-03-08 22:00 in UTC
        code, out, err = self.ci("--days", "3")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [
            "2026-03-08 runs 2, red 1, wasted 2 min (timeout 0, coverage 0, test 2, lint/type 0, superseded 0, "
            "outside 0, unknown 0); repeats without a guard 0",
            "2026-03-09 runs 0, red 0, wasted 0 min (timeout 0, coverage 0, test 0, lint/type 0, superseded 0, "
            "outside 0, unknown 0); repeats without a guard 0",
            f"{TODAY} runs 0, red 0, wasted 0 min (timeout 0, coverage 0, test 0, lint/type 0, superseded 0, "
            "outside 0, unknown 0); repeats without a guard 0"])
        self.assertIn("--created >=2026-03-08", self.gh.calls()[0])

    def test_json_shape(self):
        self.serve([listed(1, "failure", f"{TODAY}T09:00:00Z", branch="main"), listed(2, "success"),
                    listed(3, "failure", f"{TODAY}T08:00:00Z"), listed(4, "failure", f"{TODAY}T07:00:00Z")],
                   [(1, run_view([job(minutes=3), job("success", 9, "lint")]), log("FAIL a")),
                    (3, run_view([job(minutes=1)]), log("Snapshot `x` mismatched"))])
        code, out, err = self.ci("--json", "--max-runs", "2")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {
            "repo": "acme/app", "max_runs": 2, "repeats_without_guard": 0,
            "days": [{"date": TODAY, "runs": 4, "red": 3, "wasted": 4.0, "skipped": 1, "partial": False,
                      "minutes": {"timeout": 0.0, "coverage": 0.0, "test": 4.0, "lint/type": 0.0, "superseded": 0.0,
                                  "outside": 0.0, "unknown": 0.0},
                      "red_runs": [{"run": 1, "attempt": 1, "branch": "main", "class": "test", "sub_kind": "",
                                    "minutes": 3.0},
                                   {"run": 3, "attempt": 1, "branch": "feature/x", "class": "test",
                                    "sub_kind": "snapshot", "minutes": 1.0}]}]})

    def test_per_class_minutes_are_rounded(self):
        self.serve([listed(1, "failure", f"{TODAY}T09:00:00Z"), listed(2, "failure", f"{TODAY}T08:00:00Z")],
                   [(1, run_view([job(minutes=0, seconds=6)]), log("FAIL a")),  # 0.1 min
                    (2, run_view([job(minutes=0, seconds=12)]), log("FAIL b"))])  # 0.2 min
        code, out, err = self.ci("--json")
        self.assertEqual(code, 0, err)
        day = json.loads(out)["days"][0]
        self.assertEqual((day["wasted"], day["minutes"]["test"]), (0.3, 0.3))  # never 0.30000000000000004

    def test_max_runs_0_counts_red_runs_and_reads_none(self):
        self.serve([listed(1, "failure"), listed(2, "cancelled")])
        code, out, err = self.ci("--max-runs", "0")
        self.assertEqual(code, 0, err)
        self.assertIn("runs 2, red 2, wasted 0 min", out)
        self.assertIn("; skipped 2 attempts over --max-runs 0 (not in the minutes)", out)
        self.assertFalse([call for call in self.gh.calls() if "run view" in call])

    def test_an_unreadable_failed_log_is_classified_from_its_jobs(self):
        self.serve([listed(1, "failure"), listed(2, "failure")],
                   [(1, run_view([job(minutes=4)]), None),  # a job that never started: gh has no log to serve
                    (2, run_view([job(minutes=3)]), log("FAIL a"))])
        code, out, err = self.ci()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), f"{TODAY} runs 2, red 2, wasted 7 min (timeout 0, coverage 0, test 3, "
                                      "lint/type 0, superseded 0, outside 0, unknown 4); repeats without a guard 0")
        self.assertIn("run 1 attempt 1: failed log unreadable", err)

    def test_earlier_red_attempts_of_a_re_run_are_counted(self):
        self.serve([listed(1, "success", attempt=3)], [
            (1, run_view([job(minutes=12)]), log("FAIL a"), 1),
            (1, run_view([job("success", 5)], "success"), "", 2)])
        code, out, err = self.ci("--json")
        self.assertEqual(code, 0, err)
        day = json.loads(out)["days"][0]
        self.assertEqual((day["runs"], day["red"], day["wasted"], day["minutes"]["test"]), (1, 1, 12.0, 12.0))
        self.assertEqual([(red["run"], red["attempt"]) for red in day["red_runs"]], [(1, 1)])
        logs = [call for call in self.gh.calls() if "--log-failed" in call]
        self.assertEqual(len(logs), 1)  # attempt 2 passed: no log read
        self.assertIn("--attempt 1", logs[0])
        self.assertFalse([call for call in self.gh.calls() if "--attempt 3" in call])  # the latest passed

    def test_a_listed_red_run_that_the_view_shows_passed_is_not_red(self):
        self.serve([listed(1, "failure")], [(1, run_view([job("success", 2)], "success"), "")])
        code, out, err = self.ci()
        self.assertEqual(code, 0, err)
        self.assertIn("runs 1, red 0, wasted 0 min", out)
        self.assertFalse([call for call in self.gh.calls() if "--log-failed" in call])

    def test_a_startup_failure_is_red(self):
        self.serve([listed(1, "startup_failure")], [(1, run_view([], "startup_failure"), None)])
        code, out, err = self.ci()
        self.assertEqual(code, 0, err)
        self.assertIn("runs 1, red 1, wasted 0 min", out)

    def test_fractional_minutes_keep_one_decimal(self):
        view = run_view([{**job(minutes=2), "completedAt": "2026-03-10T09:02:30Z"}])
        self.serve([listed(1, "failure")], [(1, view, log("FAIL a"))])
        code, out, err = self.ci()
        self.assertEqual(code, 0, err)
        self.assertIn("wasted 2.5 min (timeout 0, coverage 0, test 2.5,", out)

    def test_a_gh_list_failure_exits_2(self):
        self.serve([], list_rc=1)
        code, out, err = self.ci()
        self.assertEqual((code, out), (2, ""))
        self.assertIn("exited 1", err)

    def test_a_gh_view_failure_exits_2_and_names_the_run(self):
        self.gh.rules([{"match": ["run list"], "stdout": [listed(7, "failure")]},
                       {"match": ["run view 7 "], "rc": 1}])
        code, out, err = self.ci()
        self.assertEqual((code, out), (2, ""))
        self.assertIn("run 7", err)

    def test_list_output_that_is_not_a_list_exits_2(self):
        self.serve({"message": "Not Found"})
        code, _, err = self.ci()
        self.assertEqual(code, 2)
        self.assertIn("no run list", err)

    def test_a_list_at_the_gh_limit_marks_the_days_it_may_have_cut(self):
        self.serve([listed(i, "success", f"{TODAY}T09:00:00Z") for i in range(1, 151)] +
                   [listed(i, "success", "2026-03-09T09:00:00Z") for i in range(151, 201)])
        code, out, err = self.ci("--days", "3")
        self.assertEqual(code, 0, err)
        first, second, last = out.splitlines()
        self.assertTrue(first.startswith("2026-03-08 runs 0,") and first.endswith(LIMIT_NOTE), first)
        self.assertTrue(second.startswith("2026-03-09 runs 50,") and second.endswith(LIMIT_NOTE), second)
        self.assertTrue(last.startswith(f"{TODAY} runs 150,") and last.endswith("repeats without a guard 0"), last)
        code, out, _ = self.ci("--days", "3", "--json")
        self.assertEqual([day["partial"] for day in json.loads(out)["days"]], [True, True, False])

    def test_a_list_under_the_gh_limit_marks_no_day(self):
        self.serve([listed(i, "success") for i in range(1, 200)])
        code, out, err = self.ci()
        self.assertEqual(code, 0, err)
        self.assertNotIn("limit", out)

    def test_bad_arguments_exit_2(self):
        for args in (["--days", "0"], ["--days", "401"], ["--days", "100000000"], ["--max-runs", "-1"],
                     ["--repo", "no-owner"], ["--repo", "a/b c"]):
            with self.subTest(args=args):
                code, _, _ = self.ci(*args)
                self.assertEqual(code, 2)
        self.assertEqual(self.gh.calls(), [])

    def test_400_days_is_the_longest_window(self):
        self.serve([])
        code, out, err = self.ci("--days", "400")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.splitlines()), 400)
        self.assertIn("--created >=2025-02-04", self.gh.calls()[0])

    def test_a_ledger_that_is_not_a_file_exits_2(self):
        for name in ("project", "global"):
            with self.subTest(ledger=name):
                folder = self.ledger if name == "project" else self.global_ledger
                folder.mkdir(parents=True)
                self.serve([])
                code, out, err = self.ci()
                self.assertEqual((code, out), (2, ""))
                self.assertIn("not a file", err)
                folder.rmdir()

    def test_an_unreadable_ledger_fails_the_count(self):
        sys.path.insert(0, str(SCRIPT.parent))
        import ci_cost
        self.ledger.write_text(LEDGER_HEADER + lesson_line("L001", 2), encoding="utf-8")
        self.global_ledger.parent.mkdir()
        self.global_ledger.write_text(LEDGER_HEADER + lesson_line("G001", 2), encoding="utf-8")
        real = ci_cost.lessons.Ledger
        for unreadable in (self.ledger, self.global_ledger):
            def ledger(path, prefix="L", unreadable=unreadable):
                if Path(path) == unreadable:
                    raise PermissionError(13, "Permission denied", str(path))
                return real(path, prefix)
            with self.subTest(ledger=unreadable.name), mock.patch.dict(os.environ, {
                    "LESSONS_FILE": str(self.ledger), "LESSONS_GLOBAL_FILE": str(self.global_ledger)}), \
                    mock.patch.object(ci_cost.lessons, "Ledger", ledger):
                with self.assertRaisesRegex(ci_cost.Failed, "Permission denied"):
                    ci_cost.repeats_without_guard()
        with mock.patch.dict(os.environ, {"LESSONS_FILE": str(self.ledger),
                                          "LESSONS_GLOBAL_FILE": str(self.global_ledger)}):
            self.assertEqual(ci_cost.repeats_without_guard(), 2)

    def test_without_the_ci_wait_skill_beside_it_exits_2(self):
        alone = self.tmp / "skills" / "usage-stats" / "scripts"
        shutil.copytree(SCRIPT.parent, alone, ignore=shutil.ignore_patterns("__pycache__"))
        done = subprocess.run([sys.executable, str(alone / SCRIPT.name), "ci", "--repo", "acme/app"],
                              capture_output=True, text=True, cwd=self.tmp, env=self.gh.env(), timeout=60)
        self.assertEqual((done.returncode, done.stdout), (2, ""))
        self.assertIn("ci needs the ci-wait and lessons-learned skills", done.stderr)
        self.assertEqual(self.gh.calls(), [])

    def in_process(self, *args):
        """`ci` run in this process, so a test can shorten ci_wait.GH_TIMEOUT: (exit code, stdout, stderr)."""
        sys.path.insert(0, str(SCRIPT.parent))
        import ci_cost
        import usage_stats
        out, err = io.StringIO(), io.StringIO()
        env = {"PATH": self.gh.env()["PATH"], "LESSONS_FILE": str(self.ledger),
               "LESSONS_GLOBAL_FILE": str(self.global_ledger)}
        with mock.patch.dict(os.environ, env), mock.patch.object(ci_cost.ci_wait, "GH_TIMEOUT", 0.5), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = usage_stats.main(["ci", "--repo", "acme/app", "--today", TODAY, *args])
        return code, out.getvalue(), err.getvalue()

    def test_a_gh_call_that_hangs_exits_2(self):
        hang = {"sleep": 3}
        for name, rules in (
                ("list", [{"match": ["run list"], "stdout": [listed(1, "failure")], **hang}]),
                ("view", [{"match": ["run list"], "stdout": [listed(1, "failure")]},
                          {"match": ["run view 1 ", "--json"], "stdout": run_view([job()]), **hang}]),
                ("log", [{"match": ["run list"], "stdout": [listed(1, "failure")]},
                         {"match": ["run view 1 ", "--json"], "stdout": run_view([job()])},
                         {"match": ["run view 1 ", "--log-failed"], "stdout": log("FAIL a"), **hang}])):
            with self.subTest(call=name):
                self.gh.rules(rules)
                code, out, err = self.in_process()
                self.assertEqual((code, out), (2, ""))
                self.assertIn("did not answer in 0.5 s", err)
                if name != "list":
                    self.assertIn("could not read run 1: ", err)

    def test_list_entries_that_are_not_objects_exit_2(self):
        for entries in ([1], [None], [listed(1, "failure"), "x"]):
            with self.subTest(entries=entries):
                self.serve(entries)
                code, out, err = self.ci()
                self.assertEqual((code, out), (2, ""))
                self.assertIn("no run list", err)

    def test_a_run_view_that_is_not_an_object_exits_2(self):
        for view in ([], None, json.dumps("x")):
            with self.subTest(view=view):
                self.serve([listed(7, "failure")], [(7, view, log("FAIL a"))])
                code, out, err = self.ci()
                self.assertEqual((code, out), (2, ""))
                self.assertIn("could not read run 7: gh run view printed no run", err)

    def test_a_full_list_without_dates_marks_every_day_partial_and_says_so(self):
        self.serve([listed(i, "success", created=None) for i in range(1, 201)])
        code, out, err = self.ci("--days", "3", "--json")
        self.assertEqual(code, 0, err)
        days = json.loads(out)["days"]
        self.assertEqual([(day["runs"], day["partial"]) for day in days], [(0, True), (0, True), (0, True)])
        self.assertIn("note: 200 listed runs have no readable createdAt and are not counted", err)

    def test_a_run_without_a_branch_shows_a_question_mark(self):
        self.serve([listed(1, "failure", branch=None)], [(1, run_view([job()]), log("FAIL a"))])
        code, out, err = self.ci("--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["days"][0]["red_runs"][0]["branch"], "?")

    @unittest.skipUnless(resource, "needs the resource module (POSIX)")
    def test_a_huge_attempt_count_is_never_built_in_memory(self):
        self.serve([listed(1, "success", attempt=10**8)], [(1, run_view([job()]), log("FAIL a"), 10**8 - 1)])
        env = {**self.gh.env(), "LESSONS_FILE": str(self.ledger), "LESSONS_GLOBAL_FILE": str(self.global_ledger)}
        cap = 1024 ** 3  # 1 GiB: a list of 10**8 attempts needs several

        def limit_memory():
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        done = subprocess.run([sys.executable, str(SCRIPT), "ci", "--repo", "acme/app", "--today", TODAY, "--json",
                               "--max-runs", "1"], capture_output=True, text=True, cwd=self.tmp, env=env, timeout=120,
                              preexec_fn=limit_memory)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        day = json.loads(done.stdout)["days"][0]
        self.assertEqual((day["red"], day["skipped"]), (1, 10**8 - 2))
        self.assertEqual([red["attempt"] for red in day["red_runs"]], [10**8 - 1])

    def test_budget_goes_to_attempts_newest_first(self):
        self.serve([listed(102, "success", f"{TODAY}T12:00:00Z", attempt=2), listed(104, "failure")],
                   [(102, run_view([job("success", 2)], "success"), "", 1)])
        code, out, err = self.ci("--max-runs", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("runs 2, red 1, wasted 0 min", out)
        self.assertTrue(out.strip().endswith("; skipped 1 attempt over --max-runs 1 (not in the minutes)"), out)

    def test_a_read_red_latest_attempt_is_not_counted_again_when_earlier_ones_are_skipped(self):
        self.serve([listed(1, "failure", attempt=2)], [(1, run_view([job(minutes=3)]), log("FAIL a"), 2)])
        code, out, err = self.ci("--max-runs", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("runs 1, red 1, wasted 3 min", out)
        self.assertIn("; skipped 1 attempt over --max-runs 1", out)

    def test_help_says_max_runs_caps_attempts(self):
        done = subprocess.run([sys.executable, str(SCRIPT), "ci", "--help"], capture_output=True, text=True,
                              timeout=60)
        self.assertEqual(done.returncode, 0)
        self.assertIn("attempts read and classified at most", " ".join(done.stdout.split()))

    def test_no_ledger_is_written(self):
        self.ledger.write_text(LEDGER_HEADER + lesson_line("L001", 1), encoding="utf-8")
        before = self.ledger.read_bytes()
        self.serve([listed(1, "failure")], [(1, run_view([job()]), log("FAIL a"))])
        code, _, err = self.ci()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(sorted(path.name for path in self.tmp.iterdir()), ["bin", "lessons.md"])


if __name__ == "__main__":
    unittest.main()
