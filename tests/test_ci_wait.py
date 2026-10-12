"""Unit tests for the ci-wait skill's waiting script."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "ci-wait" / "scripts"))

import ci_wait  # noqa: E402

HEAD = "a" * 40
LINK = "https://github.com/acme/app/actions/runs/77/job/1"


def check(bucket, name="tests", link=LINK):
    return {"name": name, "bucket": bucket, "link": link}


def jobs(steps=(("Run tests", "failure"),), conclusion="failure"):
    job_steps = [{"name": name, "conclusion": result} for name, result in steps]
    return {"jobs": [{"name": "tests", "conclusion": conclusion, "steps": job_steps},
                     {"name": "lint", "conclusion": "success", "steps": []}]}


class FakeGh:
    """Scripted `gh`: each command prefix answers from a queue; the last answer repeats."""

    def __init__(self, head=HEAD, checks=(), run_jobs=None, log=""):
        self.answers = {
            "pr view": [json.dumps({"headRefOid": head})],
            "pr checks": [json.dumps(batch) for batch in checks] or [""],
            "run view --json": [json.dumps(run_jobs or jobs())],
            "run view --log-failed": [log],
        }
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["run", "rerun"]:
            return 0, ""
        key = " ".join(args[:2])
        if key == "run view":
            key += " " + args[3]
        queue = self.answers[key]
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        return (answer if isinstance(answer, tuple) else (0, answer))

    def count(self, *prefix):
        return sum(1 for call in self.calls if call[:len(prefix)] == list(prefix))


class CiWaitTests(unittest.TestCase):
    def run_wait(self, gh, **options):
        self.sleeps, self.lines = [], []
        return ci_wait.wait(12, runner=gh, sleep=self.sleeps.append, out=self.lines.append, **options)

    def output(self):
        return "\n".join(self.lines)

    def test_green_prints_the_tested_commit_and_merge_command(self):
        gh = FakeGh(checks=[[check("pending")], [check("pass"), check("skipping", "docs")]])
        self.assertEqual(self.run_wait(gh), ci_wait.EXIT_GREEN)
        self.assertIn(f"gh pr merge 12 --match-head-commit {HEAD}", self.output())
        self.assertEqual(self.sleeps, [30])
        self.assertEqual(gh.count("run", "rerun"), 0)

    def test_head_moved_while_waiting_waits_for_the_new_commit(self):
        gh = FakeGh(checks=[[check("pass")]])
        new_head = "b" * 40
        gh.answers["pr view"] = [json.dumps({"headRefOid": h}) for h in (HEAD, new_head, new_head)]
        self.assertEqual(self.run_wait(gh), ci_wait.EXIT_GREEN)
        self.assertIn(f"CI is green on {new_head}.", self.output())
        self.assertNotIn(f"CI is green on {HEAD}.", self.output())

    def test_change_failure_exits_1_with_job_step_and_error_lines(self):
        log = "tests\tRun tests\t\x1b[31mAssertionError: expected 200\x1b[0m\ntests\tRun tests\tFAIL src/a.test"
        gh = FakeGh(checks=[[check("fail"), check("pass", "lint")]], log=log)
        self.assertEqual(self.run_wait(gh), ci_wait.EXIT_CHANGE_FAILED)
        self.assertIn("tests: Run tests", self.output())
        self.assertIn("AssertionError: expected 200", self.output())
        self.assertNotIn("\x1b", self.output())
        self.assertEqual(gh.count("run", "rerun"), 0)

    def test_failing_check_without_a_run_link_is_the_change(self):
        gh = FakeGh(checks=[[check("fail", "external", "https://status.example/1")]])
        self.assertEqual(self.run_wait(gh), ci_wait.EXIT_CHANGE_FAILED)
        self.assertIn("external", self.output())

    def test_outside_failure_is_rerun_then_green(self):
        gh = FakeGh(checks=[[check("fail")], [check("pass")]], log="toomanyrequests: slow down")
        self.assertEqual(self.run_wait(gh), ci_wait.EXIT_GREEN)
        self.assertIn(["run", "rerun", "77", "--failed"], gh.calls)
        self.assertEqual(self.sleeps, [240, 60])
        self.assertIn("registry rate limit", self.output())

    def test_rerun_cap_then_exit_1(self):
        gh = FakeGh(checks=[[check("fail")]], log="net/http: TLS handshake timeout")
        self.assertEqual(self.run_wait(gh), ci_wait.EXIT_CHANGE_FAILED)
        self.assertEqual(gh.count("run", "rerun"), 2)
        self.assertIn("after 2 rerun(s)", self.output())

    def test_rerun_cap_is_configurable(self):
        gh = FakeGh(checks=[[check("fail")]], log="ECONNRESET")
        self.assertEqual(self.run_wait(gh, max_reruns=0), ci_wait.EXIT_CHANGE_FAILED)
        self.assertEqual(gh.count("run", "rerun"), 0)

    def test_mixed_runs_are_not_rerun_when_one_has_no_outside_cause(self):
        other = "https://github.com/acme/app/actions/runs/78/job/2"
        gh = FakeGh(checks=[[check("fail"), check("fail", "build", other)]])
        gh.answers["run view --log-failed"] = ["i/o timeout", "error: type mismatch", "x"]
        self.assertEqual(self.run_wait(gh), ci_wait.EXIT_CHANGE_FAILED)
        self.assertEqual(gh.count("run", "rerun"), 0)

    def test_unreadable_pull_request_exits_2(self):
        for answer in ((1, ""), (0, "not json"), (0, "{}"), (0, "[]")):
            with self.subTest(answer=answer):
                gh = FakeGh()
                gh.answers["pr view"] = [answer]
                self.assertEqual(self.run_wait(gh), ci_wait.EXIT_UNREADABLE)

    def test_unreadable_checks_or_run_exit_2(self):
        gh = FakeGh()
        gh.answers["pr checks"] = [(1, "<html>bad gateway</html>")]
        self.assertEqual(self.run_wait(gh), ci_wait.EXIT_UNREADABLE)
        gh = FakeGh(checks=[{"not": "a list"}])
        self.assertEqual(self.run_wait(gh), ci_wait.EXIT_UNREADABLE)
        gh = FakeGh(checks=[[check("fail")]])
        gh.answers["run view --json"] = [(1, "")]
        self.assertEqual(self.run_wait(gh), ci_wait.EXIT_UNREADABLE)

    def test_timeout_while_pending_exits_3(self):
        gh = FakeGh(checks=[[check("pending")]])
        self.assertEqual(self.run_wait(gh, interval=10, timeout=30), ci_wait.EXIT_NOT_FINISHED)
        self.assertEqual(self.sleeps, [10, 10, 10])

    def test_empty_check_lists_exit_3(self):
        for answer in ((1, ""), (0, "[]")):
            with self.subTest(answer=answer):
                gh = FakeGh()
                gh.answers["pr checks"] = [answer]
                self.assertEqual(self.run_wait(gh, interval=30, timeout=60), ci_wait.EXIT_NOT_FINISHED)
                self.assertIn("no checks", self.output())

    def test_failing_checks_exit_code_from_gh_is_not_an_error(self):
        gh = FakeGh()
        gh.answers["pr checks"] = [(8, json.dumps([check("pending")])), (0, json.dumps([check("pass")]))]
        self.assertEqual(self.run_wait(gh), ci_wait.EXIT_GREEN)

    def test_jobs_that_never_started_exit_4_without_rerun(self):
        gh = FakeGh(checks=[[check("fail")]], run_jobs=jobs(steps=()))
        self.assertEqual(self.run_wait(gh), ci_wait.EXIT_NEVER_STARTED)
        self.assertEqual(gh.count("run", "rerun"), 0)
        self.assertIn("tests: no step ran", self.output())

    def test_billing_in_the_log_exits_4(self):
        gh = FakeGh(checks=[[check("cancel")]], run_jobs=jobs(conclusion="cancelled"),
                    log="recent account payments have failed")
        self.assertEqual(self.run_wait(gh), ci_wait.EXIT_NEVER_STARTED)

    def test_missing_gh_binary_exits_2(self):
        self.assertEqual(self.run_wait(lambda args: (127, "")), ci_wait.EXIT_UNREADABLE)


class ClassifyLogTests(unittest.TestCase):
    SAMPLES = {
        "registry rate limit": ["429 Too Many Requests", "toomanyrequests: pull limit",
                                "API rate limit exceeded for installation"],
        "registry or upstream unavailable": ["Get https://auth.docker.io/token: EOF",
                                             "503 Service Unavailable", "502 Bad Gateway",
                                             "504 Gateway Timeout", "504 Gateway Time-out"],
        "network": ["net/http: TLS handshake timeout", "dial tcp 10.0.0.1:443: i/o timeout",
                    "read ECONNRESET", "getaddrinfo EAI_AGAIN registry.npmjs.org",
                    "connection reset by peer", "Temporary failure in name resolution",
                    "curl: (6) Could not resolve host: example.org"],
        "runner lost": ["The runner has received a shutdown signal.",
                        "The self-hosted runner lost communication with the server.",
                        "The hosted runner encountered an error while running your job."],
        "CI provider": ["Failed to download action 'https://api.github.com/x'",
                        "Unable to download artifact(s)", "##[error]The service is unavailable."],
        "billing": ["because recent account payments have failed",
                    "or your spending limit needs to be increased"],
    }

    def test_every_outside_pattern_is_recognised(self):
        self.assertEqual(set(self.SAMPLES), {label for label, _, _ in ci_wait.OUTSIDE_CAUSES})
        for label, lines in self.SAMPLES.items():
            for line in lines:
                with self.subTest(line=line):
                    self.assertEqual([found for found, _ in ci_wait.classify_log(line)], [label])

    def test_only_billing_is_not_rerunnable(self):
        blocked = [label for label, _, rerunnable in ci_wait.OUTSIDE_CAUSES if not rerunnable]
        self.assertEqual(blocked, ["billing"])

    def test_change_failures_empty_and_none_are_not_outside(self):
        for text in ("AssertionError: expected 200 got 500", "error TS2322: type mismatch",
                     "Test timeout of 5000ms exceeded", "", None):
            with self.subTest(text=text):
                self.assertEqual(ci_wait.classify_log(text), [])

    def test_colour_codes_and_case_do_not_hide_a_cause(self):
        self.assertEqual(ci_wait.classify_log("\x1b[31mTOOMANYREQUESTS\x1b[0m"),
                         [("registry rate limit", True)])

    def test_error_lines_are_distinct_trimmed_and_capped(self):
        log = "\n".join(["ok"] + [f"Error: boom {n % 20}" for n in range(40)] + ["x" * 300 + " FAIL"])
        lines = ci_wait.error_lines(log, limit=5)
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[-1], "Error: boom 19")
        self.assertEqual(ci_wait.error_lines(None), [])

    def test_main_rejects_missing_argument(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            ci_wait.main([])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
