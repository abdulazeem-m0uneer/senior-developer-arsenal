"""Each optional-tooling reference is linked from its skill and gives every tool a use case and a command."""
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / ".agents" / "skills"
REFS = {
    "security-audit": "scanner-tooling.md",
    "mobile-expert": "mobile-scan-tooling.md",
    "devops-ci": "host-hardening-tooling.md",
    "test-strategy": "fuzzing-tooling.md",
}


def _tool_rows(text):
    return [
        row for row in text.splitlines()
        if row.startswith("| ") and not row.startswith(("| Tool", "| :"))
    ]


class ToolingReferenceTest(unittest.TestCase):
    def test_reference_is_linked_from_skill(self):
        for skill, ref in REFS.items():
            body = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn(f"](./references/{ref})", body, skill)

    def test_every_tool_row_has_use_case_and_command(self):
        for ref in REFS.values():
            text = next(SKILLS.glob(f"*/references/{ref}")).read_text(encoding="utf-8")
            rows = _tool_rows(text)
            self.assertTrue(rows, ref)
            for row in rows:
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                self.assertEqual(len(cells), 3, row)
                self.assertTrue(all(cells), row)
                self.assertRegex(cells[2], r"`[^`]+`", row)

    def test_reference_says_what_to_do_when_tool_is_missing(self):
        for ref in REFS.values():
            text = next(SKILLS.glob(f"*/references/{ref}")).read_text(encoding="utf-8")
            self.assertIn("installed", text, ref)
            self.assertIn("not run", text, ref)


if __name__ == "__main__":
    unittest.main()
