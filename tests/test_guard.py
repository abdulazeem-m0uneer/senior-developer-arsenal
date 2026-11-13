import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "hooks" / "guard.py"

sys.path.insert(0, str(SCRIPT.parent))
import guard  # noqa: E402


def git(cwd, *args, env=None):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                   capture_output=True, env={**os.environ, **(env or {})})


BEFORE_THE_SESSION = {"GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z"}


class GuardCase(unittest.TestCase):
    """A git repository with one commit and one pre-existing dirty source file; state lives outside it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(os.path.realpath(self.tmp.name))
        git(self.dir, "init", "-q")
        self.write("README.md", "x")
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-qm", "init")
        self.write("legacy.py", "dirty before the session")
        self.outside = tempfile.TemporaryDirectory()
        self.state = Path(self.outside.name) / "snap.guard.jsonl"

    def tearDown(self):
        self.tmp.cleanup()
        self.outside.cleanup()

    def write(self, name, text="x"):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def run_hook(self, cmd, payload=None, cwd=None, env=None):
        stdin = payload if isinstance(payload, str) else json.dumps(payload or {})
        base = {**os.environ, "HANDOFF_SNAPSHOT": str(Path(self.outside.name) / "snap.md")}
        for name in ("ARSENAL_GUARD", "ARSENAL_GUARD_DESTRUCTIVE", "ARSENAL_RUN_LIMITS", "CLAUDE_PROJECT_DIR"):
            base.pop(name, None)  # the developer's own session must not leak into the hook under test
        result = subprocess.run([sys.executable, str(SCRIPT), cmd], cwd=cwd or self.dir, input=stdin,
                                capture_output=True, text=True, env={**base, **(env or {})})
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def start(self, source="startup"):
        self.assertEqual(self.run_hook("baseline", {"source": source}), "")

    def stop(self, **kwargs):
        out = self.run_hook("stop", kwargs.pop("payload", {"stop_hook_active": False}), **kwargs)
        return json.loads(out)["reason"] if out else ""

    def bash(self, command, failed=False, **extra):
        event = "PostToolUseFailure" if failed else "PostToolUse"
        payload = {"hook_event_name": event, "tool_name": "Bash", "tool_input": {"command": command}, **extra}
        self.assertEqual(self.run_hook("track", payload), "")


class TestGateTest(GuardCase):
    def test_code_only_change_blocks_once_with_valid_json(self):
        self.start()
        self.write("src/app.py")
        out = self.run_hook("stop", {"stop_hook_active": False})
        block = json.loads(out)
        self.assertEqual(block["decision"], "block")
        self.assertIn("src/app.py", block["reason"])
        self.assertIn("no test applies", block["reason"])
        self.assertLess(len(block["reason"]), 700)
        self.assertEqual(self.stop(), "")  # same situation: the "no test applies" answer ends it

    def test_baseline_excludes_files_dirty_before_the_session(self):
        self.start()
        self.write("legacy.py", "edited again")
        self.assertEqual(self.stop(), "")

    def test_only_new_files_are_named_after_an_earlier_block(self):
        self.start()
        self.write("a.py")
        self.assertIn("a.py", self.stop())
        self.write("b.py")
        reason = self.stop()
        self.assertIn("b.py", reason)
        self.assertNotIn("a.py", reason)

    def test_code_with_test_change_passes(self):
        self.start()
        self.write("src/app.py")
        self.write("tests/test_app.py")
        self.assertEqual(self.stop(), "")

    def test_docs_config_and_generated_changes_pass(self):
        self.start()
        for name in ("docs/guide.md", "config.yaml", "package-lock.json", "dist/app.js", "vendor/lib/x.go"):
            self.write(name)
        self.assertEqual(self.stop(), "")

    def test_committed_changes_since_baseline_are_seen(self):
        self.start()
        self.write("src/app.py")
        git(self.dir, "add", "src/app.py")
        git(self.dir, "commit", "-qm", "feat")
        self.assertIn("src/app.py", self.stop())

    def test_staged_change_and_subdirectory_cwd_are_seen(self):
        self.start()
        self.write("src/app.py")
        self.write("src/deep/x.txt")
        git(self.dir, "add", "src/app.py")
        self.assertIn("src/app.py", self.stop(cwd=self.dir / "src" / "deep"))

    def test_names_at_most_eight_files(self):
        self.start()
        for index in range(11):
            self.write(f"m{index:02}.py")
        reason = self.stop()
        self.assertIn("m07.py", reason)
        self.assertNotIn("m08.py", reason)
        self.assertIn("(+3 more)", reason)

    def test_repository_without_commits(self):
        fresh = tempfile.TemporaryDirectory()
        self.addCleanup(fresh.cleanup)
        git(fresh.name, "init", "-q")
        (Path(fresh.name) / "old.py").write_text("x")
        self.run_hook("baseline", {"source": "startup"}, cwd=fresh.name)
        (Path(fresh.name) / "new.py").write_text("x")
        reason = self.stop(cwd=fresh.name)
        self.assertIn("new.py", reason)
        self.assertNotIn("old.py", reason)

    def test_compact_keeps_the_baseline_and_restart_replaces_it(self):
        self.start()
        self.write("src/app.py")
        self.start("compact")
        self.assertIn("src/app.py", self.stop())
        self.write("src/other.py")
        self.start("resume")
        self.assertEqual(self.stop(), "")

    def test_history_rewritten_under_the_baseline_fails_open(self):
        self.start()
        git(self.dir, "checkout", "-q", "--orphan", "other")
        self.write("src/app.py")
        self.assertEqual(self.stop(), "")

    def test_a_branch_that_was_already_ahead_fails_open(self):
        git(self.dir, "checkout", "-qb", "feat")
        self.write("big.py")
        git(self.dir, "add", "big.py")
        git(self.dir, "commit", "-qm", "earlier work", env=BEFORE_THE_SESSION)
        git(self.dir, "checkout", "-q", "-")
        self.start()
        git(self.dir, "checkout", "-q", "feat")
        self.assertEqual(self.stop(), "")

    def test_a_branch_created_and_committed_in_the_session_is_still_gated(self):
        self.start()
        git(self.dir, "checkout", "-qb", "feat")
        self.write("src/app.py")
        git(self.dir, "add", "src/app.py")
        git(self.dir, "commit", "-qm", "feat")
        self.assertIn("src/app.py", self.stop())

    def test_another_working_tree_fails_open(self):
        linked = Path(self.outside.name) / "linked"
        git(self.dir, "worktree", "add", "-q", str(linked))
        self.start()
        (linked / "w.py").write_text("x")
        self.assertEqual(self.stop(cwd=linked), "")

    def test_a_baseline_without_root_or_time_fails_open(self):
        self.start()
        base = json.loads(self.state.read_text())
        self.write("src/app.py")
        git(self.dir, "add", "src/app.py")
        git(self.dir, "commit", "-qm", "feat")
        failure = json.dumps({"event": "fail", "command": "pytest"})
        for dropped in ("root", "time"):
            partial = {key: value for key, value in base.items() if key != dropped}
            self.state.write_text(f"{json.dumps(partial)}\n{failure}\n")
            reason = self.stop()
            self.assertIn("pytest", reason, dropped)  # the lesson gate does not depend on the baseline
            self.assertNotIn("src/app.py", reason, dropped)

    def test_deleting_renaming_or_changing_the_mode_of_a_file_is_not_a_change(self):
        for name in ("gone.py", "old.py", "mode.py", "tests/test_gone.py"):
            self.write(name, "print('a line long enough for rename detection')\n" * 5)
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-qm", "files")
        self.start()
        git(self.dir, "rm", "-q", "gone.py", "tests/test_gone.py")
        git(self.dir, "mv", "old.py", "new.py")
        os.chmod(self.dir / "mode.py", 0o755)
        self.assertEqual(self.stop(), "")

    def test_a_deleted_test_does_not_count_as_a_test_change(self):
        self.write("tests/test_app.py")
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-qm", "test")
        self.start()
        git(self.dir, "rm", "-q", "tests/test_app.py")
        self.write("src/app.py")
        self.assertIn("src/app.py", self.stop())

    def test_a_rename_with_edits_is_named_by_its_new_path(self):
        body = "".join(f"line {n} of a file long enough for rename detection\n" for n in range(20))
        self.write("old.py", body)
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-qm", "file")
        self.start()
        git(self.dir, "mv", "old.py", "new.py")
        self.write("new.py", body + "changed = True\n")
        reason = self.stop()
        self.assertIn("new.py", reason)
        self.assertNotIn("old.py", reason)

    def test_gitignored_files_are_not_changes(self):
        self.write(".gitignore", "cache/\n")
        self.start()
        self.write("cache/built.py")
        self.assertEqual(self.stop(), "")

    def test_names_git_would_quote_are_named_verbatim(self):
        self.start()
        names = ["my file.py", "na\u00efve.py", *(['q"uote.py'] if os.name == "posix" else [])]
        for name in names:
            self.write(name)
        reason = self.stop()
        for name in names:
            self.assertIn(name, reason)

    def test_unknown_is_not_the_same_as_unchanged(self):
        original = guard.git_fields
        self.addCleanup(setattr, guard, "git_fields", original)
        for failing in ("diff", "--others"):
            guard.git_fields = lambda root, *args, failing=failing: None if failing in args else original(root, *args)
            self.assertIsNone(guard.changed_paths(str(self.dir), "HEAD"), failing)
        guard.git_fields = original
        self.assertEqual(guard.changed_paths(str(self.dir), "HEAD"), {"legacy.py"})


class FailOpenTest(GuardCase):
    def test_stop_hook_active_passes(self):
        self.start()
        self.write("src/app.py")
        self.assertEqual(self.stop(payload={"stop_hook_active": True}), "")
        self.assertIn("src/app.py", self.stop())  # and it was not counted as asked

    def test_opt_out_env(self):
        self.start()
        self.write("src/app.py")
        self.bash("pytest -q", failed=True)
        self.assertEqual(self.stop(env={"ARSENAL_GUARD": "off"}), "")
        self.assertEqual(self.stop(env={"ARSENAL_GUARD": " OFF "}), "")

    def test_outside_a_repository(self):
        plain = tempfile.TemporaryDirectory()
        self.addCleanup(plain.cleanup)
        (Path(plain.name) / "app.py").write_text("x")
        self.bash("pytest -q", failed=True)
        for cmd in ("baseline", "stop"):
            self.assertEqual(self.run_hook(cmd, {"source": "startup"}, cwd=plain.name), "")
        self.assertNotIn("baseline", self.state.read_text())

    def test_unusable_state_path_never_fails_the_session(self):
        self.write("src/app.py")
        target = Path(self.outside.name) / "target"
        blockers = [self.state.mkdir, *([lambda: self.state.symlink_to(target)] if os.name == "posix" else [])]
        for make in blockers:
            make()
            for cmd in ("baseline", "track", "stop"):
                payload = {"source": "startup", "hook_event_name": "PostToolUseFailure",
                           "tool_input": {"command": "pytest"}}
                self.assertEqual(self.run_hook(cmd, payload), "")  # run_hook asserts exit 0
            if self.state.is_symlink():
                self.assertFalse(target.exists())  # never written through a link someone planted
                self.state.unlink()
            else:
                self.state.rmdir()

    def test_garbage_stdin_and_unknown_command(self):
        for cmd in ("baseline", "track", "stop", "nonsense"):
            for payload in ("not json", "[1, 2]", '{"tool_input": 5, "stop_hook_active": "x"}', ""):
                self.assertEqual(self.run_hook(cmd, payload), "")

    def test_without_session_id_nothing_is_recorded_or_blocked(self):
        self.write("src/app.py")
        env = {"HANDOFF_SNAPSHOT": "", "TMPDIR": self.outside.name}
        for cmd in ("baseline", "track", "stop"):
            self.assertEqual(self.run_hook(cmd, {"source": "startup"}, env=env), "")
        self.assertEqual(os.listdir(self.outside.name), [])

    def test_git_missing_passes(self):
        self.start()
        self.write("src/app.py")
        self.assertEqual(self.stop(env={"PATH": ""}), "")

    def test_no_baseline_means_no_test_gate(self):
        self.write("src/app.py")
        self.assertEqual(self.stop(), "")

    def test_damaged_state_lines_are_ignored(self):
        self.start()
        with open(self.state, "a") as out:
            out.write("{broken\n[1]\n" + json.dumps({"event": "asked", "files": 7}) + "\n")
        self.write("src/app.py")
        self.assertIn("src/app.py", self.stop())

    def test_state_file_is_private_and_outside_the_repo(self):
        self.start()
        if os.name == "posix":
            self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
        self.assertEqual(subprocess.run(["git", "status", "--short"], cwd=self.dir, capture_output=True,
                                        text=True).stdout.strip(), "?? legacy.py")


class LessonGateTest(GuardCase):
    def test_failed_check_asks_for_a_lesson_once(self):
        self.start()
        self.bash("cd api && python3 -m pytest -q", failed=True, error="Exit code 1", is_interrupt=False)
        reason = self.stop()
        self.assertIn("1 test/build/lint command(s) failed", reason)
        self.assertIn("cd api && python3 -m pytest -q", reason)
        self.assertRegex(reason, r'lessons\.py" add --tags a,b --mistake "\.\.\." --cause "\.\.\." --rule "\.\.\."')
        self.assertEqual(self.stop(), "")  # "nothing was learned" ends it
        self.bash("npm test", failed=True)
        self.assertIn("1 test/build/lint command(s) failed", self.stop())  # a new failure is a new situation

    def test_recorded_lesson_clears_the_failures(self):
        self.start()
        self.bash("npm test", failed=True)
        self.bash("go test ./...", failed=True)
        self.bash(f'python3 "{guard.LESSONS}" add --tags js --mistake m --cause c --rule r')
        self.assertEqual(self.stop(), "")
        self.bash("npm test", failed=True)
        self.bash("python .agents/skills/lessons-learned/scripts/lessons.py --file x.md bump L001")
        self.assertEqual(self.stop(), "")

    def test_lesson_command_forms(self):
        recorded = ['python3 lessons.py --file "my x.md" add --tags a', "python3 lessons.py --file 'a b.md' bump 1",
                    'cd repo && python3 "/plugin dir/lessons.py" add --tags js', "./lessons.py --file=x.md add",
                    "uv run python lessons.py add --tags a", "/usr/bin/python3 -B lessons.py bump L001"]
        not_recorded = ["echo lessons.py add", 'grep -n "lessons.py add" README.md', "lessons.py add --help",
                        "python3 lessons.py add -h", "python3 lessons.py search add", "cat lessons.py add"]
        for command in recorded:
            self.assertTrue(guard.LESSON_COMMAND.search(command), command)
        for command in not_recorded:
            self.assertFalse(guard.LESSON_COMMAND.search(command), command)

    def test_failed_or_read_only_lesson_command_does_not_clear(self):
        self.start()
        self.bash("npm test", failed=True)
        self.bash("python3 lessons.py add --tags js", failed=True)
        self.bash("python3 lessons.py active")
        self.bash("python3 lessons.py search add")
        self.assertIn("npm test", self.stop())

    def test_other_failures_interrupts_and_passing_checks_are_not_counted(self):
        self.start()
        self.bash("grep -n pytest setup.cfg", failed=True)
        self.bash("ls missing", failed=True)
        self.bash("pytest -q", failed=True, is_interrupt=True)
        self.assertEqual(self.stop(), "")

    def test_a_pass_hidden_by_a_pipe_or_a_non_run_does_not_clear_a_failure(self):
        for hiding in ("pytest -q 2>&1 | tail -5", "pytest --version", "pytest || true", "pytest; echo done",
                       "pytest -q &"):
            self.start()
            self.bash("pytest -q", failed=True)
            self.bash(hiding)
            self.assertIn("pytest", self.stop(), hiding)

    def test_a_pass_that_decides_the_exit_status_still_clears(self):
        for deciding in ("pytest -q 2>&1", "pytest -q && echo ok", "pytest -q;", "cd api && pytest -q\n"):
            self.start()
            self.bash("pytest -q", failed=True)
            self.bash(deciding)
            self.assertEqual(self.stop(), "", deciding)

    def test_ruff_format_does_not_clear_a_failed_ruff_check(self):
        self.start()
        self.bash("ruff check .", failed=True)
        self.bash("ruff format .")
        self.assertIn("ruff check", self.stop())

    def test_a_check_that_goes_green_again_is_not_asked_about(self):
        self.start()
        self.bash("python3 -m pytest tests/test_new.py -x", failed=True)  # red first
        self.bash("cd api && timeout 60 pytest -q")  # green: other flags, paths and wrappers, the same check
        self.assertEqual(self.stop(), "")
        self.assertNotIn("pytest", self.state.read_text().split('"pass"')[1].split("checks")[0])  # no command text kept

    def test_a_check_still_red_at_stop_asks_once(self):
        self.start()
        self.bash("npm test", failed=True)
        self.bash("npm run test -- --watch=false")  # green
        self.bash("npm test", failed=True)  # red again after the green run
        self.bash("go test ./...", failed=True)
        self.bash("go vet ./...")  # another check passing clears nothing
        reason = self.stop()
        self.assertIn("2 test/build/lint command(s) failed", reason)
        self.assertIn("did not pass again", reason)
        self.assertEqual(self.stop(), "")
        self.bash("go test ./...")
        self.assertEqual(self.stop(), "")

    def test_a_command_with_several_checks_needs_each_of_them_green(self):
        self.start()
        self.bash("ruff check . && pytest -q", failed=True)
        self.bash("pytest -q")
        self.assertIn("ruff check . && pytest -q", self.stop())  # ruff may have been the red one
        self.bash("ruff check . && pytest -q", failed=True)
        self.bash("pytest -q")
        self.bash("ruff check src")
        self.assertEqual(self.stop(), "")

    def test_scripts_are_separate_checks_and_old_state_lines_still_count(self):
        self.start()
        self.bash("python3 tests/test_a.py", failed=True)
        self.bash("python tests/test_b.py")
        self.assertIn("tests/test_a.py", self.stop())
        self.bash(".venv/bin/python tests/test_a.py", failed=True)
        self.bash("python3 tests/test_a.py -v")
        self.assertEqual(self.stop(), "")
        with self.state.open("a") as handle:  # a failure recorded before checks were named
            handle.write(json.dumps({"event": "fail", "command": "make test"}) + "\n")
        self.bash("make test")
        self.assertIn("make test", self.stop())

    def test_both_gates_combine_into_one_block(self):
        self.start()
        self.write("src/app.py")
        self.bash("dotnet test", failed=True)
        reason = self.stop()
        self.assertIn("src/app.py", reason)
        self.assertIn("dotnet test", reason)
        self.assertLess(len(reason), 900)
        self.assertEqual(self.stop(), "")

    def test_long_command_is_clipped(self):
        self.start()
        self.bash("pytest " + "x" * 500, failed=True)
        self.assertLess(len(self.stop()), 700)


class ClassificationTest(unittest.TestCase):
    def test_paths(self):
        expected = {
            "test": ["tests/test_app.py", "pkg/app_test.go", "src/app.test.ts", "src/app.spec.tsx", "test_app.py",
                     "src/__tests__/app.js", "Api.Tests/OrderTests.cs", "src/OrderServiceTest.java", "spec/user_spec.rb",
                     "e2e/login.ts", "app/tests.py", "conftest.py", "tests/helpers.py", "UnitTests/Helper.cs",
                     "test_foo.cpp", "test_foo.rb", "src/tests.rs", "test.js", "src/foo.cy.ts", "src/FooTest.tsx",
                     "src/__mocks__/a.ts", "testdata/x.go", "tests.unit/a.py", "spec/spec_helper.rb",
                     # anything under a test directory, whatever its extension
                     "tests/data/case.json", "tests/fixtures/case.json", "tests/smoke.sh", "tests/a.bats",
                     "tests/conf.py"],
            "source": ["src/app.py", "cmd/main.go", "src/app.tsx", "Api/Order.cs", "lib/user.rb", "src/main.rs",
                       "scripts/build.py", "src/latest.py", "src/contest.ts", "contests/a.py", "Audit.java",
                       "src/spec/openapi.py", "pkg/testing/helpers.go", "src/Latest.tsx", ".agents/skills/x/a.py",
                       "cmd/setup.go",
                       # build, out and target are ignored only at the top level
                       "src/build/compile.ts", "internal/build/x.go", "app/out/handler.py"],
            None: ["README.md", "docs/a.md", "package.json", "config.yaml", "poetry.lock", "go.sum", "Makefile",
                   "dist/app.js", "vendor/x/y.go", "node_modules/a/b.js", "app.min.js", "types.d.ts", "api_pb2.py",
                   "db/migrations/0001_init.py", "install.sh", "schema.sql", "py", "styles.css", "obj/Debug/A.cs",
                   "build/gen.py", "target/debug/x.rs", "out/a.js", "node_modules/x/test/a.js",
                   # config and tooling written in a code language
                   "vite.config.ts", "jest.config.js", "eslint.config.mjs", "setup.py", "docs/conf.py", "noxfile.py",
                   "gulpfile.js",
                   ".storybook/main.ts", "src/Button.stories.tsx", ".eslintrc.js"],
        }
        for want, paths in expected.items():
            for path in paths:
                self.assertEqual(guard.kind(path), want, path)

    def test_commands(self):
        checks = ["pytest", "python3 -m pytest -q tests", "python -m unittest discover -s tests", "npm test",
                  "npm run test:unit", "pnpm test", "yarn test", "yarn jest src", "npx vitest run", "npx jest",
                  "dotnet test", "dotnet build -c Release", "go test ./...", "cargo test", "mvn -q test",
                  "./gradlew test", "make test", "make check", "ruff check .", "mypy src", "npx eslint .",
                  "npx tsc --noEmit", "gh run watch", "gh pr checks --watch", "cd api && npm test",
                  "CI=1 npm test", "uv run pytest", "node_modules/.bin/jest", "(cd web; pnpm run lint)",
                  "git add -A\npytest -q",
                  # wrappers, options before the script name, more tools, scripts that are checks
                  "timeout 60 pytest", "env X=1 pytest", "nice -n 5 pytest", "if ! pytest; then echo no; fi",
                  "docker compose run --rm app pytest", "make -C d test", "pnpm -r test", "npm --prefix web test",
                  "yarn workspace web test", "mvn clean install", "mvn -q package", "cargo nextest run",
                  "deno test", "pre-commit run -a", "rails test", "php artisan test", "python3 tests/test_x.py",
                  "bash tests/smoke.sh", "python3 scripts/build.py --check", "git log --grep=test | ruff"]
        others = ["ls", "git status", "grep -rn pytest .", "cat jest.config.js", "echo npm test", "npm install",
                  "pip install pytest", "python3 app.py", "git commit -m 'make test pass'", "vim tsconfig.json",
                  "gh pr view", "go run .", "cargo fmt", "", None, 5,
                  # text inside a quoted argument is not a command
                  "git commit -m 'fix; npm test'", 'git commit -m "wip; pytest"', "grep 'foo|pytest bar' f",
                  "npm install jest", "npm --version", "make install", "python3 scripts/latest.py", "node server.js",
                  "python3 contest.py --verbose", "python3 app.py --checkpoint x", "cat tests/test_x.py", "which pytest"]
        for command in checks:
            self.assertTrue(guard.is_check_command(command), command)
        for command in others:
            self.assertFalse(guard.is_check_command(command), command)

    def test_check_names_ignore_wrappers_flags_and_paths(self):
        same = {"pytest": ["pytest", "pytest -q tests/a.py", "cd api && python3 -m pytest -x", "uv run pytest",
                           "timeout 60 .venv/bin/pytest -k x", "env FOO=1 pytest"],
                "npm test": ["npm test", "npm run test", "npm --silent test", "npm test -- --coverage"],
                "go test": ["go test ./...", "go test -race ./pkg/..."],
                "tests/run.py": ["python3 tests/run.py", "python tests/run.py -v", "/usr/bin/python3.12 tests/run.py"],
                "scripts/build.py --check": ["python3 scripts/build.py --check"]}
        for key, commands in same.items():
            for command in commands:
                self.assertEqual(guard.check_keys(command), [key], command)
        self.assertEqual(guard.check_keys("ruff check . && pytest -q; echo done"), ["pytest", "ruff check"])
        self.assertEqual(guard.check_keys("python3 scripts/build.py --validate"), ["scripts/build.py --validate"])
        self.assertEqual(guard.check_keys('echo "pytest"'), [])

    def test_long_commands_are_matched_in_linear_time(self):
        probe = ("import sys; sys.path.insert(0, sys.argv[1]); import guard\n"
                 "for unit in (' --a b', ' -C d', ' --chec', ' lessons.py --file', ' x;', ' if', ' a=b'):\n"
                 "    for start in ('npm', 'make', 'docker compose run', 'python3 x', 'python3'):\n"
                 "        guard.is_check_command(start + unit * 5000)\n"
                 "        guard.LESSON_COMMAND.search(start + unit * 5000)\n"
                 "for hostile in ('\\n' * 8000, (';' + 'x' * 50) * 8000, ' \\n' * 4000):\n"
                 "    guard.check_keys(hostile, decisive=True)\n"
                 "    guard.LESSON_COMMAND.search(guard.bounded(hostile))\n")
        # 5 s is the track hook's own timeout
        subprocess.run([sys.executable, "-c", probe, str(SCRIPT.parent)], check=True, timeout=5)


class WiringTest(unittest.TestCase):
    def setUp(self):
        self.hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]

    def commands(self, event):
        return [(entry.get("matcher"), hook) for entry in self.hooks[event] for hook in entry["hooks"]]

    def test_guard_is_wired_to_each_event(self):
        expected = {"SessionStart": ("startup|resume|clear", "baseline"), "PostToolUse": ("Bash", "track"),
                    "PostToolUseFailure": ("Bash", "track"), "Stop": (None, "stop"),
                    "PreToolUse": (None, "pre")}  # every tool: a run limit must stop Edit and Agent calls too
        for event, (matcher, cmd) in expected.items():
            found = [(m, h) for m, h in self.commands(event) if "guard.py" in h["command"]]
            self.assertEqual(len(found), 1, event)
            self.assertEqual(found[0][0], matcher, event)
            command = found[0][1]["command"]
            self.assertIn(f'"${{CLAUDE_PLUGIN_ROOT}}/hooks/guard.py" {cmd} || python ', command)
            self.assertLessEqual(found[0][1]["timeout"], 15)

    def test_subagent_stop_is_not_gated(self):
        self.assertNotIn("SubagentStop", self.hooks)

    def test_reason_points_at_the_shipped_lessons_script(self):
        self.assertTrue(guard.LESSONS.is_file())


if __name__ == "__main__":
    unittest.main()
