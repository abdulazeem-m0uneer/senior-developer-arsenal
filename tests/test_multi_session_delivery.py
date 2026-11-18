"""Unit tests for the multi-session-delivery skill: the guarded merge script and the session bus."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from datetime import datetime
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


def fake_slow_gh():
    """A directory holding a `gh` that never answers, joined with the current PATH."""
    directory = tempfile.TemporaryDirectory()
    gh = Path(directory.name) / "gh"
    gh.write_text("#!/bin/sh\nexec sleep 60\n")
    gh.chmod(0o755)

    class Slow:
        def __enter__(self):
            return directory.name + os.pathsep + os.environ.get("PATH", "")

        def __exit__(self, *exc):
            directory.cleanup()
    return Slow()


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
        (args, options), = calls
        self.assertEqual((args, options["expect"]), ((9, False, None), ["tests", "e2e"]))
        self.assertEqual(options["runner"].keywords, {"timeout": merge_green.GH_TIMEOUT})

    def test_gh_timeout_flag_reaches_the_runner_and_must_be_positive(self):
        calls = []
        with unittest.mock.patch.object(merge_green, "merge_green", lambda *a, **k: calls.append(k) or 0):
            merge_green.main(["9", "--gh-timeout", "7.5"])
            with unittest.mock.patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
                merge_green.main(["9", "--gh-timeout", "0"])
        self.assertEqual(calls[0]["runner"].keywords, {"timeout": 7.5})
        self.assertEqual(raised.exception.code, 2)

    def test_gh_timeout_rejects_nan_and_inf(self):
        for value in ("nan", "inf"):
            with unittest.mock.patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
                merge_green.main(["9", "--gh-timeout", value])
            self.assertEqual(raised.exception.code, 2, value)

    def test_view_timeout_exits_4_and_never_merges(self):
        gh = FakeGh((merge_green.GH_TIMED_OUT, "gh did not answer in 120 s"))
        self.assertEqual(self.run_merge(gh, yes=True), merge_green.EXIT_GH_TIMEOUT)
        self.assertIn("timeout: gh pr view #7: gh did not answer in 120 s; nothing was merged", self.err[0])
        self.assertEqual(gh.merged(), [])

    def test_merge_call_timeout_reports_the_state_it_found(self):
        timed_out = (merge_green.GH_TIMED_OUT, "gh did not answer in 120 s")
        still_open = FakeGh(pull(comments=[review_line()]), merge=timed_out, after={"state": "OPEN"})
        self.assertEqual(self.run_merge(still_open, yes=True), merge_green.EXIT_GH_TIMEOUT)
        self.assertIn("timeout: #7 merge call", self.err[0])
        self.assertIn("is OPEN now and may still merge", self.err[0])
        merged = FakeGh(pull(comments=[review_line()]), merge=timed_out)
        self.assertEqual(self.run_merge(merged, yes=True), 0)
        self.assertTrue(self.out[0].startswith("merged: #7"))

    def test_hung_gh_binary_is_killed_and_reported(self):
        with fake_slow_gh() as path, unittest.mock.patch.dict(os.environ, {"PATH": path}):
            started = time.monotonic()
            code, text = merge_green.run_gh(["pr", "view", "7"], timeout=0.5)
        self.assertEqual((code, text), (merge_green.GH_TIMED_OUT, "gh did not answer in 0.5 s"))
        self.assertLess(time.monotonic() - started, 10)

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
        for name in ("send.sh", "send_check.py", "read.sh", "archive.sh", "lock.sh", "lanes.txt"):
            shutil.copy(SKILL / "templates" / "bus" / name, self.bus / name)

    def run_bus(self, script, *args, **env):
        done = subprocess.run(["bash", str(self.bus / script), *args], capture_output=True, text=True, check=False,
                              env={**os.environ, "BUS_LOCK_TRIES": "3", **env})
        return done.returncode, done.stdout + done.stderr

    def test_round_trip_repeats_a_line_until_it_is_acknowledged(self):
        self.assertEqual(self.run_bus("send.sh", "backend", "pm", "merged T-1 evidence"), (0, "ok inbox-backend\n"))
        for _ in range(2):   # a session that stops before acting must see the line again
            code, text = self.run_bus("read.sh", "backend")
            self.assertEqual(code, 0)
            self.assertRegex(text, r"^\d{4}-\d\d-\d\dT.* \| from pm \| merged T-1 evidence\n"
                                   r"\(1 unread; after acting on them: bash \S+read\.sh backend --ack 1\)\n$")
        self.assertFalse((self.bus / "read-mark-backend.txt").exists())
        self.assertEqual(self.run_bus("read.sh", "backend", "--ack", "1"), (0, "ok read-mark-backend 1\n"))
        self.assertEqual(self.run_bus("read.sh", "backend"), (0, "(no unread messages)\n"))
        self.run_bus("send.sh", "backend", "web", "Q: second")
        self.assertEqual(self.bodies(self.run_bus("read.sh", "backend")[1]), ["Q: second"])

    def test_ack_covers_only_the_lines_named_and_never_moves_back(self):
        for body in ("one", "two", "three"):
            self.run_bus("send.sh", "web", "pm", body)
        self.assertEqual(self.run_bus("read.sh", "web", "--ack", "2")[0], 0)
        self.assertEqual(self.bodies(self.run_bus("read.sh", "web")[1]), ["three"])   # arrived later: still unread
        code, text = self.run_bus("read.sh", "web", "--ack", "1")
        self.assertEqual((code, text), (0, "ok read-mark-web 2 (line 1 was already acknowledged)\n"))
        self.assertEqual((self.bus / "read-mark-web.txt").read_text(), "2\n")

    def test_ack_refuses_a_line_past_the_inbox_and_bad_usage(self):
        self.run_bus("send.sh", "web", "pm", "one")
        code, text = self.run_bus("read.sh", "web", "--ack", "2")
        self.assertEqual(code, 2)
        self.assertIn("cannot acknowledge line 2: the inbox has 1 line(s)", text)
        for args in (("web", "--ack"), ("web", "--ack", "x"), ("web", "--ack", "-1"), ("web", "--peek", "1"),
                     ("backend", "--ack", "1")):   # backend has no inbox
            with self.subTest(args=args):
                self.assertEqual(self.run_bus("read.sh", *args)[0], 2)
        self.assertFalse((self.bus / "read-mark-web.txt").exists())

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
        return [line.rsplit("| ", 1)[1] for line in text.splitlines() if " | from " in line]

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
        self.run_bus("read.sh", "web", "--ack", "2")
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

    def hold_lock(self, pid=None, age=0, host=None):
        host = host or subprocess.run(["bash", "-c", "echo ${HOSTNAME:-$(uname -n)}"], capture_output=True,
                                      text=True, check=True).stdout.strip()
        (self.bus / ".lock").write_text(f"{pid or os.getpid()} {int(time.time()) - age} {host}\n")

    def dead_pid(self):
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        return child.pid

    def test_lock_held_by_a_live_process_makes_writers_wait_then_fail_cleanly(self):
        self.hold_lock()
        code, text = self.run_bus("send.sh", "web", "pm", "x")
        self.assertEqual(code, 3)
        self.assertIn(f"bus is locked ({self.bus / '.lock'}, owner pid {os.getpid()})", text)
        self.assertFalse((self.bus / "inbox-web.md").exists())
        self.assertTrue((self.bus / ".lock").exists())   # a waiter never removes a lock it does not own
        self.assertEqual(self.run_bus("read.sh", "web", "--ack", "0")[0], 2)
        (self.bus / ".lock").unlink()
        self.assertEqual(self.run_bus("send.sh", "web", "pm", "x")[0], 0)
        self.assertFalse((self.bus / ".lock").exists())

    def test_lock_of_a_dead_process_is_taken_over(self):
        self.hold_lock(pid=self.dead_pid())
        self.assertEqual(self.run_bus("send.sh", "web", "pm", "x"), (0, "ok inbox-web\n"))
        self.assertEqual(sorted(path.name for path in self.bus.glob(".lock*")), [])

    def test_lock_older_than_the_bound_is_taken_over_even_when_its_pid_is_alive(self):
        self.hold_lock(age=120)
        self.assertEqual(self.run_bus("send.sh", "web", "pm", "x")[0], 0)
        self.hold_lock(age=120)
        self.assertEqual(self.run_bus("send.sh", "web", "pm", "x", BUS_LOCK_STALE="600")[0], 3)

    def test_pid_of_another_host_is_not_judged_dead(self):
        self.hold_lock(pid=self.dead_pid(), host="another-host")
        self.assertEqual(self.run_bus("send.sh", "web", "pm", "x")[0], 3)
        self.hold_lock(pid=self.dead_pid(), host="another-host", age=120)
        self.assertEqual(self.run_bus("send.sh", "web", "pm", "x")[0], 0)

    def test_lock_without_an_owner_is_taken_over_only_when_old(self):
        for make in (lambda path: path.write_text(""), lambda path: path.mkdir()):   # torn write, pre-file bus
            with self.subTest(make=make):
                lock = self.bus / ".lock"
                make(lock)
                self.assertEqual(self.run_bus("send.sh", "web", "pm", "x")[0], 3)
                old = time.time() - 600
                os.utime(lock, (old, old))
                self.assertEqual(self.run_bus("send.sh", "web", "pm", "x")[0], 0)
                self.assertFalse(lock.exists())

    def test_abandoned_takeover_guard_does_not_block_recovery(self):
        (self.bus / ".lock.takeover").write_text(f"{self.dead_pid()} 0 nowhere\n")
        self.hold_lock(pid=self.dead_pid())
        self.assertEqual(self.run_bus("send.sh", "web", "pm", "x")[0], 0)
        self.assertEqual(sorted(path.name for path in self.bus.glob(".lock*")), [])

    def test_killed_script_releases_or_leaves_a_recoverable_lock(self):
        holder = self.bus / "hold.sh"
        holder.write_text('#!/usr/bin/env bash\nset -euo pipefail\ndir=$(cd "$(dirname "$0")" && pwd)\n'
                          '. "$dir/lock.sh"\necho held\nread -r -t 30 _ || true\n')
        for signal_name, released in (("terminate", True), ("kill", False)):
            with self.subTest(signal=signal_name):
                script = subprocess.Popen(["bash", str(holder)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          text=True)
                self.assertEqual(script.stdout.readline(), "held\n")
                getattr(script, signal_name)()
                script.wait()
                script.stdin.close()
                script.stdout.close()
                self.assertEqual((self.bus / ".lock").exists(), not released)   # TERM releases, KILL cannot
                self.assertEqual(self.run_bus("send.sh", "web", "pm", "x")[0], 0)

    def test_bad_stale_bound_is_refused(self):
        self.assertEqual(self.run_bus("send.sh", "web", "pm", "x", BUS_LOCK_STALE="soon")[0], 2)

    def run_parallel(self, commands):
        env = {**os.environ, "BUS_LOCK_TRIES": "3000"}   # 300 s: nobody may give up under load
        running = [subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env=env)
                   for command in commands]
        return [(process.wait(), process.stderr.read(), process.stderr.close())[:2] for process in running]

    def test_parallel_sends_lose_nothing(self):
        count = 200
        results = self.run_parallel([["bash", str(self.bus / "send.sh"), "web", "pm", f"message {number}"]
                                     for number in range(count)])
        self.assertEqual([result for result in results if result != (0, "")], [])
        bodies = self.bodies((self.bus / "inbox-web.md").read_text())
        self.assertEqual(sorted(bodies), sorted(f"message {number}" for number in range(count)))
        self.assertEqual(sorted(path.name for path in self.bus.glob(".lock*")), [])

    def test_exactly_one_holder_at_a_time(self):
        # Each holder does a read-modify-write that loses an update, and records an overlap, if two are inside.
        worker = self.bus / "count.sh"
        worker.write_text('#!/usr/bin/env bash\nset -euo pipefail\ndir=$(cd "$(dirname "$0")" && pwd)\n'
                          '. "$dir/lock.sh"\n[ ! -e "$dir/inside" ] || echo overlap >> "$dir/overlaps"\n'
                          ': > "$dir/inside"\nn=$(cat "$dir/counter" 2>/dev/null || echo 0)\n'
                          'echo $((n + 1)) > "$dir/counter"\nrm "$dir/inside"\n')
        count = 100
        self.hold_lock(pid=self.dead_pid())   # every worker also races to take over a stale lock
        results = self.run_parallel([["bash", str(worker)]] * count)
        self.assertEqual([result for result in results if result != (0, "")], [])
        self.assertFalse((self.bus / "overlaps").exists())
        self.assertEqual((self.bus / "counter").read_text(), f"{count}\n")

    def test_missing_inbox_and_rotated_inbox(self):
        self.assertEqual(self.run_bus("read.sh", "web"), (0, "(no unread messages)\n"))
        (self.bus / "read-mark-web.txt").write_text("50\n")
        self.run_bus("send.sh", "web", "pm", "after archive")
        self.assertIn("after archive", self.run_bus("read.sh", "web")[1])
        (self.bus / "read-mark-web.txt").write_text("garbage\n")
        self.assertIn("after archive", self.run_bus("read.sh", "web")[1])
        self.assertEqual(self.run_bus("read.sh", "web", "--ack", "1")[0], 0)   # an ack repairs the mark
        self.assertEqual((self.bus / "read-mark-web.txt").read_text(), "1\n")


if __name__ == "__main__":
    unittest.main()


class EtaOnEverythingTests(unittest.TestCase):
    """send.sh refuses START/BLOCKER without an ETA, DONE without evidence and wrong weekdays, and records open items;
    overdue.py lists what is late. The clock is fixed at Wednesday 2026-11-18 16:00 local time."""
    NOW = "2026-11-18T16:00:00"

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.bus = Path(directory.name)
        for name in ("send.sh", "send_check.py", "overdue.py", "lock.sh", "lanes.txt"):
            shutil.copy(SKILL / "templates" / "bus" / name, self.bus / name)
        self.items = self.bus / "open-items.tsv"

    def send(self, line, sender="backend", now=None):
        done = subprocess.run(["bash", str(self.bus / "send.sh"), "pm", sender, line], capture_output=True, text=True,
                              check=False, env={**self.base_env(), "BUS_LOCK_TRIES": "3", "BUS_NOW": now or self.NOW})
        return done.returncode, done.stderr

    @staticmethod
    def base_env():
        """The test's own environment, without a BUS_ setting inherited from the developer's shell."""
        return {key: value for key, value in os.environ.items() if not key.startswith("BUS_")}

    def assert_sent(self, line, code=0, **kwargs):
        rc, err = self.send(line, **kwargs)
        self.assertEqual(rc, code, f"{line!r}: {err}")
        return err

    def last(self):
        return self.items.read_text(encoding="utf-8").splitlines()[-1].split("\t")

    def inbox_lines(self):
        inbox = self.bus / "inbox-pm.md"
        return inbox.read_text(encoding="utf-8").splitlines() if inbox.exists() else []

    def overdue(self, now, *args, items=None):
        done = subprocess.run([sys.executable, "-I", str(self.bus / "overdue.py"), *args], capture_output=True,
                              text=True, check=False,
                              env={**self.base_env(), "BUS_NOW": now, "BUS_OPEN_ITEMS": str(items or self.items)})
        return done.returncode, done.stdout.strip(), done.stderr

    # weekday next to a date (2026-11-26 and 2026-11-19 are Thursdays, 2027-01-04 a Monday)
    def test_weekdays_that_match_their_dates_pass(self):
        for line in ("pages due Thu 11-26", "launch Mon 2027-01-04", "Thursday 2026-11-19 is fine",
                     "launch Mon 01-04", "back on Sat 08-01",  # nearest year: past August
                      "Tue 2028-02-29 check", "Wed, 11-18 sync"):
            self.assert_sent(line)

    def test_wrong_weekdays_and_impossible_dates_are_refused(self):
        for line in ("pages due Wed 11-26", "launch Sun 2027-01-04", "due Mon 02-30",
                     "Thu 2026-11-19 and Tue 2026-11-18", "Wed 2027-02-29 check"):
            self.assertIn("weekday", self.assert_sent(line, 4), line)
        self.assertEqual(self.inbox_lines(), [])

    def test_text_that_only_looks_like_a_weekday_date_passes(self):
        for line in ("due 11-26, no weekday", "see you Monday", "Monthly 11-26 renewal", "office Mon-Fri 9-5",
                     "Tue 10-12 people joined", "Wed 10-12:30 slot", "Thu 11-26 days left", "Sun 10-12h"):
            self.assert_sent(line)
        self.assertFalse(self.items.exists())  # plain lines open no item

    # START and BLOCKER
    def test_start_and_blocker_need_a_valid_future_eta(self):
        for line in ("START T-1 build the page", "BLOCKER T-1 payouts need a rebase", "START T-1 x ETA 29:99",
                     "START T-1 x ETA 23:60", "BLOCKER T-1 x ETA 13-40 10:00", "START T-1 x ETA 02-30 10:00",
                     "START T-1 x ETA 2027-02-29 10:00", "START T-1 x ETA 11-17 10:00", "START T-1 x ETA tomorrow",
                     "START", "START: ", "BLOCKER T-1 x ETA 2025-12-01 09:00"):
            self.assertIn("refused", self.assert_sent(line, 6), line)
        self.assertEqual(self.inbox_lines(), [])
        self.assertFalse(self.items.exists())

    def test_the_old_words_cannot_skip_the_eta(self):
        for line in ("started T-1 page", "Started T-1 page", "blocked T-1 on review", "BLOCKED T-1 x"):
            self.assertIn("instead of 'started' or 'blocked'", self.assert_sent(line, 6), line)
        for line in ("restarted the worker", "unblocked T-1 now", "status: started by qa"):
            self.assert_sent(line)

    def test_an_accepted_start_is_recorded_after_its_inbox_line(self):
        self.assert_sent("START T-750 build page - web - ETA 11-19 12:00")
        sent, sender, key, eta, text = self.last()
        self.assertEqual((sender, key, eta, text), ("backend", "t-750", "2026-11-19 12:00",
                                                    "START T-750 build page - web - ETA 11-19 12:00"))
        self.assertTrue(sent.startswith("2026-11-18T16:00:00"))
        self.assertRegex(self.inbox_lines()[-1], r"\| from backend \| START T-750 build page")

    def test_eta_forms(self):
        cases = [("BLOCKER: #740: rebase conflict again ETA: 11-19 9:00", "#740", "2026-11-19 09:00"),
                 ("BLOCKER PG-02 needs #736 ETA 10:00", "pg-02", "2026-11-19 10:00"),  # past today: tomorrow
                 ("START PG-03 x ETA 16:00", "pg-03", "2026-11-18 16:00"),  # this minute counts as now
                 ("START PG-04 x ETA 23:59", "pg-04", "2026-11-18 23:59"),
                 ("BLOCKER PG-05 x ETA 11/22 12:00", "pg-05", "2026-11-22 12:00"),
                 ("START PG-06, x ETA 2027-01-04 08:00", "pg-06", "2027-01-04 08:00"),
                 ("START PG-07 x ETA 01-28 10:00", "pg-07", "2027-01-28 10:00")]  # nearest year: next January
        for line, key, eta in cases:
            self.assert_sent(line)
            self.assertEqual(self.last()[2:4], [key, eta], line)

    def test_year_end_dates_take_the_nearest_year(self):
        self.assert_sent("START Y-1 x ETA 01-02 10:00", now="2026-12-30T10:00:00")
        self.assertEqual(self.last()[3], "2027-01-02 10:00")
        self.assert_sent("START Y-2 x ETA 9:00", now="2026-12-31T23:30:00")
        self.assertEqual(self.last()[3], "2027-01-01 09:00")
        self.assertIn("refused", self.assert_sent("START Y-3 x ETA 12-30 10:00", 6, now="2027-01-02T10:00:00"))

    def test_a_leap_day_eta_needs_a_leap_year_near_now(self):
        self.assert_sent("START L-1 x ETA 02-29 10:00", now="2028-02-01T10:00:00")
        self.assertEqual(self.last()[3], "2028-02-29 10:00")
        self.assertIn("does not exist", self.assert_sent("START L-2 x ETA 02-29 10:00", 6))

    def test_tabs_in_a_line_never_break_the_record(self):
        self.assert_sent("START T-8\tx\twith tabs ETA 11-19 15:00")
        self.assertEqual(len(self.last()), 5)
        self.assertEqual(self.last()[4], "START T-8 x with tabs ETA 11-19 15:00")

    # DONE and CLEARED
    def test_done_and_cleared_need_a_key_and_evidence(self):
        for line in ("DONE", "DONE T-1", "CLEARED", "CLEARED: T-1", "DONE:  T-1  "):
            self.assertIn("evidence", self.assert_sent(line, 6), line)
        self.assert_sent("DONE T-1 merged abc1234")
        self.assertEqual(self.last()[2:4], ["t-1", "DONE"])
        self.assert_sent("CLEARED: PG-02, merged 8043a3e9")
        self.assertEqual(self.last()[2:4], ["pg-02", "DONE"])
        self.assert_sent("status: DONE by qa")  # the word later in a line is plain text
        self.assertEqual(self.last()[2], "pg-02")

    def test_only_accepted_lines_reach_the_inbox(self):
        sent = 0
        for line, code in (("START A-1 x ETA 11-19 10:00", 0), ("START A-2 x", 6), ("hello", 0), ("DONE A-1", 6),
                           ("due Wed 11-26", 4), ("DONE A-1 merged 1234567", 0)):
            self.assert_sent(line, code)
            sent += code == 0
        self.assertEqual(len(self.inbox_lines()), sent)
        self.assertEqual(len(self.items.read_text().splitlines()), 2)

    def test_a_check_that_cannot_run_lets_the_line_through_untracked(self):
        (self.bus / "send_check.py").write_text("raise SystemExit(9)\n")
        self.assertIn("line sent unchecked", self.assert_sent("START T-1 build the page"))
        self.assertEqual(len(self.inbox_lines()), 1)
        self.assertFalse(self.items.exists())

    def test_send_check_usage_and_bad_clock(self):
        script = str(self.bus / "send_check.py")
        usage = subprocess.run([sys.executable, "-I", script, "only-one"], capture_output=True, text=True)
        self.assertEqual(usage.returncode, 2)
        clock = subprocess.run([sys.executable, "-I", script, "START T-1 x ETA 10:00", "backend"], capture_output=True,
                               text=True, env={**self.base_env(), "BUS_NOW": "not-a-time"})
        self.assertEqual((clock.returncode, "BUS_NOW" in clock.stderr), (6, True))  # never a silent bypass

    # overdue.py
    def test_overdue_lists_late_items_with_redates_and_escalation(self):
        self.assert_sent("BLOCKER #740 payouts need a rebase - backend - ETA 11-18 18:00")
        self.assert_sent("BLOCKER: #740: rebase conflict again ETA: 11-19 9:00")  # a re-date
        self.assert_sent("START PG-05 page ETA 11/22 12:00")
        self.assert_sent("START PG-02 x ETA 11-19 08:00")
        self.assert_sent("DONE PG-02 merged 8043a3e9")
        code, out, _ = self.overdue("2026-11-19T11:00:00")
        self.assertEqual(code, 0)
        [line] = out.splitlines()
        self.assertTrue(line.startswith("OVERDUE #740 | owner backend | ETA 2026-11-19 09:00 | open 19.0h"), line)
        self.assertIn("| re-dated 1x | ESCALATE |", line)  # overdue and open 4 h or more
        self.assertEqual(self.overdue("2026-11-19T08:30:00")[1], "none")
        listed = self.overdue("2026-11-19T08:30:00", "--all")[1].splitlines()
        self.assertEqual([row.split(" | ")[0] for row in listed], ["open #740", "open pg-05"])  # ETA order

    def test_escalation_thresholds(self):
        for eta in ("11-18 17:00", "11-18 18:00", "11-18 19:00"):
            self.assert_sent(f"START R-1 x ETA {eta}")
        _, out, _ = self.overdue("2026-11-18T17:30:00", "--all")
        self.assertIn("re-dated 2x | ESCALATE", out)  # two re-dates escalate even inside the ETA
        self.assert_sent("START R-2 x ETA 11-18 17:00")
        _, out, _ = self.overdue("2026-11-18T17:30:00")
        self.assertIn("OVERDUE r-2 | owner backend | ETA 2026-11-18 17:00 | open 1.5h | re-dated 0x | START", out)
        _, out, _ = self.overdue("2026-11-18T17:30:00", "--escalate-hours", "1")
        self.assertIn("open 1.5h | re-dated 0x | ESCALATE", out)
        for bad in (("--escalate-hours", "0"), ("--escalate-redates", "0"), ("--nope",)):
            self.assertEqual(self.overdue(self.NOW, *bad)[0], 2, bad)

    def test_only_the_same_sender_closes_an_item(self):
        self.assert_sent("BLOCKER K-1 x ETA 11-18 17:00", sender="backend")
        self.assert_sent("DONE K-1 merged abc1234", sender="web")
        self.assertIn("OVERDUE k-1 | owner backend", self.overdue("2026-11-18T18:00:00")[1])
        self.assert_sent("START K-1 x ETA 11-18 17:30", sender="web")  # web's own item with the same key
        self.assertEqual(len(self.overdue("2026-11-18T18:00:00")[1].splitlines()), 2)
        self.assert_sent("DONE k-1: merged abc1234", sender="backend")  # keys compare in lower case
        self.assertEqual(self.overdue("2026-11-18T18:00:00")[1].split(" | ")[1], "owner web")

    def test_a_closed_item_reopened_starts_fresh(self):
        self.assert_sent("START Z-1 x ETA 11-18 17:00")
        self.assert_sent("DONE Z-1 merged abc1234")
        self.assert_sent("START Z-1 again ETA 11-18 17:30")
        _, out, _ = self.overdue("2026-11-18T18:00:00")
        self.assertIn("re-dated 0x", out)

    def test_overdue_without_a_file_damaged_lines_and_bad_clock(self):
        self.items.write_text("garbage\n\nnot-a-time\tb\tk\t2026-11-18 10:00\tx\n"
                              "2026-11-18T09:00:00+00:00\tb\tk2\tsoon\tSTART k2 odd\n", encoding="utf-8")
        code, out, err = self.overdue(self.NOW)
        self.assertEqual(code, 0)
        self.assertIn("2 damaged line(s)", err)
        self.assertTrue(out.startswith("OVERDUE k2 | owner b | ETA soon (unreadable)"), out)
        self.assertEqual(self.overdue("not-a-date")[0], 2)

    def test_waiting_lists_blockers_no_acting_session_has_taken(self):
        (self.bus / "lanes.txt").write_text("backend\nbackend-b\nweb\nqa\n", encoding="utf-8")
        for sender, line in (("web", "BLOCKER PG-05 no startedAt - backend-b - ETA 11-22 12:00"),
                             ("web", "BLOCKER PG-06 no totals - backend - ETA 11-22 12:00"),
                             ("backend", "START #746 PG-06 totals - ETA 19:00"),  # names the key: taken
                             ("qa", "BLOCKER X-1 own fix - qa - ETA 11-19 10:00"),  # own item: not waiting
                             ("web", "BLOCKER PG-1 api down - backend - ETA 11-19 10:00"),
                             ("backend", "START PG-10 other page - ETA 11-19 10:00"),  # pg-10 is not pg-1
                             ("web", "BLOCKER PG-7 needs data, no session named - ETA 11-19 10:00"),
                             ("web", "BLOCKER PG-8 api - Backend-B - ETA 11-19 10:00"),
                             ("backend-b", "START PG-8 fix - ETA 11-19 09:00"),  # same key: taken
                             ("web", "BLOCKER PG-9 x - backend - ETA 11-19 10:00"),
                             ("web", "DONE PG-9 merged abc1234")):  # closed: not listed
            self.assert_sent(line, sender=sender)
        code, out, _ = self.overdue(self.NOW, "--waiting")
        self.assertEqual(code, 0)
        rows = out.splitlines()
        self.assertEqual([row.split(" | ")[0] for row in rows], ["WAITING pg-05", "WAITING pg-1"])
        self.assertEqual(rows[0].split(" | ")[1:3], ["blocked web", "needs backend-b (no open item from it)"])
        self.assertEqual(rows[1].split(" | ")[2], "needs backend (no open item from it)")

    def test_waiting_needs_the_session_names(self):
        self.assert_sent("BLOCKER W-1 x - web - ETA 11-19 10:00")
        self.assertEqual(self.overdue(self.NOW, "--waiting")[1], "WAITING w-1 | blocked backend | needs web (no open "
                         "item from it) | ETA 2026-11-19 10:00 | BLOCKER W-1 x - web - ETA 11-19 10:00")
        done = subprocess.run([sys.executable, "-I", str(self.bus / "overdue.py"), "--waiting"], capture_output=True,
                              text=True, env={**self.base_env(), "BUS_NOW": self.NOW, "BUS_OPEN_ITEMS": str(self.items),
                                              "BUS_LANES": str(self.bus / "missing.txt")})
        self.assertEqual(done.returncode, 2)
        self.assertIn("needs the session names", done.stderr)

    def test_only_a_later_eta_counts_as_a_redate(self):
        self.assert_sent("BLOCKER K-2 waits on review - web - ETA 11-19 10:00")
        self.assert_sent("START K-2 same time again - ETA 11-19 10:00")  # repeats the ETA: not a re-date
        self.assert_sent("START K-2 sooner - ETA 11-19 09:00")  # earlier: not a re-date
        self.assertIn("| re-dated 0x | START K-2 sooner", self.overdue(self.NOW, "--all")[1])
        self.assert_sent("START K-2 later - ETA 11-19 11:00")
        self.assert_sent("START K-2 later again - ETA 11-19 12:00")
        self.assertIn("re-dated 2x | ESCALATE", self.overdue(self.NOW, "--all")[1])  # the escalation uses this count

    # review findings, each pinned
    def test_abbreviated_and_slash_weekday_dates_are_checked(self):
        for line in ("Thurs 11-27", "Tues 11-25", "Weds 11-26", "Thur 11-27", "Mon 11/25", "Wednesday 11-26",
                     "Thursday 2026-11-20", "Wed, 11-26", "wed 11-26", "Fri 11-21 amend the plan", "Fri 11-21 pmo",
                     "Fri 11-21 hourly", "Fri 11-21 peoples", "Fri 11-21 daysoff"):
            self.assertIn("weekday", self.assert_sent(line, 4), line)
        for line in ("Tues 11-24", "Weds 11-25", "Thurs 11-26", "Mon 11/23", "Fri 11-6 (single digit: not read)",
                     "Mon 9-5 shift", "Fri 11-21 am", "Fri 11-21 hours"):
            self.assert_sent(line)

    def test_the_last_eta_in_a_line_counts(self):
        self.assert_sent("BLOCKER K-1 vendor ETA 09:00 - backend - ETA 18:00")
        self.assertEqual(self.last()[3], "2026-11-18 18:00")
        self.assert_sent("START K-2 x - was ETA 11-17 10:00, now ETA 18:00")  # an old, past time quoted first
        self.assertEqual(self.last()[3], "2026-11-18 18:00")

    def test_eta_grammar_and_bounds(self):
        for line in ("START T-1 x ETA 24:00", "START T-1 x ETA 11-19 24:00", "START T-1 x ETA 10:00:30",
                     "START T-1 x ETA 10:00 11-19", "START T-1 x ETA 2027-03-01 10:00"):  # more than 90 days ahead
            self.assertIn("refused", self.assert_sent(line, 6), line)
        self.assert_sent("START B-1 x ETA 11-18 16:00")  # the current minute is not the past
        self.assert_sent("START B-2 x ETA 2027-02-16 10:00")  # 90 days ahead: allowed
        rc, err = subprocess.run(["bash", str(self.bus / "send.sh"), "pm", "web", "START B-3 x ETA 11-30 10:00"],
                                 capture_output=True, text=True, env={**self.base_env(), "BUS_NOW": self.NOW,
                                                                      "BUS_ETA_MAX_DAYS": "7"}).returncode, None
        self.assertEqual(rc, 6)
        for bad in ("0", "soon"):
            done = subprocess.run(["bash", str(self.bus / "send.sh"), "pm", "web", "START B-4 x ETA 11-19 10:00"],
                                  capture_output=True, text=True,
                                  env={**self.base_env(), "BUS_NOW": self.NOW, "BUS_ETA_MAX_DAYS": bad})
            self.assertEqual((done.returncode, "BUS_ETA_MAX_DAYS" in done.stderr), (6, True), bad)

    def test_keys_and_evidence_must_be_words(self):
        for line in ("START (k) x ETA 11-19 10:00", "START - x ETA 11-19 10:00", "START ETA 11-19 10:00",
                     "BLOCKER : x ETA 11-19 10:00", "DONE k-1 -", "DONE k-1 ...", "DONE (k-1) merged abc"):
            self.assertIn("refused", self.assert_sent(line, 6), line)
        self.assert_sent("START #741: x ETA 11-19 10:00")
        self.assertEqual(self.last()[2], "#741")

    def test_case_and_leading_space_cannot_skip_the_check(self):
        for line in ("Done T-1", "done T-1 merged abc1234", "Start T-1 x ETA 11-19 10:00", "blocker T-1 x",
                     "Cleared: T-1 ok", "  START T-1 no eta", "\tDONE T-1"):
            self.assertIn("refused", self.assert_sent(line, 6), repr(line))
        self.assert_sent("  START T-1 x ETA 11-19 10:00")
        self.assertEqual(self.last()[2:4], ["t-1", "2026-11-19 10:00"])
        for line in ("Starting the worker", "Doneness test", "Blockers list"):
            self.assert_sent(line)

    def test_a_bad_clock_refuses_through_send_sh(self):
        rc, err = self.send("START T-1 x ETA 11-19 10:00", now="yesterday")
        self.assertEqual(rc, 6)
        self.assertIn("BUS_NOW", err)
        self.assertEqual(self.inbox_lines(), [])

    def test_a_record_that_cannot_be_written_still_delivers_the_line_once(self):
        self.items.mkdir()  # open-items.tsv cannot be appended to
        err = self.assert_sent("START T-1 x ETA 11-19 10:00")
        self.assertIn("line sent but not tracked", err)
        self.assertEqual(len(self.inbox_lines()), 1)

    def test_a_held_lock_refuses_before_writing_anything(self):
        (self.bus / ".lock").write_text(f"{os.getpid()} {int(time.time())} {os.uname().nodename}\n")
        rc, _ = self.send("START T-1 x ETA 11-19 10:00")
        self.assertEqual(rc, 3)
        self.assertEqual(self.inbox_lines(), [])
        self.assertFalse(self.items.exists())

    def test_long_punctuation_keys_stay_fast(self):
        started = time.monotonic()
        self.assert_sent("START " + "." * 50000 + "x - ETA 17:00", 6)
        self.assert_sent("DONE " + "," * 50000 + "x", 6)
        self.assertLess(time.monotonic() - started, 5)

    def test_record_fields(self):
        self.assert_sent("START F-1 " + "w" * 400 + " ETA 11-19 10:00")
        sent = self.last()[0]
        self.assertIsNotNone(datetime.fromisoformat(sent).utcoffset())
        row = self.overdue(self.NOW, "--all")[1]
        self.assertEqual(len(row.split(" | ")[-1]), 200)

    def test_listing_is_ordered_by_eta_not_by_arrival(self):
        self.assert_sent("START O-2 later ETA 11-18 17:30")
        self.assert_sent("START O-1 sooner ETA 11-18 17:00")
        self.assertEqual([r.split(" | ")[0] for r in self.overdue("2026-11-18T16:30:00", "--all")[1].splitlines()],
                         ["open o-1", "open o-2"])
        self.assertEqual([r.split(" | ")[0] for r in self.overdue("2026-11-18T18:00:00")[1].splitlines()],
                         ["OVERDUE o-1", "OVERDUE o-2"])

    def test_hours_open_count_from_the_first_line_and_boundaries(self):
        self.assert_sent("START H-1 x ETA 11-19 10:00")
        self.assert_sent("START H-1 later ETA 11-19 11:00", now="2026-11-18T20:00:00")
        self.assertIn("open 19.0h", self.overdue("2026-11-19T11:00:00", "--all")[1])
        self.assertEqual(self.overdue("2026-11-19T11:00:00")[1], "none")  # at the ETA minute: not yet late
        self.assertIn("OVERDUE h-1", self.overdue("2026-11-19T11:01:00")[1])
        self.assert_sent("START E-1 x ETA 11-18 18:00")
        self.assertIn("open 4.0h | re-dated 0x | ESCALATE", self.overdue("2026-11-18T20:00:00")[1])
        self.assertNotIn("ESCALATE", self.overdue("2026-11-18T19:59:00")[1].split("\n")[0] + "")

    def test_waiting_takes_the_session_named_last(self):
        (self.bus / "lanes.txt").write_text("backend\nweb\n", encoding="utf-8")
        self.assert_sent("BLOCKER W-2 the web form sends bad dates - backend - ETA 11-19 10:00", sender="web")
        self.assertIn("needs backend", self.overdue(self.NOW, "--waiting")[1])
        (self.bus / "lanes.txt").write_bytes(b"backend\nweb\n\xff\n")  # not UTF-8: still read
        self.assertEqual(self.overdue(self.NOW, "--waiting")[0], 0)

    def test_overdue_bad_inputs(self):
        self.assertEqual(self.overdue(self.NOW, "--escalate-hours", "nan")[0], 2)
        self.assertEqual(self.overdue(self.NOW, "--waiting", "--accuracy")[0], 2)
        code, _, err = self.overdue(self.NOW, items=self.bus / "typo.tsv")
        self.assertEqual(code, 2)
        self.assertIn("no open-items file", err)
        directory = self.bus / "dir.tsv"
        directory.mkdir()
        self.assertEqual(self.overdue(self.NOW, items=directory)[0], 2)
        done = subprocess.run([sys.executable, "-I", str(self.bus / "overdue.py")], capture_output=True, text=True,
                              env={**self.base_env(), "BUS_NOW": self.NOW})  # default path, no file yet
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "none"))

    def test_an_unreadable_eta_sorts_first_on_a_leap_day(self):
        self.items.write_text("2028-02-28T09:00:00+00:00\tb\tk\tsoon\tSTART k odd\n"
                              "2028-02-28T09:00:00+00:00\tb\tk2\t2028-02-28 10:00\tSTART k2 x\n", encoding="utf-8")
        code, out, _ = self.overdue("2028-02-29T12:00:00")
        self.assertEqual(code, 0)
        self.assertEqual([r.split(" | ")[0] for r in out.splitlines()], ["OVERDUE k", "OVERDUE k2"])

    def test_accuracy_against_the_first_promised_eta(self):
        self.items.write_text("".join(f"{line}\n" for line in (
            "2026-11-18T09:00:00\tqa\ta1\t2026-11-18 10:00\tSTART a1 x",
            "2026-11-18T09:50:00\tqa\ta1\tDONE\tDONE a1 ok",
            "2026-11-18T09:00:00\tqa\ta2\t2026-11-18 10:00\tSTART a2 x",
            "2026-11-18T09:30:00\tqa\ta2\t2026-11-18 11:00\tSTART a2 later",
            "2026-11-18T11:30:00\tqa\ta2\tDONE\tDONE a2 merged",
            "2026-11-18T09:00:00\tqa\ta3\t2026-11-18 11:00\tSTART a3 x",
            "2026-11-18T09:00:00\tweb\tw1\t2026-11-18 10:00\tSTART w1 x",
            "2026-11-18T10:00:00\tweb\tw1\tDONE\tDONE w1 exactly on time",
            "2026-11-18T09:00:00\tweb\tw2\tsoon\tSTART w2 unreadable",
            "2026-11-18T10:00:00\tweb\tw2\tDONE\tDONE w2 x",
            "2026-11-18T09:00:00\tweb\tw3\t2026-11-18 13:00\tSTART w3 still in time")), encoding="utf-8")
        code, out, _ = self.overdue("2026-11-18T12:00:00", "--accuracy")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "ACCURACY qa | finished 2 | on first ETA 1 of 2 (50%) | median late 90 min | re-dated 1x | "
            "open past first ETA 1",
            "ACCURACY web | finished 1 | on first ETA 1 of 1 (100%) | median late 0 min | re-dated 0x | "
            "open past first ETA 0"])  # w2's unreadable first ETA is left out
        self.assertEqual(self.overdue("2026-11-18T12:00:00", "--accuracy", items=self.bus / "none.tsv")[0], 2)
        self.items.write_text("", encoding="utf-8")
        self.assertEqual(self.overdue(self.NOW, "--accuracy")[1], "none")

    def test_accuracy_median_is_the_lower_middle(self):
        lines = []
        for n, late in enumerate((30, 10, 20, 40)):
            lines += [f"2026-11-18T09:00:00\tqa\tm{n}\t2026-11-18 10:00\tSTART m{n} x",
                      f"2026-11-18T10:{late:02d}:00\tqa\tm{n}\tDONE\tDONE m{n} x"]
        self.items.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertIn("on first ETA 0 of 4 (0%) | median late 20 min", self.overdue(self.NOW, "--accuracy")[1])

    # second review pass
    def test_hour_ranges_written_with_time_words_pass_and_bare_pairs_say_how(self):
        # 2026-10-12 is a Monday, so "Tue 10-12" would be a wrong date unless a time word follows
        for line in ("Tue 10-12 hrs blocked", "Tue 10-12 mins", "Tue 10-12 noon slot", "Tue 10-12 UTC"):
            self.assert_sent(line)
        self.assertIn("write them as times: 10:00-12:00", self.assert_sent("Tue 10-12 standup", 4))
        self.assert_sent("Tue 10:00-12:00 standup")

    def test_twelve_hour_and_malformed_etas_are_refused_with_the_reason(self):
        for line in ("START T-1 x ETA 5:00pm", "START T-1 x ETA 5:00 PM", "START T-1 x ETA 11:30a.m.",
                     "START T-1 x ETA 10:00:30", "START T-1 x ETA 17:00 10-12 tests"):
            self.assertIn("24-hour time", self.assert_sent(line, 6), line)
        self.assert_sent("START T-2 x eta 11-19 10:00")  # the word in any case
        self.assertEqual(self.last()[3], "2026-11-19 10:00")
        self.assertIn("needs 'ETA HH:MM'", self.assert_sent("START T-3 x no time at all", 6))

    def test_eta_ceiling_has_bounds(self):
        for bad in ("999999999", "36501"):
            done = subprocess.run(["bash", str(self.bus / "send.sh"), "pm", "web", "START B-5 x ETA 11-19 10:00"],
                                  capture_output=True, text=True,
                                  env={**self.base_env(), "BUS_NOW": self.NOW, "BUS_ETA_MAX_DAYS": bad})
            self.assertEqual((done.returncode, "from 1 to 36500" in done.stderr), (6, True), bad)

    def accuracy_of(self, *records, now="2026-11-18T12:00:00"):
        self.items.write_text("".join(f"{record}\n" for record in records), encoding="utf-8")
        return self.overdue(now, "--accuracy")[1].splitlines()

    def test_accuracy_rules(self):
        t = "2026-11-18T09:00:00"
        rows = self.accuracy_of(
            f"{t}\tzz\tz1\t2026-11-18 10:00\tSTART z1", "2026-11-18T10:00:30\tzz\tz1\tDONE\tDONE z1 x",  # 30 s late
            f"{t}\tzz\tz2\t2026-11-18 10:00\tSTART z2", "2026-11-18T10:01:30\tzz\tz2\tDONE\tDONE z2 x",  # 90 s
            f"{t}\tzz\tz3\t2026-11-18 10:00\tSTART z3", "2026-11-18T10:00:00\tzz\tz3\tDONE\tDONE z3 x",  # exact
            f"{t}\taa\ta1\t2026-11-18 11:00\tSTART a1 only open, overdue",  # nothing finished: n/a
            f"{t}\tmm\tm1\tsoon\tSTART m1", "2026-11-18T10:00:00\tmm\tm1\tDONE\tDONE m1 x",  # unreadable: left out
            f"{t}\tmm\tm2\t2026-11-18 10:00\tSTART m2", "2026-11-18T09:30:00\tmm\tm2\tCLEARED\tCLEARED m2 x",
            f"{t}\tmm\tm2\t2026-11-18 11:00\tSTART m2 reopened", "2026-11-18T10:30:00\tmm\tm2\tDONE\tDONE m2 y",
            f"{t}\tmm\tm3\t2026-11-18 11:00\tSTART m3", "2026-11-18T09:10:00\tmm\tm3\t2026-11-18 13:00\tSTART m3 later")
        self.assertEqual(rows, [
            "ACCURACY aa | finished 0 | on first ETA 0 of 0 (n/a) | median late 0 min | re-dated 0x | "
            "open past first ETA 1",
            "ACCURACY mm | finished 2 | on first ETA 2 of 2 (100%) | median late 0 min | re-dated 0x | "
            "open past first ETA 1",
            "ACCURACY zz | finished 3 | on first ETA 1 of 3 (33%) | median late 1 min | re-dated 0x | "
            "open past first ETA 0"])

    def test_accuracy_percentage_rounds(self):
        t = "2026-11-18T09:00:00"
        rows = self.accuracy_of(*[line for n, close in enumerate(("09:30", "09:40", "10:20"))
                                  for line in (f"{t}\tqa\tp{n}\t2026-11-18 10:00\tSTART p{n}",
                                               f"2026-11-18T{close}:00\tqa\tp{n}\tDONE\tDONE p{n} x")])
        self.assertIn("on first ETA 2 of 3 (67%) | median late 20 min", rows[0])

    def test_waiting_ignores_a_blocker_on_its_own_sender_and_takes_the_last_name(self):
        (self.bus / "lanes.txt").write_text("backend\nweb\n", encoding="utf-8")
        self.assert_sent("BLOCKER W-3 x - web - backend - ETA 11-19 10:00", sender="web")
        self.assert_sent("BLOCKER W-4 x - backend - web - ETA 11-19 10:00", sender="web")  # waits on itself
        self.assertEqual(self.overdue(self.NOW, "--waiting")[1].split(" | ")[:3],
                         ["WAITING w-3", "blocked web", "needs backend (no open item from it)"])

    # events and --health
    def events(self):
        path = self.bus / "events.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_every_attempt_is_an_event_without_the_message(self):
        self.assert_sent("START T-1 secretword ETA 11-19 10:00")
        self.assert_sent("START T-2 secretword", 6)
        self.assert_sent("due Wed 11-26 secretword", 4)
        self.assert_sent("plain note")
        self.assertEqual([e["outcome"] for e in self.events()], ["sent", "refused-eta", "refused-weekday", "sent"])
        self.assertEqual({(e["from"], e["to"]) for e in self.events()}, {("backend", "pm")})
        self.assertNotIn("secretword", (self.bus / "events.jsonl").read_text())

    def test_bypasses_are_events(self):
        (self.bus / "send_check.py").write_text("raise SystemExit(9)\n")
        self.assert_sent("START T-1 x")
        shutil.copy(SKILL / "templates" / "bus" / "send_check.py", self.bus / "send_check.py")
        self.items.mkdir()
        self.assert_sent("START T-2 x ETA 11-19 10:00")
        self.assertEqual([e["outcome"] for e in self.events()], ["unchecked", "untracked"])

    def test_an_event_that_cannot_be_written_never_stops_the_line(self):
        (self.bus / "events.jsonl").mkdir()
        self.assertIn("event not logged", self.assert_sent("plain note"))
        self.assertEqual(len(self.inbox_lines()), 1)

    def health(self, now=None, *args, items=None):
        done = subprocess.run([sys.executable, "-I", str(self.bus / "overdue.py"), "--health", *args],
                              capture_output=True, text=True,
                              env={**self.base_env(), "BUS_NOW": now or "2026-11-18T18:00:00",
                                   "BUS_OPEN_ITEMS": str(items or self.items)})
        return done.returncode, done.stdout.strip(), done.stderr

    def test_health_counts_and_degrades_on_bypass(self):
        self.assert_sent("START H-1 x ETA 11-18 17:00")
        self.assert_sent("START H-2 x ETA 11-19 10:00")
        self.assert_sent("START H-3 x", 6)
        self.assertEqual(self.health(), (0, "HEALTH ok | open 2 | overdue 1 | escalate 0 | sent 2 | refused 1 | "
                                            "unchecked 0 | untracked 0 | damaged 0 | since 24h", ""))
        (self.bus / "send_check.py").write_text("raise SystemExit(9)\n")
        self.assert_sent("START H-4 x")
        code, out, _ = self.health()
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("HEALTH degraded |"), out)
        self.assertIn("| unchecked 1 |", out)

    def test_health_window_damage_and_bad_input(self):
        (self.bus / "events.jsonl").write_text(
            '{"time":"2026-11-16T10:00:00Z","from":"a","to":"pm","outcome":"unchecked"}\n'  # outside 24 h
            '{"time":"2026-11-18T15:00:00Z","from":"a","to":"pm","outcome":"sent"}\n', encoding="utf-8")
        self.items.write_text("", encoding="utf-8")
        code, out, _ = self.health()
        self.assertEqual((code, "| sent 1 | refused 0 | unchecked 0 |" in out), (0, True))
        code, out, _ = self.health(None, "--since", "7d")
        self.assertEqual((code, "| unchecked 1 |" in out, out.endswith("since 7d")), (1, True, True))
        with open(self.bus / "events.jsonl", "a", encoding="utf-8") as handle:
            handle.write("not json\n{}\n")
        code, out, _ = self.health()
        self.assertEqual((code, "| damaged 2 |" in out), (1, True))
        for bad in (("--since", "0h"), ("--since", "week"), ("--health", "--accuracy")):
            self.assertEqual(self.health(None, *bad)[0], 2, bad)
        (self.bus / "events.jsonl").unlink()
        self.assertEqual(self.health()[0], 0)  # no events yet is healthy
