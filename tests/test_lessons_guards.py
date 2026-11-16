"""lessons.py commands that turn repeats into guards: unguarded, hits, the promotion threshold, promote --keep-rule."""
import os
import re
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lessons import LedgerCase, promotion  # noqa: E402

import guard_hits  # noqa: E402  (on sys.path through test_lessons)


class GuardLedgerCase(LedgerCase):
    def setUp(self):
        super().setUp()
        self.hits_file = self.dir / "hits.jsonl"
        patch = mock.patch.dict(os.environ, {"LESSONS_GUARD_HITS_FILE": str(self.hits_file)})
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("LESSONS_PROMOTE_AT", None)

    def lesson(self, mistake, rule, hits=1, extra=()):
        lesson_id = re.search(r"added ([LG]\d{3,})", self.add(mistake, rule=rule, extra=extra)[1]).group(1)
        for _ in range(hits - 1):
            self.run_cli("bump", lesson_id)
        return lesson_id


class UnguardedTests(GuardLedgerCase):
    def setUp(self):
        super().setUp()
        self.once = self.lesson("Alpha happened once", "alpha rule unique")
        self.twice = self.lesson("Bravo happened twice", "bravo rule unique", hits=2)
        self.four = self.lesson("Charlie happened four times", "charlie rule unique", hits=4)
        self.guard = self.dir / "guard.py"
        self.guard.write_text("", encoding="utf-8")

    def listed(self, *argv):
        code, out, err = self.run_cli("unguarded", *argv)
        self.assertEqual(code, 0, err)
        return [line.split()[0] for line in out.splitlines()[:-1]], out.splitlines()[-1]

    def test_lists_repeats_without_a_guard_most_hits_first(self):
        ids, summary = self.listed("--min", "2")
        self.assertEqual(ids, [self.four, self.twice])
        self.assertEqual(summary, "2 lessons seen 2+ times without a guard")
        self.assertEqual(self.listed()[0], [self.four])  # default threshold 3

    def test_guarded_lessons_drop_out_and_archived_ones_stay(self):
        self.run_cli("promote", self.four, "--guard", str(self.guard))
        self.run_cli("archive", self.twice)
        _, out, _ = self.run_cli("unguarded", "--min", "2")
        self.assertNotIn(self.four, out)
        self.assertIn(f"{self.twice} hits:2 [archive]", out)

    def test_global_and_named_ledgers_are_included_once(self):
        self.lesson("Delta global mistake", "delta rule unique", hits=2, extra=("--global",))
        other = self.dir / "other.md"
        self.run_cli("--file", str(other), "add", "--mistake", "Echo other mistake", "--cause", "c", "--rule",
                     "echo rule unique")  # parsed last: --file given twice, the later wins
        self.run_cli("--file", str(other), "bump", "L001")
        _, out, _ = self.run_cli("unguarded", "--min", "2", str(other), self.file)
        self.assertIn("G001 hits:2 [active]", out)
        self.assertIn(f"L001 hits:2 [active] {other}", out)
        self.assertEqual(out.count("bravo rule unique"), 1)
        self.assertTrue(out.endswith("4 lessons seen 2+ times without a guard\n"))

    def test_globalized_lessons_are_counted_in_the_global_ledger_only(self):
        self.run_cli("globalize", self.four)
        _, out, _ = self.run_cli("unguarded")
        self.assertEqual(out.count("charlie rule unique"), 1)
        self.assertIn("G001 hits:4", out)

    def test_a_missing_named_ledger_and_a_bad_threshold_are_usage_errors(self):
        code, _, err = self.run_cli("unguarded", str(self.dir / "nope.md"))
        self.assertEqual(code, 2)
        self.assertIn("no ledger at", err)
        for bad in ("0", "-2"):
            self.assertEqual(self.run_cli("unguarded", "--min", bad)[0], 2, bad)

    def test_an_empty_ledger_lists_nothing(self):
        self.file = str(self.dir / "empty.md")
        self.assertEqual(self.listed("--min", "1"), ([], "0 lessons seen 1+ times without a guard"))


