"""Unit tests for `lessons.py retro` (lessons-learned/scripts/retro.py)."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "lessons-learned" / "scripts" / "lessons.py"


def git(cwd, *args, when=None):
    env = {**os.environ}
    if when:
        env.update(GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                   capture_output=True, env=env)


def lesson(lesson_id, hits, days_ago, rule="run the suite before pushing", promoted=""):
    when = (date.today() - timedelta(days=days_ago)).isoformat()
    return (f"- {lesson_id} [ci] hits:{hits} | {when} | Mistake: m{lesson_id} | Cause: c | Rule: {rule} | Check: k"
            + (f" | Promoted: {promoted}" if promoted else ""))


class RetroCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.repo, self.home = base / "repo", base / "home"
        self.repo.mkdir()
        self.home.mkdir()
        self.env = {**os.environ, "LESSONS_GLOBAL_FILE": str(self.home / "lessons.md"),
                    "LESSONS_EVIDENCE_FILE": str(self.home / "evidence.jsonl"),
                    "LESSONS_GUARD_HITS_FILE": str(self.home / "hits.jsonl")}
        self.env.pop("LESSONS_FILE", None)

    def tearDown(self):
        self.tmp.cleanup()

    def ledger(self, *lines, path=None):
        target = path or self.repo / ".agents" / "lessons.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Lessons Learned\n\n## Active\n" + "".join(line + "\n" for line in lines) + "\n## Archive\n")

    def commit(self, name, subject, days_ago=0):
        (self.repo / name).write_text(f"{subject}\n{time.time()}\n")
        git(self.repo, "add", "-A")
        when = (date.today() - timedelta(days=days_ago)).isoformat() + "T12:00:00"
        git(self.repo, "commit", "-qm", subject, when=when)

    def retro(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), "retro", *args], cwd=self.repo, capture_output=True,
                                text=True, env=self.env)
        return result.returncode, result.stdout, result.stderr


class EmptyTest(RetroCase):
    def test_outside_a_repository_and_without_a_ledger(self):
        code, out, _ = self.retro()
        self.assertEqual(code, 0)
        self.assertIn("not a git repository", out)
        self.assertIn("no lessons ledger found", out)
        self.assertIn("nothing repeated in the window", out)
        self.assertIn("1. Nothing to act on", out)

    def test_an_empty_repository(self):
        git(self.repo, "init", "-q")
        code, out, _ = self.retro()
        self.assertEqual(code, 0)
        self.assertIn("no commits in the window", out)

    def test_days_must_be_positive(self):
        code, _, err = self.retro("--days", "0")
        self.assertEqual(code, 2)
        self.assertIn("--days must be 1 or more", err)


class WeekTest(RetroCase):
    def setUp(self):
        super().setUp()
        git(self.repo, "init", "-q")
        self.commit("pay.py", "feat(pay): add refunds", days_ago=3)
        self.commit("pay.py", "fix(pay): round refunds", days_ago=2)
        self.commit("pay.py", "fix(pay): refund currency", days_ago=1)
        self.commit("api.py", 'Revert "feat(api): v2 routes"', days_ago=1)
        self.commit("old.py", "fix: ancient", days_ago=30)
        self.ledger(lesson("L001", 4, 1, rule="run pytest before pushing"),
                    lesson("L002", 1, 0, rule="quote heredocs"),
                    lesson("L003", 5, 20, rule="old repeat"),
                    lesson("L004", 3, 2, rule="guarded habit", promoted="hooks/guard_lessons.py"))
        self.ledger(lesson("G001", 2, 3, rule="never pgrep -f"), path=self.home / "lessons.md")
        (self.home / "evidence.jsonl").write_text(json.dumps(
            {"time": date.today().isoformat() + "T10:00:00+0000", "lesson": "L001", "failures": ["a", "b"]}) + "\n")
        (self.home / "hits.jsonl").write_text(json.dumps(
            {"time": int(time.time()) - 3600, "lesson": "L004", "rule": "no-help", "cwd": "/x"}) + "\n")

    def test_a_week_with_repeats(self):
        code, out, _ = self.retro()
        self.assertEqual(code, 0, out)
        self.assertIn("- 4 commits: 1 feat, 2 fix, 1 revert, 0 other", out)
        self.assertIn("lesson guards stopped 1 repeats on this machine: L004 x1", out)
        self.assertIn("L004 is enforced by hooks/guard_lessons.py", out)
        self.assertIn("1 new lessons recorded: L002", out)
        self.assertIn("- L001 x4 (no guard yet), 2 failed commands before it: run pytest before pushing", out)
        self.assertIn("- G001 x2: never pgrep -f", out)
        self.assertIn("pay.py fixed 2 times", out)
        self.assertIn('revert ', out)
        self.assertNotIn("L003", out.split("### Repeats without a guard")[0])  # dated outside the window
        self.assertIn("- L003 x5", out.split("### Repeats without a guard")[1].split("### Top 3 actions")[0])
        actions = out.split("### Top 3 actions")[1].strip().splitlines()
        self.assertEqual(len(actions), 3)
        self.assertTrue(actions[0].startswith("1. Guard L003 (x5)"))  # most hits among unguarded, whatever its date
        self.assertTrue(actions[1].startswith("2. Guard L001 (x4)"))
        self.assertNotIn("ancient", out)

    def test_project_leaves_out_the_global_ledger(self):
        _, out, _ = self.retro("--project")
        self.assertNotIn("G001", out)

    def test_the_days_boundary(self):
        self.ledger(lesson("L010", 2, 6, rule="six days ago"), lesson("L011", 2, 7, rule="seven days ago"))
        _, out, _ = self.retro("--days", "7")
        self.assertIn("L010 x2", out)
        self.assertNotIn("L011 x2", out)
        _, out, _ = self.retro("--days", "8")
        self.assertIn("L011 x2", out)

    def test_damaged_evidence_and_hit_lines_are_skipped(self):
        with (self.home / "evidence.jsonl").open("a") as handle:
            handle.write("not json\n[1]\n")
        with (self.home / "hits.jsonl").open("a") as handle:
            handle.write("{broken\n")
        code, out, _ = self.retro()
        self.assertEqual(code, 0)
        self.assertIn("2 failed commands before it", out)


class RepeatsWithoutAGuardTest(RetroCase):
    def section(self, out):
        return out.split("### Repeats without a guard")[1].split("### Top 3 actions")[0]

    def test_ten_are_listed_with_their_last_date_and_the_rest_counted(self):
        self.ledger(*[lesson(f"L{n:03d}", 20 - n, 40 + n, rule=f"rule number {n}") for n in range(1, 13)])
        code, out, _ = self.retro()
        self.assertEqual(code, 0)
        section = self.section(out)
        listed = [line for line in section.splitlines() if line.startswith("- L")]
        self.assertEqual([line.split(" ")[1] for line in listed], [f"L{n:03d}" for n in range(1, 11)])
        when = (date.today() - timedelta(days=41)).isoformat()
        self.assertIn(f"- L001 x19 (last {when}): rule number 1", section)
        self.assertIn("- and 2 more: `lessons.py unguarded`", section)
        self.ledger(*[lesson(f"L{n:03d}", 20 - n, 40 + n) for n in range(1, 12)])  # eleven: one more than shown
        self.assertIn("- and 1 more: `lessons.py unguarded`", self.section(self.retro()[1]))

    def test_none_left_with_and_without_exemptions(self):
        self.ledger(lesson("L001", 4, 1, promoted="tests/test_x.py"))
        self.assertIn("- none: every repeat has a guard\n", self.section(self.retro()[1]))
        self.ledger(lesson("L001", 4, 1, promoted="tests/test_x.py"), lesson("L002", 3, 1, promoted="exempt@3: why"))
        section = self.section(self.retro()[1])
        self.assertIn("- none: every repeat has a guard or an exemption (1)", section)
        self.assertNotIn("exempted on purpose", section)

    def test_a_lapsed_exemption_is_listed_again(self):
        self.ledger(lesson("L001", 5, 1, promoted="exempt@3: why"), lesson("L002", 3, 1, promoted="exempt@3: holds"))
        section = self.section(self.retro()[1])
        self.assertIn("- L001 x5", section)
        self.assertIn("- 1 exempted on purpose: L002", section)


class UnguardedStillWorksTest(RetroCase):
    def test_unguarded_output_is_unchanged_by_the_shared_helper(self):
        self.ledger(lesson("L001", 4, 1), lesson("L002", 1, 0), lesson("L004", 3, 2, promoted="x.py"))
        result = subprocess.run([sys.executable, str(SCRIPT), "unguarded"], cwd=self.repo, capture_output=True,
                                text=True, env=self.env)
        self.assertEqual(result.returncode, 0)
        self.assertIn("L001 hits:4 [active]", result.stdout)
        self.assertIn("1 lessons seen 3+ times without a guard", result.stdout)
        missing = subprocess.run([sys.executable, str(SCRIPT), "unguarded", "nope.md"], cwd=self.repo,
                                 capture_output=True, text=True, env=self.env)
        self.assertEqual(missing.returncode, 2)


if __name__ == "__main__":
    unittest.main()
