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
    env = {**os.environ, "HANDOFF_SNAPSHOT": str(Path(cwd) / "snap.md")}
    return subprocess.run([sys.executable, str(SCRIPT), cmd], cwd=cwd, input=stdin,
                          capture_output=True, text=True, env=env)


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        subprocess.run(["git", "init", "-q"], cwd=self.dir, check=True)
        (Path(self.dir) / "work.txt").write_text("x")

    def tearDown(self):
        self.tmp.cleanup()

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

    def test_hooks_json_wires_precompact_and_session_start(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        self.assertIn("snapshot.py", json.dumps(hooks["PreCompact"]))
        self.assertIn("snapshot.py", json.dumps(hooks["SessionStart"]))


if __name__ == "__main__":
    unittest.main()