class ThresholdTests(GuardLedgerCase):
    def setUp(self):
        super().setUp()
        self.twice = self.lesson("Bravo happened twice", "bravo rule unique", hits=2)

    def test_check_min_and_the_environment_set_the_candidate_threshold(self):
        self.assertNotIn("candidate", self.run_cli("check")[1])
        self.assertIn(f"candidate {self.twice} hits:2", self.run_cli("check", "--min", "2")[1])
        with mock.patch.dict(os.environ, {"LESSONS_PROMOTE_AT": "2"}):
            self.assertIn(f"candidate {self.twice} hits:2", self.run_cli("check")[1])
            self.assertIn(f"{self.twice} hits:2", self.run_cli("unguarded")[1])
            self.assertNotIn("candidate", self.run_cli("check", "--min", "3")[1])  # the option wins

    def test_the_bump_hint_follows_the_threshold(self):
        third = self.lesson("Golf ball lost in the pond", "carry spare golf balls always")
        with mock.patch.dict(os.environ, {"LESSONS_PROMOTE_AT": "2"}):
            self.assertIn(f"PROMOTE {third}", self.run_cli("bump", third)[1])

    def test_an_unusable_environment_value_refuses_and_writes_nothing(self):
        before = Path(self.file).read_text(encoding="utf-8")
        for bad in ("two", "0", "-1"):
            with mock.patch.dict(os.environ, {"LESSONS_PROMOTE_AT": bad}):
                code, _, err = self.run_cli("bump", self.twice)
            self.assertEqual(code, 2, bad)
            self.assertIn("LESSONS_PROMOTE_AT", err)
        self.assertEqual(Path(self.file).read_text(encoding="utf-8"), before)


class KeepRuleTests(GuardLedgerCase):
    def setUp(self):
        super().setUp()
        self.add("Pasted a password into a chat line", rule="Name the secret file, never its value")
        self.guard = self.dir / "chat-guard.mjs"
        self.guard.write_text("", encoding="utf-8")
        self.rules = Path(self.file).parent / "rules" / promotion.RULE_FILE

    def test_a_partial_guard_also_writes_the_rule(self):
        code, out, _ = self.run_cli("promote", "L001", "--guard", str(self.guard), "--keep-rule")
        self.assertEqual(code, 0)
        self.assertIn("keeps the part of the rule", out)
        self.assertIn("- Name the secret file, never its value Check:", self.rules.read_text(encoding="utf-8"))
        promoted = f"| Promoted: {self.guard.as_posix()} + rule {self.rules.as_posix()}"
        self.assertIn(promoted, Path(self.file).read_text(encoding="utf-8"))
        self.assertNotIn("L001", self.run_cli("unguarded", "--min", "1")[1])
        self.assertEqual(self.run_cli("check")[0], 0)

    def test_keep_rule_needs_a_guard(self):
        code, _, err = self.run_cli("promote", "L001", "--keep-rule")
        self.assertEqual(code, 2)
        self.assertIn("--keep-rule goes with --guard", err)
        self.assertFalse(self.rules.exists())

    def test_a_missing_guard_writes_no_rule(self):
        code, _, _ = self.run_cli("promote", "L001", "--guard", str(self.dir / "nope.mjs"), "--keep-rule")
        self.assertEqual(code, 2)
        self.assertFalse(self.rules.exists())

    def test_a_full_guard_writes_no_rule(self):
        self.assertEqual(self.run_cli("promote", "L001", "--guard", str(self.guard))[0], 0)
        self.assertFalse(self.rules.exists())


class HitsCommandTests(GuardLedgerCase):
    def test_counts_per_lesson_in_the_window(self):
        guard_hits.append("G027", "hook-bypass", "/w")
        guard_hits.append("G027", "hook-bypass", "/w")
        guard_hits.append(None, "help-probe", "/w")
        guard_hits.append("G002", "pgrep-wait-loop", "/w", now=1)  # long ago
        code, out, _ = self.run_cli("hits", "--since", "24h")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[:2], ["G027 (hook-bypass) x2", "- (help-probe) x1"])
        self.assertIn("3 guard refusals in the last 24h", out)
        self.assertNotIn("G002", out)

    def test_no_log_and_damaged_lines(self):
        self.assertIn("0 guard refusals in the last 24h", self.run_cli("hits")[1])
        self.hits_file.write_text("garbage\n", encoding="utf-8")
        self.assertIn("1 damaged lines skipped", self.run_cli("hits")[1])

    def test_a_bad_window_is_a_usage_error(self):
        code, _, err = self.run_cli("hits", "--since", "yesterday")
        self.assertEqual(code, 2)
        self.assertIn("not a positive number", err)
