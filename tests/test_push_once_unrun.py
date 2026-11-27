"""Tests for push_once's unrun-red check (G038): run markers in the local test log, and the pre-push template."""
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_gh import path_without_gh  # noqa: E402
from test_push_once import REPO_URL, SCRIPTS, TEMPLATE, ZEROS, OPT_OUTS, PushOnceCase, git, runs  # noqa: E402

class UnrunRedTests(PushOnceCase):
    """G038: a push after a red CI run needs a newer local test log naming that run's failed test files."""
    FILES = ["tests/test_a.py", "tests/test_b.py"]

    def setUp(self):
        super().setUp()
        self.gh.rules([runs("completed", self.pushed)])
        self.log = self.repo / ".agents" / "test-run.log"
        self.local = self.commit("c.py", "c\n", "feat: c")

    def record(self, files=None, head=None, at=None, repo="owner/repo"):
        entry = {"run": 77, "head_sha": head or self.pushed, "time": at or time.time() - 100,
                 "files": self.FILES if files is None else files}
        self.red_runs.write_text(json.dumps({repo: entry}))

    def write_log(self, text, age=0):
        """A log whose one run starts with a marker `age` seconds ago, followed by `text`."""
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text(f"{self.marker(age)}\n{text}")

    @staticmethod
    def marker(age=0, epoch=None):
        return f"### arsenal-test-run {int(time.time() - age) if epoch is None else epoch}"

    def push(self, **extra):
        return self.hook(self.local, env=self.env(**extra))

    def test_a_newer_log_naming_every_file_passes(self):
        self.record()
        self.write_log("tests/test_a.py ..\ntests/test_b.py ..\n")
        code, out = self.push()
        self.assertEqual(code, 0, out)
        self.assertNotIn("refused", out)

    def test_a_log_older_than_the_record_refuses(self):
        self.record()
        self.write_log("tests/test_a.py ..\ntests/test_b.py ..\n", age=500)
        code, out = self.push()
        self.assertEqual(code, 1, out)
        self.assertIn("tests/test_a.py, tests/test_b.py", out)
        self.assertIn(">> ", out)  # the command to run them

    def test_an_earlier_run_does_not_count_when_a_later_unrelated_run_appends(self):
        self.record()
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text(f"{self.marker(500)}\ntests/test_a.py ..\ntests/test_b.py ..\n"
                            f"{self.marker()}\ntests/test_c.py ..\n")
        code, out = self.push()
        self.assertEqual(code, 1, out)
        self.assertIn("tests/test_a.py, tests/test_b.py", out)
        self.assertIn("### arsenal-test-run $(date +%s)", out)
        self.assertIn(f">> {self.log}", out)

    def test_a_marker_after_the_record_then_the_name_passes_and_clears_the_record(self):
        self.record(files=["tests/test_a.py"])
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text(f"{self.marker(500)}\ntests/test_c.py ..\n{self.marker()}\ntests/test_a.py ..\n")
        self.assertEqual(self.push()[0], 0)
        self.assertNotIn("owner/repo", json.loads(self.red_runs.read_text()))

    def test_a_marker_before_the_record_then_the_name_refuses(self):
        self.record(files=["tests/test_a.py"])
        self.write_log("tests/test_a.py ..\n", age=500)
        self.assertEqual(self.push()[0], 1)

    def test_a_log_without_markers_refuses(self):
        self.record(files=["tests/test_a.py"])
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text("tests/test_a.py ..\n")
        self.assertEqual(self.push()[0], 1)

    def test_only_the_section_from_the_first_new_marker_counts(self):
        self.record(files=["tests/test_a.py"])
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text(f"{self.marker(900)}\ntests/test_a.py ..\n{self.marker(800)}\ntests/test_b.py ..\n"
                            f"{self.marker()}\ntests/test_c.py ..\n")
        self.assertEqual(self.push()[0], 1)
        self.log.write_text(f"{self.marker(900)}\ntests/test_b.py ..\n{self.marker(50)}\ntests/test_c.py ..\n"
                            f"{self.marker()}\ntests/test_a.py ..\n")
        self.assertEqual(self.push()[0], 0)

    def test_a_marker_with_a_bad_epoch_is_ignored(self):
        self.record(files=["tests/test_a.py"])
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text("### arsenal-test-run soon\n### arsenal-test-run\ntests/test_a.py ..\n")
        self.assertEqual(self.push()[0], 1)

    def test_no_log_refuses_and_names_the_files(self):
        self.record()
        code, out = self.push()
        self.assertEqual(code, 1, out)
        self.assertIn("run 77", out)
        self.assertIn("tests/test_b.py", out)

    def test_a_log_naming_only_some_files_refuses_with_the_missing_ones(self):
        self.record()
        self.write_log("tests/test_a.py ..\n")
        code, out = self.push()
        self.assertEqual(code, 1, out)
        self.assertIn("failed tests/test_b.py,", out)
        self.assertNotIn("failed tests/test_a.py", out)

    def test_a_log_naming_the_dotted_module_form_counts(self):
        self.record(files=["tests/test_a.py", "tests/test_b.py"])
        self.write_log("test_x (tests.test_a.CaseA) ... ok\nRan 1 test in tests.test_b\n")
        code, out = self.push()
        self.assertEqual(code, 0, out)

    def test_the_path_form_still_counts(self):
        self.record(files=["tests/test_a.py"])
        self.write_log("tests/test_a.py ..\n")
        self.assertEqual(self.push()[0], 0)

    def test_a_dotted_form_of_another_file_does_not_count(self):
        self.record(files=["tests/test_a.py"])
        self.write_log("tests.test_ab ... ok\n")
        self.assertEqual(self.push()[0], 1)

    def test_pytest_q_output_without_paths_refuses_with_the_hint(self):
        self.record(files=["tests/test_a.py"])
        self.write_log("..\n2 passed in 0.1s\n")
        code, out = self.push()
        self.assertEqual(code, 1, out)
        self.assertIn("rerun with the paths given explicitly", out)
        self.assertIn("pytest -v <path>", out)

    def test_an_unreadable_log_refuses_and_keeps_the_record(self):
        self.record()
        self.log.mkdir(parents=True)  # a directory where the log should be: reading it fails
        code, out = self.push()
        self.assertEqual(code, 1, out)
        self.assertIn("tests/test_a.py, tests/test_b.py", out)
        self.assertIn("unreadable", out)
        self.assertNotIn("not checked", out)
        self.assertIn("refus", out)
        self.assertIn("owner/repo", json.loads(self.red_runs.read_text()))

    def test_an_unreadable_log_still_passes_with_the_opt_out(self):
        self.record()
        self.log.mkdir(parents=True)
        self.assertEqual(self.push(ARSENAL_ALLOW_UNRUN_RED="log on a slow disk")[0], 0)
        self.assertIn("owner/repo", json.loads(self.red_runs.read_text()))

    def test_a_path_inside_a_longer_path_does_not_count(self):
        self.record(files=["test_a.py"])
        self.write_log("tests/sub/test_a.py ..\n")
        self.assertEqual(self.push()[0], 1)

    def test_a_path_after_a_dot_prefix_or_word_char_does_not_count(self):
        for text in ("xtest_a.py ..", "_test_a.py ..", "1test_a.py ..", ".test_a.py ..", "test_a.pyc ..", "test_a.py2 ..",
                     "test_a.py_ ..", "mytest_a.py .."):
            with self.subTest(text=text):
                self.record(files=["test_a.py"])
                self.write_log(text + "\n")
                self.assertEqual(self.push()[0], 1)

    def test_a_path_with_punctuation_around_it_counts(self):
        for text in ("test_a.py ..", "(test_a.py)", "FAILED test_a.py::t - x", "a.py test_a.py:3"):
            with self.subTest(text=text):
                self.record(files=["test_a.py"])
                self.write_log(text + "\n")
                self.assertEqual(self.push()[0], 0)
                self.red_runs.write_text("{}")

    def test_a_dot_slash_or_absolute_path_of_the_same_file_counts(self):
        top = str(self.repo.resolve())
        for text in ("./tests/test_a.py ..", f"{top}/tests/test_a.py ..", f'  File "{top}/tests/test_a.py", line 3',
                     "FAILED ./tests/test_a.py::t"):
            with self.subTest(text=text):
                self.record(files=["tests/test_a.py"])
                self.write_log(text + "\n")
                self.assertEqual(self.push()[0], 0)
                self.red_runs.write_text("{}")

    def test_another_files_path_with_the_same_tail_does_not_count(self):
        top = str(self.repo.resolve())
        for text in ("src/tests/test_a.py ..", "tests/sub/test_a.py ..", "./src/tests/test_a.py ..",
                     f"{top}/src/tests/test_a.py ..", "/elsewhere/tests/test_a.py .."):
            with self.subTest(text=text):
                self.record(files=["tests/test_a.py"])
                self.write_log(text + "\n")
                self.assertEqual(self.push()[0], 1)

    def test_a_dotted_form_inside_a_longer_dotted_name_does_not_count(self):
        self.record(files=["tests/test_a.py"])
        self.write_log("tests.test_a_extra ... ok\npkg_tests.test_a ... ok\ntests.test_a_ ... ok\n")
        self.assertEqual(self.push()[0], 1)

    def test_a_dotted_form_with_a_prefix_package_counts(self):
        self.record(files=["tests/test_a.py"])
        self.write_log("test_x (tests.test_a.CaseA) ... ok\n")
        self.assertEqual(self.push()[0], 0)

    def test_a_dotted_form_preceded_by_a_word_char_does_not_count(self):
        self.record(files=["tests/test_a.py"])
        self.write_log("xtests.test_a ... ok\n")
        self.assertEqual(self.push()[0], 1)

    def test_a_record_with_every_file_named_is_removed(self):
        self.record(files=["tests/test_a.py"])
        self.red_runs.write_text(json.dumps({"owner/repo": json.loads(self.red_runs.read_text())["owner/repo"],
                                             "o/other": {"run": 1, "head_sha": "x", "time": 1, "files": []}}))
        self.write_log("tests/test_a.py ..\n")
        self.assertEqual(self.push()[0], 0)
        self.assertEqual(list(json.loads(self.red_runs.read_text())), ["o/other"])

    def test_a_record_with_a_file_unnamed_stays(self):
        self.record()
        self.write_log("tests/test_a.py ..\n")
        self.assertEqual(self.push()[0], 1)
        self.assertIn("owner/repo", json.loads(self.red_runs.read_text()))

    def test_a_failed_removal_is_only_a_warning(self):
        self.record(files=["tests/test_a.py"])
        self.write_log("tests/test_a.py ..\n")
        self.red_runs.chmod(0o444)
        self.red_runs.parent.chmod(0o555)
        try:
            code, out = self.push()
        finally:
            self.red_runs.parent.chmod(0o755)
        if os.geteuid() != 0:  # root ignores the mode bits, so only check the warning where the write fails
            self.assertIn("warning", out)
        self.assertEqual(code, 0, out)

    def test_the_opt_out_passes_and_is_logged_with_its_reason(self):
        self.record()
        code, out = self.push(ARSENAL_ALLOW_UNRUN_RED="infra flake, see run 77")
        self.assertEqual(code, 0, out)
        entry = self.optouts()[-1]
        self.assertEqual((entry["flag"], entry["branch"], entry["local_sha"]), ("ARSENAL_ALLOW_UNRUN_RED", "feature",
                                                                                 self.local))
        self.assertIn("infra flake", entry["reason"])
        self.assertIn("tests/test_a.py", entry["reason"])

    def test_a_record_whose_head_is_an_ancestor_of_the_pushed_head_applies(self):
        self.record(head=git(self.repo, "rev-parse", "HEAD~1"))
        self.assertEqual(self.push()[0], 1)

    def test_a_record_whose_head_is_not_in_the_push_passes_with_a_warning(self):
        other = git(self.repo, "rev-parse", "main")
        git(self.repo, "checkout", "-q", "-b", "side", "main")
        side = self.commit("side.py", "s\n", "feat: side")
        git(self.repo, "checkout", "-q", "feature")
        self.record(head=side)
        code, out = self.push()
        self.assertEqual(code, 0, out)
        self.assertIn("warning", out)
        self.assertNotEqual(side, other)

    def test_a_record_with_no_files_passes(self):
        self.record(files=[])
        self.assertEqual(self.push()[0], 0)

    def test_another_repository_record_does_not_apply(self):
        self.record(repo="owner/other")
        code, out = self.push()
        self.assertEqual(code, 0, out)
        self.assertIn("warning: no CI record for owner/repo", out)

    def test_a_missing_state_file_passes_with_a_warning(self):
        code, out = self.push()
        self.assertEqual(code, 0, out)
        self.assertIn("warning: no CI record", out)

    def test_a_corrupt_state_file_passes_with_a_warning(self):
        for text in ("{not json", "[]", '{"owner/repo": "x"}', '{"owner/repo": {"files": "a", "time": 1}}'):
            with self.subTest(text=text):
                self.red_runs.write_text(text)
                code, out = self.push()
                self.assertEqual(code, 0, out)
                self.assertIn("warning", out)

    def test_an_unreadable_state_file_passes_with_a_warning(self):
        self.red_runs.mkdir()  # reading a directory fails with an OSError
        code, out = self.push()
        self.assertEqual(code, 0, out)
        self.assertIn("warning: CI record unreadable", out)

    def test_gh_down_never_turns_the_check_into_a_refusal(self):
        self.record()
        self.write_log("tests/test_a.py\ntests/test_b.py\n")
        env = {**path_without_gh(Path(self.tmp.name) / "nogh"), "ARSENAL_RED_RUNS": str(self.red_runs)}
        code, out = self.hook(self.local, env=env)
        self.assertEqual(code, 0, out)
        self.assertIn("warning: gh", out)

    def test_a_deletion_and_the_rebase_opt_outs_skip_the_check(self):
        self.record()
        self.assertEqual(self.hook(ZEROS)[0], 0)
        for flag in OPT_OUTS:
            with self.subTest(flag=flag):
                self.assertEqual(self.push(**{flag: "1"})[0], 0)

    def test_the_log_path_comes_from_arsenal_test_log(self):
        self.record()
        custom = self.repo / "out" / "t.log"
        custom.parent.mkdir()
        custom.write_text(f"{self.marker()}\ntests/test_a.py tests/test_b.py\n")
        self.assertEqual(self.push(ARSENAL_TEST_LOG="out/t.log")[0], 0)

    def test_the_template_writes_the_log_it_checks(self):
        self.record(files=["tests/test_a.py"])
        report = Path(self.tmp.name) / "lcov.info"
        report.write_text("SF:c.py\nDA:1,1\nend_of_record\n")
        env = self.env(ARSENAL_QUALITY_GATE=str(SCRIPTS), AFFECTED_TESTS_CMD="echo tests/test_a.py ok",
                       COVERAGE_REPORT=str(report), PUSH_BASE="origin/main")
        line = f"refs/heads/feature {self.local} refs/heads/feature {self.pushed}\n"
        result = subprocess.run(["sh", str(TEMPLATE), "origin", REPO_URL], input=line, cwd=self.repo,
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("tests/test_a.py", self.log.read_text())
        self.assertRegex(self.log.read_text(), r"(?m)^### arsenal-test-run \d+$")
        self.assertIn("tests/test_a.py ok", result.stdout)  # the test output still reaches the terminal


    def template_env(self):
        report = Path(self.tmp.name) / "lcov.info"
        report.write_text("SF:c.py\nDA:1,1\nend_of_record\n")
        return report, f"refs/heads/feature {self.local} refs/heads/feature {self.pushed}\n"

    def test_the_template_streams_the_test_output_before_the_command_ends(self):
        report, line = self.template_env()
        go = Path(self.tmp.name) / "go"
        cmd = f'echo first-line; i=0; while [ ! -f {go} ] && [ $i -lt 150 ]; do i=$((i+1)); sleep 0.1; done; echo last-line'
        env = self.env(ARSENAL_QUALITY_GATE=str(SCRIPTS), AFFECTED_TESTS_CMD=cmd, COVERAGE_REPORT=str(report),
                       PUSH_BASE="origin/main")
        proc = subprocess.Popen(["sh", str(TEMPLATE), "origin", REPO_URL], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, cwd=self.repo, text=True, env=env)
        proc.stdin.write(line)
        proc.stdin.close()
        seen = []
        reader = threading.Thread(target=lambda: seen.append(proc.stdout.readline()))
        reader.start()
        reader.join(10)
        streamed = list(seen)
        go.write_text("go")  # release the command; without this it ends by itself after 15 seconds
        rest = proc.stdout.read()
        proc.wait(30)
        self.assertEqual(streamed, ["first-line\n"], "the first line must reach the terminal while the command runs")
        self.assertIn("last-line", rest)
        self.assertIn("last-line", self.log.read_text())

    def test_the_template_leaves_no_temp_file_after_a_normal_or_failing_run(self):
        report, line = self.template_env()
        for cmd, code in (("echo ok", 0), ("exit 3", 3)):
            tmpdir = Path(self.tmp.name) / f"tmp{code}"
            tmpdir.mkdir()
            env = self.env(ARSENAL_QUALITY_GATE=str(SCRIPTS), AFFECTED_TESTS_CMD=cmd, COVERAGE_REPORT=str(report),
                           PUSH_BASE="origin/main", TMPDIR=str(tmpdir))
            result = subprocess.run(["sh", str(TEMPLATE), "origin", REPO_URL], input=line, cwd=self.repo,
                                    capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            self.assertEqual(list(tmpdir.iterdir()), [])

    def test_the_template_removes_its_temp_file_when_terminated_and_exits_143(self):
        report, line = self.template_env()
        go, tmpdir = Path(self.tmp.name) / "go2", Path(self.tmp.name) / "tmpsig"
        tmpdir.mkdir()
        cmd = f'echo started; i=0; while [ ! -f {go} ] && [ $i -lt 150 ]; do i=$((i+1)); sleep 0.1; done'
        env = self.env(ARSENAL_QUALITY_GATE=str(SCRIPTS), AFFECTED_TESTS_CMD=cmd, COVERAGE_REPORT=str(report),
                       PUSH_BASE="origin/main", TMPDIR=str(tmpdir))
        proc = subprocess.Popen(["sh", str(TEMPLATE), "origin", REPO_URL], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, cwd=self.repo, text=True, env=env)
        proc.stdin.write(line)
        proc.stdin.close()
        self.assertEqual(proc.stdout.readline(), "started\n")  # the temp file exists now
        self.assertEqual(len(list(tmpdir.iterdir())), 1)
        proc.terminate()
        go.write_text("go")  # the shell runs its trap once the foreground command ends
        proc.stdout.read()
        self.assertEqual(proc.wait(30), 143)
        self.assertEqual(list(tmpdir.iterdir()), [])

    def test_the_template_fails_the_hook_with_the_failing_tests_exit_code_and_logs_the_output(self):
        report, line = self.template_env()
        env = self.env(ARSENAL_QUALITY_GATE=str(SCRIPTS), AFFECTED_TESTS_CMD="echo boom; echo err >&2; exit 3",
                       COVERAGE_REPORT=str(report), PUSH_BASE="origin/main")
        result = subprocess.run(["sh", str(TEMPLATE), "origin", REPO_URL], input=line, cwd=self.repo,
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("boom", result.stdout)
        self.assertIn("err", result.stdout)
        self.assertIn("boom", self.log.read_text())
        self.assertIn("err", self.log.read_text())

    def test_the_template_appends_to_the_log_and_keeps_it_bounded(self):
        self.record(files=["tests/test_a.py"])
        report = Path(self.tmp.name) / "lcov.info"
        report.write_text("SF:c.py\nDA:1,1\nend_of_record\n")
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text("EARLIER RUN\n")
        env = self.env(ARSENAL_QUALITY_GATE=str(SCRIPTS), AFFECTED_TESTS_CMD="echo tests/test_a.py ok",
                       COVERAGE_REPORT=str(report), PUSH_BASE="origin/main")
        line = f"refs/heads/feature {self.local} refs/heads/feature {self.pushed}\n"

        def run():
            return subprocess.run(["sh", str(TEMPLATE), "origin", REPO_URL], input=line, cwd=self.repo,
                                  capture_output=True, text=True, env=env)
        self.assertEqual(run().returncode, 0)
        text = self.log.read_text()
        self.assertTrue(text.startswith("EARLIER RUN\n"), text)
        self.assertIn("tests/test_a.py ok", text)
        self.log.write_bytes(b"x" * (5 * 1024 * 1024 + 10))
        self.assertEqual(run().returncode, 0)
        size = self.log.stat().st_size
        self.assertLess(size, 2 * 1024 * 1024 + 200)
        self.assertGreater(size, 2 * 1024 * 1024)
        self.assertTrue(self.log.read_text().endswith("tests/test_a.py ok\n"))


if __name__ == "__main__":
    unittest.main()
