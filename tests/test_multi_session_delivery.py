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
        for name in ("send.sh", "read.sh", "archive.sh", "lock.sh", "lanes.txt"):
            shutil.copy(SKILL / "templates" / "bus" / name, self.bus / name)

    def run_bus(self, script, *args, **env):
        done = subprocess.run(["bash", str(self.bus / script), *args], capture_output=True, text=True, check=False,
                              env={**os.environ, "BUS_LOCK_TRIES": "3", **env})
        return done.returncode, done.stdout + done.stderr

    def test_round_trip_repeats_a_line_until_it_is_acknowledged(self):
        self.assertEqual(self.run_bus("send.sh", "backend", "pm", "started T-1 evidence"), (0, "ok inbox-backend\n"))
        for _ in range(2):   # a session that stops before acting must see the line again
            code, text = self.run_bus("read.sh", "backend")
            self.assertEqual(code, 0)
            self.assertRegex(text, r"^\d{4}-\d\d-\d\dT.* \| from pm \| started T-1 evidence\n"
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
