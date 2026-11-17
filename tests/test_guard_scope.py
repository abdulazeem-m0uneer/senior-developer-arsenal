"""Tests for the edit-scope lock (hooks/guard_scope.py), its wiring in guard.py pre, and scope.py."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "hooks" / "guard.py"
SCOPE = ROOT / ".agents" / "skills" / "parallel-sessions" / "scripts" / "scope.py"
sys.path.insert(0, str(ROOT / "hooks"))
import guard_scope  # noqa: E402


class ScopeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(os.path.realpath(self.tmp.name)) / "repo"
        for folder in ("src/billing", "src/auth", "tests/billing", ".claude"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def lock(self, content):
        text = content if isinstance(content, str) else json.dumps(content)
        (self.root / ".claude" / "arsenal-scope.json").write_text(text)

    def judge(self, path, tool="Write", cwd=None, key="file_path"):
        return guard_scope.refusal(tool, {key: path}, str(cwd or self.root))


class LockTest(ScopeCase):
    def test_no_lock_file_allows_everything(self):
        self.assertEqual(self.judge("src/auth/x.py"), "")

    def test_writes_inside_the_allowed_folders_pass_and_outside_are_denied(self):
        self.lock({"allow": ["src/billing", "tests/billing"], "reason": "billing refactor"})
        for path in ("src/billing/a.py", "src/billing/deep/b.py", str(self.root / "tests/billing/t.py")):
            self.assertEqual(self.judge(path), "", path)
        reason = self.judge("src/auth/x.py")
        self.assertIn("outside the allowed folders src/billing, tests/billing (billing refactor)", reason)
        self.assertIn("scope.py", reason)

    def test_every_write_tool_is_judged_and_other_tools_are_not(self):
        self.lock({"allow": ["src/billing"]})
        for tool in ("Write", "Edit", "MultiEdit"):
            self.assertTrue(self.judge("src/auth/x.py", tool), tool)
        self.assertTrue(self.judge("src/auth/n.ipynb", "NotebookEdit", key="notebook_path"))
        self.assertEqual(self.judge("src/auth/x.py", "Read"), "")
        self.assertEqual(guard_scope.refusal("Bash", {"command": "echo > src/auth/x.py"}, str(self.root)), "")

    def test_dot_dot_and_symlinks_are_resolved_before_comparing(self):
        self.lock({"allow": ["src/billing"]})
        self.assertTrue(self.judge("src/billing/../auth/x.py"))
        (self.root / "src/billing/link").symlink_to(self.root / "src/auth")
        self.assertTrue(self.judge("src/billing/link/x.py"))
        self.assertTrue(self.judge("src/billing-other/x.py"))  # a prefix of the name is not the folder

    def test_relative_paths_resolve_against_the_working_directory_and_the_lock_is_found_upward(self):
        self.lock({"allow": ["src/billing"]})
        self.assertEqual(self.judge("a.py", cwd=self.root / "src/billing"), "")
        self.assertTrue(self.judge("a.py", cwd=self.root / "src/auth"))

    def test_the_lock_file_itself_cannot_be_edited_unless_listed(self):
        self.lock({"allow": ["src/billing"]})
        self.assertTrue(self.judge(".claude/arsenal-scope.json", "Edit"))

    def test_a_malformed_lock_denies_every_write_and_names_the_fault(self):
        faults = {"{not json": "unreadable", json.dumps({"allow": []}): "non-empty list",
                  json.dumps({"allow": "src"}): "non-empty list", json.dumps(["src"]): "non-empty list",
                  json.dumps({"allow": ["/etc"]}): "absolute", json.dumps({"allow": ["../outside"]}): "outside",
                  json.dumps({"allow": [""]}): "non-empty list", "x" * (guard_scope.MAX_BYTES + 1): "larger than"}
        for content, fault in faults.items():
            with self.subTest(fault=fault):
                self.lock(content)
                reason = self.judge("src/billing/a.py")
                self.assertIn("malformed", reason)
                self.assertIn(fault, reason)

    def test_an_input_without_a_path_is_not_judged(self):
        self.lock({"allow": ["src/billing"]})
        for tool_input in ({}, {"file_path": ""}, {"file_path": 3}, None):
            self.assertEqual(guard_scope.refusal("Write", tool_input, str(self.root)), "")

    def test_a_lock_outside_the_repository_is_not_used(self):
        parent = self.root.parent / ".claude"
        parent.mkdir()
        (parent / "arsenal-scope.json").write_text(json.dumps({"allow": ["elsewhere"]}))
        self.assertEqual(self.judge("src/auth/x.py"), "")


class PreHookTest(ScopeCase):
    def pre(self, tool, tool_input, **env):
        payload = {"tool_name": tool, "tool_input": tool_input, "cwd": str(self.root), "permission_mode": "default",
                   "session_id": "scope-test"}
        environment = {k: v for k, v in os.environ.items() if not k.startswith("ARSENAL_")}
        environment.update(HANDOFF_SNAPSHOT=str(self.root.parent / "snap.md"), **env)
        out = subprocess.run([sys.executable, str(GUARD), "pre"], input=json.dumps(payload), cwd=self.root,
                             capture_output=True, text=True, env=environment)
        self.assertEqual((out.returncode, out.stderr), (0, ""))
        return json.loads(out.stdout)["hookSpecificOutput"] if out.stdout.strip() else None

    def test_the_hook_denies_a_write_outside_the_lock(self):
        self.lock({"allow": ["src/billing"]})
        decision = self.pre("Edit", {"file_path": str(self.root / "src/auth/x.py")})
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("arsenal scope lock", decision["permissionDecisionReason"])
        self.assertIsNone(self.pre("Edit", {"file_path": str(self.root / "src/billing/x.py")}))

    def test_the_report_write_a_reached_run_limit_allows_is_not_taken_back_by_the_lock(self):
        self.lock({"allow": ["src/billing"]})
        (self.root / ".claude" / "arsenal-run-limits.json").write_text(json.dumps({"max_tool_calls": 1}))
        self.assertIsNone(self.pre("Read", {"file_path": str(self.root / "src/billing/x.py")}))  # the one call
        handoff = self.pre("Write", {"file_path": str(self.root / "HANDOFF.md")})
        self.assertIsNone(handoff)  # the run-limit message promises that a .md report still works
        for elsewhere in (self.root.parent / "outside.md", Path.home() / ".claude" / "CLAUDE.md",
                          self.root / ".." / ".." / "escape.md", self.root / "CLAUDE.md", self.root / "AGENTS.md",
                          self.root / ".claude" / "commands" / "x.md", self.root / "docs" / "SKILL.md",
                          str(self.root / "notes") + "\x00.md"):
            with self.subTest(path=str(elsewhere)):  # the promise covers this project's lock root, nothing beyond
                decision = self.pre("Write", {"file_path": str(elsewhere)})
                self.assertEqual(decision["permissionDecision"], "deny")
                self.assertIn("arsenal scope lock", decision["permissionDecisionReason"])
        code = self.pre("Write", {"file_path": str(self.root / "src/auth/x.py")})
        self.assertEqual(code["permissionDecision"], "deny")
        self.assertIn("run limit", code["permissionDecisionReason"])

    def test_switches_turn_the_lock_off(self):
        self.lock({"allow": ["src/billing"]})
        path = {"file_path": str(self.root / "src/auth/x.py")}
        self.assertIsNone(self.pre("Write", path, ARSENAL_GUARD_SCOPE="off"))
        self.assertIsNone(self.pre("Write", path, ARSENAL_GUARD="off"))


class ScopeScriptTest(ScopeCase):
    def run_scope(self, *args, cwd=None):
        out = subprocess.run([sys.executable, str(SCOPE), *args], cwd=cwd or self.root, capture_output=True, text=True)
        return out.returncode, out.stdout, out.stderr

    def test_set_show_clear_round_trip(self):
        code, out, _ = self.run_scope("set", "src/billing", "tests/billing", "--reason", "billing refactor")
        self.assertEqual(code, 0, out)
        stored = json.loads((self.root / ".claude/arsenal-scope.json").read_text())
        self.assertEqual(stored, {"allow": ["src/billing", "tests/billing"], "reason": "billing refactor"})
        self.assertIn("src/billing", self.run_scope("show")[1])
        self.assertEqual(self.run_scope("clear")[:2], (0, "scope lock cleared\n"))
        self.assertEqual(self.run_scope("show")[1], "no scope lock\n")
        self.assertEqual(self.run_scope("clear")[1], "no scope lock\n")

    def test_folders_are_stored_relative_to_the_root_from_a_subdirectory(self):
        self.assertEqual(self.run_scope("set", "billing", cwd=self.root / "src")[0], 0)
        self.assertEqual(json.loads((self.root / ".claude/arsenal-scope.json").read_text())["allow"], ["src/billing"])

    def test_usage_errors(self):
        for args in ((), ("bogus",), ("set",), ("set", "missing"), ("set", ".."), ("set", "."),
                     ("set", "src/billing", "--reason")):
            with self.subTest(args=args):
                self.assertEqual(self.run_scope(*args)[0], 2)
        with tempfile.TemporaryDirectory() as plain:
            self.assertEqual(self.run_scope("show", cwd=plain)[0], 2)

    def test_a_lock_written_by_the_script_is_enforced(self):
        self.run_scope("set", "src/billing")
        self.assertTrue(self.judge("src/auth/x.py"))
        self.assertEqual(self.judge("src/billing/x.py"), "")


if __name__ == "__main__":
    unittest.main()
