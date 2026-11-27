"""Scripts must parse on Python 3.9, which doctor.py supports: no backslash inside an f-string replacement field
(a SyntaxError before 3.12), and nothing the 3.9 grammar lacks (match, parenthesized context managers)."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = sorted([*ROOT.glob("hooks/*.py"), *ROOT.glob("scripts/*.py"), *ROOT.glob(".agents/skills/*/scripts/*.py"),
                  *ROOT.glob("tests/*.py")])


def backslash_fields(tree, source):
    """Line numbers of f-string replacement fields whose expression text holds a backslash."""
    return [node.lineno for fv in ast.walk(tree) if isinstance(fv, ast.FormattedValue)
            for node in [fv.value] if "\\" in (ast.get_source_segment(source, node) or "")]


class Python39SyntaxTests(unittest.TestCase):
    def test_the_scan_finds_the_scripts(self):
        self.assertTrue(any(p.name == "push_once.py" for p in SOURCES))

    def test_the_scan_catches_a_backslash_in_a_field(self):
        source = "x = f\"{'a' if y else '|\\\\.py'}\"\n"
        self.assertEqual(backslash_fields(ast.parse(source), source), [1])

    def test_no_script_has_a_backslash_in_an_f_string_field(self):
        for path in SOURCES:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertEqual(backslash_fields(ast.parse(source), source), [])

    def test_every_script_parses_with_the_python_39_grammar(self):
        if sys.version_info < (3, 8):
            self.skipTest("feature_version needs 3.8+")
        for path in SOURCES:
            with self.subTest(path=str(path.relative_to(ROOT))):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 9))


if __name__ == "__main__":
    unittest.main()
