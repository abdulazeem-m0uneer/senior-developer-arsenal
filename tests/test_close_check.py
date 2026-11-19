"""Tests for the delivery-board-sync close check: a task is closed only with evidence for every criterion."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "delivery-board-sync" / "scripts"))
import close_check  # noqa: E402

CRITERIA = """# done line and the requester's close list
C1 rider can book a seat on a shared trip
C2: the booking shows on the driver's manifest
receipt email is sent
"""


class ProblemTests(unittest.TestCase):
    def check(self, comment, criteria=CRITERIA):
        return close_check.problems(close_check.criteria_of(criteria), comment)

    def test_every_criterion_with_evidence_closes(self):
        comment = """CLOSE CHECK:
- C1: merged 3433860 in #24, smoke 26 passed
- c2: https://ci.example.com/runs/44353184835
- Receipt email is sent: v1.13.0 released, verified on staging run 123456789
"""
        self.assertEqual(self.check(comment), [])

    def test_a_criterion_may_be_named_by_its_id_its_text_or_both(self):
        for label in ("C1", "rider can book a seat on a shared trip", "C1 rider can book a seat on a shared trip",
                      "Rider can book a seat, on a shared trip!"):
            comment = (f"CLOSE CHECK:\n- {label}: #12\n- C2: 12/12 tests\n"
                       "- receipt email is sent: abc1234")
            self.assertEqual(self.check(comment), [], label)

    def test_missing_lines_and_missing_evidence_are_named(self):
        comment = "CLOSE CHECK:\n- C1: looks good\n- C2: done, trust me"
        self.assertEqual(self.check(comment), [
            "no evidence for: C1 rider can book a seat on a shared trip (give a commit, #PR, link, passing test "
            "count, tag or run id)",
            "no evidence for: C2 the booking shows on the driver's manifest (give a commit, #PR, link, passing test "
            "count, tag or run id)",
            "no line for: receipt email is sent"])

    def test_the_comment_must_start_with_the_mark(self):
        for comment in ("closing this\n- C1: #1", "", "Close check - C1: #1"):
            self.assertEqual(self.check(comment), ['the comment must start with "CLOSE CHECK:"'], comment)
        self.assertEqual(self.check("  close check:\n- C1: #1\n- C2: #2\n- receipt email is sent: #3"), [])

    def test_what_counts_as_evidence(self):
        for evidence in ("abc1234", "a" * 39 + "1", "#7", "https://x.example/pr/7", "http://ci.example.com/1",
                         "41 passed", "12/12", "v2.0.1", "run 4433804086", "merged 3433860ab99d in #24"):
            comment = f"CLOSE CHECK:\n- C1: {evidence}\n- C2: #1\n- receipt email is sent: #2"
            self.assertEqual(self.check(comment), [], evidence)
        for evidence in ("done", "merged", "abc12", "#", "v2", "v1.2", "run 12", "looks fine on staging", "x#7",
                         "defaced", "cafebabe", "0/12", "12/20", "2026/11", "0 passed", "3 tests", "5 OK",
                         "all 9 green", "http://localhost", "https://x", "a" * 39 + "1" + "0"):
            comment = f"CLOSE CHECK:\n- C1: {evidence}\n- C2: #1\n- receipt email is sent: #2"
            self.assertEqual(len(self.check(comment)), 1, evidence)

    def test_criteria_file_forms(self):
        self.assertEqual(close_check.criteria_of("- AC-2 seats are held\n* plain text one\n\n# note"),
                         [("AC-2", "seats are held"), (None, "plain text one")])
        with self.assertRaises(close_check.Usage):
            close_check.criteria_of("# only comments\n\n")


class ReviewFindingTests(unittest.TestCase):
    def check(self, comment, criteria=CRITERIA):
        return close_check.problems(close_check.criteria_of(criteria), comment)

    def test_criteria_in_any_script_are_told_apart(self):
        criteria = "يحجز الراكب مقعدا\nيظهر الحجز للسائق\nCafé opens\nCaf opens"
        comment = "CLOSE CHECK:\n- يحجز الراكب مقعدا: #11\n- Café opens: #12\n- Caf opens: #13"
        self.assertEqual(self.check(comment, criteria), ["no line for: يظهر الحجز للسائق"])
        for bad in ("...\n", "C1 ???\n"):
            with self.assertRaises(close_check.Usage, msg=bad):
                close_check.criteria_of(bad)

    def test_an_unfilled_or_partly_filled_template_never_closes(self):
        criteria = "C1 add 12/12 tests for deadbeef1 parsing\nC2 ship v1.0.0 notes"
        skeleton = close_check.template(close_check.criteria_of(criteria))
        self.assertEqual(len(self.check(skeleton, criteria)), 2)
        partly = skeleton.replace(close_check.PLACEHOLDER, "#5", 1)
        self.assertEqual(self.check(partly, criteria), ["no evidence for: C2 ship v1.0.0 notes (give a commit, #PR, "
                                                        "link, passing test count, tag or run id)"])

    def test_a_line_that_says_not_done_closes_nothing(self):
        for evidence in ("not done yet, #12 open", "#12 pending review", "TODO after #12", "abc1234 failed on CI",
                         "#9 unmerged", "WIP in #3", "tests failing in run 4433804086", "not merged: #4"):
            comment = f"CLOSE CHECK:\n- C1: {evidence}\n- C2: #1\n- receipt email is sent: #2"
            [problem] = self.check(comment)
            self.assertTrue(problem.startswith("not done: C1"), evidence)

    def test_duplicate_criteria_are_refused(self):
        for criteria in ("C1 a\nC1 b", "C1 same text\nC2 same text", "same text\nSame Text!", "C1 a\nc1 b"):
            with self.assertRaises(close_check.Usage, msg=criteria):
                close_check.criteria_of(criteria)

    def test_honest_forms_are_accepted(self):
        criteria = "AC-12 docs: install and upgrade\nC2 second\nthird thing\nC4 fourth"
        comment = "\ufeffCLOSE CHECK：\r\n1. AC12: #3\r\n• C2： merged abc1234\r\n+ Third thing: 4 passed\r\n"
        self.assertEqual(self.check(comment, criteria), ["no line for: C4 fourth"])
        self.assertEqual(self.check("CLOSE CHECK:\n* ac-12: #1\n- c2: #2\n- third thing: #3\n- C4 fourth: #4",
                                    criteria), [])
        self.assertEqual(self.check("CLOSE CHECK:\n- docs: install and upgrade: #1\n- C2: #2\n- third thing: #3\n"
                                    "- C4: #4", criteria), [])  # the criterion text itself holds a colon

    def test_a_first_line_wins_and_other_lines_are_ignored(self):
        comment = "CLOSE CHECK:\n- C1: #1\n- C1: nothing here\nC2 shipped #9\n- C2: #2\n- receipt email is sent: #3"
        self.assertEqual(self.check(comment), [])


class CliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.criteria = self.dir / "criteria.txt"
        self.criteria.write_text(CRITERIA, encoding="utf-8")

    def run_cli(self, *argv, stdin="", stdin_bytes=None):
        out, err = io.StringIO(), io.StringIO()
        raw = io.TextIOWrapper(io.BytesIO(stdin_bytes if stdin_bytes is not None else stdin.encode("utf-8")))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(sys, "stdin", raw):
            code = close_check.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_template_then_check(self):
        code, out, _ = self.run_cli("template", "--criteria", str(self.criteria))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "CLOSE CHECK:",
            "C1 is: rider can book a seat on a shared trip",
            "- C1: <merged commit, #PR, link, passing test count, tag or run id>",
            "C2 is: the booking shows on the driver's manifest",
            "- C2: <merged commit, #PR, link, passing test count, tag or run id>",
            "- receipt email is sent: <merged commit, #PR, link, passing test count, tag or run id>"])
        self.assertEqual(self.run_cli("check", "--criteria", str(self.criteria), "--comment", "-", stdin=out)[0], 1)
        filled = out.replace("<merged commit, #PR, link, passing test count, tag or run id>", "#42")
        code, out, _ = self.run_cli("check", "--criteria", str(self.criteria), "--comment", "-", stdin=filled)
        self.assertEqual((code, out.strip()), (0, "closes: 3 criteria, each with evidence"))

    def test_usage_errors_exit_2(self):
        empty = self.dir / "empty.txt"
        empty.write_text("\n", encoding="utf-8")
        for argv in (("check", "--criteria", str(empty), "--comment", str(self.criteria)),
                     ("check", "--criteria", str(self.dir / "nope.txt"), "--comment", str(self.criteria)),
                     ("check", "--criteria", "-", "--comment", "-")):
            code, _, err = self.run_cli(*argv, stdin="C1 x")
            self.assertEqual(code, 2, argv)
            self.assertIn("close_check:", err, argv)
        with self.assertRaises(SystemExit):
            self.run_cli("check", "--criteria", str(self.criteria))  # --comment missing
        binary = self.dir / "binary.txt"
        binary.write_bytes(b"\xff\xfe\x00junk")
        self.assertEqual(self.run_cli("check", "--criteria", str(self.criteria), "--comment", str(binary))[0], 2)
        self.assertEqual(self.run_cli("check", "--criteria", str(self.criteria), "--comment", "-",
                                      stdin_bytes=b"\xff\xfe junk")[0], 2)

    def test_a_bom_on_the_criteria_file_is_not_part_of_the_first_criterion(self):
        self.criteria.write_bytes("\ufeffC1 first\nC2 second\n".encode("utf-8"))
        comment = self.dir / "c.txt"
        comment.write_text("CLOSE CHECK:\n- C1: #1\n- C2: #2", encoding="utf-8")
        self.assertEqual(self.run_cli("check", "--criteria", str(self.criteria), "--comment", str(comment))[0], 0)

    def test_a_refusal_lists_what_is_missing(self):
        comment = self.dir / "comment.txt"
        comment.write_text("CLOSE CHECK:\n- C1: #3\n", encoding="utf-8")
        code, out, _ = self.run_cli("check", "--criteria", str(self.criteria), "--comment", str(comment))
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[0], "not closed:")
        self.assertIn("- no line for: C2 the booking shows on the driver's manifest", out)


if __name__ == "__main__":
    unittest.main()
