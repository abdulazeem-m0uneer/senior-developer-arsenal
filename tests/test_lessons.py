"""Unit tests for the lessons-learned skill's ledger script."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "lessons-learned" / "scripts"))

import lessons  # noqa: E402


class LessonsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.file = str(Path(directory.name) / "nested" / "lessons.md")

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lessons.main(["--file", self.file, *argv])
        return code, out.getvalue(), err.getvalue()

    def add(self, mistake, rule="Run the migration dry run first", tags="sql"):
        return self.run_cli("add", "--tags", tags, "--mistake", mistake, "--cause", "assumed it was safe",
                            "--rule", rule, "--check", "grep dry-run in CI")

    def test_add_creates_file_and_active_lists_it(self):
        code, out, _ = self.add("Dropped a column without a dry run")
        self.assertEqual((code, out.strip()), (0, "added L001"))
        _, active, _ = self.run_cli("active")
        self.assertIn("L001 [sql] hits:1", active)
        self.assertIn("Check: grep dry-run in CI", active)

    def test_similar_lesson_bumps_instead_of_adding(self):
        self.add("Dropped a column without a dry run")
        _, out, _ = self.add("Dropped a column without any dry run again")
        self.assertIn("duplicate of L001: hits bumped to 2", out)
        self.assertEqual(self.run_cli("check")[1].count("L00"), 0)
        self.assertIn("1 lessons", self.run_cli("check")[1])

    def test_third_repeat_suggests_promotion(self):
        self.add("Dropped a column without a dry run")
        self.run_cli("bump", "L001")
        _, out, _ = self.run_cli("bump", "L001")
        self.assertIn("PROMOTE L001", out)

    def test_active_cap_archives_least_hit_oldest(self):
        for n in range(lessons.ACTIVE_CAP + 1):
            self.add(f"unique{n} thing{n} broke{n}", rule=f"distinct{n} guard{n} step{n}")
        active = self.run_cli("active")[1]
        self.assertEqual(len(active.strip().splitlines()), lessons.ACTIVE_CAP)
        self.assertIn("[archive]", self.run_cli("search", "unique0")[1])

    def test_secret_like_content_is_refused(self):
        code, _, err = self.run_cli("add", "--mistake", "Committed api_key=sk-123456", "--cause", "x", "--rule", "y")
        self.assertEqual(code, 2)
        self.assertIn("secret", err)
        self.assertFalse(Path(self.file).exists())

    def test_missing_required_field_is_a_usage_error(self):
        self.assertEqual(self.run_cli("add", "--mistake", "m", "--rule", "r")[0], 2)

    def test_pipe_in_text_cannot_break_the_line_format(self):
        self.run_cli("add", "--mistake", "a | b", "--cause", "c | d", "--rule", "e | f")
        self.assertEqual(self.run_cli("check")[0], 0)

    def test_search_requires_every_word_and_archive_moves_lesson(self):
        self.add("Dropped a column without a dry run")
        self.assertEqual(self.run_cli("search", "column", "nonexistent")[1], "")
        self.run_cli("archive", "L001")
        self.assertEqual(self.run_cli("active")[1], "")
        self.assertIn("[archive] - L001", self.run_cli("search", "column")[1])

    def test_unknown_id_and_stray_lines_are_reported(self):
        self.assertEqual(self.run_cli("bump", "L999")[0], 2)
        self.add("Dropped a column without a dry run")
        Path(self.file).write_text(Path(self.file).read_text() + "hand written note\n")
        self.assertEqual(self.run_cli("check")[0], 1)
        self.assertEqual(self.run_cli("bump", "L001")[0], 2)

    def hook_context(self):
        code, out, _ = self.run_cli("active", "--hook")
        self.assertEqual(code, 0)
        payload = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(payload["hookEventName"], "SessionStart")
        return payload["additionalContext"]

    def test_hook_mode_emits_session_start_json_with_self_recording_instruction(self):
        context = self.hook_context()
        self.assertIn("If you catch your own mistake", context)
        self.assertIn("lessons.py add", context)
        self.assertIn("(no lessons yet)", context)
        self.add("Dropped a column without a dry run")
        context = self.hook_context()
        self.assertIn("L001 [sql]", context)
        self.assertNotIn("(no lessons yet)", context)

    def test_shipped_session_hook_points_at_this_script(self):
        config = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        entries = config["hooks"]["SessionStart"]
        self.assertIn("compact", entries[0]["matcher"])
        command = next(h["command"] for h in entries[0]["hooks"] if "lessons.py" in h["command"])
        relative = command.split("${CLAUDE_PLUGIN_ROOT}/")[1].split('"')[0]
        self.assertTrue((ROOT / relative).is_file(), relative)
        self.assertIn("active --hook", command)

    def test_date_is_today(self):
        with mock.patch.object(lessons, "today", return_value="2026-11-04"):
            self.add("Dropped a column without a dry run")
        self.assertIn("| 2026-11-04 |", self.run_cli("active")[1])


if __name__ == "__main__":
    unittest.main()
