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

    def test_a_push_behind_an_escalated_lesson_never_ran_and_is_not_red(self):
        self.bash(f"python3 {LESSONS} bump L004 && git push origin feat", failed=True, is_interrupt=False,
                  error="Exit code 3\nL004 hits:3\nESCALATE L004 x3: this lesson has repeated without a guard.")
        self.assertEqual(self.pre("git push origin feat"), "")

    def test_a_push_behind_a_quiet_escalated_lesson_never_ran_and_is_not_red(self):
        self.bash(f"pytest -q; python3 {LESSONS} bump L004 >/dev/null 2>&1 && git push origin feat", failed=True,
                  is_interrupt=False, error="Exit code 3")
        self.assertEqual(self.pre("git push origin feat"), "")
        self.assertIn("rerun-after-red", self.pre("pytest -q"))  # the check before the lesson did run

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


class EmptyCheckKeyTest(RerunCase):
    """1.38.0 recorded "" as the key of `node --test <file>` (the only words were options): every command whose push
    key is "" (any command that is not a push) was then refused until a bare cause note."""

    def test_a_check_named_only_by_options_keeps_a_key(self):
        sys.path.insert(0, str(ROOT / "hooks"))
        import guard
        for command, key in (("node --test $A/bus/send.test.sh", "node --test"),
                             ("node --test bus/send.test.sh", "node --test"),
                             ("bash -c-test x", "bash -c-test")):
            self.assertEqual(guard.check_keys(command), [key], command)

    def test_a_variable_only_key_is_never_recorded(self):
        sys.path.insert(0, str(ROOT / "hooks"))
        import guard
        self.assertEqual(guard.check_keys("bash ${test}"), [])
        self.assertEqual(guard.check_keys("bash $A/bus/send.test.sh"), ["$A/bus/send.test.sh"])

    def test_after_the_failure_other_commands_pass(self):
        self.bash("node --test $A/bus/send.test.sh", failed=True)
        for command in ("ls -la", "git status", "echo hi"):
            self.assertEqual(self.pre(command), "", command)
        self.assertIn("rerun-after-red", self.pre("node --test $A/bus/send.test.sh"))

    def test_an_empty_key_left_by_the_old_release_is_ignored(self):
        sys.path.insert(0, str(ROOT / "hooks"))
        import guard
        self.assertEqual(guard.red_checks([{"event": "fail", "checks": ["", "pytest"]}]), {"pytest"})
        self.assertEqual(guard.red_checks([{"event": "push_fail", "key": ""}]), set())


