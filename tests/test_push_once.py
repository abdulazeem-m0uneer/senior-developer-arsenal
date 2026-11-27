"""Tests for quality-gate's push_once.py (one CI run per branch) and the pre-push hook template."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents" / "skills" / "quality-gate" / "scripts"
SCRIPT = SCRIPTS / "push_once.py"
TEMPLATE = ROOT / ".agents" / "skills" / "quality-gate" / "templates" / "pre-push"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_gh import FakeGh, path_without_gh  # noqa: E402

IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@example.com")
ZEROS = "0" * 40
REPO_URL = "git@github.com:owner/repo.git"
OPT_OUTS = ("ARSENAL_PUSH_REBASE", "ARSENAL_ALLOW_PUSH")
FRESH_ENV = ("ARSENAL_PUSH_BASE", "ARSENAL_ALLOW_STALE_BASE", "ARSENAL_ALLOW_UNRUN_RED", "ARSENAL_TEST_LOG")


def git(cwd, *args):
    return subprocess.run(["git", *IDENTITY, *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def runs(status, sha="a" * 40, run_id=42):
    return {"match": ["run list"], "stdout": [{"databaseId": run_id, "status": status, "headSha": sha}]}


FAKE_SSH = """#!/usr/bin/env python3
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
aliases = json.load(open(os.path.join(here, "ssh-aliases.json")))
with open(os.path.join(here, "ssh-calls.log"), "a") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:2] != ["-G"] or len(sys.argv) != 3:
    sys.exit(255)
print("user git")
print("hostname " + aliases.get(sys.argv[2], sys.argv[2]))
"""


def fake_ssh(bin_dir, aliases):
    """An `ssh` on PATH that answers `ssh -G <host>` from {alias: hostname}, as ~/.ssh/config would."""
    (bin_dir / "ssh-aliases.json").write_text(json.dumps(aliases))
    script = bin_dir / "ssh"
    script.write_text(FAKE_SSH)
    script.chmod(0o755)


class PushOnceCase(unittest.TestCase):
    """origin (bare) with main and feature pushed; feature has two commits on top of main."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.origin, self.repo = base / "origin.git", base / "repo"
        self.red_runs = base / "red-runs.json"  # never the real ~/.cache state
        git(base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(base, "clone", "-q", str(self.origin), str(self.repo))
        git(self.repo, "checkout", "-q", "-b", "main")
        self.commit("README.md", "x\n", "init")
        git(self.repo, "push", "-q", "-u", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        git(self.repo, "checkout", "-q", "-b", "feature")
        self.commit("app.py", "a = 1\n", "feat: a")
        self.commit("lib.py", "b = 1\n", "feat: b")
        git(self.repo, "push", "-q", "-u", "origin", "feature")
        self.pushed = git(self.repo, "rev-parse", "HEAD")
        self.gh = FakeGh(base / "bin")
        self.gh.rules([runs("in_progress", self.pushed)])
        fake_ssh(base / "bin", {"github-work": "github.com"})

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, name, text, message, amend=False):
        (self.repo / name).write_text(text)
        git(self.repo, "add", name)
        git(self.repo, "commit", "-q", *(["--amend"] if amend else []), "-m", message)
        return git(self.repo, "rev-parse", "HEAD")

    def env(self, **extra):
        env = {key: value for key, value in self.gh.env().items() if key not in OPT_OUTS + FRESH_ENV}
        return {**env, "ARSENAL_RED_RUNS": str(self.red_runs), **extra}

    def hook(self, local, remote=None, env=None, *args, url=REPO_URL, ref="refs/heads/feature"):
        line = f"{ref} {local} {ref} {remote or self.pushed}\n"
        result = subprocess.run([sys.executable, str(SCRIPT), "hook", "origin", url, *args], input=line,
                                cwd=self.repo, capture_output=True, text=True, env=env or self.env())
        return result.returncode, result.stdout + result.stderr

    def optouts(self):
        log = self.repo / ".agents" / "ci-optouts.log"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def rebase_onto_new_main(self):
        git(self.repo, "checkout", "-q", "main")
        self.commit("main.txt", "m\n", "main moves")
        git(self.repo, "push", "-q", str(self.origin), "main")  # by path: CliTests point origin's push URL at GitHub
        git(self.repo, "fetch", "-q", "origin")
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "rebase", "-q", "main")
        return git(self.repo, "rev-parse", "HEAD")


