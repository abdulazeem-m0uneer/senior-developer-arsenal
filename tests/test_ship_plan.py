"""Unit tests for the ship skill's plan script."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "ship" / "scripts" / "ship_plan.py"
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ship_plan  # noqa: E402
from fake_gh import FakeGh, path_without_gh  # noqa: E402

IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
NO_PR = {"match": ["pr view"], "rc": 1, "stderr": 'no pull requests found for branch "feature"\n'}


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env={**os.environ, **IDENTITY})


class ShipPlanCase(unittest.TestCase):
    """A clone of a bare `origin` with main pushed, on branch `feature` with one commit ahead."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.origin, self.repo = base / "origin.git", base / "repo"
        git(base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(base, "clone", "-q", str(self.origin), str(self.repo))
        git(self.repo, "checkout", "-q", "-b", "main")
        self.write("README.md", "x")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "init")
        git(self.repo, "push", "-q", "-u", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        git(self.repo, "checkout", "-q", "-b", "feature")
        self.write("app.py", "x = 1\n")
        git(self.repo, "add", "app.py")
        git(self.repo, "commit", "-qm", "feat: app")
        self.gh = FakeGh(base / "bin")
        self.gh.rules([NO_PR])

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def run_plan(self, *args, env=None):
        result = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo), *args], capture_output=True,
                                text=True, env=env or self.gh.env())
        return result.returncode, result.stdout, result.stderr


class PlanTest(ShipPlanCase):
    def test_a_feature_branch_gets_the_full_ordered_plan(self):
        self.write("dirty.py", "y = 2\n")
        code, out, _ = self.run_plan()
        self.assertEqual(code, ship_plan.EXIT_OK)
        steps = [line.strip() for line in out.splitlines()[1:]]
        self.assertTrue(steps[0].startswith("1. verify"))
        self.assertIn("git add -- dirty.py", out)
        self.assertIn("git push -u origin feature", out)
        self.assertIn("gh pr create --base main --head feature", out)
        self.assertIn("ci_wait.py", out)
        self.assertIn("at most 3 rounds", out)
        self.assertIn("merge only on the user's explicit approval", out)
        self.assertNotIn("git add -A", out)

    def test_an_open_pull_request_is_updated_not_reopened(self):
        self.gh.rules([{"match": ["pr view"], "stdout": {"number": 7, "url": "https://x/pull/7", "state": "OPEN",
                                                         "isDraft": False, "baseRefName": "main"}}])
        code, out, _ = self.run_plan()
        self.assertEqual(code, ship_plan.EXIT_OK)
        self.assertIn("pull request #7 is open", out)
        self.assertNotIn("gh pr create", out)

    def test_a_merged_pull_request_does_not_count_as_open(self):
        self.gh.rules([{"match": ["pr view"], "stdout": {"number": 7, "state": "MERGED"}}])
        self.assertIn("gh pr create", self.run_plan()[1])

    def test_an_existing_upstream_is_pushed_plainly(self):
        git(self.repo, "push", "-q", "-u", "origin", "feature")
        self.write("more.py", "z = 3\n")
        self.assertIn("push: git push (origin/feature)", self.run_plan()[1])

    def test_json_output_carries_state_plan_and_exit(self):
        code, out, _ = self.run_plan("--json")
        data = json.loads(out)
        self.assertEqual((code, data["exit"], data["branch"], data["base"], data["commits_ahead"]),
                         (0, 0, "feature", "main", 1))
        self.assertEqual(len(data["plan"]), 6)

    def test_base_can_be_given_explicitly(self):
        git(self.repo, "remote", "set-head", "origin", "--delete")
        self.assertIn("--base main", self.run_plan("--base", "main")[1])


