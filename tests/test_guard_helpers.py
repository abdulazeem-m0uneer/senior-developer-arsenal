"""A missing or broken optional helper of hooks/guard.py costs only its own check; the other gates keep working."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPERS = ("guard_destructive", "guard_limits", "guard_lessons")
DESTRUCTIVE = "git reset --hard"
LESSON = "while pgrep -f vitest; do sleep 1; done"


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                   capture_output=True)


class InstalledLayout(unittest.TestCase):
    """hooks/ copied beside the skills they import, as the installer lays them out, and a repository to work in."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.hooks, self.repo = base / "agents" / "arsenal-hooks", base / "repo"
        shutil.copytree(ROOT / "hooks", self.hooks, ignore=shutil.ignore_patterns("__pycache__"))
        for skill in ("lessons-learned", "handoff", "dead-code"):
            shutil.copytree(ROOT / ".agents" / "skills" / skill, base / "agents" / "skills" / skill,
                            ignore=shutil.ignore_patterns("__pycache__"))
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        (self.repo / "README.md").write_text("x")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "init")
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("ARSENAL_", "LESSONS_")) and key != "CLAUDE_PROJECT_DIR"}
        self.env["HANDOFF_SNAPSHOT"] = str(base / "snap.md")
        self.env["LESSONS_EVIDENCE"] = "off"
        self.env["HOME"] = str(base / "home")  # no global lesson guards or hit log of the developer's own

    def tearDown(self):
        self.tmp.cleanup()

    def run_guard(self, cmd, payload):
        result = subprocess.run([sys.executable, str(self.hooks / "guard.py"), cmd], input=json.dumps(payload),
                                cwd=self.repo, capture_output=True, text=True, env=self.env)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        return json.loads(result.stdout) if result.stdout.strip() else None

    def decision(self, command, mode="default"):
        out = self.run_guard("pre", {"tool_name": "Bash", "tool_input": {"command": command},
                                     "cwd": str(self.repo), "permission_mode": mode})
        return out["hookSpecificOutput"]["permissionDecision"] if out else None

    def stop_blocks(self):
        self.run_guard("baseline", {"source": "startup", "cwd": str(self.repo)})
        (self.repo / "app.py").write_text("x = 1\n")
        out = self.run_guard("stop", {"stop_hook_active": False, "cwd": str(self.repo)})
        (self.repo / "app.py").unlink()
        return bool(out and out.get("decision") == "block")

    def break_helper(self, name, how):
        path = self.hooks / f"{name}.py"
        if how == "missing":
            path.unlink()
        else:
            path.write_text("raise RuntimeError('broken install')\n")


class HelperFailOpenTest(InstalledLayout):
    def test_the_intact_layout_runs_every_gate(self):
        self.assertEqual(self.decision(DESTRUCTIVE), "ask")
        self.assertEqual(self.decision(LESSON), "deny")
        self.assertTrue(self.stop_blocks())

    def test_each_missing_or_broken_helper_costs_only_its_own_check(self):
        expected = {  # what still answers when the helper named in the key is gone
            "guard_destructive": {DESTRUCTIVE: None, LESSON: None},  # guard_lessons parses shell with it
            "guard_lessons": {DESTRUCTIVE: "ask", LESSON: None},
            "guard_limits": {DESTRUCTIVE: "ask", LESSON: "deny"},
        }
        for name in HELPERS:
            for how in ("missing", "broken"):
                with self.subTest(helper=name, how=how):
                    self.tearDown()
                    self.setUp()
                    self.break_helper(name, how)
                    for command, decision in expected[name].items():
                        self.assertEqual(self.decision(command), decision, command)
                    self.assertTrue(self.stop_blocks(), "the stop gate needs none of the optional helpers")

    def test_a_missing_snapshot_helper_still_fails_open_silently(self):
        shutil.rmtree(self.hooks.parent / "skills" / "handoff")
        self.assertIsNone(self.decision(DESTRUCTIVE))
        self.assertIsNone(self.run_guard("stop", {"stop_hook_active": False, "cwd": str(self.repo)}))


if __name__ == "__main__":
    unittest.main()
