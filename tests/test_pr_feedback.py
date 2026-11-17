"""Unit tests for the ship skill's pull request feedback collector."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "ship" / "scripts" / "pr_feedback.py"
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pr_feedback  # noqa: E402
from fake_gh import FakeGh, path_without_gh  # noqa: E402

REPO_VIEW = {"match": ["repo view"], "stdout": {"owner": {"login": "acme"}, "name": "app"}}
PR_VIEW = {"match": ["pr view 12"], "stdout": {"files": [{"path": "a.py"}, {"path": "b.py"}], "headRefOid": "f" * 40,
                                               "state": "OPEN"}}
CHECKS = {"match": ["pr checks 12"], "rc": 1, "stdout": [
    {"name": "tests", "bucket": "fail", "link": "https://ci/1", "workflow": "CI"},
    {"name": "lint", "bucket": "pass", "link": "https://ci/2", "workflow": "CI"},
    {"name": "e2e", "bucket": "pending", "link": "https://ci/3", "workflow": "CI"}]}


def thread(tid, path, body, resolved=False, outdated=False, line=3):
    return {"id": tid, "isResolved": resolved, "isOutdated": outdated, "path": path, "line": line,
            "comments": {"nodes": [{"author": {"login": "rev"}, "body": body, "url": f"https://x/{tid}"}]}}


def page(threads, next_cursor=None):
    return {"data": {"repository": {"pullRequest": {"reviewThreads": {
        "pageInfo": {"hasNextPage": bool(next_cursor), "endCursor": next_cursor}, "nodes": threads}}}}}


FIRST = [thread("t1", "a.py", "Please rename `x` to `total`."),
         thread("t2", "a.py", "done", resolved=True),
         thread("t3", "b.py", "Why do we need a second query here?")]
SECOND = [thread("t4", "a.py", "Nice, but let's do the caching in a follow-up PR."),
          thread("t5", "c.py", "This file needs a docstring."),
          thread("t6", "a.py", "Use a constant.", outdated=True),
          thread("t7", "b.py", "```suggestion\nreturn total\n```")]
GRAPHQL = [{"match": ["api graphql"], "unless": ["cursor="], "stdout": page(FIRST, "c1")},
           {"match": ["api graphql", "cursor=c1"], "stdout": page(SECOND)}]


class FeedbackCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.gh = FakeGh(Path(self.tmp.name) / "bin")

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args, env=None):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                                env=env or self.gh.env())
        return result.returncode, (json.loads(result.stdout) if result.stdout.strip() else None), result.stderr


class WorklistTest(FeedbackCase):
    def test_threads_and_checks_are_classified_across_pages(self):
        self.gh.rules([REPO_VIEW, PR_VIEW, CHECKS, *GRAPHQL])
        code, data, _ = self.run_script("12")
        self.assertEqual(code, pr_feedback.EXIT_WORK)
        got = {item["id"]: item["class"] for item in data["worklist"]}
        self.assertEqual(got, {"tests": "fix", "t1": "fix", "t3": "question", "t4": "out-of-scope",
                               "t5": "out-of-scope", "t6": "question", "t7": "fix"})
        self.assertNotIn("t2", got)  # resolved threads are not work
        self.assertEqual(data["summary"], {"fix": 3, "question": 2, "out-of-scope": 2})
        self.assertEqual(data["pending_checks"], ["e2e"])
        self.assertEqual(data["head"], "f" * 40)
        self.assertEqual(len([c for c in self.gh.calls() if c.startswith("api graphql")]), 2)

    def test_given_repo_skips_the_lookup_and_is_passed_on(self):
        self.gh.rules([PR_VIEW, CHECKS, *GRAPHQL])
        code, _, _ = self.run_script("12", "--repo", "acme/app")
        self.assertEqual(code, pr_feedback.EXIT_WORK)
        calls = self.gh.calls()
        self.assertFalse(any(c.startswith("repo view") for c in calls))
        self.assertTrue(all("--repo acme/app" in c for c in calls if c.startswith("pr ")))
        self.assertTrue(any("owner=acme" in c and "name=app" in c and "pr=12" in c for c in calls))

    def test_nothing_to_do(self):
        self.gh.rules([REPO_VIEW, PR_VIEW, {"match": ["pr checks"], "stdout": [{"name": "t", "bucket": "pass"}]},
                       {"match": ["api graphql"], "stdout": page([thread("t2", "a.py", "ok", resolved=True)])}])
        code, data, _ = self.run_script("12")
        self.assertEqual((code, data["worklist"], data["summary"]),
                         (pr_feedback.EXIT_CLEAN, [], {"fix": 0, "question": 0, "out-of-scope": 0}))

    def test_only_out_of_scope_items_and_no_checks_mean_clean(self):
        self.gh.rules([REPO_VIEW, PR_VIEW,
                       {"match": ["pr checks"], "rc": 1, "stderr": "no checks reported on the 'x' branch"},
                       {"match": ["api graphql"], "stdout": page([thread("t5", "c.py", "docstring please")])}])
        code, data, _ = self.run_script("12")
        self.assertEqual(code, pr_feedback.EXIT_CLEAN)
        self.assertEqual(data["summary"]["out-of-scope"], 1)

    def test_reviewer_text_is_capped(self):
        self.gh.rules([REPO_VIEW, PR_VIEW, {"match": ["pr checks"], "stdout": []},
                       {"match": ["api graphql"], "stdout": page([thread("t1", "a.py", "x" * 5000)])}])
        self.assertEqual(len(self.run_script("12")[1]["worklist"][0]["text"]), pr_feedback.TEXT_CHARS)


class ErrorTest(FeedbackCase):
    def test_no_such_pull_request(self):
        self.gh.rules([REPO_VIEW, {"match": ["pr view"], "rc": 1,
                                   "stderr": "GraphQL: Could not resolve to a PullRequest with the number of 99."}])
        code, data, err = self.run_script("99")
        self.assertEqual((code, data), (pr_feedback.EXIT_ERROR, None))
        self.assertIn("Could not resolve", err)

    def test_graphql_errors_and_a_vanished_pull_request(self):
        self.gh.rules([REPO_VIEW, PR_VIEW, CHECKS, {"match": ["api graphql"], "stdout": {"errors": [{"message": "boom"}]}}])
        self.assertEqual(self.run_script("12")[0], pr_feedback.EXIT_ERROR)
        self.gh.rules([REPO_VIEW, PR_VIEW, CHECKS,
                       {"match": ["api graphql"], "stdout": {"data": {"repository": {"pullRequest": None}}}}])
        self.assertEqual(self.run_script("12")[0], pr_feedback.EXIT_ERROR)

    def test_pagination_is_bounded(self):
        self.gh.rules([REPO_VIEW, PR_VIEW, CHECKS, {"match": ["api graphql"], "stdout": page([], "again")}])
        code, _, err = self.run_script("12", "--max-pages", "3")
        self.assertEqual(code, pr_feedback.EXIT_ERROR)
        self.assertIn("more than 3 pages", err)
        self.assertEqual(len([c for c in self.gh.calls() if c.startswith("api graphql")]), 3)

    def test_a_checks_error_is_not_read_as_no_checks(self):
        self.gh.rules([REPO_VIEW, PR_VIEW, {"match": ["pr checks"], "rc": 1, "stderr": "HTTP 502: Bad Gateway"}])
        code, _, err = self.run_script("12")
        self.assertEqual(code, pr_feedback.EXIT_ERROR)
        self.assertIn("unreadable output: HTTP 502", err)
        self.gh.rules([REPO_VIEW, PR_VIEW, {"match": ["pr checks"], "rc": 2, "stderr": "unknown flag"}])
        self.assertEqual(self.run_script("12")[0], pr_feedback.EXIT_ERROR)

    def test_unreadable_output(self):
        self.gh.rules([REPO_VIEW, {"match": ["pr view"], "stdout": "<html>"}])
        self.assertEqual(self.run_script("12")[0], pr_feedback.EXIT_ERROR)

    def test_gh_missing_unauthenticated_or_silent(self):
        self.assertEqual(self.run_script("12", env=path_without_gh(Path(self.tmp.name) / "nogh"))[0],
                         pr_feedback.EXIT_GH)
        self.gh.rules([{"match": ["repo view"], "rc": 4, "stderr": "To get started with GitHub CLI, run: gh auth login"}])
        self.assertEqual(self.run_script("12")[0], pr_feedback.EXIT_GH)
        self.gh.rules([dict(REPO_VIEW, sleep=3)])
        code, _, err = self.run_script("12", "--gh-timeout", "0.5")
        self.assertEqual(code, pr_feedback.EXIT_GH)
        self.assertIn("did not answer", err)

    def test_bad_arguments(self):
        self.assertEqual(self.run_script("not-a-number")[0], pr_feedback.EXIT_ERROR)
        self.assertEqual(self.run_script("12", "--repo", "no slash; rm -rf /")[0], pr_feedback.EXIT_ERROR)
        self.assertEqual(self.gh.calls(), [])


class ClassifyTest(unittest.TestCase):
    CHANGED = {"a.py"}

    def klass(self, body, path="a.py", outdated=False):
        return pr_feedback.classify_thread(thread("t", path, body, outdated=outdated), self.CHANGED)[0]

    def test_rules_in_order(self):
        self.assertEqual(self.klass("Why not?", path=None), "out-of-scope")  # no file beats everything
        self.assertEqual(self.klass("Why not?", outdated=True), "question")
        self.assertEqual(self.klass("Why not split it? Fine as a follow-up."), "out-of-scope")
        self.assertEqual(self.klass("Is there a reason for the retry?"), "question")
        self.assertEqual(self.klass("nit: trailing space"), "fix")
        self.assertEqual(self.klass("Can you rename this?"), "fix")  # a request phrased as a question
        self.assertEqual(self.klass(""), "question")  # nothing readable: ask, never guess a change
        self.assertEqual(self.klass("Please extract this into a helper."), "fix")
        self.assertEqual(self.klass("This should use the shared client."), "fix")
        self.assertEqual(self.klass("Hmm, interesting approach."), "question")
        self.assertEqual(self.klass("LGTM overall, small concern on naming here"), "question")
        self.assertEqual(self.klass("🤔"), "question")

    def test_quoted_lines_are_not_the_reviewers_words(self):
        self.assertEqual(self.klass("> why is this here?\nPlease move it to utils."), "fix")
        self.assertEqual(self.klass("> please fix later\nWhat is the expected range?"), "question")


if __name__ == "__main__":
    unittest.main()