class RefusalTest(ShipPlanCase):
    def assert_refused(self, phrase, *args):
        code, out, _ = self.run_plan(*args)
        self.assertEqual(code, ship_plan.EXIT_UNSAFE, out)
        self.assertIn(phrase, out)
        self.assertEqual(self.gh.calls(), [])  # nothing is asked of gh in an unsafe state

    def test_the_default_branch(self):
        git(self.repo, "checkout", "-q", "main")
        self.write("x.py", "x")
        self.assert_refused("on the default branch 'main'")

    def test_detached_head(self):
        git(self.repo, "checkout", "-q", "--detach")
        self.assert_refused("detached HEAD")

    def test_no_remote(self):
        git(self.repo, "remote", "remove", "origin")
        self.assert_refused("no remote")

    def test_unknown_default_branch(self):
        git(self.repo, "remote", "set-head", "origin", "--delete")
        git(self.repo, "update-ref", "-d", "refs/remotes/origin/main")  # no origin/HEAD, main or master
        self.assert_refused("default branch unknown")

    def test_secret_looking_files_untracked_or_committed(self):
        self.write(".env", "TOKEN=x")
        self.assert_refused(".env")
        (self.repo / ".env").unlink()
        self.write("config/prod.pem", "key")
        git(self.repo, "add", "config/prod.pem")
        git(self.repo, "commit", "-qm", "oops")
        self.assert_refused("config/prod.pem")

    def test_example_env_files_and_public_keys_are_fine(self):
        self.write(".env.example", "TOKEN=")
        self.write("deploy/id_rsa.pub", "ssh-rsa AAA")
        self.assertEqual(self.run_plan()[0], ship_plan.EXIT_OK)

    def test_a_merge_conflict(self):
        git(self.repo, "checkout", "-q", "main")
        self.write("app.py", "x = 2\n")
        git(self.repo, "add", "app.py")
        git(self.repo, "commit", "-qm", "main side")
        git(self.repo, "checkout", "-q", "feature")
        subprocess.run(["git", "merge", "-q", "main"], cwd=self.repo, capture_output=True,
                       env={**os.environ, **IDENTITY})
        code, out, _ = self.run_plan()
        self.assertEqual(code, ship_plan.EXIT_UNSAFE)
        self.assertIn("unresolved merge conflicts: app.py", out)
        self.assertIn("a merge is in progress", out)

    def test_every_refusal_is_listed_at_once(self):
        git(self.repo, "checkout", "-q", "--detach")
        git(self.repo, "remote", "remove", "origin")
        out = self.run_plan()[1]
        self.assertIn("detached HEAD", out)
        self.assertIn("no remote", out)


class OutcomeTest(ShipPlanCase):
    def test_nothing_to_ship(self):
        git(self.repo, "push", "-q", "origin", "feature:main")
        git(self.repo, "fetch", "-q")
        code, out, _ = self.run_plan()
        self.assertEqual(code, ship_plan.EXIT_NOTHING)
        self.assertIn("nothing to ship", out)

    def test_gh_missing(self):
        env = path_without_gh(Path(self.tmp.name) / "nogh")
        code, _, err = self.run_plan(env=env)
        self.assertEqual(code, ship_plan.EXIT_GH)
        self.assertIn("gh is not installed", err)

    def test_gh_not_authenticated(self):
        self.gh.rules([{"match": ["pr view"], "rc": 4, "stderr": "To get started with GitHub CLI, run: gh auth login\n"}])
        code, _, err = self.run_plan()
        self.assertEqual(code, ship_plan.EXIT_GH)
        self.assertIn("not authenticated", err)

    def test_gh_timeout(self):
        self.gh.rules([dict(NO_PR, sleep=3)])
        code, _, err = self.run_plan("--gh-timeout", "0.5")
        self.assertEqual(code, ship_plan.EXIT_GH)
        self.assertIn("did not answer", err)

    def test_gh_garbage_output(self):
        self.gh.rules([{"match": ["pr view"], "stdout": "not json"}])
        self.assertEqual(self.run_plan()[0], ship_plan.EXIT_GH)

    def test_not_a_repository_and_bad_arguments(self):
        with tempfile.TemporaryDirectory() as plain:
            result = subprocess.run([sys.executable, str(SCRIPT), "--repo", plain], capture_output=True, text=True)
            self.assertEqual(result.returncode, ship_plan.EXIT_USAGE)
        self.assertEqual(self.run_plan("--bogus")[0], ship_plan.EXIT_USAGE)


class HelperTest(unittest.TestCase):
    def test_is_secret(self):
        for path in (".env", "a/.env.production", "k.pem", "id_rsa", "x/credentials.json", "terraform.tfstate",
                     "secrets.yaml", ".npmrc", "release.jks"):
            self.assertTrue(ship_plan.is_secret(path), path)
        for path in (".env.example", "id_rsa.pub", "app.py", "README.md", "keys.py", "environment.ts"):
            self.assertFalse(ship_plan.is_secret(path), path)

    def test_dirty_paths_reads_renames_and_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo, "init", "-q")
            (repo / "old name.py").write_text("x")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "i")
            git(repo, "mv", "old name.py", "new name.py")
            (repo / "fresh.py").write_text("y")
            self.assertEqual(sorted(ship_plan.dirty_paths(repo)), ["fresh.py", "new name.py"])


if __name__ == "__main__":
    unittest.main()
