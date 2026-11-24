"""Tests for .agents/skills/test-every-change/scripts/mutate.py: each mutant runs in a temporary copy of the tracked
files, and that copy is always removed (killed, survived, timeout, bad mutant, SIGTERM)."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "test-every-change" / "scripts" / "mutate.py"
PY = sys.executable
CHECK = "import sys; from app import VALUE; sys.exit(0 if VALUE == 2 else 1)\n"
SLOW_UNDER_MUTANT = "import sys, time; from app import VALUE\nif VALUE != 2: time.sleep(30)\n"


def git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
                   cwd=repo, check=True, capture_output=True)


class MutateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.repo, self.work = base / "repo", base / "work"
        self.repo.mkdir()
        self.work.mkdir()
        (self.repo / "app.py").write_text("VALUE = 1 + 1\n")
        (self.repo / "check.py").write_text(CHECK)
        (self.repo / "ignored.log").write_text("not tracked\n")
        git(self.repo, "init", "-q")
        git(self.repo, "add", "app.py", "check.py")
        git(self.repo, "commit", "-q", "-m", "start")

    def run_mutate(self, mutants, *extra, timeout=60):
        spec = self.work.parent / "mutants.json"
        spec.write_text(json.dumps(mutants))
        env = {**os.environ, "ARSENAL_MUTATION_DIR": str(self.work)}
        return subprocess.run([PY, str(SCRIPT), "--mutants", str(spec), *extra, "--", PY, "check.py"],
                              cwd=self.repo, capture_output=True, text=True, env=env, timeout=timeout)

    def assertNothingLeft(self):
        self.assertEqual(list(self.work.iterdir()), [])


class MutateTests(MutateCase):

    def test_a_killed_mutant_is_reported_and_its_copy_removed(self):
        result = self.run_mutate([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "minus"}])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("killed minus", result.stdout)
        self.assertNothingLeft()

    def test_a_surviving_mutant_exits_1_and_its_copy_is_removed(self):
        result = self.run_mutate([{"file": "app.py", "old": "1 + 1", "new": "2 * 1", "label": "same value"}])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("SURVIVED same value", result.stdout)
        self.assertNothingLeft()

    def test_only_tracked_files_are_copied(self):
        check = "import os, sys; sys.exit(1 if os.path.exists('ignored.log') else 0)\n"
        (self.repo / "check.py").write_text(check)
        git(self.repo, "commit", "-q", "-am", "check for the untracked file")
        result = self.run_mutate([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "m"}])
        self.assertIn("SURVIVED m", result.stdout)  # the copy has no ignored.log, so the check passes
        self.assertNothingLeft()

    def test_a_mutant_whose_text_is_missing_or_repeated_is_refused_and_nothing_is_left(self):
        (self.repo / "app.py").write_text("VALUE = 1 + 1  # 1 + 1\n")
        git(self.repo, "commit", "-q", "-am", "twice")
        for old in ("no such text", "1 + 1"):
            result = self.run_mutate([{"file": "app.py", "old": old, "new": "x", "label": "bad"}])
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertNothingLeft()

    def test_a_timeout_counts_as_killed_and_the_copy_is_removed(self):
        (self.repo / "check.py").write_text(SLOW_UNDER_MUTANT)
        git(self.repo, "commit", "-q", "-am", "slow under the mutant")
        result = self.run_mutate([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "slow"}],
                                 "--timeout", "2")
        self.assertIn("killed slow (timeout", result.stdout)
        self.assertNothingLeft()

    def test_sigterm_removes_the_copy_in_use(self):
        (self.repo / "check.py").write_text("import time; time.sleep(30)\n")
        git(self.repo, "commit", "-q", "-am", "slow")
        spec = self.work.parent / "mutants.json"
        spec.write_text(json.dumps([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "m"}]))
        env = {**os.environ, "ARSENAL_MUTATION_DIR": str(self.work)}
        proc = subprocess.Popen([PY, str(SCRIPT), "--mutants", str(spec), "--", PY, "check.py"], cwd=self.repo,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        deadline = time.monotonic() + 20
        while not any(self.work.iterdir()) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(any(self.work.iterdir()), "the copy was never made")
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=20)
        self.assertNotEqual(proc.returncode, 0)
        self.assertNothingLeft()

    def test_usage_errors_exit_2(self):
        result = subprocess.run([PY, str(SCRIPT), "--mutants", "/nonexistent.json", "--", "true"], cwd=self.repo,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        result = subprocess.run([PY, str(SCRIPT), "--mutants", "/nonexistent.json"], cwd=self.repo,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


class SafetyTests(MutateCase):
    """Paths, processes, baseline and exit codes: the review of the first version."""

    def assertRepoUnchanged(self):
        self.assertEqual((self.repo / "app.py").read_text(), "VALUE = 1 + 1\n")

    def test_a_mutant_file_outside_the_copy_is_refused_and_the_checkout_untouched(self):
        for name in (str(self.repo / "app.py"), "../repo/app.py", "sub/../../repo/app.py", "untracked.py"):
            with self.subTest(name=name):
                (self.repo / "untracked.py").write_text("VALUE = 1 + 1\n")
                result = self.run_mutate([{"file": name, "old": "1 + 1", "new": "1 - 1", "label": "out"}])
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertRepoUnchanged()
                self.assertNothingLeft()

    def test_every_run_leaves_the_checkout_unchanged(self):
        self.run_mutate([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "m"}])
        self.assertRepoUnchanged()

    def test_a_timeout_kills_the_children_of_the_test_command(self):
        marker = self.work.parent / "child.pid"
        (self.repo / "check.py").write_text(
            "import subprocess, sys\nfrom app import VALUE\nif VALUE == 2: sys.exit(0)\n"
            f"child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            f"open({str(marker)!r}, 'w').write(str(child.pid))\n"
            "child.wait()\n")
        git(self.repo, "commit", "-q", "-am", "a child")
        result = self.run_mutate([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "slow"}],
                                 "--timeout", "2")
        self.assertIn("killed slow (timeout", result.stdout)
        pid = int(marker.read_text())
        deadline = time.monotonic() + 5
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(alive(pid), "the test command's child outlived the timeout")
        self.assertNothingLeft()

    def test_the_tests_must_pass_without_a_mutant(self):
        (self.repo / "check.py").write_text("import sys; sys.exit(1)\n")
        git(self.repo, "commit", "-q", "-am", "always red")
        result = self.run_mutate([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "m"}])
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("fail without any mutant", result.stderr)
        self.assertNotIn("killed m", result.stdout)
        self.assertNothingLeft()

    def test_two_mutants_both_run_and_one_survivor_exits_1(self):
        result = self.run_mutate([{"file": "app.py", "old": "1 + 1", "new": "2 * 1", "label": "same"},
                                  {"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "minus"}])
        self.assertEqual(result.returncode, 1)
        self.assertIn("SURVIVED same", result.stdout)
        self.assertIn("killed minus", result.stdout)

    def test_bad_input_exits_2(self):
        mutant = {"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "m"}
        cases = {"timeout 0": ([mutant], ("--timeout", "0")), "negative timeout": ([mutant], ("--timeout", "-1")),
                 "empty list": ([], ()), "missing label": ([{"file": "app.py", "old": "1", "new": "2"}], ())}
        for name, (mutants, extra) in cases.items():
            with self.subTest(name=name):
                result = self.run_mutate(mutants, *extra)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertNothingLeft()

    def test_a_non_utf8_or_symlinked_file_is_refused_with_exit_2(self):
        (self.repo / "latin.py").write_bytes(b"NAME = '\xe9'\n")
        os.symlink("app.py", self.repo / "link.py")
        git(self.repo, "add", "latin.py", "link.py")
        git(self.repo, "commit", "-q", "-m", "latin and a link")
        for name in ("latin.py", "link.py"):
            with self.subTest(name=name):
                result = self.run_mutate([{"file": name, "old": "NAME" if name == "latin.py" else "1 + 1",
                                           "new": "X", "label": name}])
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertNothingLeft()

    def test_a_tracked_symlink_stays_a_link_in_the_copy(self):
        os.symlink("app.py", self.repo / "link.py")
        (self.repo / "check.py").write_text("import sys; from link import VALUE; sys.exit(0 if VALUE == 2 else 1)\n")
        git(self.repo, "add", "link.py", "check.py")
        git(self.repo, "commit", "-q", "-m", "import through a link")
        result = self.run_mutate([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "via link"}])
        self.assertIn("killed via link", result.stdout)

    def test_crlf_line_endings_are_kept_and_matched(self):
        (self.repo / "app.py").write_bytes(b"VALUE = 1 + 1\r\n")
        git(self.repo, "commit", "-q", "-am", "crlf")
        result = self.run_mutate([{"file": "app.py", "old": "1 + 1\r\n", "new": "1 - 1\r\n", "label": "crlf"}])
        self.assertIn("killed crlf", result.stdout)

    def test_a_missing_mutation_dir_or_no_repository_exits_2(self):
        spec = self.work.parent / "mutants.json"
        spec.write_text(json.dumps([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "m"}]))
        env = {**os.environ, "ARSENAL_MUTATION_DIR": str(self.work / "nope")}
        result = subprocess.run([PY, str(SCRIPT), "--mutants", str(spec), "--", PY, "check.py"], cwd=self.repo,
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 2, result.stderr)
        outside = Path(self.tmp.name) / "plain"
        outside.mkdir()
        result = subprocess.run([PY, str(SCRIPT), "--mutants", str(spec), "--", PY, "check.py"], cwd=outside,
                                capture_output=True, text=True, env={**os.environ, "GIT_CEILING_DIRECTORIES": self.tmp.name})
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_each_stop_signal_exits_128_plus_its_number_and_removes_the_copy(self):
        (self.repo / "check.py").write_text("import time; time.sleep(30)\n")
        git(self.repo, "commit", "-q", "-am", "slow")
        spec = self.work.parent / "mutants.json"
        spec.write_text(json.dumps([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "m"}]))
        env = {**os.environ, "ARSENAL_MUTATION_DIR": str(self.work)}
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            with self.subTest(signal=signum):
                proc = subprocess.Popen([PY, str(SCRIPT), "--mutants", str(spec), "--timeout", "60", "--",
                                         PY, "check.py"], cwd=self.repo, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, env=env)
                deadline = time.monotonic() + 20
                while len(list(self.work.iterdir())) < 1 and time.monotonic() < deadline:
                    time.sleep(0.05)
                time.sleep(0.5)  # past the copy, into the test command
                proc.send_signal(signum)
                proc.communicate(timeout=20)
                self.assertEqual(proc.returncode, 128 + signum)
                self.assertNothingLeft()


class RoundTwoTests(MutateCase):
    """Signals, leftover children, odd inputs and the copy's isolation from the checkout's git."""

    def child_check(self, marker, then_exit=None):
        """check.py: passes unmutated; under the mutant starts a 30 s child, writes its pid, then waits or exits."""
        end = "child.wait()\n" if then_exit is None else f"sys.exit({then_exit})\n"
        (self.repo / "check.py").write_text(
            "import subprocess, sys\nfrom app import VALUE\nif VALUE == 2: sys.exit(0)\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            f"open({str(marker)!r}, 'w').write(str(child.pid))\n" + end)
        git(self.repo, "commit", "-q", "-am", "a child under the mutant")

    def wait_gone(self, pid):
        deadline = time.monotonic() + 5
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        return not alive(pid)

    def test_a_stop_signal_kills_the_test_commands_processes(self):
        marker = self.work.parent / "child.pid"
        self.child_check(marker)
        spec = self.work.parent / "mutants.json"
        spec.write_text(json.dumps([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "m"}]))
        env = {**os.environ, "ARSENAL_MUTATION_DIR": str(self.work)}
        proc = subprocess.Popen([PY, str(SCRIPT), "--mutants", str(spec), "--", PY, "check.py"], cwd=self.repo,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        deadline = time.monotonic() + 20
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(marker.exists(), "the mutant's child never started")
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=20)
        self.assertEqual(proc.returncode, 128 + signal.SIGTERM)
        self.assertTrue(self.wait_gone(int(marker.read_text())), "a child outlived SIGTERM")
        self.assertNothingLeft()

    def test_a_background_child_left_by_a_finished_command_is_killed(self):
        marker = self.work.parent / "child.pid"
        self.child_check(marker, then_exit=1)
        result = self.run_mutate([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "m"}])
        self.assertIn("killed m", result.stdout)
        self.assertTrue(self.wait_gone(int(marker.read_text())), "a background child outlived the run")

    def test_a_second_stop_signal_is_ignored_while_cleaning_up(self):
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import mutate
        finally:
            sys.path.remove(str(SCRIPT.parent))
        saved = {signum: signal.getsignal(signum) for signum in mutate.STOP_SIGNALS}
        try:
            with self.assertRaises(SystemExit) as stopped:
                mutate.stop(signal.SIGTERM, None)
            self.assertEqual(stopped.exception.code, 128 + signal.SIGTERM)
            for signum in mutate.STOP_SIGNALS:
                self.assertEqual(signal.getsignal(signum), signal.SIG_IGN, signum)
        finally:
            for signum, handler in saved.items():
                signal.signal(signum, handler)

    def test_a_nan_timeout_exits_2(self):
        result = self.run_mutate([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "m"}],
                                 "--timeout", "nan")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_an_odd_label_is_printed_not_crashed_on(self):
        result = self.run_mutate([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "odd \ud800"}])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("killed odd", result.stdout)

    def test_output_is_exactly_one_line_per_mutant(self):
        (self.repo / "check.py").write_text(
            "import sys; from app import VALUE; print('noise'); print('err', file=sys.stderr)\n"
            "sys.exit(0 if VALUE == 2 else 1)\n")
        git(self.repo, "commit", "-q", "-am", "noisy")
        result = self.run_mutate([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "a"},
                                  {"file": "app.py", "old": "1 + 1", "new": "2 * 1", "label": "b"}])
        self.assertEqual(result.stdout.splitlines(), ["killed a", "SURVIVED b"])

    def test_a_tracked_file_deleted_in_the_checkout_and_a_non_ascii_name(self):
        (self.repo / "gone.py").write_text("x = 1\n")
        (self.repo / "caf\u00e9.py").write_text("VALUE = 1 + 1\n")
        (self.repo / "check.py").write_text(
            "import importlib, sys; m = importlib.import_module('caf\\u00e9'); sys.exit(0 if m.VALUE == 2 else 1)\n")
        git(self.repo, "add", "gone.py", "caf\u00e9.py", "check.py")
        git(self.repo, "commit", "-q", "-m", "more files")
        (self.repo / "gone.py").unlink()
        result = self.run_mutate([{"file": "caf\u00e9.py", "old": "1 + 1", "new": "1 - 1", "label": "accent"}])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("killed accent", result.stdout)

    def test_git_in_the_copy_never_finds_an_enclosing_repository(self):
        inside = self.repo / ".mutants"
        inside.mkdir()
        (self.repo / "check.py").write_text(
            "import subprocess, sys\n"
            "found = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True).returncode == 0\n"
            "sys.exit(1 if found else 0)\n")
        git(self.repo, "commit", "-q", "-am", "git must not find a repository")
        spec = self.work.parent / "mutants.json"
        spec.write_text(json.dumps([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "m"}]))
        result = subprocess.run([PY, str(SCRIPT), "--mutants", str(spec), "--", PY, "check.py"], cwd=self.repo,
                                capture_output=True, text=True, env={**os.environ, "ARSENAL_MUTATION_DIR": str(inside)})
        self.assertNotIn("fail without any mutant", result.stderr)  # the baseline found no repository
        self.assertEqual(list(inside.iterdir()), [])


class RoundThreeTests(MutateCase):
    """A signal during the copy's removal, and git variables inherited from a hook."""

    def load(self):
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import mutate
        finally:
            sys.path.remove(str(SCRIPT.parent))
        return mutate

    def test_a_stop_signal_during_removal_waits_until_the_copy_is_gone(self):
        mutate = self.load()
        real_rmtree = mutate.shutil.rmtree

        def rmtree_hit_by_a_signal(path, *args, **kwargs):
            os.kill(os.getpid(), signal.SIGTERM)  # this process only: the stop arrives mid-removal
            return real_rmtree(path, *args, **kwargs)

        saved = {signum: signal.getsignal(signum) for signum in mutate.STOP_SIGNALS}
        os.environ["ARSENAL_MUTATION_DIR"] = str(self.work)
        try:
            for signum in mutate.STOP_SIGNALS:
                signal.signal(signum, mutate.stop)
            names = mutate.tracked_files(str(self.repo))
            with unittest.mock.patch.object(mutate.shutil, "rmtree", rmtree_hit_by_a_signal):
                with self.assertRaises(SystemExit) as stopped:
                    mutate.in_copy(str(self.repo), names, [PY, "-c", "pass"], 30)
            self.assertEqual(stopped.exception.code, 128 + signal.SIGTERM)
            self.assertNothingLeft()
        finally:
            os.environ.pop("ARSENAL_MUTATION_DIR", None)
            for signum, handler in saved.items():
                signal.signal(signum, handler)

    def test_a_stop_signal_during_removal_waits_even_with_another_thread_alive(self):
        import threading
        stop_thread = threading.Event()
        helper = threading.Thread(target=stop_thread.wait, daemon=True)  # a thread that leaves the signal unblocked
        helper.start()
        self.addCleanup(stop_thread.set)
        self.test_a_stop_signal_during_removal_waits_until_the_copy_is_gone()

    def test_inherited_git_variables_never_reach_the_real_repository(self):
        (self.repo / "check.py").write_text(
            "import subprocess, sys\n"
            "subprocess.run(['git', 'config', 'arsenal.touched', 'yes'], capture_output=True)\n")
        git(self.repo, "commit", "-q", "-am", "a test that runs git")
        spec = self.work.parent / "mutants.json"
        spec.write_text(json.dumps([{"file": "app.py", "old": "1 + 1", "new": "1 - 1", "label": "m"}]))
        env = {**os.environ, "ARSENAL_MUTATION_DIR": str(self.work), "GIT_DIR": str(self.repo / ".git"),
               "GIT_WORK_TREE": str(self.repo), "GIT_INDEX_FILE": str(self.repo / ".git" / "index")}
        subprocess.run([PY, str(SCRIPT), "--mutants", str(spec), "--", PY, "check.py"], cwd=self.repo,
                       capture_output=True, text=True, env=env)
        config = (self.repo / ".git" / "config").read_text()
        self.assertNotIn("touched", config)
        self.assertNothingLeft()

    def test_a_non_string_field_exits_2(self):
        result = self.run_mutate([{"file": "app.py", "old": 1, "new": "x", "label": "m"}])
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


def alive(pid):
    """True while pid runs; a zombie counts as gone (inside a pid namespace the runner may not reap it at once)."""
    try:
        with open(f"/proc/{pid}/stat") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


if __name__ == "__main__":
    unittest.main()
