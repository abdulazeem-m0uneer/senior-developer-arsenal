"""Tests for the shell-syntax lesson guard: hooks/guard_syntax.py, its registry entry, and its place in guard.py pre."""
import json
import os
import shutil
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import guard_lessons  # noqa: E402
import guard_syntax  # noqa: E402
import hook_env  # noqa: E402

APOSTROPHE = "echo 'the build isn't green'"


def fake_run(returncode=0, stderr=b"", error=None, calls=None):
    """A stand-in for subprocess.run: records its call, then raises error or returns the given result."""
    def run(argv, **kwargs):
        if calls is not None:
            calls.append((argv, kwargs))
        if error:
            raise error
        return subprocess.CompletedProcess(argv, returncode, b"", stderr)
    return run


class RealShellTests(unittest.TestCase):
    """The real bash parses each command; nothing it reads is run."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)

    def test_an_apostrophe_inside_single_quotes_is_a_parse_error(self):
        error = guard_syntax.parse_error(APOSTROPHE)
        self.assertIsNotNone(error)
        self.assertIn("unexpected EOF while looking for matching", error)

    def test_other_parse_errors(self):
        for command in ("if true; then echo x", "echo )", "for x in a b; do echo $x", "echo \"open",
                        "case $x in a) echo a;;", "f() { echo x"):
            self.assertIsNotNone(guard_syntax.parse_error(command), command)

    def test_valid_commands_pass(self):
        for command in (
                "cat <<'EOF' > notes.md\nit's fine, don't worry: the team's build\nEOF",
                "git commit -F - <<'EOF'\nfix: the parser's quote\n\nIt's done.\nEOF",
                "ls !(*.py)",
                "shopt -s extglob\nls +(a|b).txt @(x|y) ?(z)*(w)",
                "echo $'it\\'s here' $'tab\\there'",
                "case \"$x\" in\n  a|b) echo one ;;\n  'it''s') echo two ;;\n  *) echo other ;;\nesac",
                "set -euo pipefail\nfor f in *.txt; do\n  if [[ -s $f ]]; then\n    wc -l \"$f\"\n  fi\ndone\n"
                "build() { make \"$@\"; }\nbuild all\n",
                "echo \"it's fine in double quotes\"",
                "x=$(printf '%s' \"$(date)\"); echo \"$x\" | tr a b",
                "echo 'it'\\''s escaped the shell way'",
                "(( n = 1 + 2 )) && echo $n",
        ):
            self.assertIsNone(guard_syntax.parse_error(command), command)

    def test_an_open_here_document_is_only_a_warning(self):
        self.assertIsNone(guard_syntax.parse_error("cat <<'EOF'\nno end word"))

    def test_nothing_runs_during_the_check(self):
        made = self.dir / "made"
        for command in (f"touch {made}", f"touch {made}; echo 'it's'", f"echo $(touch {made})",
                        f"touch {made}\necho ok\necho 'won't parse'\n", f"cat <(touch {made})"):
            guard_syntax.parse_error(command)
            self.assertFalse(made.exists(), command)

    def test_the_error_names_the_line_of_a_multi_line_command(self):
        error = guard_syntax.parse_error("echo one\necho two\nfi\n")
        self.assertIn("line 3", error)

    @unittest.skipUnless(shutil.which("dash"), "dash is not installed")
    def test_another_shell_parses_by_its_own_grammar(self):
        self.assertIsNotNone(guard_syntax.parse_error(APOSTROPHE, "dash"))
        self.assertIsNone(guard_syntax.parse_error("echo 'fine'", "dash"))

    def test_a_zsh_glob_qualifier_is_a_bash_parse_error_so_the_docs_say_to_match_the_agents_shell(self):
        self.assertIsNotNone(guard_syntax.parse_error("for f in **/*.py(.); do echo $f; done"))
        reference = ROOT / ".agents" / "skills" / "lessons-learned" / "references" / "lesson-format-and-promotion.md"
        for text in (guard_lessons.__doc__, reference.read_text(encoding="utf-8")):
            self.assertIn("the shell the agent runs commands in", " ".join(text.split()))

    def test_a_missing_shell_passes(self):
        with mock.patch.dict(os.environ, {"PATH": str(self.dir)}):
            self.assertIsNone(guard_syntax.parse_error(APOSTROPHE))


class FailOpenTests(unittest.TestCase):
    """Every fault of the check passes the command."""

    def test_the_shell_is_called_with_no_execution_extglob_a_bare_environment_and_a_timeout(self):
        calls = []
        guard_syntax.parse_error("echo x", run=fake_run(calls=calls))
        guard_syntax.parse_error("echo x", "zsh", run=fake_run(calls=calls))
        guard_syntax.parse_error("echo x", "dash", run=fake_run(calls=calls))
        (bash, kwargs), (zsh, _), (dash, _) = calls
        self.assertEqual(bash, ["bash", "-n", "-O", "extglob"])
        self.assertEqual(zsh, ["zsh", "-n", "-f"])
        self.assertEqual(dash, ["dash", "-n"])
        self.assertEqual(kwargs["input"], b"echo x")
        self.assertEqual(kwargs["timeout"], 1.0)
        self.assertEqual(set(kwargs["env"]), {"PATH", "LC_ALL"})
        self.assertEqual(kwargs["env"]["LC_ALL"], "C")

    def test_faults_pass(self):
        for error in (FileNotFoundError("bash"), PermissionError("bash"), subprocess.TimeoutExpired("bash", 1.0),
                      OSError("fork failed"), RuntimeError("anything")):
            self.assertIsNone(guard_syntax.parse_error(APOSTROPHE, run=fake_run(error=error)), repr(error))

    def test_an_exit_that_is_not_a_parse_error_passes(self):
        for code, stderr in ((2, b"bash: extglob: invalid shell option name"), (1, b""), (127, b"not found"),
                             (0, b"bash: line 1: syntax error near unexpected token")):
            self.assertIsNone(guard_syntax.parse_error("echo x", run=fake_run(code, stderr)), (code, stderr))

    def test_the_first_parse_error_line_is_shown_after_a_warning(self):
        stderr = (b"bash: warning: here-document at line 1 delimited by end-of-file\n"
                  b"bash: line 2: syntax error near unexpected token `)'\nbash: line 2: `echo )'\n")
        self.assertEqual(guard_syntax.parse_error("x", run=fake_run(2, stderr)),
                         "bash: line 2: syntax error near unexpected token `)'")

    def test_the_error_line_is_cut_to_200_characters(self):
        error = guard_syntax.parse_error("x", run=fake_run(2, b"syntax error " + b"y" * 500))
        self.assertEqual(len(error), 200)
        self.assertTrue(error.endswith("\u2026"))
        self.assertEqual(guard_syntax.parse_error("x", run=fake_run(2, b"syntax error near x")), "syntax error near x")

    def test_only_the_first_4096_bytes_of_output_are_read(self):
        stderr = b"note\n" * 1000 + b"syntax error late\n"
        self.assertIsNone(guard_syntax.parse_error("x", run=fake_run(2, stderr)))

    def test_output_that_is_not_utf8_still_reads(self):
        self.assertIn("syntax error", guard_syntax.parse_error("x", run=fake_run(2, b"\xff\xfe syntax error")))

    def test_inputs_it_cannot_check_pass_without_running_a_shell(self):
        calls = []
        run = fake_run(2, b"syntax error", calls=calls)
        too_long = "echo " + "a" * guard_syntax.MAX_COMMAND_BYTES
        for command, shell in ((too_long, "bash"), (None, "bash"), (b"echo 'x", "bash"), ("echo 'x", "fish"),
                               ("echo 'x", "/bin/bash"), ("echo \udc80'x", "bash")):
            self.assertIsNone(guard_syntax.parse_error(command, shell, run=run), (command[:20] if command else command,
                                                                                  shell))
        self.assertEqual(calls, [])
        at_limit = "a" * guard_syntax.MAX_COMMAND_BYTES
        self.assertEqual(guard_syntax.parse_error(at_limit, run=run), "syntax error")


class RegistryTests(unittest.TestCase):
    """The rule in guard_lessons: off until named, judged first, configured per entry."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.project = self.dir / "project"
        self.project.mkdir()
        patch = mock.patch.dict(os.environ, {"LESSONS_GUARDS_GLOBAL_FILE": str(self.dir / "none.json")})
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)

    def registry(self, *guards):
        path = self.project / ".agents" / "lesson-guards.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"guards": list(guards)}), encoding="utf-8")

    def judge(self, command):
        return guard_lessons.judge(command, str(self.project))

    def test_off_until_a_registry_entry_names_it(self):
        self.assertIsNone(self.judge(APOSTROPHE))
        self.registry({"rule": "shell-syntax", "enabled": False})
        self.assertIsNone(self.judge(APOSTROPHE))

    def test_refuses_with_the_error_and_what_to_do_instead(self):
        self.registry({"rule": "shell-syntax", "lesson": "G008"})
        hit = self.judge(APOSTROPHE)
        self.assertEqual((hit.lesson, hit.rule), ("G008", "shell-syntax"))
        self.assertIn("unexpected EOF while looking for matching", hit.reason)
        self.assertIn("Write tool", hit.reason)
        self.assertIn("<<'EOF'", hit.reason)
        self.assertNotIn("{error}", hit.reason)
        self.assertIsNone(self.judge("cat <<'EOF'\nit's fine\nEOF"))

    def test_a_registry_reason_replaces_the_default(self):
        self.registry({"rule": "shell-syntax", "lesson": "G008", "reason": "Quote it properly."})
        self.assertEqual(self.judge(APOSTROPHE).reason, "Quote it properly.")

    def test_it_is_judged_before_the_other_rules_which_still_apply_to_valid_commands(self):
        self.registry({"rule": "shell-syntax"})
        self.assertEqual(self.judge("git commit --no-verify -m 'it's'").rule, "shell-syntax")
        self.assertEqual(self.judge("git commit --no-verify -m 'done'").rule, "hook-bypass")

    def test_the_shell_key(self):
        self.registry({"rule": "shell-syntax", "shell": "sh"})
        self.assertEqual(self.judge(APOSTROPHE).rule, "shell-syntax")
        self.assertEqual(guard_lessons.registry_problems(str(self.project)), [])

    def test_a_bad_shell_key_skips_the_entry_and_leaves_the_rule_off(self):
        for entry in ({"rule": "shell-syntax", "shell": "fish"}, {"rule": "shell-syntax", "shell": "/bin/bash"},
                      {"rule": "shell-syntax", "shell": ["bash"]}, {"rule": "shell-syntax", "shell": None},
                      {"rule": "help-probe", "shell": "bash"}):
            self.registry(entry)
            [problem] = guard_lessons.registry_problems(str(self.project))
            self.assertIn("shell is for the shell-syntax rule only", problem, entry)
            self.assertIsNone(self.judge(APOSTROPHE), entry)

    def test_min_version_1_29_0_skips_the_entry_on_an_older_hook(self):
        self.registry({"rule": "shell-syntax", "min_version": "1.29.0"})
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 28, 1)):
            self.assertIsNone(self.judge(APOSTROPHE))
            self.assertEqual(guard_lessons.registry_problems(str(self.project)), [])
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 29, 0)):
            self.assertEqual(self.judge(APOSTROPHE).rule, "shell-syntax")

    def test_a_broken_check_passes_the_command(self):
        self.registry({"rule": "shell-syntax"})
        with mock.patch.dict(os.environ, {"PATH": str(self.dir)}):
            self.assertIsNone(self.judge(APOSTROPHE))
        with mock.patch.object(guard_syntax.subprocess, "run", side_effect=subprocess.TimeoutExpired("bash", 1)):
            self.assertIsNone(self.judge(APOSTROPHE))


