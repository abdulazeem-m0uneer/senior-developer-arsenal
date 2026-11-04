"""Unit tests for the multi-session-delivery skill: the guarded merge script and the session bus."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".agents" / "skills" / "multi-session-delivery"
sys.path.insert(0, str(SKILL / "scripts"))

import merge_green  # noqa: E402

HEAD = "b" * 40
OTHER = "c" * 40


def review_line(head=HEAD, reviewer="rev", author="dev", verdict="mergeable", blockers=0, highs=0):
    return (f"REVIEW-RESULT head={head} reviewer={reviewer} author={author} "
            f"verdict={verdict} blockers={blockers} highs={highs}")


def pull(state="OPEN", head=HEAD, checks=(("SUCCESS", "tests"),), comments=(), reviews=(), draft=False):
    return {"state": state, "isDraft": draft, "headRefOid": head,
            "statusCheckRollup": [{"name": name, "conclusion": result} for result, name in checks],
            "comments": [{"body": body} for body in comments], "reviews": list(reviews)}


class FakeGh:
    def __init__(self, view, merge=(0, ""), after=None):
        self.view, self.merge, self.after = view, merge, after or {"state": "MERGED", "mergeCommit": {"oid": "d" * 40}}
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["pr", "merge"]:
            return self.merge
        if any("mergeCommit" in arg for arg in args):
            return 0, json.dumps(self.after)
        return self.view if isinstance(self.view, tuple) else (0, json.dumps(self.view))

    def merged(self):
        return [call for call in self.calls if call[:2] == ["pr", "merge"]]


class MergeGreenTests(unittest.TestCase):
    def run_merge(self, gh, yes=False, repo=None, expect=()):
        self.out, self.err = [], []
        return merge_green.merge_green(7, yes, repo, runner=gh, out=self.out.append, err=self.err.append,
                                       expect=expect)

    def test_dry_run_reports_and_never_merges(self):
        gh = FakeGh(pull(comments=[review_line()]))
        self.assertEqual(self.run_merge(gh), 0)
        self.assertIn(f"would merge: #7 head {HEAD}", self.out[0])
        self.assertEqual(gh.merged(), [])

    def test_yes_merges_pinned_to_the_full_head(self):
        gh = FakeGh(pull(comments=[review_line()]))
        self.assertEqual(self.run_merge(gh, yes=True, repo="acme/app"), 0)
        self.assertEqual(gh.merged(), [["pr", "merge", "7", "-R", "acme/app", "--squash", "--match-head-commit", HEAD]])
        self.assertEqual(self.out, [f"merged: #7 head {HEAD} as dddddddd"])

    def test_refusals_exit_1_without_merging(self):
        cases = {
            "not open": pull(state="MERGED", comments=[review_line()]),
            "short head": pull(head="b" * 10, comments=[review_line()]),
            "no checks": pull(checks=(), comments=[review_line()]),
            "red check": pull(checks=(("SUCCESS", "lint"), ("FAILURE", "tests")), comments=[review_line()]),
            "pending check": dict(pull(comments=[review_line()]),
                                  statusCheckRollup=[{"name": "tests", "conclusion": "", "status": "IN_PROGRESS"}]),
            "pending commit status": dict(pull(comments=[review_line()]),
                                          statusCheckRollup=[{"context": "ci/build", "state": "PENDING"}]),
            "all skipped": pull(checks=(("SKIPPED", "deploy"),), comments=[review_line()]),
            "draft": pull(draft=True, comments=[review_line()]),
            "auto-merge enabled": dict(pull(comments=[review_line()]), autoMergeRequest={"enabledAt": "x"}),
            "self review in other case": pull(comments=[review_line(reviewer="Dev", author="dev")]),
            "later objection by same reviewer": pull(comments=[review_line(), review_line(highs=2)]),
            "objection by a second reviewer": pull(comments=[review_line(), review_line(reviewer="rev2", blockers=1)]),
            "changes requested on head": pull(comments=[review_line()], reviews=[
                {"state": "CHANGES_REQUESTED", "commit": {"oid": HEAD}, "author": {"login": "lead"}}]),
            "no review": pull(),
            "review of another head": pull(comments=[review_line(head=OTHER)]),
            "self review": pull(comments=[review_line(reviewer="dev", author="dev")]),
            "review with a high": pull(comments=[review_line(highs=1)]),
            "review not mergeable": pull(comments=[review_line(verdict="changes")]),
            "approval on old commit": pull(reviews=[{"state": "APPROVED", "commit": {"oid": OTHER}}]),
        }
        for name, view in cases.items():
            with self.subTest(name):
                gh = FakeGh(view)
                self.assertEqual(self.run_merge(gh, yes=True), 1)
                self.assertTrue(self.err[0].startswith("refused: #7 "), self.err)
                self.assertEqual(gh.merged(), [])

    def test_red_check_names_the_failing_check(self):
        self.run_merge(FakeGh(pull(checks=(("SUCCESS", "lint"), ("FAILURE", "tests")), comments=[review_line()])))
        self.assertIn("checks not green: tests", self.err[0])

    def test_commit_status_checks_count_when_green(self):
        view = dict(pull(comments=[review_line()]), statusCheckRollup=[{"context": "ci/build", "state": "SUCCESS"}])
        self.assertEqual(self.run_merge(FakeGh(view)), 0)

    def test_later_clean_verdict_replaces_an_earlier_objection(self):
        self.assertEqual(self.run_merge(FakeGh(pull(comments=[review_line(highs=1), review_line()]))), 0)

    def test_expected_check_missing_is_refused(self):
        gh = FakeGh(pull(comments=[review_line()]))
        self.assertEqual(self.run_merge(gh, yes=True, expect=("tests", "e2e")), 1)
        self.assertIn("missing or not successful: e2e", self.err[0])
        skipped = pull(checks=(("SUCCESS", "tests"), ("SKIPPED", "e2e")), comments=[review_line()])
        self.assertEqual(self.run_merge(FakeGh(skipped), expect=("e2e",)), 1)
        self.assertEqual(self.run_merge(FakeGh(pull(comments=[review_line()])), expect=("tests",)), 0)

    def test_merge_left_open_is_not_merged(self):
        gh = FakeGh(pull(comments=[review_line()]), merge=(0, "queued"), after={"state": "OPEN"})
        self.assertEqual(self.run_merge(gh, yes=True), 1)
        self.assertIn("not merged: #7 is OPEN (refused, or waiting in a merge queue)", self.err[0])

    def test_unreadable_state_after_merge_exits_3(self):
        original = FakeGh(pull(comments=[review_line()]), merge=(1, "HTTP 502"))
        gh_calls = lambda args: (1, "HTTP 502") if any("mergeCommit" in a for a in args) else original(args)
        self.assertEqual(self.run_merge(gh_calls, yes=True), 3)
        self.assertIn("check it by hand", self.err[0])

    def test_later_self_review_does_not_hide_an_independent_one(self):
        self.assertEqual(self.run_merge(FakeGh(pull(comments=[review_line(), review_line(author="rev")]))), 0)

    def test_main_parses_expect_and_defaults_to_dry_run(self):
        calls = []
        with unittest.mock.patch.object(merge_green, "merge_green", lambda *a, **k: calls.append((a, k)) or 0):
            self.assertEqual(merge_green.main(["9", "--expect", "tests, e2e ,"]), 0)
        self.assertEqual(calls, [((9, False, None), {"expect": ["tests", "e2e"]})])

    def test_approved_review_on_the_head_is_enough(self):
        gh = FakeGh(pull(reviews=[{"state": "APPROVED", "commit": {"oid": HEAD}, "author": {"login": "lead"}}]))
        self.assertEqual(self.run_merge(gh), 0)
        self.assertIn("approved review by lead", self.out[0])

    def test_gh_failure_or_bad_json_exits_2(self):
        for view in ((1, "HTTP 502"), (0, "not json"), (0, "null"), (0, "[]")):
            with self.subTest(view=view):
                self.assertEqual(self.run_merge(FakeGh(view)), 2)

    def test_failed_merge_call_that_merged_is_reported_merged(self):
        gh = FakeGh(pull(comments=[review_line()]), merge=(1, "HTTP 502"))
        self.assertEqual(self.run_merge(gh, yes=True), 0)
        self.assertTrue(self.out[0].startswith("merged: #7"))

    def test_failed_merge_that_did_not_merge_exits_1(self):
        gh = FakeGh(pull(comments=[review_line()]), merge=(1, "head moved"), after={"state": "OPEN"})
        self.assertEqual(self.run_merge(gh, yes=True), 1)
        self.assertIn("not merged: #7 is OPEN (refused, or waiting in a merge queue): head moved", self.err[0])


@unittest.skipUnless(shutil.which("bash"), "bash is not available")
class SessionBusTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.bus = Path(directory.name)
        for name in ("send.sh", "read.sh", "archive.sh", "lock.sh", "lanes.txt"):
            shutil.copy(SKILL / "templates" / "bus" / name, self.bus / name)

    def run_bus(self, script, *args):
        done = subprocess.run(["bash", str(self.bus / script), *args], capture_output=True, text=True, check=False,
                              env={**os.environ, "BUS_LOCK_TRIES": "3"})
        return done.returncode, done.stdout + done.stderr

    def test_round_trip_reads_each_line_once(self):
        self.assertEqual(self.run_bus("send.sh", "backend", "pm", "started T-1 evidence"), (0, "ok inbox-backend\n"))
        code, text = self.run_bus("read.sh", "backend")
        self.assertEqual(code, 0)
        self.assertRegex(text, r"^\d{4}-\d\d-\d\dT.* \| from pm \| started T-1 evidence\n$")
        self.assertEqual(self.run_bus("read.sh", "backend"), (0, "(no unread messages)\n"))
        self.run_bus("send.sh", "backend", "web", "Q: second")
        self.assertIn("from web | Q: second", self.run_bus("read.sh", "backend")[1])

    def test_message_and_sender_are_kept_on_one_line(self):
        (self.bus / "lanes.txt").write_text("Web\r\n")   # names are matched in lowercase
        self.assertEqual(self.run_bus("send.sh", "WEB", "pm", "x")[0], 0)
        (self.bus / "lanes.txt").write_text("Web  \r\nbackend\n")
        self.run_bus("send.sh", "PM", "Backend", "line one\nline two")
        lines = (self.bus / "inbox-pm.md").read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].endswith("| from backend | line one line two"))
        self.assertEqual(self.run_bus("send.sh", "pm", "back\nend|x", "x")[0], 2)
        self.assertEqual(self.run_bus("send.sh", "pm", "stranger", "x")[0], 2)

    def test_unknown_inbox_empty_message_and_bad_usage_exit_2(self):
        for args in (("nobody", "pm", "x"), ("web", "pm", ""), ("web", "pm")):
            with self.subTest(args=args):
                self.assertEqual(self.run_bus("send.sh", *args)[0], 2)
        self.assertFalse(list(self.bus.glob("inbox-*")))
        self.assertEqual(self.run_bus("read.sh")[0], 2)
        self.assertEqual(self.run_bus("read.sh", "../web")[0], 2)

    def bodies(self, text):
        return [line.rsplit("| ", 1)[1] for line in text.splitlines()]

    def test_archive_moves_only_old_lines_already_read(self):
        old = "".join(f"2000-01-01T00:00:0{i}Z | from pm | old{i}\n" for i in range(5))
        (self.bus / "inbox-web.md").write_text(old)
        (self.bus / "read-mark-web.txt").write_text("3\n")   # old0-old2 read, old3-old4 unread
        self.run_bus("send.sh", "web", "pm", "new1")
        self.assertEqual(self.run_bus("archive.sh", "7"), (0, "archived 3 line(s) of inbox-web\n"))
        self.assertEqual((self.bus / "read-mark-web.txt").read_text(), "0\n")
        archived = list((self.bus / "archive").glob("inbox-web-*.md"))
        self.assertEqual(self.bodies(archived[0].read_text()), ["old0", "old1", "old2"])
        self.run_bus("send.sh", "web", "pm", "new2")
        self.assertEqual(self.bodies(self.run_bus("read.sh", "web")[1]), ["old3", "old4", "new1", "new2"])

    def test_archive_keeps_everything_for_a_reader_without_a_mark(self):
        (self.bus / "inbox-web.md").write_text("2000-01-01T00:00:00Z | from pm | old\n")
        self.assertEqual(self.run_bus("archive.sh"), (0, ""))
        self.assertEqual(self.bodies(self.run_bus("read.sh", "web")[1]), ["old"])

    def test_archive_shifts_a_mark_past_the_archived_lines(self):
        (self.bus / "inbox-web.md").write_text("2000-01-01T00:00:00Z | from pm | old\n")
        self.run_bus("send.sh", "web", "pm", "read already")
        self.run_bus("read.sh", "web")
        self.run_bus("send.sh", "web", "pm", "fresh")
        self.run_bus("archive.sh")
        self.assertEqual((self.bus / "read-mark-web.txt").read_text(), "1\n")
        self.assertEqual(self.bodies(self.run_bus("read.sh", "web")[1]), ["fresh"])

    def test_archive_and_send_refuse_bad_input(self):
        self.assertEqual(self.run_bus("archive.sh", "x")[0], 2)
        self.assertEqual(self.run_bus("send.sh", "../web", "pm", "x")[0], 2)
        bad = subprocess.run(["bash", str(self.bus / "send.sh"), "web", "pm", "x"], capture_output=True, text=True,
                             env={**os.environ, "BUS_LOCK_TRIES": "abc"}, check=False)
        self.assertEqual(bad.returncode, 2)
        (self.bus / "lanes.txt").unlink()
        code, text = self.run_bus("send.sh", "web", "pm", "x")
        self.assertEqual(code, 2)
        self.assertIn("missing lanes.txt", text)

    def test_held_lock_makes_writers_wait_then_fail_cleanly(self):
        (self.bus / ".lock").mkdir()
        code, text = self.run_bus("send.sh", "web", "pm", "x")
        self.assertEqual(code, 3)
        self.assertIn("bus is locked", text)
        (self.bus / ".lock" / "pid").write_text("999999999\n")
        self.assertIn("owner pid 999999999 probably not running", self.run_bus("send.sh", "web", "pm", "x")[1])
        (self.bus / ".lock" / "pid").unlink()
        self.assertFalse((self.bus / "inbox-web.md").exists())
        (self.bus / ".lock").rmdir()
        self.assertEqual(self.run_bus("send.sh", "web", "pm", "x")[0], 0)
        self.assertFalse((self.bus / ".lock").exists())

    def test_missing_inbox_and_rotated_inbox(self):
        self.assertEqual(self.run_bus("read.sh", "web"), (0, "(no unread messages)\n"))
        (self.bus / "read-mark-web.txt").write_text("50\n")
        self.run_bus("send.sh", "web", "pm", "after archive")
        self.assertIn("after archive", self.run_bus("read.sh", "web")[1])
        (self.bus / "read-mark-web.txt").write_text("garbage\n")
        self.assertIn("after archive", self.run_bus("read.sh", "web")[1])


if __name__ == "__main__":
    unittest.main()
