"""PRIVACY.md must disclose every field the usage-stats recorder stores and every local store's off switch."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USAGE = ROOT / ".agents" / "skills" / "usage-stats" / "scripts" / "usage_stats.py"

# Each stored top-level field and the words PRIVACY.md uses for it. A new field fails here until it is disclosed.
DISCLOSED = {
    "schema": None,  # format version of the line, not data about the user
    "session": "session ID",
    "first": "first and last dates",
    "last": "first and last dates",
    "project": "project ID",
    "claude_version": "Claude Code and arsenal versions",
    "arsenal_version": "Claude Code and arsenal versions",
    "skills": "skills and subagents",
    "subagents": "skills and subagents",
    "blocks": "blocks",
    "resolved": "blocks",
    "denials": "guard denials",
    "checks": "checks",
    "lessons": "lesson IDs",
    "edits": "edits",
    "tokens": "token counts",
}


def stored_fields():
    source = USAGE.read_text(encoding="utf-8")
    body = source[source.index('"schema": SCHEMA'):]
    body = body[:body.index("\n        }\n")]
    nested = {"recorded", "repeats", "ids", "bumped", "guarded"}  # keys inside "lessons"
    return set(re.findall(r'"(\w+)": ', body)) - nested


class PrivacyDisclosureTest(unittest.TestCase):
    def setUp(self):
        self.policy = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")

    def test_every_stored_usage_field_is_known(self):
        self.assertEqual(stored_fields() - set(DISCLOSED), set(), "add the new field to PRIVACY.md and DISCLOSED")

    def test_every_stored_usage_field_is_disclosed(self):
        for field, words in DISCLOSED.items():
            if words:
                self.assertIn(words, self.policy, field)

    def test_transcript_reads_and_off_switches_are_disclosed(self):
        for words in ("transcript", "ARSENAL_USAGE=off", "LESSONS_EVIDENCE=off", "lessons-evidence.jsonl", ".salt"):
            self.assertIn(words, self.policy, words)


if __name__ == "__main__":
    unittest.main()
