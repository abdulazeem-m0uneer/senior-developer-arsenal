"""Turn a repeated lesson into a guard: a rule stub on disk, or a test stub to print.

Imported by lessons.py; not a command. Standard library only.
"""
import re
from pathlib import Path

from ledger_store import write_atomic

RULE_FILE = "lessons-promoted.md"
RULE_HEADER = ("---\ntrigger: always_on\n"
               "description: 'Rules promoted from the lessons ledger: mistakes that kept recurring.'\n"
               "---\n\n# Promoted Lessons\n\n")


def shown(path):
    """A path as stored in the ledger: relative to the working directory when it is inside it."""
    path = Path(path).resolve()
    here = Path.cwd().resolve()
    return (path.relative_to(here) if here in path.parents else path).as_posix().replace("|", "/")


def write_rule_stub(lesson, rules_dir):
    """Append the lesson's rule to the promoted-lessons rule file, creating it with frontmatter.

    Returns (path, appended). The rule text and check identify it, not the id: ids are reused when a ledger is
    recreated or a rules directory is shared, and a clash must not report a rule that was never written.
    """
    path = Path(rules_dir) / RULE_FILE
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else RULE_HEADER
    rule = f"- {lesson['rule']} Check: {lesson['check']}. "
    if any(line.startswith(rule) for line in text.splitlines()):
        return path, False
    line = f"{rule}(From lesson {lesson['id']}, seen {lesson['hits']} times: {lesson['mistake']})"
    write_atomic(path, text + ("" if text.endswith("\n") else "\n") + line + "\n")
    return path, True


def test_stub(lesson):
    name = "_".join(re.findall(r"[a-z0-9]+", lesson["rule"].lower())[:8]) or "lesson"
    return (f"# Regression guard for lesson {lesson['id']} (seen {lesson['hits']} times). Adapt to the project's "
            f"test framework.\n# Mistake: {lesson['mistake']}\n# Rule: {lesson['rule']}\n"
            f"import unittest\n\n\nclass Lesson{lesson['id']}Test(unittest.TestCase):\n"
            f"    def test_{name}(self):\n"
            f"        self.fail({('encode this check: ' + lesson['check'])!r})\n")
