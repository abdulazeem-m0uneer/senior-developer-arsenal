"""Unit tests for test-every-change/scripts/tdd.py (`red` records a failing run, `check` enforces it on a branch)."""
import importlib.util
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "test-every-change" / "scripts" / "tdd.py"
PY = sys.executable
DIGEST = "sha256:" + "a" * 64
HAS_PROC = Path("/proc/self/stat").exists()


def load_tdd():
    spec = importlib.util.spec_from_file_location("tdd", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tdd_env(env=None):
    base = {k: v for k, v in os.environ.items() if k != "GITHUB_HEAD_REF"}
    return {**base, **(env or {})}


def tdd(*args, cwd=None, env=None):
    return subprocess.run([PY, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, timeout=120,
                          env=tdd_env(env))


def py_command(code):
    return [PY, "-c", code]


def alive(pid):
    """True while the process runs; a zombie left for an init that never reaps counts as gone."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return state not in ("Z", "X")


def gone_within(pid, seconds=5):
    deadline = time.monotonic() + seconds
    while alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def read_pid(path, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            return int(path.read_text())
        except (FileNotFoundError, ValueError):
            time.sleep(0.05)
    raise AssertionError(f"{path} was never written")


def sleeper(pid_file):
    """A test command that records its pid, then sleeps long enough to be interrupted."""
    return py_command(f"import os, pathlib, time; pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
                      "time.sleep(30); raise SystemExit(1)")


class RedTests(unittest.TestCase):
    def test_failing_run_prints_one_trailer_line_and_exits_0(self):
        command = py_command("import sys; print('FAILED test_x'); sys.exit(3)")
        result = tdd("red", "--", *command)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^Test-Red: 3 sha256:[0-9a-f]{64} ")
        self.assertTrue(lines[0].endswith(" " + shlex.join(command)))

    def test_passing_run_is_refused_with_exit_1(self):
        result = tdd("red", "--", *py_command("print('ok')"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("the tests pass: a red run needs a test that fails before the code", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_command_not_found_is_a_launch_failure(self):
        result = tdd("red", "--", "/nonexistent/no-such-runner", "x")
        self.assertEqual(result.returncode, 2)
        self.assertIn("could not run", result.stderr)
        self.assertNotIn("Test-Red", result.stdout)

    def test_exit_127_from_a_shell_is_a_launch_failure(self):
        result = tdd("red", "--", "sh", "-c", "no-such-runner-xyz")
        self.assertEqual(result.returncode, 2)
        self.assertIn("could not run", result.stderr)

    def test_not_executable_is_a_launch_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run.sh"
            target.write_text("#!/bin/sh\nexit 1\n")
            target.chmod(0o644)
            result = tdd("red", "--", str(target))
            self.assertEqual(result.returncode, 2)
            self.assertIn("could not run", result.stderr)

    def test_timeout_is_a_launch_failure(self):
        result = tdd("red", "--timeout", "1", "--", *py_command("import time; time.sleep(30)"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("timed out", result.stderr)

    def test_signal_kill_is_a_launch_failure(self):
        result = tdd("red", "--", *py_command("import os, signal; os.kill(os.getpid(), signal.SIGKILL)"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("signal", result.stderr)

    def test_usage_errors_exit_2(self):
        for args in (["red"], ["red", "--"], ["red", "--timeout", "0", "--", "false"], ["nonsense"],
                     ["red", "--", "sh", "-c", "a\nb"]):
            with self.subTest(args=args):
                result = tdd(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("usage", result.stderr)

    def digest(self, text, code=1):
        result = tdd("red", "--", *py_command(f"import sys; sys.stdout.write({text!r}); sys.exit({code})"))
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.split()[2]

    def test_digest_ignores_colour_timing_and_temp_path_noise(self):
        plain = self.digest("FAILED test_x in 0.12s (12ms setup)\nat /tmp/pytest-of-u/pytest-7/test_x0/a.py:3\n")
        noisy = self.digest("\x1b[31mFAILED\x1b[0m test_x in 3.40s (870ms setup)\n"
                            "at /tmp/pytest-of-u/pytest-9/test_x3/a.py:3\n")
        self.assertEqual(plain, noisy)

    def test_digest_changes_with_the_failure(self):
        self.assertNotEqual(self.digest("FAILED test_x\n"), self.digest("FAILED test_y\n"))

    def test_digest_reads_only_the_last_4_kb(self):
        tail = "E assert 1 == 2\n" * 300
        self.assertEqual(self.digest("x" * 9000 + "\n" + tail), self.digest("y" * 9000 + "\n" + tail))

    def test_digest_ignores_spaced_compound_and_platform_noise(self):
        module = load_tdd()
        pairs = [("Time:        1.234 s\n", "Time:        0.512 s\n"), ("ok (12 ms)\n", "ok (3 ms)\n"),
                 ("Time elapsed: 0.05 s\n", "Time elapsed: 1.5 s\n"),
                 ("Finished in 0.01234 seconds (files took 0.2 seconds to load)\n",
                  "Finished in 2.5 seconds (files took 1 seconds to load)\n"),
                 ("took 1m2s\n", "took 13m15s\n"), ("FAILED x\r\nE boom\r\n", "FAILED x\nE boom\n"),
                 ("at /var/folders/ab/T/pytest-1/a.py:3\n", "at /var/folders/cd/T/pytest-2/a.py:3\n"),
                 ("at /private/tmp/run-1/a.py:3\n", "at /private/tmp/run-9/a.py:3\n")]
        for first, second in pairs:
            with self.subTest(first=first):
                self.assertEqual(module.digest(first), module.digest(second))

    def test_digest_ignores_a_custom_temp_dir(self):
        module = load_tdd()
        self.addCleanup(setattr, tempfile, "tempdir", tempfile.tempdir)
        tempfile.tempdir = "/srv/ci/scratch"
        self.assertEqual(module.digest("at /srv/ci/scratch/run-1/a.py:3\n"),
                         module.digest("at /srv/ci/scratch/run-9/a.py:3\n"))

    @unittest.skipUnless(HAS_PROC, "needs /proc")
    def test_a_background_child_neither_holds_the_output_nor_outlives_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "pid"
            script = f"sleep 30 & echo $! > {shlex.quote(str(pid_file))}; echo fail; exit 1"
            start = time.monotonic()
            code, output, launch_failure = load_tdd().run_bounded(["sh", "-c", script], 60)
            self.assertLess(time.monotonic() - start, 15)  # far below the 30 s sleep; a loaded runner is slow
            self.assertEqual((code, launch_failure), (1, None))
            self.assertIn("fail", output)
            self.assertTrue(gone_within(read_pid(pid_file)), "the background child outlived the run")

    @unittest.skipUnless(HAS_PROC, "needs /proc")
    def test_output_is_kept_when_a_child_that_left_the_group_holds_the_pipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "pid"
            escape = (f"import os, pathlib, time; os.setsid(); pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
                      "time.sleep(30)")
            waits = f"while [ ! -s {shlex.quote(str(pid_file))} ]; do sleep 0.05; done"
            script = f"{shlex.join(py_command(escape))} & {waits}; echo fail; exit 1"
            try:
                code, output, launch_failure = load_tdd().run_bounded(["sh", "-c", script], 60)
            finally:
                os.kill(read_pid(pid_file), signal.SIGKILL)
            self.assertEqual((code, launch_failure), (1, None))
            self.assertIn("fail", output)

    def test_digest_keeps_counts_that_are_not_timings(self):
        module = load_tdd()
        for first, second in (("2 tests failed\n", "3 tests failed\n"), ("1 skipped\n", "2 skipped\n"),
                              ("assert 5 == 6\n", "assert 5 == 7\n")):
            with self.subTest(first=first):
                self.assertNotEqual(module.digest(first), module.digest(second))

    def test_shell_style_timeout_and_signal_exits_are_launch_failures(self):
        for code in (124, 129, 130, 137, 143, 159):
            with self.subTest(code=code):
                result = tdd("red", "--", "sh", "-c", f"exit {code}")
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertNotIn("Test-Red", result.stdout)

    def test_other_non_zero_exits_are_red(self):
        for code in (1, 2, 4, 5, 123, 125, 128, 160, 255):
            with self.subTest(code=code):
                result = tdd("red", "--", "sh", "-c", f"exit {code}")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.startswith(f"Test-Red: {code} "))

    def test_pytest_usage_error_and_no_tests_collected_are_not_red(self):
        for code, expected in ((4, 2), (5, 2), (1, 0)):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                fake = Path(tmp) / "pytest"
                fake.write_text(f"#!/bin/sh\nexit {code}\n")
                fake.chmod(0o755)
                (Path(tmp) / "pytest.py").write_text(f"raise SystemExit({code})\n")
                self.assertEqual(tdd("red", "--", str(fake), "tests/x.py").returncode, expected)
                self.assertEqual(tdd("red", "--", PY, "-m", "pytest", cwd=tmp).returncode, expected)

    def test_output_is_bounded_to_the_last_64_kb(self):
        code, output, launch_failure = load_tdd().run_bounded(
            py_command("import sys; sys.stdout.write('x' * 200000 + 'END'); sys.exit(1)"), 60)
        self.assertEqual((code, launch_failure, len(output)), (1, None, 64 * 1024))
        self.assertTrue(output.endswith("END"))

    def test_default_timeout_is_600_seconds(self):
        top = load_tdd().parser()
        self.assertEqual(top.parse_args(["red", "--", "x"]).timeout, 600)
        self.assertEqual(top.parse_args(["check", "--base", "main"]).timeout, 600)

    @unittest.skipUnless(HAS_PROC, "needs /proc")
    def test_timeout_kills_the_whole_process_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "pid"
            script = f"sleep 30 >/dev/null 2>&1 & echo $! > {shlex.quote(str(pid_file))}; wait"
            result = tdd("red", "--timeout", "1", "--", "sh", "-c", script)
            self.assertEqual(result.returncode, 2)
            self.assertTrue(gone_within(read_pid(pid_file)), "the backgrounded grandchild survived the timeout")

    @unittest.skipUnless(HAS_PROC, "needs /proc")
    def test_interrupt_stops_the_test_command_and_exits_2(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(sig=sig), tempfile.TemporaryDirectory() as tmp:
                pid_file = Path(tmp) / "pid"
                proc = subprocess.Popen([PY, str(SCRIPT), "red", "--", *sleeper(pid_file)], stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, env=tdd_env())
                child = read_pid(pid_file)
                proc.send_signal(sig)
                out, err = proc.communicate(timeout=30)
                self.assertEqual(proc.returncode, 2, err)
                self.assertIn("interrupted", err)
                self.assertNotIn("Traceback", err)
                self.assertEqual(out, "")
                self.assertTrue(gone_within(child), "the test command outlived the interrupt")

    def test_signals_are_held_while_cleaning_up(self):
        module = load_tdd()
        before = signal.getsignal(signal.SIGINT)
        with module.signals_held():
            os.kill(os.getpid(), signal.SIGINT)
            time.sleep(0.1)
        self.assertIs(signal.getsignal(signal.SIGINT), before)

    def test_red_in_a_subdirectory_records_the_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repo(Path(os.path.realpath(tmp)) / "repo")
            api = repo.path / "packages" / "api"
            api.mkdir(parents=True)
            command = py_command("raise SystemExit(1)")
            line = tdd("red", "--", *command, cwd=api).stdout.strip()
            recorded = line.split(" ", 3)[3]
            self.assertEqual(shlex.split(recorded),
                             ["sh", "-c", f"cd packages/api || exit 127; exec {shlex.join(command)}"])
            top = tdd("red", "--", *command, cwd=repo.path).stdout.strip()
            self.assertTrue(top.endswith(" " + shlex.join(command)), top)


class CleanupTests(unittest.TestCase):
    def test_a_verify_folder_left_behind_is_reported(self):
        module = load_tdd()
        with tempfile.TemporaryDirectory() as tmp:
            holder = os.path.join(tmp, "tdd-verify-x")
            os.makedirs(holder)
            err = __import__("io").StringIO()
            with unittest.mock.patch.object(module, "git", return_value=tmp), \
                    unittest.mock.patch.object(module.shutil, "rmtree"), \
                    unittest.mock.patch.object(module.sys, "stderr", err):
                module.remove_worktree(holder)
            self.assertIn("could not remove", err.getvalue())
            self.assertIn(holder, err.getvalue())


class Repo:
    """A throwaway git repository; identity set per command with -c, the global config is never written."""

    def __init__(self, path):
        self.path = path
        path.mkdir()
        self.git("-c", "init.defaultBranch=main", "init", "-q")
        self.commit("chore: start", {"README.md": "start\n"})

    def git(self, *args, env=None):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                               "-c", "commit.gpgsign=false", *args], cwd=self.path, check=True,
                              capture_output=True, text=True, env={**os.environ, **(env or {})}).stdout.strip()

    def commit(self, subject, files, trailer=None):
        for name, text in files.items():
            target = self.path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            self.git("add", name)
        message = ["-m", subject] + (["-m", f"Test-Red: {trailer}"] if trailer else [])
        self.git("commit", "-q", *message)
        return self.git("rev-parse", "HEAD")


TEST_FILE = "import pathlib, sys\nsys.exit(0 if pathlib.Path('app.py').exists() else 1)\n"
RED_COMMAND = shlex.join([PY, "tests/test_app.py"])


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = None
        self.fresh()

    def tearDown(self):
        self.tmp.cleanup()

    def fresh(self):
        if self.tmp:
            self.tmp.cleanup()
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repo(Path(os.path.realpath(self.tmp.name)) / "repo")

    def branch(self, name):
        self.repo.git("checkout", "-q", "-b", name)

    def check(self, *args, env=None):
        return tdd("check", "--base", "main", *args, cwd=self.repo.path, env=env)

    def tdd_branch(self, name="feat/app", first_files=None, trailer=f"1 {DIGEST} {RED_COMMAND}"):
        self.branch(name)
        first = self.repo.commit("feat: app", first_files or {"tests/test_app.py": TEST_FILE}, trailer)
        self.repo.commit("feat: make it pass", {"app.py": "VALUE = 1\n"})
        return first

    def test_feat_branch_with_a_test_and_a_trailer_passes(self):
        self.tdd_branch()
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ok", result.stdout)

    def test_first_commit_without_a_test_file_is_refused(self):
        self.tdd_branch(first_files={"app.py": "VALUE = 0\n"})
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("changes no test file", result.stdout)

    def test_first_commit_without_a_trailer_is_refused(self):
        self.tdd_branch(trailer=None)
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("has no Test-Red trailer", result.stdout)

    def test_each_missing_part_gets_its_own_line(self):
        self.tdd_branch(first_files={"app.py": "VALUE = 0\n"}, trailer=None)
        result = self.check()
        self.assertEqual(result.returncode, 1)
        problems = [line for line in result.stdout.splitlines() if line.startswith("- ")]
        self.assertEqual(len(problems), 2, result.stdout)

    def test_malformed_trailer_is_refused(self):
        for bad in ("1 not-a-digest cmd", f"0 {DIGEST} {RED_COMMAND}", f"x {DIGEST} {RED_COMMAND}",
                    f"1 {DIGEST}  {RED_COMMAND}"):
            with self.subTest(bad=bad):
                self.fresh()
                self.tdd_branch(trailer=bad)
                result = self.check()
                self.assertEqual(result.returncode, 1)
                self.assertIn("malformed", result.stdout)

    def test_test_file_patterns_per_stack(self):
        module = load_tdd()
        tests =["tests/a.py", "pkg/test/a.go", "web/__tests__/a.js", "spec/a.rb", "test_a.py", "a_test.py",
                 "a.test.ts", "a.spec.tsx", "a.test.mjs", "a.spec.cjs", "a_test.go", "FooTest.java", "FooTests.cs",
                 "FooTest.cs", "a_spec.rb", "run.test.sh", "src/test/java/Foo.java",
                 "Tests/LibTests/LibTests.swift", "Sources/LibTests.swift", "app/tests.py", "app/test.py",
                 "app/src/androidTest/java/FooInstrumented.java", "e2e/login.e2e.ts", "cypress/e2e/login.cy.ts",
                 "FooTest.kt", "FooTests.java", "a.test.mts", "a.spec.cts"]
        others = ["app.py", "src/app.ts", "testing.py", "contest.py", "latest/a.py", "a.test.txt", "README.md",
                  "Sources/Lib.swift", "app/attests.py"]
        for path in tests:
            self.assertTrue(module.is_test_file(path), path)
        for path in others:
            self.assertFalse(module.is_test_file(path), path)
        for path in ("lib/checkout.dart", "src/components/Cart.vue", "src/App.svelte", "src/Main.kts",
                     "lib/app.ex", "test/app_test.exs", "init.lua", "Sources/a.m", "src/a.mts", "src/a.cts",
                     "deploy.ps1"):
            self.assertTrue(module.is_source_file(path), path)
        self.assertTrue(module.is_source_file("db/001.sql"))
        self.assertFalse(module.is_source_file("package-lock.json"))
        self.assertFalse(module.is_source_file("docs/logo.png"))

    def test_test_projects_and_folders_named_the_usual_ways_count_as_tests(self):
        module = load_tdd()
        for path in ("services/Billing.Tests/InvoiceShould.cs", "src/Foo.Tests/FooFacts.cs",
                     "src/Billing.UnitTests/A.cs", "Api.IntegrationTests/B.cs", "integration-tests/a.py",
                     "packages/web/e2e/login.pw.ts", "web/login.pw.ts", "unit_tests/a.py", "specs/a.rb"):
            self.assertTrue(module.is_test_file(path), path)
        for path in ("src/latest/a.py", "src/contest/a.py", "src/Testable/a.cs", "src/protest-app/a.ts"):
            self.assertFalse(module.is_test_file(path), path)

    def test_build_scripts_with_code_suffixes_are_config_not_source(self):
        module = load_tdd()
        for path in ("build.gradle.kts", "app/settings.gradle.kts", "Package.swift", "setup.py", "vite.config.ts",
                     "web/next.config.mjs", ".eslintrc.cjs", "jest.config.js"):
            self.assertFalse(module.is_source_file(path), path)

    def test_dependency_update_branches_are_exempt(self):
        for name, subject, files in (("renovate/kotlin-2.x", "fix(deps): update kotlin to v2", {"build.gradle.kts": "x\n"}),
                                     ("dependabot/npm/lodash-5", "fix(deps): bump lodash", {"app.js": "x\n"}),
                                     ("update-lodash", "fix(deps): bump lodash", {"src/app.ts": "x\n"}),
                                     ("update-kotlin", "fix: bump kotlin", {"build.gradle.kts": "x\n"})):
            with self.subTest(name=name):
                self.fresh()
                self.branch(name)
                self.repo.commit(subject, files)
                result = self.check()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("exempt", result.stdout)

    def test_an_inline_rust_test_counts_as_a_test_change(self):
        self.branch("feat/parse")
        lib = "pub fn two() -> u8 { 2 }\n\n#[cfg(test)]\nmod tests {\n    #[test]\n    fn two_is_two() { assert_eq!(super::two(), 2); }\n}\n"
        self.repo.commit("feat: parse", {"src/lib.rs": lib}, f"1 {DIGEST} {RED_COMMAND}")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.fresh()
        self.branch("feat/parse")
        self.repo.commit("feat: parse", {"src/lib.rs": "pub fn two() -> u8 { 2 }\n"}, f"1 {DIGEST} {RED_COMMAND}")
        self.assertEqual(self.check().returncode, 1)

    def test_docs_and_chore_branches_are_exempt(self):
        for name in ("docs/guide", "chore/deps", "refactor/x", "ci/x", "build/x", "test/x", "revert/x"):
            with self.subTest(name=name):
                self.fresh()
                self.branch(name)
                self.repo.commit("feat: app", {"app.py": "VALUE = 1\n"})
                result = self.check()
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn("exempt", result.stdout)
                self.assertIn(name.split("/")[0], result.stdout)

    def test_diff_without_source_files_is_exempt(self):
        self.branch("feat/docs-only")
        self.repo.commit("feat: describe it", {"README.md": "more\n", "package-lock.json": "{}\n",
                                               "docs/logo.png": "png"})
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("no source file", result.stdout)

    def test_empty_range_is_exempt(self):
        self.branch("feat/nothing")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("no commits", result.stdout)

    def test_conventional_type_decides_when_the_branch_name_says_nothing(self):
        for subject, refused in (("feat(api)!: add", True), ("fix: crash", True), ("docs: words", False),
                                 ("update stuff", False)):
            with self.subTest(subject=subject):
                self.fresh()
                self.branch("topic")
                self.repo.commit(subject, {"app.py": "VALUE = 1\n"})
                result = self.check()
                self.assertEqual(result.returncode, 1 if refused else 0, result.stdout)

    def test_branch_name_comes_from_github_head_ref_then_the_checkout(self):
        self.branch("topic")
        self.repo.commit("work", {"app.py": "VALUE = 1\n"})
        self.assertEqual(self.check(env={"GITHUB_HEAD_REF": "fix/crash"}).returncode, 1)
        self.assertEqual(self.check("--branch", "docs/x", env={"GITHUB_HEAD_REF": "fix/crash"}).returncode, 0)
        self.assertEqual(self.check("--branch", "Fix/Crash").returncode, 1)
        self.repo.git("checkout", "-q", "-b", "bugfix/crash")
        self.assertEqual(self.check().returncode, 1)

    def test_head_option_selects_the_range(self):
        first = self.tdd_branch()
        self.repo.git("checkout", "-q", "main")
        result = self.check("--head", "feat/app", "--branch", "feat/app", "--json")
        self.assertEqual(json.loads(result.stdout)["first_commit"], first)

    def test_verify_passes_when_the_recorded_command_fails_at_the_first_commit(self):
        self.tdd_branch()
        result = self.check("--verify")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_verify_refuses_when_the_recorded_command_passes_at_the_first_commit(self):
        self.tdd_branch(first_files={"tests/test_app.py": TEST_FILE, "app.py": "VALUE = 0\n"})
        result = self.check("--verify")
        self.assertEqual(result.returncode, 1)
        self.assertIn("passes at the first commit", result.stdout)

    def test_verify_refuses_a_command_that_cannot_run(self):
        self.tdd_branch(trailer=f"1 {DIGEST} /nonexistent/no-such-runner")
        result = self.check("--verify")
        self.assertEqual(result.returncode, 1)
        self.assertIn("could not run", result.stdout)

    def state(self):
        return (self.repo.git("status", "--porcelain"), self.repo.git("worktree", "list", "--porcelain"),
                self.repo.git("rev-parse", "HEAD"))

    def private_temp(self):
        scratch = Path(os.path.realpath(self.tmp.name)) / "scratch"
        scratch.mkdir()
        return scratch

    def test_verify_leaves_the_repository_and_temp_dir_unchanged(self):
        self.tdd_branch(first_files={"tests/test_app.py": TEST_FILE, "app.py": "VALUE = 0\n"})
        (self.repo.path / "scratch.txt").write_text("untracked\n")
        scratch = self.private_temp()
        before = self.state()
        for _ in range(2):
            self.check("--verify", env={"TMPDIR": str(scratch)})
        self.assertEqual(before, self.state())
        self.assertEqual(list(scratch.iterdir()), [])

    def test_verify_keeps_other_worktrees_even_when_prunable(self):
        self.tdd_branch()
        extra = Path(os.path.realpath(self.tmp.name)) / "extra"
        self.repo.git("worktree", "add", "-q", "--detach", str(extra), "main")
        extra.rename(extra.with_name("moved"))
        before = self.state()
        self.assertIn("prunable", before[1])
        self.assertEqual(self.check("--verify").returncode, 0)
        self.assertEqual(before, self.state())

    @unittest.skipUnless(HAS_PROC, "needs /proc")
    def test_sigterm_during_verify_stops_the_command_and_removes_the_worktree(self):
        pid_file = Path(os.path.realpath(self.tmp.name)) / "pid"
        self.tdd_branch(trailer=f"1 {DIGEST} {shlex.join(sleeper(pid_file))}")
        scratch = self.private_temp()
        before = self.state()
        proc = subprocess.Popen([PY, str(SCRIPT), "check", "--base", "main", "--verify"], cwd=self.repo.path,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=tdd_env({"TMPDIR": str(scratch)}))
        child = read_pid(pid_file)
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 2, out + err)
        self.assertIn("interrupted", err)
        self.assertTrue(gone_within(child), "the recorded command outlived SIGTERM")
        self.assertEqual(before, self.state())
        self.assertEqual(list(scratch.iterdir()), [])

    def test_verify_runs_a_red_run_recorded_in_a_subdirectory_there(self):
        for cheat, expected in ((False, 0), (True, 1)):
            with self.subTest(cheat=cheat):
                self.fresh()
                self.branch("feat/api")
                api = self.repo.path / "packages" / "api"
                files = {"packages/api/tests/test_app.py": TEST_FILE}
                for name, text in files.items():
                    (self.repo.path / name).parent.mkdir(parents=True, exist_ok=True)
                    (self.repo.path / name).write_text(text)
                red = tdd("red", "--", PY, "tests/test_app.py", cwd=api)
                self.assertEqual(red.returncode, 0, red.stderr)
                if cheat:
                    files["packages/api/app.py"] = "VALUE = 1\n"
                self.repo.commit("feat: api", files, red.stdout.strip().split(": ", 1)[1])
                result = self.check("--verify")
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                if cheat:
                    self.assertIn("passes at the first commit", result.stdout)

    def test_pull_request_merge_commit_is_read_through_the_pull_request_head(self):
        first = self.tdd_branch()
        self.repo.git("checkout", "-q", "main")
        self.repo.commit("chore: main moved", {"notes.md": "x\n"})
        self.repo.git("checkout", "-q", "--detach", "main")
        self.repo.git("merge", "-q", "--no-ff", "-m", "Merge feat/app into main", "feat/app")
        payload = json.loads(self.check("--branch", "feat/app", "--json").stdout)
        self.assertEqual((payload["result"], payload["first_commit"]), ("ok", first), payload)

    def test_merges_from_base_are_skipped_when_finding_the_first_commit(self):
        self.branch("feat/app")
        self.repo.git("checkout", "-q", "main")
        self.repo.commit("chore: main moved", {"notes.md": "x\n"})
        self.repo.git("checkout", "-q", "feat/app")
        self.repo.git("merge", "-q", "--no-ff", "-m", "Merge main", "main")
        first = self.repo.commit("feat: app", {"tests/test_app.py": TEST_FILE}, f"1 {DIGEST} {RED_COMMAND}")
        self.repo.commit("feat: make it pass", {"app.py": "VALUE = 1\n"})
        self.repo.git("checkout", "-q", "main")
        self.repo.commit("chore: main moved again", {"more.md": "y\n"})
        self.repo.git("checkout", "-q", "feat/app")
        self.repo.git("merge", "-q", "--no-ff", "-m", "Merge main again", "main")
        payload = json.loads(self.check("--json").stdout)
        self.assertEqual((payload["result"], payload["first_commit"]), ("ok", first), payload)

    def test_commits_merged_in_from_a_side_branch_are_not_the_first_commit(self):
        self.branch("side")
        self.repo.commit("side work", {"lib.py": "X = 1\n"})
        old = "2001-01-01T00:00:00Z"
        self.repo.git("commit", "-q", "--amend", "--no-edit", "--date", old, env={"GIT_COMMITTER_DATE": old})
        self.repo.git("checkout", "-q", "main")
        first = self.tdd_branch()
        self.repo.git("merge", "-q", "--no-ff", "-m", "Merge side", "side")
        payload = json.loads(self.check("--json").stdout)
        self.assertEqual((payload["result"], payload["first_commit"]), ("ok", first), payload)

    def test_source_change_on_main_does_not_end_a_docs_only_exemption(self):
        self.branch("feat/docs")
        self.repo.commit("feat: describe it", {"README.md": "more\n"})
        self.repo.git("checkout", "-q", "main")
        self.repo.commit("feat: code on main", {"app.py": "VALUE = 1\n"})
        result = self.check("--head", "feat/docs", "--branch", "feat/docs")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("no source file", result.stdout)

    def test_deleting_a_test_file_is_not_adding_one(self):
        self.repo.commit("chore: old test", {"tests/test_old.py": "pass\n"})
        self.branch("fix/x")
        self.repo.git("rm", "-q", "tests/test_old.py")
        self.repo.commit("fix: x", {"app.py": "VALUE = 1\n"}, f"1 {DIGEST} {RED_COMMAND}")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("changes no test file", result.stdout)

    def test_the_first_test_red_trailer_is_the_one_read(self):
        for trailers, expected in (((f"1 {DIGEST} {RED_COMMAND}", "bad"), 0), (("bad", f"1 {DIGEST} {RED_COMMAND}"), 1)):
            with self.subTest(trailers=trailers):
                self.fresh()
                self.branch("feat/app")
                (self.repo.path / "tests").mkdir()
                (self.repo.path / "tests" / "test_app.py").write_text(TEST_FILE)
                self.repo.git("add", "tests/test_app.py")
                self.repo.git("commit", "-q", "-m", "feat: app", "-m", "\n".join(f"Test-Red: {t}" for t in trailers))
                self.assertEqual(self.check().returncode, expected)

    def test_feature_segment_anywhere_in_a_nested_branch_name_counts(self):
        for name, subject, expected in (("alice/feat/x", "add thing", 1), ("users/alice/fix/bug", "add thing", 1),
                                        ("alice/docs/x", "feat: x", 0), ("team/topic", "add thing", 0),
                                        ("fix", "add thing", 0), ("x/docs", "feat: x", 1)):
            with self.subTest(name=name):
                self.fresh()
                self.branch(name)
                self.repo.commit(subject, {"app.py": "VALUE = 1\n"})
                result = self.check()
                self.assertEqual(result.returncode, expected, result.stdout)

    def test_a_feat_commit_after_a_test_first_commit_makes_the_branch_feature_work(self):
        self.branch("topic")
        self.repo.commit("test: app", {"tests/test_app.py": TEST_FILE})
        self.repo.commit("feat: app", {"app.py": "VALUE = 1\n"})
        for checkout in ("topic", "--detach"):
            with self.subTest(checkout=checkout):
                self.repo.git("checkout", "-q", checkout)
                result = self.check()
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("has no Test-Red trailer", result.stdout)

    def test_a_branch_of_test_commits_only_stays_exempt(self):
        self.branch("topic")
        self.repo.commit("test: app", {"tests/test_app.py": TEST_FILE})
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("exempt", result.stdout)

    def test_detached_checkout_has_no_branch_name(self):
        self.tdd_branch(trailer=None)
        self.repo.git("checkout", "-q", "--detach")
        self.assertIn("on (detached)", self.check().stdout)
        self.assertEqual(json.loads(self.check("--json").stdout)["branch"], "")

    def test_a_test_red_line_pasted_under_prose_is_read(self):
        self.branch("feat/app")
        (self.repo.path / "tests").mkdir()
        (self.repo.path / "tests" / "test_app.py").write_text(TEST_FILE)
        self.repo.git("add", "tests/test_app.py")
        self.repo.git("commit", "-q", "-m", "feat: app",
                      "-m", f"Adds the failing test.\nTest-Red: 1 {DIGEST} {RED_COMMAND}")
        result = self.check("--verify")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_plain_check_never_runs_the_recorded_command(self):
        marker = Path(os.path.realpath(self.tmp.name)) / "ran"
        command = shlex.join(py_command(f"import pathlib; pathlib.Path({str(marker)!r}).touch()"))
        self.tdd_branch(trailer=f"1 {DIGEST} {command}")
        self.assertEqual(self.check().returncode, 0)
        self.assertFalse(marker.exists(), "plain check ran the command taken from the commit")
        self.assertEqual(self.check("--verify").returncode, 1)
        self.assertTrue(marker.exists())

    def test_verify_runs_no_repository_hook(self):
        self.tdd_branch()
        marker = Path(os.path.realpath(self.tmp.name)) / "hook-ran"
        hook = self.repo.path / ".git" / "hooks" / "post-checkout"
        hook.write_text(f"#!/bin/sh\ntouch {shlex.quote(str(marker))}\nexit 1\n")
        hook.chmod(0o755)
        result = self.check("--verify")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(marker.exists(), "a repository hook ran during --verify")

    def test_verify_finds_the_checkouts_ignored_tools_but_not_its_caches(self):
        self.repo.commit("chore: ignore", {".gitignore": "node_modules/\n.pytest_cache/\n"})
        runner = self.repo.path / "node_modules" / ".bin" / "runner"
        runner.parent.mkdir(parents=True)
        runner.write_text("#!/bin/sh\n[ -e .pytest_cache ] && exit 0\nexec .venv/bin/run tests/test_app.py\n")
        runner.chmod(0o755)
        venv_run = self.repo.path / ".venv" / "bin" / "run"
        venv_run.parent.mkdir(parents=True)
        (self.repo.path / ".venv" / ".gitignore").write_text("*\n")
        venv_run.write_text(f"#!/bin/sh\nexec {shlex.quote(PY)} \"$@\"\n")
        venv_run.chmod(0o755)
        (self.repo.path / ".pytest_cache").mkdir()
        (self.repo.path / ".pytest_cache" / "lastfailed").write_text("{}\n")
        self.tdd_branch(trailer=f"1 {DIGEST} node_modules/.bin/runner")
        scratch = self.private_temp()
        before = self.state()
        result = self.check("--verify", env={"TMPDIR": str(scratch)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, self.state())
        self.assertEqual(list(scratch.iterdir()), [])
        self.assertTrue(runner.exists() and venv_run.exists(), "cleanup removed the checkout's own dependencies")

    def test_verify_imports_the_first_commits_code_over_an_editable_install(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        venv = Path(os.path.realpath(holder.name)) / "venv"
        made = subprocess.run([PY, "-m", "venv", "--without-pip", str(venv)], capture_output=True, text=True)
        if made.returncode != 0:
            self.skipTest(f"venv unavailable: {made.stderr.strip()[:200]}")
        site = next(venv.glob("lib/python*/site-packages"))
        test = "import sys\ntry:\n    import pkg.r\nexcept ImportError:\n    sys.exit(1)\n"
        command = shlex.join([str(venv / "bin" / "python"), "tests/test_r.py"])
        for layout in ("src", "flat"):
            package = "src/pkg" if layout == "src" else "pkg"
            for on_pythonpath in (False, True):
                with self.subTest(layout=layout, on_pythonpath=on_pythonpath):
                    self.fresh()
                    installed = self.repo.path / "src" if layout == "src" else self.repo.path
                    env = {"PYTHONPATH": str(installed)} if on_pythonpath else {}
                    (site / "editable.pth").write_text(f"{installed}\n")
                    self.repo.commit("chore: package", {f"{package}/__init__.py": ""})
                    self.branch("feat/r")
                    self.repo.commit("feat: r", {"tests/test_r.py": test}, f"1 {DIGEST} {command}")
                    self.repo.commit("feat: make it pass", {f"{package}/r.py": "VALUE = 1\n"})
                    result = self.check("--verify", env=env)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_verify_timeout_refuses_and_cleans_up(self):
        self.tdd_branch(trailer=f"1 {DIGEST} {shlex.join(py_command('import time; time.sleep(30)'))}")
        scratch = self.private_temp()
        before = self.state()
        result = self.check("--verify", "--timeout", "1", env={"TMPDIR": str(scratch)})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("timed out", result.stdout)
        self.assertEqual(before, self.state())
        self.assertEqual(list(scratch.iterdir()), [])

    def test_cleanup_removes_a_worktree_whose_git_file_was_never_written(self):
        module = load_tdd()
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.repo.path)
        before = self.state()
        holder = Path(tempfile.mkdtemp(prefix="tdd-verify-", dir=self.private_temp()))
        worktree = holder / holder.name
        self.repo.git("worktree", "add", "-q", "--detach", str(worktree), "main")
        (worktree / ".git").unlink()
        module.remove_worktree(str(holder))
        self.assertEqual(before, self.state())
        self.assertFalse(holder.exists())

    def test_json_shape(self):
        first = self.tdd_branch(trailer=None)
        payload = json.loads(self.check("--json").stdout)
        self.assertEqual(set(payload), {"result", "branch", "first_commit", "problems", "exempt_reason"})
        self.assertEqual((payload["result"], payload["branch"], payload["first_commit"]),
                         ("refused", "feat/app", first))
        self.assertEqual(len(payload["problems"]), 1)
        self.assertIsNone(payload["exempt_reason"])
        self.repo.git("checkout", "-q", "-b", "docs/x")
        payload = json.loads(self.check("--json").stdout)
        self.assertEqual((payload["result"], payload["problems"]), ("exempt", []))
        self.assertIn("docs", payload["exempt_reason"])

    def test_usage_and_git_errors_exit_2(self):
        self.assertIn("usage", tdd("check", cwd=self.repo.path).stderr)
        for result in (self.check("--head", "no-such-ref"), tdd("check", "--base", "no-such-ref", cwd=self.repo.path)):
            self.assertEqual(result.returncode, 2)
            self.assertIn("git", result.stderr)
        outside = Path(os.path.realpath(self.tmp.name)) / "plain"
        outside.mkdir()
        self.assertEqual(tdd("check", "--base", "main", cwd=outside, env={"GIT_CEILING_DIRECTORIES":
                                                                          str(outside.parent)}).returncode, 2)


if __name__ == "__main__":
    unittest.main()