class RunningRunTests(PushOnceCase):
    def test_pure_rebase_while_ci_runs_passes(self):
        code, out = self.hook(self.rebase_onto_new_main())
        self.assertEqual(code, 0, out)
        self.assertIn("rebase", out)
        self.assertEqual(self.gh.calls(), ["run list --repo github.com/owner/repo --branch feature --json "
                                           "databaseId,status,headSha,event -L 10"])

    def test_amend_with_changed_content_while_ci_runs_is_refused(self):
        amended = self.commit("lib.py", "b = 2\n", "feat: b", amend=True)
        code, out = self.hook(amended)
        self.assertEqual(code, 1)
        self.assertIn(f"run 42 on {self.pushed} is still running", out)
        self.assertIn("gh run cancel 42", out)

    def test_amend_after_run_finished_passes(self):
        self.gh.rules([runs("completed", self.pushed)])
        amended = self.commit("lib.py", "b = 2\n", "feat: b", amend=True)
        code, out = self.hook(amended)
        self.assertEqual(code, 0, out)

    def test_fast_forward_while_ci_runs_is_refused(self):
        local = self.commit("c.py", "c\n", "feat: c")
        for status in ("in_progress", "queued", "waiting", "requested", "pending"):
            with self.subTest(status=status):
                self.gh.rules([runs(status, self.pushed, run_id=7)])
                code, out = self.hook(local)
                self.assertEqual(code, 1, out)
                self.assertIn(f"run 7 on {self.pushed} is still running; wait for it, or cancel it on purpose "
                              "with gh run cancel 7", out)
                self.assertNotIn("not a pure rebase", out)

    def test_new_branch_passes_while_ci_runs(self):
        code, out = self.hook(self.commit("c.py", "c\n", "feat: c"), remote=ZEROS)
        self.assertEqual(code, 0, out)

    def test_branch_deletion_passes_without_asking_gh(self):
        code, out = self.hook(ZEROS)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.gh.calls(), [])

    def test_rebase_that_drops_a_commit_is_refused(self):
        git(self.repo, "reset", "-q", "--hard", "HEAD~1")
        code, out = self.hook(self.rebase_onto_new_main())
        self.assertEqual(code, 1, out)

    def test_rebase_dropping_a_commit_the_base_already_has_passes(self):
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "cherry-pick", "feature")  # feat: b lands on main as a hotfix
        self.commit("z.txt", "z\n", "main: z")
        git(self.repo, "push", "-q", str(self.origin), "main")
        git(self.repo, "fetch", "-q", "origin")
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "rebase", "-q", "main")  # drops feat: b, now redundant
        self.assertEqual(git(self.repo, "rev-list", "--count", "main..feature"), "1")
        code, out = self.hook(git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(code, 0, out)
        self.assertIn("pure rebase", out)

    def test_rebase_dropping_one_of_two_identical_commits_is_refused(self):
        self.commit("f.txt", "x\n", "add f")
        git(self.repo, "rm", "-q", "f.txt")
        git(self.repo, "commit", "-qm", "drop f")
        self.commit("f.txt", "x\n", "add f again")  # same patch as "add f"
        git(self.repo, "push", "-q", "origin", "feature")
        self.pushed = git(self.repo, "rev-parse", "HEAD")
        self.gh.rules([runs("in_progress", self.pushed)])  # the run CI starts on the new remote head
        git(self.repo, "reset", "-q", "--hard", "HEAD~1")
        code, out = self.hook(self.rebase_onto_new_main())
        self.assertEqual(code, 1, out)
        self.assertIn("not a pure rebase", out)

    def test_refusal_names_the_newest_running_run(self):
        self.gh.rules([{"match": ["run list"], "stdout": [
            {"databaseId": 9, "status": "queued", "headSha": self.pushed, "event": "push"},
            {"databaseId": 8, "status": "in_progress", "headSha": self.pushed, "event": "push"}]}])
        code, out = self.hook(self.commit("c.py", "c\n", "feat: c"))
        self.assertEqual(code, 1, out)
        self.assertIn(f"run 9 on {self.pushed} is still running", out)

    def test_run_on_another_sha_of_the_same_branch_name_does_not_block(self):
        # gh --branch filters on the head branch name, so a fork's pull request run on "feature" is listed too
        self.gh.rules([runs("in_progress", "c" * 40, run_id=9)])
        amended = self.commit("lib.py", "b = 2\n", "feat: b", amend=True)
        git(self.repo, "reset", "-q", "--hard", self.pushed)
        fast_forward = self.commit("c.py", "c\n", "feat: c")
        for local in (fast_forward, amended):
            code, out = self.hook(local)
            self.assertEqual(code, 0, out)
            self.assertIn("no CI run going", out)
        self.gh.rules([{"match": ["run list"], "stdout": [
            {"databaseId": 9, "status": "in_progress", "headSha": "c" * 40, "event": "pull_request"},
            {"databaseId": 8, "status": "in_progress", "headSha": self.pushed, "event": "push"}]}])
        code, out = self.hook(amended)
        self.assertEqual(code, 1, out)
        self.assertIn(f"run 8 on {self.pushed} is still running", out)

    def test_rebase_onto_a_base_change_next_to_the_branch_change_passes(self):
        # the 3 lines of diff context change with the base, the change itself does not
        git(self.repo, "checkout", "-q", "main")
        self.commit("shared.txt", "".join(f"line{n}\n" for n in range(1, 8)), "main: shared")
        git(self.repo, "push", "-q", str(self.origin), "main")
        git(self.repo, "fetch", "-q", "origin")
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "rebase", "-q", "main")
        self.commit("shared.txt", "line1\nline2\nline3\nbranch4\nline5\nline6\nline7\n", "feat: line 4")
        git(self.repo, "push", "-q", "-f", "origin", "feature")
        self.pushed = git(self.repo, "rev-parse", "HEAD")
        self.gh.rules([runs("in_progress", self.pushed)])
        git(self.repo, "checkout", "-q", "main")
        self.commit("shared.txt", "line1\nmain2\nline3\nline4\nline5\nline6\nline7\n", "main: line 2")
        git(self.repo, "push", "-q", str(self.origin), "main")
        git(self.repo, "fetch", "-q", "origin")
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "rebase", "-q", "main")
        self.assertEqual((self.repo / "shared.txt").read_text(),
                         "line1\nmain2\nline3\nbranch4\nline5\nline6\nline7\n")
        code, out = self.hook(git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(code, 0, out)
        self.assertIn("pure rebase", out)
        amended = self.commit("shared.txt", "line1\nmain2\nline3\nbranch4b\nline5\nline6\nline7\n", "feat: line 4",
                              amend=True)
        code, out = self.hook(amended)
        self.assertEqual(code, 1, out)
        self.assertIn("not a pure rebase", out)

    def test_only_runs_a_push_starts_count(self):
        local = self.commit("c.py", "c\n", "feat: c")
        for event, wanted in (("schedule", 0), ("workflow_dispatch", 0), ("push", 1), ("pull_request", 1)):
            with self.subTest(event=event):
                self.gh.rules([{"match": ["run list"], "stdout": [
                    {"databaseId": 5, "status": "waiting", "headSha": self.pushed, "event": event}]}])
                code, out = self.hook(local)
                self.assertEqual(code, wanted, out)

    def test_base_falls_back_to_main_without_remote_head(self):
        git(self.repo, "remote", "set-head", "origin", "--delete")
        code, out = self.hook(self.rebase_onto_new_main())
        self.assertEqual(code, 0, out)

    def test_explicit_base_is_used(self):
        git(self.repo, "branch", "old-main", "main")
        rebased = self.rebase_onto_new_main()
        code, out = self.hook(rebased, None, None, "--base", "old-main")  # main's new commit counts as content
        self.assertEqual(code, 1, out)
        code, out = self.hook(rebased, None, None, "--base", "origin/main")
        self.assertEqual(code, 0, out)

    def test_unknown_old_head_is_refused_with_fetch_hint(self):
        self.gh.rules([runs("in_progress", "b" * 40)])
        code, out = self.hook(self.commit("c.py", "c\n", "feat: c"), remote="b" * 40)
        self.assertEqual(code, 1)
        self.assertIn("git fetch", out)

    def test_no_running_run_passes(self):
        self.gh.rules([{"match": ["run list"], "stdout": []}])
        amended = self.commit("lib.py", "b = 2\n", "feat: b", amend=True)
        self.assertEqual(self.hook(amended)[0], 0)

    def test_reset_of_the_base_branch_itself_is_refused(self):
        git(self.repo, "checkout", "-q", "main")
        old = self.commit("m2.txt", "m\n", "main: two")
        git(self.repo, "push", "-q", "origin", "main")
        git(self.repo, "reset", "-q", "--hard", "HEAD~1")
        self.gh.rules([runs("in_progress", old)])
        code, out = self.hook(git(self.repo, "rev-parse", "HEAD"), old, ref="refs/heads/main")
        self.assertEqual(code, 1, out)
        self.assertIn("drops commits", out)

    def merge_side_branch(self):
        git(self.repo, "checkout", "-q", "-b", "side", "main")
        self.commit("side.py", "s\n", "side: s")
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "merge", "-q", "--no-ff", "side", "-m", "merge side")
        git(self.repo, "push", "-q", "origin", "feature")
        self.pushed = git(self.repo, "rev-parse", "HEAD")
        self.gh.rules([runs("in_progress", self.pushed)])  # the run CI starts on the new remote head

    def test_merge_with_changed_content_while_ci_runs_is_refused(self):
        self.merge_side_branch()
        (self.repo / "extra.py").write_text("e\n")
        git(self.repo, "add", "extra.py")
        git(self.repo, "commit", "-q", "--amend", "--no-edit")
        code, out = self.hook(git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(code, 1, out)
        self.assertIn("not a pure rebase", out)

    def test_clean_merge_flattened_by_a_rebase_passes(self):
        self.merge_side_branch()
        code, out = self.hook(self.rebase_onto_new_main())
        self.assertEqual(code, 0, out)
        self.assertIn("pure rebase", out)

    def test_base_is_the_remote_default_branch(self):
        git(self.repo, "checkout", "-q", "-b", "release", "main")
        self.commit("release.txt", "r\n", "release: r")
        git(self.repo, "push", "-q", "origin", "release")
        git(self.repo, "remote", "set-head", "origin", "release")
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "rebase", "-q", "release")
        code, out = self.hook(git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(code, 0, out)
        self.assertIn("onto refs/remotes/origin/release", out)

    def test_base_falls_back_to_local_main_without_remote_refs(self):
        git(self.repo, "remote", "set-head", "origin", "--delete")
        git(self.repo, "update-ref", "-d", "refs/remotes/origin/main")
        git(self.repo, "checkout", "-q", "main")
        self.commit("main.txt", "m\n", "main moves")
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "rebase", "-q", "main")
        code, out = self.hook(git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(code, 0, out)
        self.assertIn("onto refs/heads/main", out)

    def test_tag_push_passes_without_asking_gh(self):
        code, out = self.hook(self.pushed, ZEROS, ref="refs/tags/v1")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.gh.calls(), [])