class CauseInAListTest(RerunCase):
    """A cause note inside a list (`;`, `&&`) runs before the steps after it: they are not refused, and it is recorded."""

    def test_the_steps_after_the_note_pass(self):
        self.bash("pytest -q", failed=True)
        for command in (f"{CAUSE} && pytest -q", f"{CAUSE}; pytest -q", f"cd /tmp && {CAUSE} && pytest -q",
                        f"cd /tmp; {CAUSE}; echo done"):
            self.assertEqual(self.pre(command), "", command)

    def test_a_rerun_before_the_note_is_still_refused(self):
        self.bash("pytest -q", failed=True)
        self.assertIn("rerun-after-red", self.pre(f"pytest -q; {CAUSE}"))
        self.assertEqual(self.pre(f'echo "a; pytest -q"; {CAUSE}'), "")  # a quoted word runs nothing

    def test_a_note_lessons_py_refuses_or_only_shows_help_lifts_nothing(self):
        self.bash("pytest -q", failed=True)
        for note in ('"nothing"', '"pytest: "'):
            self.assertIn("rerun-after-red", self.pre(f"python3 {LESSONS} cause {note}; pytest -q"), note)
        sys.path.insert(0, str(ROOT / "hooks"))
        import guard_lessons
        for note in ("--help", '"pytest: x" -h'):  # help-probe refuses these first: judge the note on its own
            cmd = next(iter(guard_lessons.commands(f"python3 {LESSONS} cause {note}")))
            self.assertFalse(guard_lessons.accepted_note(cmd), note)

    def test_a_step_that_runs_only_when_the_note_failed_is_still_judged(self):
        self.bash("pytest -q", failed=True)
        self.assertIn("rerun-after-red", self.pre(f"{CAUSE} || pytest -q"))

    def test_a_note_that_may_not_run_lifts_nothing(self):
        self.bash("pytest -q", failed=True)
        for command in (f"false && {CAUSE}; pytest -q", f"cd /tmp && false && {CAUSE}; pytest -q",
                        f"if false; then {CAUSE}; fi; pytest -q", f"case $X in a) {CAUSE};; esac; pytest -q",
                        f"false || {CAUSE}; pytest -q", f"if true; then {CAUSE}; else pytest -q; fi",
                        'python3 /nope/lessons.py cause "a: b"; pytest -q',
                        'python3 ./no-such-dir/lessons.py cause "a: b"; pytest -q',
                        f"cd /no-such-dir-xyz && {CAUSE}; pytest -q", f'cd "$UNSET_X" && {CAUSE}; pytest -q',
                        f"cd && {CAUSE}; pytest -q", f"for f in $EMPTY; do {CAUSE}; done; pytest -q",
                        f"while false; do {CAUSE}; done; pytest -q", f"until true; do {CAUSE}; done; pytest -q",
                        f"f() {{ {CAUSE}; }}; pytest -q", f"function f() {{ {CAUSE}; }}; pytest -q",
                        f"f() ( {CAUSE} ); pytest -q", f"f() {{ for x in a; do {CAUSE}; done; pytest -q; }}"):
            self.assertIn("rerun-after-red", self.pre(command), command)

    def test_a_note_in_the_same_loop_or_function_body_as_the_step_lifts_the_refusal(self):
        self.bash("pytest -q", failed=True)
        for command in (f"for f in a; do {CAUSE}; pytest -q; done", f"f() {{ {CAUSE}; pytest -q; }}",
                        f"{{ {CAUSE}; }}; pytest -q", f"for f in a; do :; done; {CAUSE}; pytest -q",
                        f"while {CAUSE}; do pytest -q; done"):
            self.assertEqual(self.pre(command), "", command)

    def test_a_bare_lessons_name_counts_only_when_it_is_on_path(self):
        self.bash("pytest -q", failed=True)
        bare = 'lessons cause "a: b"; pytest -q'
        self.assertIn("rerun-after-red", self.pre(bare, env={"PATH": "/usr/bin:/bin"}))
        shim = Path(self.outside.name) / "bin"
        shim.mkdir()
        (shim / "lessons").write_text("#!/bin/sh\n")
        (shim / "lessons").chmod(0o755)
        self.assertEqual(self.pre(bare, env={"PATH": f"{shim}:/usr/bin:/bin"}), "")

    def test_a_note_on_every_path_to_the_step_lifts_the_refusal(self):
        self.bash("pytest -q", failed=True)
        for command in (f"if true; then {CAUSE}; pytest -q; fi", f"if {CAUSE}; then pytest -q; fi",
                        f"cd /tmp && cd / && {CAUSE} && pytest -q", f"cd /tmp && {CAUSE}; pytest -q"):
            self.assertEqual(self.pre(command), "", command)

    def test_cause_noted_echoed_by_another_step_records_nothing(self):
        self.bash("pytest -q", failed=True)
        for text in ("cause noted", "x cause noted; rerun the failed command now"):
            self.bash(f"echo '{text}'; python3 {LESSONS} cause nothing", failed=True, is_interrupt=False,
                      error=f'Exit code 1\n{text}\nlessons: a cause note reads "<check>: <cause>"')
            self.assertIn("rerun-after-red", self.pre("pytest -q"), text)

    def test_a_note_inside_a_list_is_recorded(self):
        self.bash("pytest -q", failed=True)
        self.bash(f"cd /tmp && {CAUSE}; git status")
        self.assertEqual(self.pre("pytest -q"), "")

    def test_a_note_in_a_call_that_failed_later_is_recorded_before_the_failure(self):
        self.bash("ruff check .", failed=True)
        self.bash(f"{CAUSE} && pytest -q", failed=True, is_interrupt=False,
                  error="Exit code 1\ncause noted; rerun the failed command now\n1 failed")
        self.assertEqual(self.pre("ruff check ."), "")
        self.assertIn("rerun-after-red", self.pre("pytest -q"))  # the failure after the note is a new red


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
