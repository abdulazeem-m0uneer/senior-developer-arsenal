import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "handoff" / "scripts" / "snapshot.py"


def run(cwd, cmd, stdin=""):
    env = {**os.environ, "HANDOFF_SNAPSHOT": str(Path(cwd) / "snap.md")}  # explicit override for most tests
    return subprocess.run([sys.executable, str(SCRIPT), cmd], cwd=cwd, input=stdin,
                          capture_output=True, text=True, env=env)


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        subprocess.run(["git", "init", "-q"], cwd=self.dir, check=True)
        (Path(self.dir) / "work.txt").write_text("x")
        self.outside = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()
        self.outside.cleanup()

    def test_write_records_uncommitted_work(self):
        result = run(self.dir, "write")
        self.assertEqual(result.returncode, 0)
        self.assertIn("work.txt", (Path(self.dir) / "snap.md").read_text())

    def test_show_after_compact_emits_hook_json(self):
        run(self.dir, "write")
        out = run(self.dir, "show", '{"source": "compact"}')
        context = json.loads(out.stdout)["hookSpecificOutput"]
        self.assertEqual(context["hookEventName"], "SessionStart")
        self.assertIn("work.txt", context["additionalContext"])

    def test_show_is_silent_on_other_sources(self):
        run(self.dir, "write")
        for source in ("startup", "resume", "clear"):
            self.assertEqual(run(self.dir, "show", json.dumps({"source": source})).stdout, "")

    def test_never_fails_outside_a_repo_or_on_bad_input(self):
        with tempfile.TemporaryDirectory() as plain:
            self.assertEqual(run(plain, "write").returncode, 0)
            self.assertFalse((Path(plain) / "snap.md").exists())
            self.assertEqual(run(plain, "show", "not json").returncode, 0)

    def test_default_path_is_outside_the_project_and_keyed_by_session(self):
        env = {k: v for k, v in os.environ.items() if k != "HANDOFF_SNAPSHOT"}
        env["TMPDIR"] = self.outside.name
        payload = json.dumps({"session_id": "abc/../123"})
        subprocess.run([sys.executable, str(SCRIPT), "write"], cwd=self.dir, input=payload,
                       capture_output=True, text=True, env=env, check=True)
        self.assertTrue((Path(self.outside.name) / "arsenal-snapshot-abc123.md").is_file())
        tracked = subprocess.run(["git", "status", "--short"], cwd=self.dir, capture_output=True, text=True)
        self.assertEqual(tracked.stdout.strip(), "?? work.txt")

    def test_precompact_timeout_covers_the_git_budget(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        self.assertGreaterEqual(hooks["PreCompact"][0]["hooks"][0]["timeout"], 15)

    def test_hooks_json_wires_precompact_and_session_start(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        self.assertIn("snapshot.py", json.dumps(hooks["PreCompact"]))
        self.assertIn("snapshot.py", json.dumps(hooks["SessionStart"]))


class SessionCoreTest(unittest.TestCase):
    def test_core_hook_emits_static_capped_context(self):
        script = ROOT / "hooks" / "session_core.py"
        first = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
        second = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
        self.assertEqual(first.returncode, 0)
        self.assertEqual(first.stdout, second.stdout)  # static text keeps the prompt cache warm
        context = json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(context), 1500)
        self.assertIn("test-every-change", context)

    def test_core_names_only_real_skills(self):
        text = (ROOT / "hooks" / "core.md").read_text()
        for skill in ("investigate", "test-every-change", "refactor-legacy", "code-review",
                      "requirements-grilling", "definition-of-done"):
            self.assertIn(skill, text)
            self.assertTrue((ROOT / ".agents" / "skills" / skill / "SKILL.md").is_file(), skill)

    def test_core_hook_is_wired_first_on_session_start(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        self.assertIn("session_core.py", hooks["SessionStart"][0]["hooks"][0]["command"])


if __name__ == "__main__":
    unittest.main()