class RepositoryTests(PushOnceCase):
    def test_gh_is_asked_about_the_pushed_remote_repository(self):
        local = self.commit("c.py", "c\n", "feat: c")
        for url, repo in (("git@github.com:owner/repo.git", "github.com/owner/repo"),
                          ("https://github.com/owner/repo", "github.com/owner/repo"),
                          ("https://user@github.com/owner/repo.git/", "github.com/owner/repo"),
                          ("ssh://git@ghe.example.com:2222/team/app.git", "ghe.example.com/team/app"),
                          ("git@github-work:owner/repo.git", "github.com/owner/repo"),
                          ("ssh://git@github-work/owner/repo.git", "github.com/owner/repo"),
                          ("ssh://git@ssh.github.com:443/owner/repo.git", "github.com/owner/repo"),
                          ("https://github-work/owner/repo", "github-work/owner/repo")):
            with self.subTest(url=url):
                code, out = self.hook(local, url=url)
                self.assertEqual(code, 1, out)
                self.assertIn(f"run list --repo {repo} --branch feature ", self.gh.calls()[-1])

    def test_host_is_kept_when_ssh_cannot_resolve_it(self):
        (Path(self.tmp.name).resolve() / "bin" / "ssh").write_text("#!/bin/sh\nexit 255\n")
        code, out = self.hook(self.commit("c.py", "c\n", "feat: c"), url="git@github-work:owner/repo.git")
        self.assertEqual(code, 1, out)
        self.assertIn("--repo github-work/owner/repo ", self.gh.calls()[-1])

    def test_host_that_looks_like_an_option_is_not_given_to_ssh(self):
        code, out = self.hook(self.commit("c.py", "c\n", "feat: c"), url="git@-oProxyCommand=x:owner/repo.git")
        self.assertEqual(code, 1, out)
        self.assertIn("--repo -oProxyCommand=x/owner/repo ", self.gh.calls()[-1])
        self.assertFalse((Path(self.tmp.name).resolve() / "bin" / "ssh-calls.log").exists())

    def test_remote_that_is_not_a_hosted_repository_passes_without_asking_gh(self):
        local = self.commit("c.py", "c\n", "feat: c")
        for url in (str(self.origin), "file:///srv/r.git", "C:/backup/r.git", "https://example.com/a/b/c.git"):
            with self.subTest(url=url):
                code, out = self.hook(local, url=url)
                self.assertEqual(code, 0, out)
                self.assertIn("not a GitHub repository", out)
        self.assertEqual(self.gh.calls(), [])