class HookTests(unittest.TestCase):
    """guard.py pre run as Claude Code runs it."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        registry = self.dir / ".agents" / "lesson-guards.json"
        registry.parent.mkdir()
        registry.write_text(json.dumps({"guards": [{"rule": "shell-syntax", "lesson": "G008"}]}), encoding="utf-8")

    def pre(self, command):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command},
                   "cwd": str(self.dir), "permission_mode": "default"}
        env = {k: v for k, v in os.environ.items() if not k.startswith(("ARSENAL_", "LESSONS_"))}
        env.update(hook_env.lesson_guard_files(self.dir), HANDOFF_SNAPSHOT=str(self.dir / "snap.md"),
                   CLAUDE_PROJECT_DIR=str(self.dir))
        done = subprocess.run([sys.executable, str(SCRIPT), "pre"], input=json.dumps(payload), capture_output=True,
                              text=True, cwd=self.dir, env=env, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["hookSpecificOutput"] if done.stdout.strip() else None

    def test_an_unparseable_command_is_denied_and_logged_without_its_text(self):
        made = self.dir / "made"
        out = self.pre(f"touch {made}\necho 'it's'")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("G008 (shell-syntax)", out["permissionDecisionReason"])
        self.assertFalse(made.exists())
        hits = (self.dir / "lesson-guard-hits.jsonl").read_text(encoding="utf-8")
        self.assertIn('"rule": "shell-syntax"', hits)
        self.assertNotIn("touch", hits)

    def test_a_valid_command_passes(self):
        self.assertIsNone(self.pre("cat <<'EOF'\nit's fine\nEOF"))


if __name__ == "__main__":
    unittest.main()
