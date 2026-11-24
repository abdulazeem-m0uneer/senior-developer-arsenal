"""Tests for the ci-wait skill's ci_learn.py: one red run becomes one classified, counted lesson.

`gh` is a fake executable on PATH (fake_gh.py) serving synthetic run JSON and logs in the GitHub log format.
"""
import contextlib
import importlib
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_gh import FakeGh  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "ci-wait" / "scripts" / "ci_learn.py"
sys.path.insert(0, str(SCRIPT.parent))
ci_learn = importlib.import_module("ci_learn")
CYAN, RED, RESET = "\x1b[36;1m", "\x1b[31;1m", "\x1b[0m"
EXIT_OK, EXIT_UNREADABLE, EXIT_ESCALATE = 0, 2, 3


def job(name="tests", conclusion="failure", start="2026-01-05T10:00:00Z", end="2026-01-05T10:02:00Z", steps=(),
        job_id=None):
    found = {"name": name, "conclusion": conclusion, "startedAt": start, "completedAt": end,
             "steps": [{"name": step, "conclusion": result} for step, result in steps]}
    return {**found, "databaseId": job_id} if job_id else found


def run_json(jobs, conclusion="failure", branch="feature/x", repo="acme/app", run_id="101"):
    return {"jobs": jobs, "conclusion": conclusion, "headBranch": branch, "headSha": "c" * 40,
            "event": "push", "url": f"https://github.com/{repo}/actions/runs/{run_id}", "workflowName": "ci"}


def log(*lines, job_name="tests", step="Run tests"):
    """GitHub's --log-failed shape: <job>\\t<step>\\t<ISO time> <text>, one line per entry."""
    return "".join(f"{job_name}\t{step}\t2026-01-05T10:00:{i:02d}.1234567Z {text}\n" for i, text in enumerate(lines))


def echoed(*script):
    """A step's script as the runner echoes it before running it: a Run group, cyan lines, the shell, then its env
    inputs and endgroup."""
    return [f"##[group]Run {script[0]}", *(f"{CYAN}{line}{RESET}" for line in script),
            "shell: /usr/bin/bash -e {0}", "env:", "  CI: true", "  NODE_OPTIONS: --max-old-space-size=4096",
            "##[endgroup]"]


class CiLearnTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.gh = FakeGh(self.tmp / "bin")
        self.ledger = self.tmp / "lessons.md"

    def serve(self, run, text="", run_id="101", log_rc=0, view_rc=0):
        self.gh.rules([
            {"match": [f"run view {run_id}", "--log-failed"], "stdout": text, "rc": log_rc},
            {"match": [f"run view {run_id}", "--json"], "stdout": run, "rc": view_rc},
        ])

    def learn(self, *args, run_id="101", env=None):
        environment = {**self.gh.env(), "LESSONS_GLOBAL_FILE": str(self.tmp / "global" / "lessons.md"),
                       "LESSONS_PROMOTE_AT": "3", **(env or {})}
        environment.pop("LESSONS_FILE", None)
        done = subprocess.run([sys.executable, str(SCRIPT), run_id, "--ledger", str(self.ledger), *args],
                              capture_output=True, text=True, cwd=self.tmp, env=environment, timeout=60)
        return done.returncode, done.stdout, done.stderr

    def classify(self, run, text=""):
        self.serve(run, text)
        code, out, err = self.learn("--dry-run")
        self.assertEqual(code, EXIT_OK, err)
        return out.splitlines()[0].split()[0], out

    def learn_in_process(self, *args):
        """main() in this process, so a test can hold the ledger lock or shorten the gh timeout."""
        out, err = io.StringIO(), io.StringIO()
        env = {"PATH": self.gh.env()["PATH"], "LESSONS_GLOBAL_FILE": str(self.tmp / "global" / "lessons.md")}
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ci_learn.main(["101", "--ledger", str(self.ledger), *args])
        return code, out.getvalue(), err.getvalue()

    def ledger_text(self):
        return self.ledger.read_text(encoding="utf-8")

    # --- one fixture run per class -------------------------------------------------------------------------------
    def test_cancelled_run_is_superseded_even_with_assertion_text(self):
        self.serve(run_json([job(conclusion="cancelled")], conclusion="cancelled"),
                   log(f"{RED}AssertionError: expected 1 to be 2{RESET}"))
        code, out, err = self.learn()
        self.assertEqual(code, EXIT_OK, err)
        self.assertTrue(out.startswith("superseded 2.0 min wasted, run 101 feature/x: L001 added"), out)
        self.assertIn("[ci-superseded,repo-app]", self.ledger_text())
        self.assertIn("Push once per run: wait for the running CI or cancel it on purpose", self.ledger_text())

    def test_every_non_success_job_cancelled_is_superseded(self):
        run = run_json([job("lint", "success"), job("tests", "cancelled"), job("e2e", "skipped")])
        self.assertEqual(self.classify(run, log(" FAIL  src/a.test.ts"))[0], "superseded")

    def test_outside_cause_records_nothing_and_names_the_cause(self):
        self.serve(run_json([job()]), log(f"{RED}Error: toomanyrequests: rate limit{RESET}"))
        code, out, err = self.learn()
        self.assertEqual(code, EXIT_OK, err)
        self.assertTrue(out.startswith("outside 2.0 min wasted, run 101 feature/x: no lesson (registry rate limit)"),
                        out)
        self.assertFalse(self.ledger.exists())

    def test_timed_out_job_is_timeout(self):
        run = run_json([job(conclusion="timed_out", end="2026-01-05T10:30:00Z")])
        self.serve(run, log("still running", f"{RED}AssertionError: late{RESET}"))
        code, out, err = self.learn()
        self.assertEqual(code, EXIT_OK, err)
        self.assertTrue(out.startswith("timeout 30.0 min wasted, run 101 feature/x: L001 added"), out)
        self.assertIn("run the shard locally under the CI time budget", self.ledger_text())

    def test_timeout_annotation_is_timeout(self):
        text = log("##[error]The job running on runner r1 has exceeded the maximum execution time of 30 minutes.")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "timeout")
        self.assertEqual(self.classify(run_json([job()]), log("##[error]Step ran past the 20 minute limit"))[0],
                         "timeout")

    def test_failed_coverage_step_is_coverage(self):
        run = run_json([job(steps=(("Unit tests", "success"), ("Check coverage", "failure")))])
        self.assertEqual(self.classify(run, log("Process completed with exit code 1."))[0], "coverage")

    def test_coverage_threshold_message_is_coverage(self):
        text = log(f"{RED}ERROR: Coverage for lines (81.2%) does not meet global threshold (90%){RESET}")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "coverage")

    def test_lint_and_type_errors_are_lint_type(self):
        for line in ("✖ 3 problems (3 errors, 0 warnings)", "src/a.ts(4,2): error TS2345: Argument of type",
                     "Found 2 errors in 1 file (checked 9 source files)"):
            with self.subTest(line=line):
                self.assertEqual(self.classify(run_json([job()]), log(line))[0], "lint/type")

    def test_lint_type_lesson_has_its_rule(self):
        self.serve(run_json([job()]), log("src/a.ts(4,2): error TS2345: Argument"))
        self.assertEqual(self.learn()[0], EXIT_OK)
        self.assertIn("[ci-lint/type,repo-app]", self.ledger_text())
        self.assertIn("Run lint and the type check on every touched workspace before pushing", self.ledger_text())

    def test_failing_tests_are_test(self):
        for line in (f"{RED} FAIL {RESET} src/a.test.ts > adds", "AssertionError: 1 != 2", "=== 3 failed, 9 passed",
                     "--- FAIL: TestAdd (0.00s)"):
            with self.subTest(line=line):
                self.assertEqual(self.classify(run_json([job()]), log(line))[0], "test")

    def test_snapshot_mismatch_is_test_snapshot(self):
        self.serve(run_json([job()]), log(" FAIL  src/view.test.ts", "Error: Snapshot `view 1` mismatched"))
        code, out, err = self.learn()
        self.assertEqual(code, EXIT_OK, err)
        self.assertTrue(out.startswith("test/snapshot 2.0 min wasted"), out)
        self.assertIn("a snapshot change needs its snapshot updated in the same commit", self.ledger_text())

    def test_unknown_records_nothing(self):
        self.serve(run_json([job()]), log("Process completed with exit code 1."))
        code, out, err = self.learn()
        self.assertEqual(code, EXIT_OK, err)
        self.assertTrue(out.startswith("unknown 2.0 min wasted, run 101 feature/x: no lesson"), out)
        self.assertFalse(self.ledger.exists())

    def test_successful_run_has_nothing_to_record(self):
        self.serve(run_json([job(conclusion="success")], conclusion="success"))
        code, out, err = self.learn()
        self.assertEqual(code, EXIT_OK, err)
        self.assertIn("nothing to record", out)
        self.assertFalse(self.ledger.exists())

    def test_unfinished_run_exits_2_and_records_nothing(self):
        self.serve(run_json([job(conclusion="", end=None)], conclusion=""))
        code, out, err = self.learn()
        self.assertEqual(code, EXIT_UNREADABLE)
        self.assertIn("has not finished", err)
        self.assertFalse(self.ledger.exists())

    def test_coverage_step_that_never_ran_is_not_coverage(self):
        for conclusion in (None, "skipped"):
            with self.subTest(coverage_step=conclusion):
                run = run_json([job(steps=(("Unit tests", "failure"), ("Check coverage", conclusion)))])
                self.assertEqual(self.classify(run, log("Process completed with exit code 1."))[0], "unknown")

    # --- the echoed-script trap and evidence -------------------------------------------------------------------
    def test_echoed_script_never_decides_the_class(self):
        text = log(*echoed('echo "::error title=tests timed out::shard ran past its limit"',
                           "echo exceeded the maximum execution time; npx eslint; error TS9999"),
                   f"{RED}AssertionError: expected 3 to equal 4{RESET}")
        self.serve(run_json([job()]), text)
        code, out, err = self.learn()
        self.assertEqual(code, EXIT_OK, err)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("test 2.0 min wasted"), out)
        self.assertEqual(lines[1], "evidence: AssertionError: expected 3 to equal 4")

    def test_echoed_script_alone_is_unknown(self):
        text = log(*echoed("echo '##[error]job timed out' && exit 1"), "Process completed with exit code 1.")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "unknown")

    def test_evidence_is_the_first_deciding_line_cut_to_200(self):
        long_line = "AssertionError: " + "x" * 300
        self.serve(run_json([job()]), log("setup ok", long_line, "AssertionError: second"))
        out = self.learn("--dry-run")[1]
        evidence = out.splitlines()[1]
        self.assertEqual(evidence, "evidence: " + long_line[:200])

    def test_log_is_bounded_to_its_last_two_megabytes(self):
        limit = 2 * 1024 * 1024
        head = log("setup ok", "src/a.ts(1,1): error TS2345: early line") + log(*(["ok " + "y" * 200] * 100))
        cut_line = log("z" * 2000 + " error TS2345: the line the cut goes through")
        tail = log("AssertionError: late")
        line = log("ok " + "y" * 200)  # one fixed-width line, so the filler's size is exact
        filler = line * ((limit - 1500) // len(line))
        after = filler + tail
        self.assertTrue(limit - 1900 < len(after.encode()) < limit, len(after.encode()))  # the cut is inside cut_line
        kind, out = self.classify(run_json([job()]), head + cut_line + after)
        self.assertEqual(kind, "test", out)
        self.assertIn("evidence: AssertionError: late", out)

    # --- minutes ---------------------------------------------------------------------------------------------------
    def test_minutes_count_failed_timed_out_and_cancelled_jobs_only(self):
        run = run_json([
            job("a", "failure", "2026-01-05T10:00:00Z", "2026-01-05T10:02:30Z"),
            job("b", "timed_out", "2026-01-05T10:00:00Z", "2026-01-05T10:10:00Z"),
            job("c", "cancelled", "2026-01-05T10:00:00Z", None),
            job("f", "cancelled", "2026-01-05T10:00:00Z", "2026-01-05T10:01:00Z"),
            job("d", "success", "2026-01-05T10:00:00Z", "2026-01-05T10:20:00Z"),
            job("e", "failure", "0001-01-01T00:00:00Z", "2026-01-05T10:20:00Z"),
        ])
        self.serve(run, log("AssertionError: x"))
        out = self.learn("--dry-run")[1]
        self.assertTrue(out.startswith("timeout 13.5 min wasted"), out)

    def test_superseded_minutes_count_every_job(self):
        run = run_json([job("a", "cancelled", "2026-01-05T10:00:00Z", "2026-01-05T10:01:06Z"),
                        job("b", "success", "2026-01-05T10:00:00Z", "2026-01-05T10:04:00Z")], conclusion="cancelled")
        self.serve(run)
        self.assertTrue(self.learn("--dry-run")[1].startswith("superseded 5.1 min wasted"))

    # --- the ledger ------------------------------------------------------------------------------------------------
    def test_add_then_repeat_on_the_same_class_and_repo(self):
        self.serve(run_json([job()]), log("AssertionError: x"))
        self.assertEqual(self.learn()[0], EXIT_OK)
        self.serve(run_json([job()], run_id="202"), log("--- FAIL: TestB"), run_id="202")
        code, out, err = self.learn(run_id="202")
        self.assertEqual(code, EXIT_OK, err)
        self.assertTrue(out.startswith("test 2.0 min wasted, run 202 feature/x: L001 repeat x2"), out)
        self.assertIn("L001 [ci-test,repo-app] hits:2", self.ledger_text())
        events = (self.tmp / "lessons.events.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["event"] for line in events], ["add", "repeat"])

    def test_other_repo_or_class_gets_its_own_lesson(self):
        self.serve(run_json([job()]), log("AssertionError: x"))
        self.learn()
        self.serve(run_json([job()], repo="acme/web", run_id="303"), log("AssertionError: x"), run_id="303")
        self.assertIn("L002 added", self.learn(run_id="303")[1])
        self.serve(run_json([job()], run_id="404"), log("error TS2345: y"), run_id="404")
        self.assertIn("L003 added", self.learn(run_id="404")[1])

    def test_repo_flag_names_the_repo_and_is_passed_to_gh(self):
        self.serve(run_json([job()]), log("AssertionError: x"))
        self.assertEqual(self.learn("--repo", "octo/Thing")[0], EXIT_OK)
        self.assertIn("[ci-test,repo-thing]", self.ledger_text())
        self.assertTrue(all("-R octo/Thing" in call for call in self.gh.calls()), self.gh.calls())

    def test_archived_lesson_counts_as_a_repeat_and_returns(self):
        self.ledger.write_text("# Lessons Learned\n\n## Active\n\n## Archive\n"
                               "- L007 [ci-test,repo-app] hits:1 | 2026-01-01 | Mistake: m | Cause: c | Rule: r "
                               "| Check: k\n", encoding="utf-8")
        self.serve(run_json([job()]), log("AssertionError: x"))
        code, out, err = self.learn()
        self.assertEqual(code, EXIT_OK, err)
        self.assertIn("L007 repeat x2", out)
        self.assertLess(self.ledger_text().index("L007"), self.ledger_text().index("## Archive"))

    def serve_and_learn(self, run_id, *lines):
        self.serve(run_json([job()], run_id=run_id), log(*lines), run_id=run_id)
        return self.learn(run_id=run_id)

    def test_third_repeat_passes_the_escalation_exit_on_after_printing(self):
        self.serve_and_learn("101", "AssertionError: x")
        self.serve_and_learn("202", "AssertionError: x")
        code, out, err = self.serve_and_learn("303", "AssertionError: x")
        self.assertEqual(code, EXIT_ESCALATE, err)
        self.assertIn("L001 repeat x3", out)
        self.assertIn("PROMOTE L001", out + err)
        self.assertIn("ESCALATE L001 x3: this lesson has repeated without a guard.", err)  # as lessons.py bump
        self.assertNotIn("ESCALATE", out)

    def test_a_guarded_repeat_keeps_its_hint_and_never_escalates(self):
        self.ledger.write_text("# Lessons Learned\n\n## Active\n"
                               "- L001 [ci-test,repo-app] hits:2 | 2026-01-01 | Mistake: m | Cause: c | Rule: r "
                               "| Check: k | Promoted: tests/test_x.py\n\n## Archive\n", encoding="utf-8")
        self.serve(run_json([job()]), log("AssertionError: x"))
        code, out, err = self.learn()
        self.assertEqual(code, EXIT_ESCALATE, err)
        self.assertIn("GUARD FAILED L001", out)
        self.assertNotIn("ESCALATE", out + err)

    def test_dry_run_writes_nothing(self):
        self.serve(run_json([job()]), log("AssertionError: x"))
        code, out, err = self.learn("--dry-run")
        self.assertEqual(code, EXIT_OK, err)
        self.assertIn("L001 added (dry run)", out)
        self.assertFalse(self.ledger.exists())
        self.assertFalse((self.tmp / "lessons.events.jsonl").exists())

    def test_global_targets_the_global_ledger(self):
        self.serve(run_json([job()]), log("AssertionError: x"))
        code, out, err = self.learn("--global")
        self.assertEqual(code, EXIT_OK, err)
        self.assertIn("G001 added", out)
        self.assertIn("G001 [ci-test,repo-app]", (self.tmp / "global" / "lessons.md").read_text(encoding="utf-8"))
        self.assertFalse(self.ledger.exists())

    def test_json_prints_one_object(self):
        self.serve(run_json([job()]), log(" FAIL  a.test.ts", "Snapshot `s` mismatched"))
        code, out, err = self.learn("--json")
        self.assertEqual(code, EXIT_OK, err)
        data = json.loads(out)
        self.assertEqual((data["class"], data["sub_kind"], data["minutes"], data["run"], data["branch"]),
                         ("test", "snapshot", 2.0, "101", "feature/x"))
        self.assertEqual((data["lesson"], data["action"], data["hits"]), ("L001", "added", 1))
        self.assertEqual(data["evidence"], "FAIL  a.test.ts")

    # --- review round: classes that were mis-filed ------------------------------------------------------------------
    def test_a_single_test_hitting_its_own_timeout_is_test(self):
        text = log(" FAIL  src/api.test.ts > fetches user", "##[error]Error: Test timed out in 5000ms.",
                   " Test Files  1 failed | 20 passed")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "test")
        hook = log(" FAIL  src/api.test.ts", "##[error]Error: Hook timed out in 10000ms.")
        self.assertEqual(self.classify(run_json([job()]), hook)[0], "test")

    def test_a_tool_name_in_ordinary_output_is_not_lint(self):
        for lines in (("• Packages in scope: @acme/api, @acme/prettier-config, @acme/web",
                       "@acme/api:test: AssertionError: expected 1 to be 2"),
                      ("npm warn deprecated prettier-plugin-x@1.0.0", " FAIL  src/a.test.ts"),
                      ("Successfully installed mypy-1.10.0 pytest-8.2.0", "E   AssertionError: 1 != 2"),
                      ("> eslint . && prettier --check .", "FAIL src/a.test.ts"),
                      ("go: downloading github.com/golangci/x v1.0.0 for ruff and knip", "--- FAIL: TestA")):
            with self.subTest(lines=lines):
                self.assertEqual(self.classify(run_json([job()]), log(*lines))[0], "test")

    def test_each_lint_tool_output_is_lint_type(self):
        for lines in (("[warn] src/a.ts", "[warn] Code style issues found in the above file. Run Prettier with --write"
                                          " to fix."),
                      ("src/a.py:1:8: F401 [*] `os` imported but unused", "Found 1 error."),
                      ("Found 3 errors.", "[*] 3 fixable with the `--fix` option."),
                      ("Unused files (1)", "src/old.ts"),
                      ("Unused dependencies (1)", "left-pad  package.json"),
                      ("src/a.py:3: error: Incompatible types in assignment  [assignment]",),
                      ("pkg/a.go:12:2: Error return value of `f.Close` is not checked (errcheck)", "1 issues:")):
            with self.subTest(lines=lines):
                self.assertEqual(self.classify(run_json([job()]), log(*lines))[0], "lint/type")

    def test_a_job_hitting_timeout_minutes_is_timeout_though_github_says_cancelled(self):
        text = log("##[error]The job running on runner r1 has exceeded the maximum execution time of 360 minutes.")
        for conclusion in ("cancelled", "failure"):
            with self.subTest(run_conclusion=conclusion):
                run = run_json([job("e2e", "cancelled", end="2026-01-05T16:00:00Z")], conclusion=conclusion)
                kind, out = self.classify(run, text)
                self.assertEqual(kind, "timeout", out)
                self.assertTrue(out.startswith("timeout 360.0 min wasted"), out)
                self.assertIn("evidence: ##[error]The job running on runner r1 has exceeded", out)

    def serve_annotations(self, run, annotations, rc=0, job_id=77, text=""):
        self.gh.rules([
            {"match": ["run view 101", "--log-failed"], "stdout": text},
            {"match": ["run view 101", "--json"], "stdout": run},
            {"match": [f"api repos/acme/app/check-runs/{job_id}/annotations"], "stdout": annotations, "rc": rc},
        ])

    def test_a_time_limit_seen_only_in_the_jobs_annotations_is_timeout(self):
        # GitHub cancels a job at timeout-minutes; its failed log is empty and only the check run's annotations say why
        run = run_json([job("tests (api 4/4)", "cancelled", end="2026-01-05T10:28:00Z", job_id=77)],
                       conclusion="cancelled")
        self.serve_annotations(run, [{"annotation_level": "failure", "title": "",
                                      "message": "The job has exceeded the maximum execution time of 28m0s"}])
        code, out, err = self.learn("--dry-run")
        self.assertEqual(code, EXIT_OK, err)
        self.assertTrue(out.startswith("timeout 28.0 min wasted"), out)
        self.assertIn("exceeded the maximum execution time of 28m0s", out)

    def test_annotations_that_name_no_time_limit_keep_a_cancelled_run_superseded(self):
        run = run_json([job("tests", "cancelled", job_id=77)], conclusion="cancelled")
        self.serve_annotations(run, [{"annotation_level": "failure", "title": "",
                                      "message": "The operation was canceled."}])
        self.assertTrue(self.learn("--dry-run")[1].startswith("superseded"))

    def test_unreadable_annotations_leave_the_class_from_the_log_with_a_warning(self):
        run = run_json([job("tests", "cancelled", job_id=77)], conclusion="cancelled")
        self.serve_annotations(run, [], rc=1)
        code, out, err = self.learn("--dry-run")
        self.assertEqual(code, EXIT_OK, err)
        self.assertTrue(out.startswith("superseded"), out)
        self.assertIn("annotations", err)

    def test_superseded_run_whose_log_cannot_be_read_is_still_superseded(self):
        self.serve(run_json([job(conclusion="cancelled")], conclusion="cancelled"), log_rc=1)
        code, out, err = self.learn("--dry-run")
        self.assertEqual(code, EXIT_OK, err)
        self.assertTrue(out.startswith("superseded 2.0 min wasted"), out)
        self.assertIn("failed log unreadable", err)

    def test_a_failed_step_named_coverage_with_failing_tests_is_test(self):
        run = run_json([job(steps=(("Test with coverage", "failure"),))])
        text = log("FAILED tests/test_api.py::test_get - assert 404 == 200", "1 failed, 50 passed")
        self.assertEqual(self.classify(run, text)[0], "test")

    def test_a_network_word_in_a_test_name_is_not_outside(self):
        text = log(" FAIL  src/http.test.ts > retries on ECONNRESET", "AssertionError: expected 2 to be 3",
                   " Tests  1 failed")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "test")

    def test_go_package_fail_line_with_a_tab_is_test(self):
        text = log("panic: runtime error: index out of range", "FAIL\tgithub.com/acme/app/pkg\t0.512s", "FAIL")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "test")

    def test_a_script_group_left_open_by_a_dying_script_still_counts(self):
        text = log(*echoed("npm test"), "##[group]Run unit tests", " FAIL  src/a.test.ts > x", "AssertionError")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "test")

    def test_a_script_group_left_open_ends_with_its_step(self):
        text = (log("##[group]Run unit tests", "AssertionError: x", step="Unit")
                + log("##[group]Upload summary", "uploaded", "##[endgroup]", step="Report"))
        self.assertEqual(self.classify(run_json([job()]), text)[0], "test")

    def test_a_closed_group_that_is_not_a_run_echo_counts(self):
        text = log("##[group]Lint output", "src/a.ts(1,1): error TS2345: x", "##[endgroup]", "AssertionError: y")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "lint/type")

    def test_zero_failed_is_not_a_test_failure(self):
        text = log("Ran 12 tests: 12 passed, 0 failed", "##[error]Process completed with exit code 1.")
        kind, out = self.classify(run_json([job()]), text)
        self.assertEqual(kind, "unknown")
        self.assertIn("evidence: ##[error]Process completed with exit code 1.", out)

    def test_a_byte_order_mark_does_not_hide_the_first_echo_group(self):
        text = "﻿" + log(*echoed("tsc; echo error TS2345"), "AssertionError: x")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "test")

    def test_a_job_named_coverage_without_steps_is_coverage(self):
        self.assertEqual(self.classify(run_json([job("coverage")]), log("Process completed with exit code 1."))[0],
                         "coverage")

    def test_a_failed_coverage_step_in_a_passing_job_is_not_coverage(self):
        run = run_json([job("unit", "success", steps=(("Check coverage", "failure"),)), job("tests")])
        self.assertEqual(self.classify(run, log("Process completed with exit code 1."))[0], "unknown")

    def test_outside_cause_beats_a_timed_out_job(self):
        self.assertEqual(self.classify(run_json([job(conclusion="timed_out")]), log("Error: ECONNRESET"))[0],
                         "outside")

    def test_cancelled_run_with_a_failed_job_is_superseded(self):
        run = run_json([job("a", "failure"), job("b", "cancelled")], conclusion="cancelled")
        self.assertEqual(self.classify(run, log("AssertionError: x"))[0], "superseded")

    # --- review round: ledger and robustness -------------------------------------------------------------------------
    def test_dry_run_at_the_threshold_does_not_claim_a_recorded_escalation(self):
        self.ledger.write_text("# Lessons Learned\n\n## Active\n"
                               "- L001 [ci-test,repo-app] hits:2 | 2026-01-01 | Mistake: m | Cause: c | Rule: r "
                               "| Check: k\n\n## Archive\n", encoding="utf-8")
        before = self.ledger_text()
        self.serve(run_json([job()]), log("AssertionError: x"))
        code, out, err = self.learn("--dry-run")
        self.assertEqual(code, EXIT_OK, out + err)
        self.assertIn("L001 repeat x3 (dry run)", out)
        self.assertIn("dry run, nothing recorded: PROMOTE L001", out)
        self.assertEqual(self.ledger_text(), before)

    def test_a_full_active_section_archives_the_weakest_lesson(self):
        rows = "".join(f"- L{n:03d} [area{n}] hits:{1 if n == 4 else 2} | 2026-01-{n:02d} | Mistake: m{n} "
                       f"| Cause: c{n} | Rule: r{n} | Check: k{n}\n" for n in range(1, 16))
        self.ledger.write_text(f"# Lessons Learned\n\n## Active\n{rows}\n## Archive\n", encoding="utf-8")
        self.serve(run_json([job()]), log("AssertionError: x"))
        code, out, err = self.learn()
        self.assertEqual(code, EXIT_OK, err)
        self.assertIn("L016 added", out)
        self.assertIn("archived L004", err)
        text = self.ledger_text()
        self.assertGreater(text.index("- L004 "), text.index("## Archive"))

    def test_a_ledger_with_unparsable_lines_is_refused_and_left_alone(self):
        self.ledger.write_text("# Lessons Learned\n\n## Active\n- L001 this line is broken\n\n## Archive\n",
                               encoding="utf-8")
        before = self.ledger_text()
        self.serve(run_json([job()]), log("AssertionError: x"))
        code, out, err = self.learn()
        self.assertEqual(code, EXIT_UNREADABLE, out)
        self.assertIn("unparsable", err)
        self.assertEqual(self.ledger_text(), before)

    def test_a_ledger_held_by_another_writer_is_refused(self):
        self.serve(run_json([job()]), log("AssertionError: x"))
        store = sys.modules["ledger_store"]
        with store.locked(self.ledger), mock.patch.object(store, "LOCK_WAIT", 0.1):
            code, out, err = self.learn_in_process()
        self.assertEqual(code, EXIT_UNREADABLE, out)
        self.assertIn("locked", err)
        self.assertFalse(self.ledger.exists())

    def test_a_failed_log_download_that_hangs_is_cut_off(self):
        self.gh.rules([{"match": ["run view 101", "--log-failed"], "stdout": "", "sleep": 30},
                       {"match": ["run view 101", "--json"], "stdout": run_json([job()])}])
        with mock.patch.object(sys.modules["ci_wait"], "GH_TIMEOUT", 0.5):
            code, out, err = self.learn_in_process()
        self.assertEqual(code, EXIT_UNREADABLE, out)
        self.assertIn("did not answer", err)

    def test_a_console_that_cannot_encode_the_evidence_still_prints(self):
        self.serve(run_json([job()]), log("✖ 3 problems (3 errors, 0 warnings)"))
        console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")  # strict, like a cp1252 terminal
        env = {"PATH": self.gh.env()["PATH"]}
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(console):
            code = ci_learn.main(["101", "--ledger", str(self.ledger)])
            console.flush()
        self.assertEqual(code, EXIT_OK)
        self.assertIn("evidence: ? 3 problems (3 errors", console.buffer.getvalue().decode("cp1252"))

    # --- review round 3: mis-filed classes ----------------------------------------------------------------------------
    def test_a_network_error_inside_a_failing_test_step_is_test(self):
        vitest = log("stderr | src/client.test.ts > retries on reset", "Error: read ECONNRESET",
                     " FAIL  src/client.test.ts > retries on reset", "AssertionError: expected 1 to be 3")
        jest = log("FAIL src/api.test.js", '-   "error": null,', '+   "error": "rate limit exceeded",',
                   "Tests:       1 failed, 9 passed, 10 total")
        for text in (vitest, jest):
            with self.subTest(text=text):
                self.assertEqual(self.classify(run_json([job()]), text)[0], "test")

    def test_an_outside_cause_in_a_step_without_test_results_is_outside(self):
        text = (log("Error: toomanyrequests: rate limit", step="Install")
                + log(" FAIL  src/a.test.ts", "AssertionError: x", job_name="unit", step="Run tests"))
        self.assertTrue(self.classify(run_json([job()]), text)[1].startswith("outside"))

    def test_a_runner_lost_during_the_tests_is_outside(self):
        text = log(" FAIL  src/a.test.ts > x", "##[error]The runner has received a shutdown signal.")
        self.assertTrue(self.classify(run_json([job()]), text)[1].startswith("outside"))

    def test_a_script_opening_its_own_run_group_keeps_its_output(self):
        text = log(*echoed("echo ::group::Run unit tests; pnpm test || rc=$?; echo ::endgroup::; exit $rc"),
                   "##[group]Run unit tests", f"{RED} FAIL {RESET} src/a.test.ts > adds",
                   "AssertionError: expected 1 to be 2", " Tests  1 failed", "##[endgroup]")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "test")

    def test_an_action_echo_group_with_inputs_never_decides(self):
        text = log("##[group]Run acme/report-action@v1", "with:", "  title: tests timed out", "env:",
                   "  NOTE: error TS2345", "##[endgroup]", "AssertionError: x")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "test")

    def test_composite_steps_echo_groups_never_decide(self):
        text = log(*echoed("echo setup"), "setup done", *echoed("echo 'Coverage threshold not met'"),
                   "AssertionError: x")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "test")

    def test_a_held_open_run_group_is_kept_when_the_next_group_starts(self):
        text = log("##[group]Run unit tests", "AssertionError: x", "##[group]Run next", "x", "##[endgroup]")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "test")

    def test_more_coverage_messages_are_coverage(self):
        for line in ('ERROR: Coverage for lines (71.2%) does not meet "src/**" threshold (80%)',
                     "Coverage 71% is below the 90% minimum"):
            with self.subTest(line=line):
                self.assertEqual(self.classify(run_json([job()]), log(line))[0], "coverage")

    def test_a_coverage_threshold_after_failing_tests_is_test(self):
        text = log("FAIL src/a.test.js", "Tests:       1 failed, 9 passed, 10 total",
                   'Jest: "global" coverage threshold for lines (90%) not met: 60%')
        self.assertEqual(self.classify(run_json([job()]), text)[0], "test")

    def test_more_lint_outputs_are_lint_type(self):
        for lines in (("Would reformat: src/app.py", "1 file would be reformatted, 20 files already formatted"),
                      ("Duplicate exports (1)", "a, b  src/x.ts"), ("1 issues:", "* errcheck: 1")):
            with self.subTest(lines=lines):
                self.assertEqual(self.classify(run_json([job()]), log(*lines))[0], "lint/type")

    def test_mocha_failing_count_is_test(self):
        text = log("  0 passing (2s)", "  1 failing", "  1) api", "     Error: Timeout of 2000ms exceeded.")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "test")

    def test_jest_snapshot_failure_is_test_snapshot(self):
        text = log("FAIL src/a.test.js", "expect(received).toMatchSnapshot()", " › 1 snapshot failed from 1 test suite.")
        self.assertTrue(self.classify(run_json([job()]), text)[1].startswith("test/snapshot"))

    def test_a_wait_for_a_server_that_timed_out_is_not_timeout(self):
        text = log("##[error]Timed out waiting for: http://localhost:3000")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "unknown")

    def test_superseded_evidence_names_only_the_cancelled_jobs(self):
        run = run_json([job("a", "failure"), job("b", "cancelled"), job("c", "success"), job("d", "cancelled")],
                       conclusion="cancelled")
        out = self.classify(run)[1]
        self.assertIn("evidence: run concluded cancelled; cancelled jobs: b, d", out)

    # --- review round 3: repositories, conclusions, robustness ---------------------------------------------------------
    def test_an_enterprise_server_run_url_names_the_repo(self):
        run = run_json([job()])
        run["url"] = "https://ghe.corp.example/acme/app/actions/runs/101"
        self.serve(run, log("AssertionError: x"))
        self.assertEqual(self.learn()[0], EXIT_OK)
        self.assertIn("[ci-test,repo-app]", self.ledger_text())

    def test_a_repo_flag_with_a_host_names_the_same_repo(self):
        self.serve(run_json([job()]), log("AssertionError: x"))
        code, _, err = self.learn("--repo", "ghe.corp.example/acme/app")
        self.assertEqual(code, EXIT_OK, err)
        self.assertIn("[ci-test,repo-app]", self.ledger_text())

    def test_skipped_or_neutral_run_has_nothing_to_record(self):
        for conclusion in ("skipped", "neutral"):
            with self.subTest(conclusion=conclusion):
                self.serve(run_json([job(conclusion=conclusion)], conclusion=conclusion), log("AssertionError: x"))
                code, out, err = self.learn()
                self.assertEqual(code, EXIT_OK, err)
                self.assertIn(f"concluded {conclusion}: nothing to record", out)
                self.assertFalse(self.ledger.exists())

    def test_run_view_printing_json_that_is_not_a_run_exits_2(self):
        for printed in ([], None):
            with self.subTest(printed=printed):
                self.gh.rules([{"match": ["run view 101", "--json"], "stdout": json.dumps(printed)}])
                code, _, err = self.learn()
                self.assertEqual(code, EXIT_UNREADABLE, err)
                self.assertIn("printed no run", err)

    def test_dry_run_against_an_unparsable_ledger_is_refused(self):
        self.ledger.write_text("# Lessons Learned\n\n## Active\n- L001 this line is broken\n\n## Archive\n",
                               encoding="utf-8")
        self.serve(run_json([job()]), log("AssertionError: x"))
        code, out, err = self.learn("--dry-run")
        self.assertEqual(code, EXIT_UNREADABLE, out)
        self.assertIn("unparsable", err)

    # --- final fix pass ---------------------------------------------------------------------------------------------
    def test_a_pytest_cov_threshold_line_is_coverage_not_a_failing_test(self):
        text = log("==== 120 passed in 3.20s ====",
                   "FAIL Required test coverage of 90% not reached. Total coverage: 85.00%")
        kind, out = self.classify(run_json([job()]), text)
        self.assertEqual(kind, "coverage", out)
        self.assertIn("evidence: FAIL Required test coverage of 90% not reached.", out)
        with_failure = log("FAILED tests/test_a.py::test_x - assert 1 == 2", "==== 1 failed, 119 passed ====",
                           "FAIL Required test coverage of 90% not reached. Total coverage: 85.00%")
        self.assertEqual(self.classify(run_json([job()]), with_failure)[0], "test")

    def test_a_coverage_py_fail_under_line_is_coverage(self):
        text = log("TOTAL    1200    180    85%", "Coverage failure: total of 85 is less than fail-under=90")
        self.assertEqual(self.classify(run_json([job()]), text)[0], "coverage")

    def test_a_timeout_a_test_printed_is_not_a_ci_timeout(self):
        vitest = log(" FAIL  src/api.test.ts > fetches user", "##[error]Error: Request timed out after 5000ms")
        self.assertEqual(self.classify(run_json([job()]), vitest)[0], "test")
        alone = log("##[error]Error: Request timed out after 5000ms")
        self.assertEqual(self.classify(run_json([job()]), alone)[0], "unknown")

    def test_a_step_time_limit_is_timeout_unless_the_step_shows_a_failing_test(self):
        limit = "##[error]The action 'Run tests' has timed out after 10 minutes."
        self.assertEqual(self.classify(run_json([job()]), log(limit))[0], "timeout")
        self.assertEqual(self.classify(run_json([job()]), log(" FAIL  src/a.test.ts > x", limit))[0], "test")
        other_step = log(" FAIL  src/a.test.ts > x", step="Unit") + log(limit, step="E2E")
        self.assertEqual(self.classify(run_json([job()]), other_step)[0], "timeout")

    def test_the_same_run_learned_twice_is_counted_once(self):
        self.assertEqual(self.serve_and_learn("101", "AssertionError: x")[0], EXIT_OK)
        before = self.ledger_text()
        code, out, err = self.learn()
        self.assertEqual(code, EXIT_OK, err)
        self.assertTrue(out.startswith("test 2.0 min wasted, run 101 feature/x: L001 already counted (x1)"), out)
        self.assertEqual(self.ledger_text(), before)
        events = (self.tmp / "lessons.events.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(events), 1)

    def test_a_counted_run_seen_again_after_others_never_escalates(self):
        for run_id in ("101", "202", "303"):
            code, out, err = self.serve_and_learn(run_id, "AssertionError: x")
        self.assertEqual(code, EXIT_ESCALATE, err)
        self.assertIn("; runs counted: 101 202 303 |", self.ledger_text())
        before = self.ledger_text()
        code, out, err = self.serve_and_learn("202", "AssertionError: x")
        self.assertEqual(code, EXIT_OK, out + err)
        self.assertIn("L001 already counted (x3)", out)
        self.assertNotIn("ESCALATE", out + err)
        self.assertNotIn("PROMOTE", out + err)
        self.assertEqual(self.ledger_text(), before)

    def test_counted_runs_keep_the_newest_within_the_field_limit(self):
        old = " ".join(str(10 ** 10 + n) for n in range(18))
        self.ledger.write_text("# Lessons Learned\n\n## Active\n"
                               f"- L001 [ci-test,repo-app] hits:18 | 2026-01-01 | Mistake: m; runs counted: {old} "
                               "| Cause: c | Rule: r | Check: k | Promoted: tests/test_x.py\n\n## Archive\n",
                               encoding="utf-8")
        self.serve_and_learn("99999999999", "AssertionError: x")
        mistake = self.ledger_text().split("Mistake: ", 1)[1].split(" | Cause:", 1)[0]
        self.assertLessEqual(len(mistake), 200)
        self.assertTrue(mistake.startswith("m; runs counted: "), mistake)
        self.assertTrue(mistake.endswith(" 10000000017 99999999999"), mistake)
        self.assertNotIn("10000000000", mistake)
        self.assertIn("L001 [ci-test,repo-app] hits:19", self.ledger_text())

    def test_a_cut_inside_an_echo_group_drops_the_echo_left_before_endgroup(self):
        limit = 2 * 1024 * 1024
        head = log("setup ok", *(["ok " + "y" * 200] * 100), "##[group]Run tsc --noEmit && npm test")
        cut_line = log(f"{CYAN}# " + "z" * 2000 + f"{RESET}")
        echo_tail = log(f"{CYAN}tsc --noEmit || echo 'src/a.ts(1,1): error TS2345: x'{RESET}",
                        "shell: /usr/bin/bash -e {0}", "env:", "  CI: true", "##[endgroup]")
        tail = log("AssertionError: late")
        line = log("ok " + "y" * 200)
        filler = line * ((limit - 1500 - len(echo_tail) - len(tail)) // len(line))
        after = echo_tail + filler + tail
        self.assertTrue(limit - 1900 < len(after.encode()) < limit, len(after.encode()))  # the cut is inside cut_line
        kind, out = self.classify(run_json([job()]), head + cut_line + after)
        self.assertEqual(kind, "test", out)

    def test_a_cut_keeps_lines_that_are_not_an_echo_tail(self):
        script_group = log("AssertionError: x", "##[endgroup]", "done")
        self.assertEqual(ci_learn.drop_cut_echo_tail(script_group), script_group)
        new_step = log(f"{CYAN}echo hi{RESET}", step="A") + log("##[endgroup]", "error TS2345: y", step="B")
        self.assertEqual(ci_learn.drop_cut_echo_tail(new_step), new_step)
        new_group = log(f"{CYAN}echo hi{RESET}", "##[group]Run b", "##[endgroup]", "after")
        self.assertEqual(ci_learn.drop_cut_echo_tail(new_group), new_group)
        self.assertEqual(ci_learn.drop_cut_echo_tail(""), "")
        echo = log("  CI: true", "##[endgroup]") + log("kept")
        self.assertEqual(ci_learn.drop_cut_echo_tail(echo), log("kept"))

    # --- unreadable --------------------------------------------------------------------------------------------------
    def test_unreadable_run_exits_2(self):
        self.serve({}, view_rc=1)
        code, _, err = self.learn()
        self.assertEqual(code, EXIT_UNREADABLE)
        self.assertIn("could not read run 101", err)
        self.assertFalse(self.ledger.exists())

    def test_run_view_without_json_exits_2(self):
        self.gh.rules([{"match": ["run view 101", "--json"], "stdout": "not json"}])
        self.assertEqual(self.learn()[0], EXIT_UNREADABLE)

    def test_failed_log_download_exits_2(self):
        self.serve(run_json([job()]), log_rc=1)
        self.assertEqual(self.learn()[0], EXIT_UNREADABLE)

    def test_no_gh_exits_2(self):
        env = {"PATH": str(self.tmp / "empty")}
        self.assertEqual(self.learn(env=env)[0], EXIT_UNREADABLE)

    def test_non_numeric_run_id_is_a_usage_error(self):
        self.assertEqual(self.learn(run_id="abc")[0], EXIT_UNREADABLE)


if __name__ == "__main__":
    unittest.main()