class OptOutTests(PushOnceCase):
    def test_each_opt_out_passes_and_logs_one_json_line(self):
        amended = self.commit("lib.py", "b = 2\n", "feat: b", amend=True)
        for flag in OPT_OUTS:
            with self.subTest(flag=flag):
                code, out = self.hook(amended, env=self.env(**{flag: "1"}))
                self.assertEqual(code, 0, out)
                entry = self.optouts()[-1]
                self.assertEqual((entry["flag"], entry["branch"], entry["local_sha"]), (flag, "feature", amended))
                self.assertIn("run 42", entry["reason"])
                self.assertTrue(entry["time"])
        self.assertEqual(len(self.optouts()), 2)

    def test_opt_out_passes_when_the_check_itself_fails(self):
        amended = self.commit("lib.py", "b = 2\n", "feat: b", amend=True)
        code, out = self.hook(amended, env=self.env(PUSH_ONCE_GH_TIMEOUT="x"))
        self.assertEqual(code, 2, out)
        code, out = self.hook(amended, env=self.env(PUSH_ONCE_GH_TIMEOUT="x", ARSENAL_ALLOW_PUSH="1"))
        self.assertEqual(code, 0, out)
        self.assertIn("not a number of seconds", self.optouts()[-1]["reason"])

    def test_opt_out_set_to_zero_is_not_an_opt_out(self):
        amended = self.commit("lib.py", "b = 2\n", "feat: b", amend=True)
        code, _ = self.hook(amended, env=self.env(ARSENAL_ALLOW_PUSH="0"))
        self.assertEqual(code, 1)
        self.assertEqual(self.optouts(), [])


