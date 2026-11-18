"""Tests for the lesson-pattern guard (hooks/guard_lessons.py), its hit log, and its place in guard.py pre."""
import json
import re
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "hooks" / "guard.py"

sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "lessons-learned" / "scripts"))
import guard_hits  # noqa: E402
import guard_lessons  # noqa: E402
import ledger_store  # noqa: E402

# Fake credentials, assembled at run time so that no secret scanner finds a literal one in this file.
FAKE_VALUE = "Hunter" + "2" + "xyz" + "99"
FAKE_PASSWORD = "pass" + "word=" + FAKE_VALUE
FAKE_DB_URL = "postgres://app:" + "s3cret" + "pw" + "@db:5432/x"
FAKE_JWT = ".".join(("eyJ" + "hbGciOiJIUzI1NiJ9", "eyJ" + "zdWIiOiIxMjM0NTY3ODkw", "c2lnbmF0dXJl" + "LXRleHQ"))


class RegistryCase(unittest.TestCase):
    """A project folder and a global registry path in a temp dir; the user's real registry is never read."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.project = self.dir / "project"
        (self.project / "sub").mkdir(parents=True)
        self.global_file = self.dir / "home" / "lesson-guards.json"
        self.hits = self.dir / "home" / "hits.jsonl"
        env = {"LESSONS_GUARDS_GLOBAL_FILE": str(self.global_file), "LESSONS_GUARD_HITS_FILE": str(self.hits)}
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)

    def registry(self, guards, path=None):
        path = Path(path or self.project / ".agents" / "lesson-guards.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(guards if isinstance(guards, str) else json.dumps({"guards": guards}), encoding="utf-8")

    def rule(self, command, cwd=None):
        hit = guard_lessons.judge(command, str(cwd or self.project))
        return hit.rule if hit else None


class BuiltInRuleTests(RegistryCase):
    def assert_rule(self, rule, hits, passes):
        for command in hits:
            self.assertEqual(self.rule(command), rule, command)
        for command in passes:
            self.assertIsNone(self.rule(command), command)

    def pipe(self, command):
        is_check = lambda text: bool(re.search(r"\b(?:npm test|pytest|make test|pnpm lint|gh pr checks)\b", text))
        hit = guard_lessons.judge(command, str(self.project), is_check=is_check)
        return hit.rule if hit else None

    def test_pipe_exit_refuses_acting_on_a_filtered_check(self):
        for command in ("./gate.sh | tail -n 2 && node flow", "npm test | grep ok && deploy",
                        "pytest | tee out.log || exit 1", "if make test | grep -q PASS; then x; fi",
                        "pnpm lint | tail -5; echo rc=$?", "pnpm lint | tail -5\n[ $? -eq 0 ] && ok",
                        "while ./wait.sh | grep -q busy; do sleep 1; done", "! npm test | grep FAIL",
                        "bash run.sh 2>&1 | tail -20 && git push", "cd app && npm test | tail && deploy",
                        "( pytest | tail ) && deploy", "gh pr checks 7 | grep -q pass && merge",
                        "set +o pipefail; npm test | tail && x", "python3 tools/gate.py | sort | head -3 && x",
                        "npm test | tail &&\nnext", "npm test | tail\n\necho $?", "npm test | tail;\necho rc=$?",
                        "npm test |\n tail && x", "bash -c 'npm test | tail && x'", "eval 'npm test | tail && x'",
                        "{ npm test | tail; } && x", "npm test |& tail && x", "until npm test | grep -q ok; do :; done",
                        "if a; then :; elif npm test | tail; then :; fi", "npm test | tail & echo $?",
                        "echo PIPESTATUS; npm test | tail && x", "npm test | tail && set -o pipefail",
                        "bash -c 'set -o pipefail'; npm test | tail && x", "case $1 in t) npm test | tail && x;; esac",
                        "f() { npm test | tail && x; }", "x=$(npm test | tail) && next",
                        "npm test | tail; [ ${?} -eq 0 ] && ok"):
            self.assertEqual(self.pipe(command), "pipe-exit", command)

    def test_pipe_exit_passes_pipefail_pipestatus_files_and_plain_pipes(self):
        for command in ("set -o pipefail; npm test | tail && x", "set -euo pipefail; npm test | tail && x",
                        "set -eo pipefail\npytest | tail -3 || exit 1", "npm test | tail; echo ${PIPESTATUS[0]}",
                        "npm test > out.txt 2>&1; echo rc=$?", "git branch | grep -q main && echo yes",
                        "cat f | grep x && echo y", "npm test | tail -5", "npm test | tail -5; ls",
                        'echo "npm test | tail && x"', "npm test && echo ok | tail", "echo data | pytest && x",
                        "npm test | tail -5; echo done", "pytest -q 2>&1 | tail -3",
                        "npm test | tail && echo ${PIPESTATUS[0]}", "echo pipefail; ls",
                        "cat <<EOF\nnpm test | tail && x\nEOF", "npm test | tail; echo hi",
                        "set -o pipefail\nnpm test | tail && x", "( cd a; npm test ) | tail",
                        "bash -c 'set -o pipefail; npm test | tail && x'", "echo { a b } && ls"):
            self.assertIsNone(self.pipe(command), command)

    def test_pipe_exit_finds_the_command_position_with_the_hooks_classifier(self):
        import guard  # the real classifier: a check counts only where a command starts
        for command, refused in (("case $1 in t) npm test | tail && x;; esac", True),
                                 ("f() { npm test | tail && x; }", True),
                                 ("set -o pipefail; set +o pipefail; npm test | tail && x", True),
                                 ("echo case in npm test | tail && x", False)):
            hit = guard_lessons.judge(command, str(self.project), is_check=guard.is_check_command)
            self.assertEqual(bool(hit), refused, command)

    def test_pipe_exit_without_a_classifier_still_sees_local_scripts(self):
        hit = guard_lessons.judge("./gate.sh | tail && next", str(self.project))
        self.assertEqual(hit.rule, "pipe-exit")
        self.assertIsNone(guard_lessons.judge("npm test | tail && next", str(self.project)))  # no classifier

    def test_pipe_exit_can_be_switched_off_and_tied_to_a_lesson(self):
        self.registry([{"rule": "pipe-exit", "lesson": "G004"}])
        self.assertEqual(guard_lessons.judge("./gate.sh | tail && x", str(self.project)).lesson, "G004")
        self.registry([{"rule": "pipe-exit", "enabled": False}])
        self.assertIsNone(self.pipe("./gate.sh | tail && x"))
        self.registry([{"rule": "pipe-exit", "reason": "Read the gate log first."}])
        self.assertEqual(guard_lessons.judge("./gate.sh | tail && x", str(self.project)).reason, "Read the gate log first.")

    def test_pgrep_wait_loop(self):
        self.assert_rule("pgrep-wait-loop", [
            'while pgrep -f "npm test" >/dev/null; do sleep 5; done', "until ! pgrep -af e2e/run.mjs; do sleep 2; done",
            "cd x && while pgrep -f vitest; do sleep 1; done", "timeout -k 5 600 make; while pgrep --full y; do :; done",
            "bash -c 'while pgrep -f job; do sleep 1; done'", "while kill -0 $p && pgrep -f x; do sleep 1; done",
            "while [ $(pgrep -f x | wc -l) -gt 0 ]; do sleep 1; done", "while\n  pgrep -f x\ndo\n  sleep 1\ndone",
        ], [
            "pgrep -f vitest", "while kill -0 $pid 2>/dev/null; do sleep 5; done", "while pgrep vitest; do sleep 1; done",
            'grep -n "while pgrep -f" notes.md', "echo 'never: while pgrep -f x'", "if pgrep -f x; then echo up; fi",
            "while read -r name; do echo $name; done; pgrep -f x", "while true; do sleep 1; done && pgrep -f x",
        ])

    def test_hook_bypass(self):
        self.assert_rule("hook-bypass", [
            "git commit --no-verify -m x", "git push --no-verify origin dev", 'git commit -nm "fix"', "git commit -n -m x",
            "git commit -an", "git -c core.hooksPath=/dev/null commit -m x", "git config core.hooksPath /dev/null",
            "git config --global core.hookspath .nohooks", "git config set core.hooksPath .x", "HUSKY=0 git push",
            "husky=0 git push", "export HUSKY=0 && git commit -m x", "export HUSKY=0; git push",
            "sh -c 'git commit --no-verify -m x'", 'eval "git commit -n -m x"', "git -C repo commit -n -m x",
            "git -c a=b commit -n", "git --git-dir .git commit -n", 'bash -c "bash -c \'git commit -n\'"',
            "git commit -u -n -m x", "git push -u --no-verify origin dev", 'HUSKY=0 bash -c "git commit -m x"',
            'export HUSKY=0; sh -c "git push"',
        ], [
            'git commit -m "no verify skipped, --no-verify banned"', "git commit -am x", "git push -n origin dev",
            "git config --get core.hooksPath", "git log --oneline -5", 'git commit -m "-n is banned"', "git commit -mn",
            "git -C repo commit -m x", "HUSKY=1 git push",
            "git config --get-regexp core.hooksPath", "git config --get-all core.hooksPath", "git config core.hooksPath",
            "git config --local core.hooksPath", "git config --show-origin core.hooksPath",
            "git config --unset core.hooksPath", "git config --get-regexp core.hooksPath .",
            "git config --unset-all core.hooksPath old", "git config get core.hooksPath",
            "git commit -c core.hooksPath=x -m y", "git log -c core.hooksPath=x", "HUSKY=0 bash -c 'npm ci'", "HUSKY=0 npm ci", "HUSKY=0 pnpm install",
            "env HUSKY=0 npm run release", "git commit -m --no-verify", 'git tag -m "--no-verify" v1',
            "git commit -m x -- -n", "git commit -uno -m x", "git commit -mn",
            "bash -c \"bash -c 'bash -c \\\"git commit -n\\\"'\"",  # deeper than MAX_DEPTH: not read "git commit -F - <<'EOF'\nban --no-verify\nHUSKY=0 git push\nEOF",
        ])

    def test_help_probe(self):
        self.assert_rule("help-probe", [
            "./scripts/run.sh --help", "node tools/report.mjs --help", "python3 scripts/lessons.py -h",
            "bash deploy.sh -h", "~/bin/sync.py --help", "./db.sh --help localhost",
        ], [
            "git --help", "npm --help", "./node_modules/.bin/vitest --help", "./.venv/bin/pytest -h", "node -h",
            "node tools/report.mjs get 123", "sed -n '1,40p' scripts/run.sh", "python3 -h", "/usr/bin/git --help",
            'echo "./run.sh --help"', "../tools/x --help", "./gradlew --help", "./db.sh -h localhost", "bash deploy.sh -h host", "./target/release/app --help",
        ])

    def test_help_probe_programs_name_extensionless_scripts(self):
        self.registry([{"rule": "help-probe", "programs": ["release-tool"]}])
        self.assertEqual(self.rule("release-tool --help"), "help-probe")
        self.assertEqual(self.rule("./bin/release-tool -h"), "help-probe")
        self.assertIsNone(self.rule("./gradlew --help"))

    def test_the_assembled_fakes_are_secrets_to_the_detector(self):
        for fake in (FAKE_PASSWORD, FAKE_DB_URL, FAKE_JWT):
            self.assertTrue(ledger_store.find_secret(fake))

    def test_secret_in_message_needs_the_message_programs(self):
        command = f'notify.sh team "login: {FAKE_PASSWORD}"'
        self.assertIsNone(self.rule(command))
        self.registry([{"rule": "secret-in-message", "lesson": "G021", "programs": ["notify.sh"]}])
        self.assert_rule("secret-in-message", [
            command, f'./tools/notify.sh team "db {FAKE_DB_URL}"', f'bash notify.sh team "jwt {FAKE_JWT}"',
        ], [
            'notify.sh team "credentials are in ~/.config/app/staging.env"', 'notify.sh team "token rotated at 14:24"',
            f'echo "{FAKE_PASSWORD}"', f'other.sh team "{FAKE_PASSWORD}"',
        ])

    def test_empty_and_non_text_commands_pass(self):
        for command in ("", "   ", None, 42):
            self.assertIsNone(guard_lessons.judge(command, str(self.project)))

    def test_unbalanced_quote_still_judges_what_came_before(self):
        self.assertEqual(self.rule("git commit --no-verify -m 'unfinished"), "hook-bypass")


class RegistryTests(RegistryCase):
    def test_lesson_id_and_reason_come_from_the_registry(self):
        self.registry([{"rule": "hook-bypass", "lesson": "G027", "reason": "Hooks are the only CI here."}])
        hit = guard_lessons.judge("git commit --no-verify", str(self.project / "sub"))
        self.assertEqual(hit, guard_lessons.Hit("G027", "hook-bypass", "Hooks are the only CI here."))

    def test_without_a_registry_built_in_rules_have_no_lesson_and_the_default_reason(self):
        hit = guard_lessons.judge("git commit --no-verify", str(self.project))
        self.assertEqual((hit.lesson, hit.reason), (None, guard_lessons.BUILT_IN_REASONS["hook-bypass"]))

    def test_a_rule_can_be_switched_off_and_the_project_entry_wins(self):
        self.registry([{"rule": "help-probe", "lesson": "G012"}], self.global_file)
        self.registry([{"rule": "help-probe", "enabled": False}])
        self.assertIsNone(self.rule("./run.sh --help"))
        self.assertEqual(self.rule("./run.sh --help", cwd=self.dir), "help-probe")  # outside: global only
        hit = guard_lessons.judge("./run.sh --help", str(self.dir))
        self.assertEqual(hit.lesson, "G012")

    def test_claude_project_dir_names_the_project(self):
        self.registry([{"rule": "help-probe", "enabled": False}])
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.project)}):
            self.assertIsNone(self.rule("./run.sh --help", cwd=self.dir))

    def test_a_rule_of_your_own(self):
        self.registry([{"lesson": "L031", "program": "git", "subcommand": "push", "args_any": ["--force", "-f"],
                        "reason": "Push a new branch instead."},
                       {"lesson": "L040", "program": ["make", "gmake"], "assignments_any": ["SKIP_TESTS=1"],
                        "reason": "Tests are never skipped."},
                       {"lesson": "L041", "program": "curl", "in_loop": True, "reason": "Poll with a timeout."}])
        hit = guard_lessons.judge("git push -fu origin topic", str(self.project))
        self.assertEqual(hit, guard_lessons.Hit("L031", "L031", "Push a new branch instead."))
        for command in ("git push --force", "git -C d push -f", "git -c a=b push --force", "git push -uf o b"):
            self.assertEqual(self.rule(command), "L031", command)
        self.assertEqual(self.rule("SKIP_TESTS=1 gmake release"), "L040")
        self.assertEqual(self.rule("while curl -sf localhost:8080; do sleep 1; done"), "L041")
        self.assertEqual(self.rule("until test -f ready && curl -sf x; do sleep 1; done"), "L041")
        for command in ("git push origin topic", "git fetch -f", "git -C push status -f", 'git commit -m "git push --force"', "make release",
                        "SKIP_TESTS=0 make", "curl -sf localhost:8080"):
            self.assertIsNone(self.rule(command), command)

    def test_unusable_entries_are_skipped_with_the_file_and_the_fault(self):
        cases = [
            ("{not json", "lesson-guards.json"),
            (json.dumps([]), "expected"),
            (json.dumps({"guards": [], "extra": 1}), "expected"),
            (json.dumps({"guards": ["x"]}), "not an object"),
            (json.dumps({"guards": [{"rule": "no-such-rule"}]}), "rule must be one of"),
            (json.dumps({"guards": [{"rule": "help-probe", "enabeld": False}]}), "unknown keys"),
            (json.dumps({"guards": [{"rule": "help-probe", "enabled": "no"}]}), "enabled must be"),
            (json.dumps({"guards": [{"rule": "help-probe", "lesson": "twelve"}]}), "not a lesson id"),
            (json.dumps({"guards": [{"rule": "help-probe", "lesson": "L012\n"}]}), "not a lesson id"),
            (json.dumps({"guards": [{"rule": "hook-bypass", "programs": ["x"]}]}), "programs is a list"),
            (json.dumps({"guards": [{"lesson": "L001", "program": "/usr/bin/git", "reason": "x"}]}), "without a directory"),
            (json.dumps({"guards": [{"rule": "help-probe", "reason": " "}]}), "reason must be"),
            (json.dumps({"guards": [{"rule": "secret-in-message", "programs": "notify.sh"}]}), "programs is a list"),
            (json.dumps({"guards": [{"program": "git", "reason": "x"}]}), "needs lesson, reason and program"),
            (json.dumps({"guards": [{"lesson": "L001", "program": "git", "reason": "x", "argz": []}]}), "unknown keys"),
            (json.dumps({"guards": [{"lesson": "L001", "program": [], "reason": "x"}]}), "program must be"),
            (json.dumps({"guards": [{"lesson": "L001", "program": "git", "reason": "x", "args_any": "-f"}]}), "args_any"),
            (json.dumps({"guards": [{"lesson": "L001", "program": "git", "reason": "x", "subcommand": ""}]}), "subcommand"),
            (json.dumps({"guards": [{"lesson": "L001", "program": "git", "reason": "x", "in_loop": 1}]}), "in_loop"),
        ]
        for text, fault in cases:
            self.registry(text)
            self.assertIsNone(guard_lessons.judge("ls", str(self.project)), text)  # never refused for the registry
            self.assertEqual(self.rule("git commit --no-verify"), "hook-bypass", text)  # built-in rules still apply
            [problem] = guard_lessons.registry_problems(str(self.project))
            self.assertIn(fault, problem, text)
            self.assertIn("lesson-guards.json", problem, text)
            self.assertIn("skipped", problem, text)

    def test_one_bad_entry_skips_only_itself(self):
        self.registry([{"rule": "no-such-rule", "lesson": "L001"},
                       {"rule": "hook-bypass", "lesson": "G027", "reason": "Hooks are the gate."},
                       {"lesson": "L031", "program": "git", "subcommand": "push", "args_any": ["-f"], "reason": "x"}])
        self.assertEqual(guard_lessons.judge("git commit --no-verify", str(self.project)),
                         guard_lessons.Hit("G027", "hook-bypass", "Hooks are the gate."))
        self.assertEqual(self.rule("git push -f"), "L031")
        [problem] = guard_lessons.registry_problems(str(self.project))
        self.assertIn("entry 1", problem)

    def test_min_version_skips_an_entry_for_a_newer_hook_without_a_problem(self):
        self.registry([{"rule": "help-probe", "enabled": False, "min_version": "99.0.0"},  # a future hook's entry
                       {"rule": "hook-bypass", "lesson": "G027", "min_version": "0.1.0"},
                       {"lesson": "L050", "program": "make", "reason": "x", "min_version": "99.0.0"}])
        self.assertEqual(self.rule("./run.sh --help"), "help-probe")  # the disabling entry was skipped
        self.assertEqual(guard_lessons.judge("git commit -n", str(self.project)).lesson, "G027")
        self.assertIsNone(self.rule("make all"))
        self.assertEqual(guard_lessons.registry_problems(str(self.project)), [])
        for bad in ("1.9", "v1.9.0", 190, ""):
            self.registry([{"rule": "hook-bypass", "min_version": bad}])
            [problem] = guard_lessons.registry_problems(str(self.project))
            self.assertIn("min_version must be a version", problem, bad)

    def test_without_a_version_file_min_version_entries_apply(self):
        with mock.patch.object(guard_lessons, "HOOK_VERSION", None):
            self.registry([{"rule": "help-probe", "enabled": False, "min_version": "99.0.0"}])
            self.assertIsNone(self.rule("./run.sh --help"))

    def test_odd_values_skip_only_their_entry_and_never_escape(self):
        for odd in ([{"rule": ["hook-bypass"]}], [{"rule": {"x": 1}}], [{"rule": "hook-bypass", "lesson": ["G027"]}],
                    [{"lesson": "L001", "program": "git", "reason": "x", "args_any": [["-f"]]}],
                    [{"rule": "help-probe", "min_version": "1" * 5000 + ".0.0"}],
                    [{"rule": "help-probe", "min_version": "\u0661.\u0662.\u0663"}]):  # Arabic-Indic digits
            self.registry(odd + [{"rule": "hook-bypass", "lesson": "G027"}])
            self.assertEqual(guard_lessons.judge("git commit -n", str(self.project)).lesson, "G027", odd)
            self.assertEqual(len(guard_lessons.registry_problems(str(self.project))), 1, odd)

    def test_any_unexpected_fault_in_an_entry_skips_only_that_entry(self):
        self.registry([{"rule": "help-probe", "enabled": False}, {"rule": "hook-bypass", "lesson": "G027"}])
        real = guard_lessons.validate

        def flaky(entry, where):
            if entry.get("rule") == "help-probe":
                raise TypeError("unexpected")
            return real(entry, where)
        with mock.patch.object(guard_lessons, "validate", side_effect=flaky):
            self.assertEqual(self.rule("./run.sh --help"), "help-probe")  # the disabling entry was skipped
            self.assertEqual(guard_lessons.judge("git commit -n", str(self.project)).lesson, "G027")
            [problem] = guard_lessons.registry_problems(str(self.project))
            self.assertIn("TypeError: unexpected (entry skipped)", problem)

    def test_a_file_too_deep_or_too_large_is_skipped_whole(self):
        self.registry('{"guards": ' + "[" * 100000 + "]" * 100000 + "}")
        [problem] = guard_lessons.registry_problems(str(self.project))
        self.assertIn("RecursionError", problem)
        self.registry(json.dumps({"guards": [{"rule": "hook-bypass", "reason": "x" * 1_100_000}]}))
        [problem] = guard_lessons.registry_problems(str(self.project))
        self.assertIn("larger than", problem)
        self.assertEqual(self.rule("git commit -n"), "hook-bypass")

    def test_min_version_skips_an_unknown_rule_quietly_and_compares_as_numbers(self):
        self.registry([{"rule": "rule-from-the-future", "lesson": "L190", "min_version": "99.0.0"},
                       {"lesson": "L051", "program": "make", "reason": "x", "new_key": 1, "min_version": "99.0.0"}])
        self.assertEqual(guard_lessons.registry_problems(str(self.project)), [])  # not reported: meant for later
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 9, 0)):
            self.registry([{"rule": "help-probe", "enabled": False, "min_version": "1.10.0"}])
            self.assertEqual(self.rule("./run.sh --help"), "help-probe")  # 1.10.0 is newer than 1.9.0: skipped
            self.registry([{"rule": "help-probe", "enabled": False, "min_version": "1.9.0"}])
            self.assertIsNone(self.rule("./run.sh --help"))  # equal: applied
            self.registry([{"rule": "help-probe", "enabled": False, "min_version": "1.9.1"}])
            self.assertEqual(self.rule("./run.sh --help"), "help-probe")  # one patch above: skipped
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 10, 0)):
            self.registry([{"rule": "help-probe", "enabled": False, "min_version": "1.9.0"}])
            self.assertIsNone(self.rule("./run.sh --help"))

    def test_hook_version_beside_the_hook_first_then_the_plugin_root(self):
        root = self.dir / "plugin"
        hooks = root / "hooks"
        hooks.mkdir(parents=True)
        self.assertIsNone(guard_lessons.hook_version(hooks))
        (root / "VERSION").write_text("1.11.2\n")  # plugin layout: the root
        self.assertEqual(guard_lessons.hook_version(hooks), (1, 11, 2))
        (hooks / "VERSION").write_text("1.10.0\n")  # installer layout: beside the hook wins
        self.assertEqual(guard_lessons.hook_version(hooks), (1, 10, 0))
        for junk in (b"1.12.0-rc1\n", b"\xff\xfe not utf-8", b"project version 3"):  # passed over, never raised
            (hooks / "VERSION").write_bytes(junk)
            self.assertEqual(guard_lessons.hook_version(hooks), (1, 11, 2), junk)
        (hooks / "VERSION").write_bytes(b"\xef\xbb\xbf1.10.0\n")  # a byte-order mark is not part of the version
        self.assertEqual(guard_lessons.hook_version(hooks), (1, 10, 0))

    def test_problems_come_from_every_registry(self):
        self.registry([{"rule": "hook-bypass", "lesson": "G027"}], self.global_file)
        self.registry([{"rule": "no-such-rule"}])
        [problem] = guard_lessons.registry_problems(str(self.project / "sub"))
        self.assertIn(str(self.project / ".agents" / "lesson-guards.json"), problem)
        self.assertEqual(guard_lessons.judge("git commit -n", str(self.project)).lesson, "G027")

    def test_a_registry_that_is_a_directory_is_refused(self):
        (self.project / ".agents" / "lesson-guards.json").mkdir(parents=True)
        self.assertEqual(guard_lessons.registry_paths(str(self.project)), [])  # not a file: not a registry
        self.global_file.mkdir(parents=True)
        self.assertEqual(guard_lessons.registry_paths(str(self.project)), [])


class HitLogTests(RegistryCase):
    def test_append_and_count_within_the_window(self):
        guard_hits.append("G027", "hook-bypass", "/work", now=1000)
        guard_hits.append("G027", "hook-bypass", "/work", now=5000)
        guard_hits.append(None, "help-probe", "/work", now=5100)
        guard_hits.append("G002", "pgrep-wait-loop", "/work", now=9000)  # after `now`: not counted
        found, damaged = guard_hits.counts(3600, now=5200)
        self.assertEqual(dict(found), {("G027", "hook-bypass"): 1, ("-", "help-probe"): 1})
        self.assertEqual(damaged, 0)
        self.assertEqual(oct(self.hits.stat().st_mode & 0o777), "0o600")

    def test_damaged_lines_are_skipped_and_counted(self):
        guard_hits.append("G027", "hook-bypass", "/w", now=100)
        with open(self.hits, "a", encoding="utf-8") as handle:
            handle.write("not json\nnull\n{\"time\": \"x\", \"rule\": \"r\"}\n{\"lesson\": \"L1\"}\n")
        found, damaged = guard_hits.counts(3600, now=200)
        self.assertEqual((sum(found.values()), damaged), (1, 4))

    def test_no_log_is_no_hits(self):
        self.assertEqual(guard_hits.counts(60), ({}, 0))

    def test_windows(self):
        self.assertEqual([guard_hits.window_seconds(w) for w in ("30m", "24h", "7d")], [1800, 86400, 604800])
        for bad in ("0h", "24", "h", "-1h", "1w", ""):
            with self.assertRaises(ValueError, msg=bad):
                guard_hits.window_seconds(bad)


class HookTests(RegistryCase):
    """guard.py pre run as Claude Code runs it."""

    def pre(self, command, env=None, tool="Bash"):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": command},
                   "cwd": str(self.project), "permission_mode": "default"}
        base = {k: v for k, v in os.environ.items()
                if k not in ("ARSENAL_GUARD", "ARSENAL_LESSON_GUARDS", "ARSENAL_GUARD_DESTRUCTIVE",
                             "ARSENAL_RUN_LIMITS", "CLAUDE_PROJECT_DIR")}
        result = subprocess.run([sys.executable, str(SCRIPT), "pre"], cwd=self.project, input=json.dumps(payload),
                                capture_output=True, text=True, env={**base, **(env or {})})
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None

    def test_a_refused_command_is_denied_and_logged_without_the_command(self):
        self.registry([{"rule": "hook-bypass", "lesson": "G027"}])
        out = self.pre("git commit --no-verify -m secretword")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("lesson guard G027 (hook-bypass)", out["permissionDecisionReason"])
        [entry] = [json.loads(line) for line in self.hits.read_text().splitlines()]
        self.assertEqual((entry["lesson"], entry["rule"], entry["cwd"]), ("G027", "hook-bypass", str(self.project)))
        self.assertNotIn("secretword", self.hits.read_text())

    def test_clean_commands_and_other_tools_print_nothing(self):
        self.assertIsNone(self.pre("ls -la"))
        self.assertIsNone(self.pre("git commit --no-verify", tool="Read"))
        self.assertFalse(self.hits.exists())

    def test_switches(self):
        self.assertIsNone(self.pre("git commit --no-verify", env={"ARSENAL_LESSON_GUARDS": "off"}))
        self.assertIsNone(self.pre("git commit --no-verify", env={"ARSENAL_GUARD": "off"}))
        out = self.pre("git commit --no-verify", env={"ARSENAL_GUARD_DESTRUCTIVE": "allow"})
        self.assertEqual(out["permissionDecision"], "deny")  # the destructive switch does not lift lesson guards

    def test_an_unusable_registry_never_blocks_commands(self):
        self.registry("{broken")
        self.assertIsNone(self.pre("ls"))
        self.assertEqual(self.pre("git commit --no-verify")["permissionDecision"], "deny")  # built-ins still hold
        self.registry([{"rule": "rule-of-a-newer-version", "lesson": "L190"}])
        self.assertIsNone(self.pre("ls"))
        self.registry([{"rule": ["a", "list"]}, {"rule": "hook-bypass", "lesson": "G027"}])
        self.assertIn("G027", self.pre("git commit --no-verify")["permissionDecisionReason"])  # never fails open
        self.assertEqual(self.pre("git reset --hard")["permissionDecision"], "ask")  # the destructive check still runs

    def test_an_unwritable_hit_log_still_refuses_and_says_so(self):
        self.hits.parent.mkdir(parents=True)
        self.hits.mkdir()  # a directory where the log file should be
        out = self.pre("git commit --no-verify")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("hit not logged", out["permissionDecisionReason"])

    def test_any_logging_error_still_refuses_and_says_so(self):
        import guard  # the hook module, in process: Path.home() raises RuntimeError when no home can be found
        with mock.patch.object(guard_hits, "append", side_effect=RuntimeError("no home directory")):
            reason = guard.lesson_refusal("git commit --no-verify", str(self.project))
        self.assertIn("hook-bypass", reason)
        self.assertIn("hit not logged: no home directory", reason)

    def test_a_missing_helper_module_refuses_instead_of_passing(self):
        import guard
        with mock.patch.object(guard.guard_lessons, "judge", side_effect=ImportError("No module named 'ledger_store'")):
            reason = guard.lesson_refusal("./notify.sh x", str(self.project))
        self.assertIn("cannot judge this command", reason)

    def test_the_secret_rule_runs_inside_the_hook(self):  # ledger_store is found beside lessons.py
        self.registry([{"rule": "secret-in-message", "lesson": "G021", "programs": ["notify.sh"]}])
        out = self.pre(f'./notify.sh team "{FAKE_PASSWORD}"')
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("G021 (secret-in-message)", out["permissionDecisionReason"])
        self.assertNotIn(FAKE_VALUE, out["permissionDecisionReason"] + self.hits.read_text())

    def test_pipe_exit_uses_the_hooks_own_check_classifier(self):
        self.registry([{"rule": "pipe-exit", "lesson": "G004"}])
        out = self.pre("npm test 2>&1 | tail -n 2 && git push")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("G004 (pipe-exit)", out["permissionDecisionReason"])
        self.assertIn("set -o pipefail", out["permissionDecisionReason"])
        self.assertIsNone(self.pre("set -o pipefail; npm test 2>&1 | tail -n 2 && git push"))

    def test_destructive_commands_are_still_asked_about(self):
        self.assertEqual(self.pre("git reset --hard")["permissionDecision"], "ask")


if __name__ == "__main__":
    unittest.main()
