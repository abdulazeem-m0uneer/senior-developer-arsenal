"""rerun-after-red: a check or push that failed may not be repeated before a cause note (lessons.py cause)."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from test_guard import GuardCase

ROOT = Path(__file__).resolve().parent.parent
LESSONS = ROOT / ".agents" / "skills" / "lessons-learned" / "scripts" / "lessons.py"
CAUSE = f'python3 {LESSONS} cause "test_total fails: the tax rate is applied twice"'


class RerunCase(GuardCase):
    def setUp(self):
        super().setUp()
        self.registry = Path(self.outside.name) / "no-global-lesson-guards.json"
        self.registry.write_text(json.dumps({"guards": [{"rule": "rerun-after-red", "lesson": "L083"}]}))

    def pre(self, command, **kwargs):
        out = self.run_hook("pre", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                    "tool_input": {"command": command}}, **kwargs)
        return json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"] if out else ""


class RerunAfterRedTest(RerunCase):
    def test_rerunning_a_failed_check_is_refused_with_the_steps(self):
        self.bash("pytest -q tests/a.py", failed=True)
        reason = self.pre("pytest -q tests/a.py")
        self.assertIn("rerun-after-red", reason)
        self.assertIn("L083", reason)
        self.assertIn(f"{LESSONS} cause", reason)
        self.assertIn("unknown", reason)

    def test_a_cause_note_after_the_failure_allows_the_rerun(self):
        self.bash("pytest -q", failed=True)
        self.bash(CAUSE)
        self.assertEqual(self.pre("pytest -q"), "")

    def test_a_cause_note_before_the_failure_does_not_count(self):
        self.bash(CAUSE)
        self.bash("pytest -q", failed=True)
        self.assertIn("rerun-after-red", self.pre("pytest -q"))

    def test_a_cause_note_that_failed_to_record_does_not_count(self):
        self.bash("pytest -q", failed=True)
        self.bash('python3 ' + str(LESSONS) + ' cause "nothing"', failed=True)
        self.assertIn("rerun-after-red", self.pre("pytest -q"))

    def test_a_second_failure_needs_a_new_note(self):
        self.bash("pytest -q", failed=True)
        self.bash(CAUSE)
        self.bash("pytest -q", failed=True)
        self.assertIn("rerun-after-red", self.pre("pytest -q"))

    def test_a_different_check_or_command_is_never_refused(self):
        self.bash("pytest -q", failed=True)
        for command in ("ruff check .", "ls -la", "git status", 'echo "pytest -q"', 'git commit -m "run pytest"'):
            self.assertEqual(self.pre(command), "", command)

    def test_the_same_check_with_other_flags_or_a_wrapper_is_the_same_command(self):
        self.bash("cd api && python3 -m pytest -x tests/a.py", failed=True)
        self.assertIn("rerun-after-red", self.pre("timeout 60 pytest -q"))

    def test_a_check_that_passed_since_may_run_again(self):
        self.bash("pytest -q", failed=True)
        self.bash("pytest -q")
        self.assertEqual(self.pre("pytest -q"), "")

    def test_a_pass_hidden_behind_a_pipe_does_not_clear_the_failure(self):
        self.bash("pytest -q", failed=True)
        self.bash("pytest -q | tail -3")
        self.assertIn("rerun-after-red", self.pre("pytest -q"))

    def test_a_refused_rerun_inside_a_compound_command_is_refused(self):
        self.bash("npm test", failed=True)
        self.assertIn("rerun-after-red", self.pre("cd web && npm test"))

    def test_the_cause_command_itself_is_never_refused(self):
        self.bash("pytest -q", failed=True)
        self.assertEqual(self.pre(CAUSE), "")

    def test_nothing_is_refused_without_the_registry_entry(self):
        self.registry.unlink()
        self.bash("pytest -q", failed=True)
        self.assertEqual(self.pre("pytest -q"), "")

    def test_the_lesson_guard_switch_lifts_it(self):
        self.bash("pytest -q", failed=True)
        self.assertEqual(self.pre("pytest -q", env={"ARSENAL_LESSON_GUARDS": "off"}), "")


class PushAfterRefusedPushTest(RerunCase):
    def test_pushing_again_after_a_failed_push_is_refused(self):
        self.bash("git push origin feat/x", failed=True)
        self.assertIn("rerun-after-red", self.pre("git push origin feat/x"))
        self.assertIn("rerun-after-red", self.pre("git -C repo push origin feat/x"))

    def test_a_cause_note_allows_the_push(self):
        self.bash("git push origin feat/x", failed=True)
        self.bash(CAUSE.replace("test_total fails", "push refused"))
        self.assertEqual(self.pre("git push origin feat/x"), "")

    def test_a_push_of_another_branch_or_other_git_commands_are_allowed(self):
        self.bash("git push origin feat/x", failed=True)
        for command in ("git push origin feat/y", "git status", "git pull origin feat/x"):
            self.assertEqual(self.pre(command), "", command)

    def test_a_push_that_succeeded_since_clears_it(self):
        self.bash("git push origin feat/x", failed=True)
        self.bash("git push origin feat/x")
        self.assertEqual(self.pre("git push origin feat/x"), "")

    def test_a_failed_push_is_not_a_failed_check_at_stop(self):
        self.start()
        self.bash("git push origin feat/x", failed=True)
        self.assertEqual(self.stop(), "")


class CauseCommandTest(unittest.TestCase):
    def cause(self, *words):
        return subprocess.run([sys.executable, str(LESSONS), "cause", *words], capture_output=True, text=True)

    def test_a_check_and_its_cause_are_accepted(self):
        for note in ("test_total: tax applied twice", "build: unknown", "lint E501 in a.py: line too long"):
            result = self.cause(note)
            self.assertEqual((result.returncode, result.stderr), (0, ""), note)

    def test_a_note_without_a_check_or_a_cause_is_refused(self):
        for note in ("", "tax applied twice", "test_total:", ": unknown", "   :   "):
            result = self.cause(note)
            self.assertEqual(result.returncode, 2, note)
            self.assertIn("<check or assertion>: <cause or unknown>", result.stderr)


if __name__ == "__main__":
    unittest.main()