class GhDownTests(PushOnceCase):
    def setUp(self):
        super().setUp()
        self.amended = self.commit("lib.py", "b = 2\n", "feat: b", amend=True)

    def test_gh_failure_passes_with_warning(self):
        self.gh.rules([{"match": ["run list"], "rc": 1, "stderr": "HTTP 502"}])
        code, out = self.hook(self.amended)
        self.assertEqual(code, 0, out)
        self.assertIn("warning", out)
        self.assertIn("HTTP 502", out)

    def test_gh_missing_passes_with_warning(self):
        env = path_without_gh(Path(self.tmp.name) / "nogh")
        code, out = self.hook(self.amended, env={k: v for k, v in env.items() if k not in OPT_OUTS})
        self.assertEqual(code, 0, out)
        self.assertIn("warning", out)

    def test_gh_timeout_passes_with_warning(self):
        self.gh.rules([{**runs("in_progress", self.pushed), "sleep": 3}])
        code, out = self.hook(self.amended, env=self.env(PUSH_ONCE_GH_TIMEOUT="0.5"))
        self.assertEqual(code, 0, out)
        self.assertIn("did not answer within 0.5", out)

    def test_gh_garbage_passes_with_warning(self):
        self.gh.rules([{"match": ["run list"], "stdout": "<html>"}])
        code, out = self.hook(self.amended)
        self.assertEqual(code, 0, out)
        self.assertIn("warning", out)


class CliTests(PushOnceCase):
    def setUp(self):
        super().setUp()
        git(self.repo, "config", "remote.origin.pushurl", REPO_URL)

    def run_cli(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), "check", *args], cwd=self.repo, capture_output=True,
                                text=True, env=self.env())
        return result.returncode, result.stdout + result.stderr

    def test_cli_refuses_fast_forward_of_current_branch(self):
        self.commit("c.py", "c\n", "feat: c")
        code, out = self.run_cli()
        self.assertEqual(code, 1, out)
        self.assertIn("run 42", out)
        self.assertIn("--repo github.com/owner/repo", self.gh.calls()[-1])

    def test_cli_passes_pure_rebase_of_named_branch(self):
        self.rebase_onto_new_main()
        git(self.repo, "checkout", "-q", "main")
        code, out = self.run_cli("--branch", "feature")
        self.assertEqual(code, 0, out)

    def test_cli_branch_without_remote_is_new(self):
        git(self.repo, "checkout", "-q", "-b", "fresh")
        code, out = self.run_cli()
        self.assertEqual(code, 0, out)

    def test_malformed_hook_input_is_usage_error(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "hook", "origin", "x"], input="garbage\n",
                                cwd=self.repo, capture_output=True, text=True, env=self.env())
        self.assertEqual(result.returncode, 2)


class FreshBaseTests(PushOnceCase):
    """--fresh-base BASE: refuse a push whose head does not contain the base tip, fetched just now."""

    def setUp(self):
        super().setUp()
        self.gh.rules([runs("completed", self.pushed)])
        self.base = Path(self.tmp.name)
        git(self.repo, "checkout", "-q", "-b", "development", "main")
        git(self.repo, "push", "-q", "origin", "development")
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "rebase", "-q", "development")
        git(self.repo, "push", "-q", "-f", "origin", "feature")
        self.pushed = git(self.repo, "rev-parse", "HEAD")
        self.other = self.base / "other"
        git(self.base, "clone", "-q", str(self.origin), str(self.other))
        git(self.other, "checkout", "-q", "development")

    def move_base(self):
        """Another clone pushes to development; this clone's origin/development is not updated."""
        (self.other / "moved.txt").write_text("m\n")
        git(self.other, "add", "moved.txt")
        git(self.other, "commit", "-q", "-m", "dev moves")
        git(self.other, "push", "-q", "origin", "development")
        return git(self.other, "rev-parse", "HEAD")

    def push_new_commit(self):
        return self.commit("c.py", "c\n", "feat: c")

    def test_refuses_when_the_fetched_base_tip_is_not_in_the_head(self):
        tip = self.move_base()
        code, out = self.hook(self.push_new_commit(), None, None, "--fresh-base", "origin/development")
        self.assertEqual(code, 1, out)
        self.assertIn(tip, out)
        self.assertIn("rebase onto it, rerun the checks that depend on the base", out)

    def test_passes_once_rebased_onto_the_fetched_base(self):
        self.move_base()
        git(self.repo, "fetch", "-q", "origin")
        git(self.repo, "rebase", "-q", "origin/development")
        code, out = self.hook(git(self.repo, "rev-parse", "HEAD"), None, None, "--fresh-base", "origin/development")
        self.assertEqual(code, 0, out)

    def test_passes_when_the_base_has_not_moved(self):
        code, out = self.hook(self.push_new_commit(), None, None, "--fresh-base", "origin/development")
        self.assertEqual(code, 0, out)

    def test_env_names_the_base(self):
        self.move_base()
        code, out = self.hook(self.push_new_commit(), None, self.env(ARSENAL_PUSH_BASE="origin/development"))
        self.assertEqual(code, 1, out)

    def test_option_beats_env(self):
        self.move_base()
        code, out = self.hook(self.push_new_commit(), None, self.env(ARSENAL_PUSH_BASE="origin/development"),
                              "--fresh-base", "origin/main")
        self.assertEqual(code, 0, out)

    def test_base_without_remote_prefix(self):
        self.move_base()
        code, out = self.hook(self.push_new_commit(), None, None, "--fresh-base", "development")
        self.assertEqual(code, 1, out)

    def test_no_option_no_fetch_and_passes(self):
        self.move_base()
        code, out = self.hook(self.push_new_commit())
        self.assertEqual(code, 0, out)

    def test_new_branch_is_checked_too(self):
        self.move_base()
        code, out = self.hook(self.push_new_commit(), ZEROS, None, "--fresh-base", "origin/development")
        self.assertEqual(code, 1, out)

    def test_opt_out_passes_and_logs(self):
        tip = self.move_base()
        code, out = self.hook(self.push_new_commit(), None, self.env(ARSENAL_ALLOW_STALE_BASE="1"),
                              "--fresh-base", "origin/development")
        self.assertEqual(code, 0, out)
        self.assertIn("ARSENAL_ALLOW_STALE_BASE=1", out)
        entry = self.optouts()[-1]
        self.assertEqual(entry["flag"], "ARSENAL_ALLOW_STALE_BASE")
        self.assertIn(tip, entry["reason"])

    def test_pushing_the_base_branch_itself_passes(self):
        self.move_base()
        git(self.repo, "checkout", "-q", "development")
        local = self.commit("d.txt", "d\n", "dev: d")
        code, out = self.hook(local, git(self.repo, "rev-parse", "origin/development"), None,
                              "--fresh-base", "origin/development", ref="refs/heads/development")
        self.assertEqual(code, 0, out)

    def test_deletion_passes(self):
        self.move_base()
        code, out = self.hook(ZEROS, None, None, "--fresh-base", "origin/development")
        self.assertEqual(code, 0, out)

    def test_deletion_alone_does_not_fetch(self):
        self.move_base()
        git(self.repo, "remote", "set-url", "origin", str(self.base / "missing.git"))
        code, out = self.hook(ZEROS, None, None, "--fresh-base", "origin/development")
        self.assertEqual(code, 0, out)
        self.assertNotIn("warning", out)

    def test_fetches_from_the_pushed_remote(self):
        self.move_base()
        git(self.repo, "remote", "add", "up", str(self.origin))
        git(self.repo, "remote", "set-url", "origin", str(self.base / "missing.git"))
        local = self.push_new_commit()
        result = subprocess.run([sys.executable, str(SCRIPT), "hook", "up", REPO_URL, "--fresh-base",
                                 "up/development"], input=f"refs/heads/feature {local} refs/heads/feature {self.pushed}\n",
                                cwd=self.repo, capture_output=True, text=True, env=self.env())
        self.assertEqual(result.returncode, 1, result.stderr)

    def test_deletion_next_to_a_stale_push_passes_only_the_deletion(self):
        self.move_base()
        lines = (f"(delete) {ZEROS} refs/heads/old {self.pushed}\n"
                 f"refs/heads/feature {self.push_new_commit()} refs/heads/feature {self.pushed}\n")
        result = subprocess.run([sys.executable, str(SCRIPT), "hook", "origin", REPO_URL, "--fresh-base",
                                 "origin/development"], input=lines, cwd=self.repo, capture_output=True, text=True,
                                env=self.env())
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr.count("refused"), 1, result.stderr)
        self.assertIn("old: deletion", result.stderr)

    def test_fetch_failure_passes_with_warning(self):
        self.move_base()
        git(self.repo, "remote", "set-url", "origin", str(self.base / "missing.git"))
        code, out = self.hook(self.push_new_commit(), None, None, "--fresh-base", "origin/development")
        self.assertEqual(code, 0, out)
        self.assertIn("warning", out)

    def test_fetch_timeout_passes_with_warning(self):
        real = subprocess.run(["which", "git"], capture_output=True, text=True).stdout.strip()
        fake = self.base / "gitbin" / "git"
        fake.parent.mkdir()
        fake.write_text(f'#!/bin/sh\ncase "$1" in fetch) sleep 5;; esac\nexec {real} "$@"\n')
        fake.chmod(0o755)
        env = self.env(PATH=f"{fake.parent}{os.pathsep}{self.env()['PATH']}", PUSH_ONCE_FETCH_TIMEOUT="0.3")
        self.move_base()
        code, out = self.hook(self.push_new_commit(), None, env, "--fresh-base", "origin/development")
        self.assertEqual(code, 0, out)
        self.assertIn("did not finish", out)

    def fake_git(self, fetch_script):
        real = subprocess.run(["which", "git"], capture_output=True, text=True).stdout.strip()
        fake = self.base / "gitbin" / "git"
        fake.parent.mkdir(exist_ok=True)
        fake.write_text(f'#!/bin/sh\ncase "$1" in fetch) {fetch_script};; esac\nexec {real} "$@"\n')
        fake.chmod(0o755)
        return f"{fake.parent}{os.pathsep}{self.env()['PATH']}"

    def test_stale_push_with_another_opt_out_names_the_staleness_and_logs_once(self):
        tip = self.move_base()
        for flag in OPT_OUTS:
            with self.subTest(flag=flag):
                code, out = self.hook(self.commit(f"{flag}.py", "c\n", f"feat: {flag}"), None,
                                      self.env(**{flag: "1"}), "--fresh-base", "origin/development")
                self.assertEqual(code, 0, out)
                self.assertIn(f"moved to {tip}", out)
                self.assertEqual(self.optouts()[-1]["flag"], flag)
                self.assertIn(tip, self.optouts()[-1]["reason"])

    def test_stale_base_opt_out_next_to_another_opt_out_logs_once(self):
        self.move_base()
        before = len(self.optouts())
        code, out = self.hook(self.push_new_commit(), None,
                              self.env(ARSENAL_ALLOW_STALE_BASE="1", ARSENAL_ALLOW_PUSH="1"),
                              "--fresh-base", "origin/development")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.optouts()) - before, 1)

    def test_remote_given_as_a_url_still_fetches_the_base(self):
        self.move_base()
        local = self.push_new_commit()
        result = subprocess.run([sys.executable, str(SCRIPT), "hook", str(self.origin), REPO_URL, "--fresh-base",
                                 "origin/development"], input=f"refs/heads/feature {local} refs/heads/feature {self.pushed}\n",
                                cwd=self.repo, capture_output=True, text=True, env=self.env())
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("warning", result.stderr)

    def test_ancestry_error_is_not_a_stale_refusal(self):
        self.move_base()
        code, out = self.hook("1" * 40, None, None, "--fresh-base", "origin/development")
        self.assertEqual(code, 0, out)
        self.assertNotIn("moved to", out)

    def test_fetch_that_leaves_no_commit_passes_with_warning(self):
        self.move_base()
        env = self.env(PATH=self.fake_git('rm -f "$(git rev-parse --git-dir)/FETCH_HEAD"; exit 0'))
        code, out = self.hook(self.push_new_commit(), None, env, "--fresh-base", "origin/development")
        self.assertEqual(code, 0, out)
        self.assertIn("left no commit", out)

    def test_bad_timeout_values_use_the_default(self):
        self.move_base()
        local = self.push_new_commit()
        for value in ("nan", "0", "-1", "abc"):
            with self.subTest(value=value):
                code, out = self.hook(local, None, self.env(PUSH_ONCE_FETCH_TIMEOUT=value),
                                      "--fresh-base", "origin/development")
                self.assertEqual(code, 1, out)
                self.assertNotIn("warning", out)

    def test_timeout_does_not_wait_for_a_fetch_child_holding_the_pipes(self):
        env = self.env(PATH=self.fake_git("sleep 6 & sleep 6"), PUSH_ONCE_FETCH_TIMEOUT="0.3")
        self.move_base()
        start = time.monotonic()
        code, out = self.hook(self.push_new_commit(), None, env, "--fresh-base", "origin/development")
        self.assertEqual(code, 0, out)
        self.assertIn("did not finish", out)
        self.assertLess(time.monotonic() - start, 4)

    def test_fetch_never_prompts(self):
        seen = self.base / "prompt.txt"
        env = self.env(PATH=self.fake_git(f'echo "$GIT_TERMINAL_PROMPT" > {seen}'))
        self.move_base()
        self.hook(self.push_new_commit(), None, env, "--fresh-base", "origin/development")
        self.assertEqual(seen.read_text().strip(), "0")

    def test_cli_check_takes_the_option(self):
        git(self.repo, "config", "remote.origin.pushurl", REPO_URL)
        self.move_base()
        self.push_new_commit()
        result = subprocess.run([sys.executable, str(SCRIPT), "check", "--fresh-base", "origin/development"],
                                cwd=self.repo, capture_output=True, text=True, env=self.env())
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("rebase onto it", result.stderr)


class HookTemplateTests(PushOnceCase):
    def run_template(self, affected, lines=None, **extra):
        if lines is None:
            local = self.commit("c.py", "c\n", "feat: c")
            lines = f"refs/heads/feature {local} refs/heads/feature {self.pushed}\n"
        report = Path(self.tmp.name) / "lcov.info"
        env = self.env(**{"ARSENAL_QUALITY_GATE": str(SCRIPTS), "AFFECTED_TESTS_CMD": affected,
                          "COVERAGE_REPORT": str(report), "PUSH_BASE": "origin/main", **extra})
        result = subprocess.run(["sh", str(TEMPLATE), "origin", REPO_URL], input=lines, cwd=self.repo,
                                capture_output=True, text=True, env=env)
        return result.returncode, result.stdout + result.stderr, report

    def test_failing_affected_tests_stop_before_the_other_checks(self):
        code, _, _ = self.run_template("exit 3")
        self.assertEqual(code, 3)
        self.assertEqual(self.gh.calls(), [])

    def test_runs_tests_then_coverage_then_push_once(self):
        report = Path(self.tmp.name) / "lcov.info"
        records = "".join(f"SF:{name}\nDA:1,1\nend_of_record\n" for name in ("app.py", "lib.py", "c.py"))
        report.write_text(records)
        code, out, _ = self.run_template("true")
        self.assertEqual(code, 1, out)
        self.assertIn("changed-lines coverage: 3/3", out)
        self.assertIn("run 42", out)

    def test_low_coverage_stops_before_push_once(self):
        (Path(self.tmp.name) / "lcov.info").write_text("SF:c.py\nDA:1,0\nend_of_record\n")
        code, out, _ = self.run_template("true")
        self.assertEqual(code, 1, out)
        self.assertEqual(self.gh.calls(), [])

    def test_push_without_head_skips_tests_and_coverage(self):
        main = git(self.repo, "rev-parse", "main")
        for lines in (f"(delete) {ZEROS} refs/heads/old {self.pushed}\n",
                      f"refs/tags/v1 {self.pushed} refs/tags/v1 {ZEROS}\n",
                      f"refs/heads/main {main} refs/heads/release {ZEROS}\n"):
            with self.subTest(lines=lines):
                code, out, _ = self.run_template("exit 3", lines)
                self.assertEqual(code, 0, out)
                self.assertIn("affected tests and changed-lines coverage skipped", out)
        self.assertEqual(len(self.gh.calls()), 1)  # only the new branch release asks gh

    def test_push_base_is_the_base_of_the_rebase_check(self):
        git(self.repo, "checkout", "-q", "-b", "development", "main")
        self.commit("dev.txt", "d\n", "dev: d")
        git(self.repo, "push", "-q", "origin", "development")
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "rebase", "-q", "development")
        rebased = git(self.repo, "rev-parse", "HEAD")
        (Path(self.tmp.name) / "lcov.info").write_text("SF:none.py\nDA:1,1\nend_of_record\n")
        lines = f"refs/heads/feature {rebased} refs/heads/feature {self.pushed}\n"
        code, out, _ = self.run_template("true", lines, PUSH_BASE="origin/development")
        self.assertEqual(code, 0, out)
        self.assertIn("pure rebase onto origin/development", out)

    def test_opt_out_skips_tests_and_coverage_and_logs(self):
        lines = f"refs/heads/feature {self.commit('c.py', 'c', 'feat: c')} refs/heads/feature {self.pushed}\n"
        for flag in OPT_OUTS:
            with self.subTest(flag=flag):
                code, out, _ = self.run_template("exit 3", lines, **{flag: "1"})
                self.assertEqual(code, 0, out)
                self.assertIn(f"{flag}=1: affected tests and changed-lines coverage skipped", out)
                self.assertEqual(self.optouts()[-1]["flag"], flag)


if __name__ == "__main__":
    unittest.main()
