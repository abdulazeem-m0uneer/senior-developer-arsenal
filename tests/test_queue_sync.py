"""queue_sync.py: reorder the merge slot queue from gh state. No real gh is ever called."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "multi-session-delivery" / "scripts"))

import merge_green  # noqa: E402
import merge_slot  # noqa: E402
import queue_sync  # noqa: E402

GREEN_RUN = [{"name": "tests", "conclusion": "SUCCESS"}]
HEAD = "a" * 40


def pr(state="OPEN", draft=False, merge="CLEAN", base="main", checks=None):
    return {"state": state, "isDraft": draft, "mergeStateStatus": merge, "baseRefName": base, "headRefOid": HEAD,
            "statusCheckRollup": GREEN_RUN if checks is None else checks}


class Gh:
    """Answers `gh repo view` with the trunk and `gh pr view N` from a dict; a tuple value is the raw answer."""

    def __init__(self, prs=None, trunk="main", repo_answer=None, before_pr=None):
        self.prs, self.trunk, self.repo_answer, self.before_pr, self.calls = prs or {}, trunk, repo_answer, before_pr, []

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["repo", "view"]:
            return self.repo_answer or (0, json.dumps({"defaultBranchRef": {"name": self.trunk}}))
        if self.before_pr:
            self.before_pr(int(args[2]))
        value = self.prs.get(int(args[2]), pr())
        return value if isinstance(value, tuple) else (0, json.dumps(value))


class QueueSyncTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.state = str(Path(self.dir.name) / "slot.json")

    def seed(self, queue, holder=None, refusals=None):
        state = merge_slot.empty_state()
        state["queue"] = [{"pr": n, "lane": f"l{n}", "queued_at": "2030-01-01T10:00:00+00:00", "refusals": 0}
                          for n in queue]
        state["refusals"] = refusals or {}
        if holder:
            state["holder"] = {"pr": holder, "lane": f"l{holder}", "granted_at": "2030-01-01T10:00:00+00:00",
                               "claimed": True, "expires_at": "2030-01-01T10:40:00+00:00"}
        Path(self.state).write_text(json.dumps(state))
        return Path(self.state).read_text()

    def sync(self, *args, gh=None):
        out, err = [], []
        code = queue_sync.main([*args, "--state", self.state], runner=gh or Gh(), out=out.append, err=err.append)
        return code, "\n".join(out), "\n".join(err)

    def queue(self):
        return [q["pr"] for q in json.loads(Path(self.state).read_text())["queue"]]


class OrderTests(QueueSyncTestCase):
    def test_dry_run_prints_the_new_order_and_writes_nothing(self):
        before = self.seed([1, 2])
        code, out, _ = self.sync(gh=Gh({1: pr(draft=True)}))
        self.assertEqual(code, 0)
        self.assertIn("1. #2 (l2) ready", out)
        self.assertIn("2. #1 (l1) not ready: is a draft", out)
        self.assertIn("dry run: nothing written", out)
        self.assertEqual(Path(self.state).read_text(), before)

    def test_yes_puts_ready_first_and_keeps_order_among_equals(self):
        self.seed([1, 2, 3, 4, 5])
        code, out, _ = self.sync("--yes", gh=Gh({1: pr(merge="BEHIND"), 3: pr(draft=True)}))
        self.assertEqual((code, self.queue()), (0, [2, 4, 5, 1, 3]))
        self.assertIn("written: 5 queued", out)

    def test_already_in_order_writes_nothing(self):
        before = self.seed([1, 2])
        code, out, _ = self.sync("--yes", gh=Gh({2: pr(draft=True)}))
        self.assertEqual(code, 0)
        self.assertIn("no change", out)
        self.assertEqual(Path(self.state).read_text(), before)

    def test_merged_and_closed_queued_prs_are_dropped_with_their_refusals(self):
        self.seed([1, 2, 3], refusals={"1": 2, "3": 1})
        code, out, _ = self.sync("--yes", gh=Gh({1: pr(state="MERGED"), 2: pr(state="CLOSED")}))
        self.assertEqual((code, self.queue()), (0, [3]))
        self.assertIn("dropped: #1 is MERGED", out)
        self.assertIn("dropped: #2 is CLOSED", out)
        self.assertEqual(json.loads(Path(self.state).read_text())["refusals"], {"3": 1})

    def test_empty_state_asks_gh_nothing(self):
        self.seed([])
        gh = Gh()
        code, out, _ = self.sync("--yes", gh=gh)
        self.assertEqual((code, gh.calls), (0, []))
        self.assertIn("queue: empty", out)

    def test_state_in_a_missing_directory_exits_2_and_creates_nothing(self):
        missing = Path(self.dir.name) / "typo" / "slot.json"
        for flags in ((), ("--yes",)):
            with self.subTest(flags=flags):
                gh, out, err = Gh(), [], []
                code = queue_sync.main([*flags, "--state", str(missing)], runner=gh, out=out.append, err=err.append)
                self.assertEqual((code, out, gh.calls), (2, [], []))
                self.assertEqual(err, [f"error: no directory {missing.parent} for the state file"])
                self.assertEqual(os.listdir(self.dir.name), [])

    def test_no_state_file_yet_is_nothing_to_sync_and_creates_nothing(self):
        missing = Path(self.dir.name) / "slot.json"
        for flags in ((), ("--yes",)):
            with self.subTest(flags=flags):
                gh, out, err = Gh(), [], []
                code = queue_sync.main([*flags, "--state", str(missing)], runner=gh, out=out.append, err=err.append)
                self.assertEqual((code, out, err, gh.calls), (0, [f"queue: no state file at {missing}, nothing to sync"], [], []))
                self.assertEqual(os.listdir(self.dir.name), [])

    def test_missing_bus_dir_exits_2_and_creates_nothing(self):
        bus = Path(self.dir.name) / "no-bus"
        err = []
        code = queue_sync.main(["--bus-dir", str(bus)], runner=Gh(), out=lambda _: None, err=err.append)
        self.assertEqual(code, 2)
        self.assertIn("no directory", err[0])
        self.assertFalse(bus.exists())

    def test_repo_is_passed_to_both_gh_calls(self):
        self.seed([7])
        gh = Gh()
        self.sync("-R", "o/r", gh=gh)
        self.assertEqual(gh.calls[0], ["repo", "view", "o/r", "--json", "defaultBranchRef"])
        self.assertEqual(gh.calls[1], ["pr", "view", "7", "-R", "o/r", "--json", queue_sync.FIELDS])


class ReadyTests(QueueSyncTestCase):
    def assert_not_ready(self, view, reason):
        self.seed([1, 2])
        code, out, _ = self.sync("--yes", gh=Gh({1: view}))
        self.assertEqual((code, self.queue()), (0, [2, 1]))
        self.assertIn(reason, out)

    def test_draft_is_not_ready(self):
        self.assert_not_ready(pr(draft=True), "is a draft")

    def test_merge_state_other_than_clean_is_not_ready(self):
        self.assert_not_ready(pr(merge="BLOCKED"), "mergeStateStatus is BLOCKED, not CLEAN")

    def test_pending_check_is_not_ready(self):
        pending = [{"name": "tests", "status": "IN_PROGRESS", "conclusion": ""}]
        self.assert_not_ready(pr(checks=pending), "checks not green: tests")

    def test_failed_check_is_not_ready(self):
        self.assert_not_ready(pr(checks=[{"name": "lint", "conclusion": "FAILURE"}]), "checks not green: lint")

    def test_no_checks_is_not_ready(self):
        self.assert_not_ready(pr(checks=[]), "has no checks")

    def test_only_skipped_checks_is_not_ready(self):
        self.assert_not_ready(pr(checks=[{"name": "x", "conclusion": "SKIPPED"}]), "no successful check")

    def test_base_other_than_trunk_is_flagged_and_not_put_first(self):
        self.assert_not_ready(pr(base="release"), "FLAG base is 'release', not the trunk 'main'")

    def test_flagged_pr_goes_behind_unflagged_ones_when_none_is_ready(self):
        self.seed([1, 2, 3, 4])
        code, out, _ = self.sync("--yes", gh=Gh({1: pr(base="rel"), 2: pr(draft=True), 3: pr(base="rel", draft=True),
                                                 4: pr(merge="BEHIND")}))
        self.assertEqual((code, self.queue()), (0, [2, 4, 1, 3]))
        self.assertIn("3. #1 (l1) FLAG base is 'rel', not the trunk 'main'", out)

    def test_trunk_comes_from_the_default_branch(self):
        self.seed([1, 2])
        self.sync("--yes", gh=Gh({1: pr(base="main"), 2: pr(base="trunk")}, trunk="trunk"))
        self.assertEqual(self.queue(), [2, 1])


class HolderTests(QueueSyncTestCase):
    def holder(self):
        return json.loads(Path(self.state).read_text())["holder"]

    def test_ready_holder_is_kept(self):
        self.seed([2], holder=1)
        code, out, _ = self.sync("--yes")
        self.assertEqual((code, self.holder()["pr"]), (0, 1))
        self.assertIn("holder: #1 (l1) kept, ready", out)

    def test_merged_holder_is_kept_and_flagged(self):
        self.seed([2], holder=1)
        held = self.holder()
        code, out, _ = self.sync("--yes", gh=Gh({1: pr(state="MERGED")}))
        self.assertEqual((code, self.holder(), self.queue()), (0, held, [2]))
        self.assertIn("holder: #1 (l1) kept, FLAG the holder is not ready: is MERGED", out)

    def test_holder_that_became_not_ready_is_kept_and_flagged(self):
        self.seed([], holder=1)
        held = self.holder()
        code, out, _ = self.sync("--yes", gh=Gh({1: pr(merge="BEHIND", base="dev")}))
        self.assertEqual((code, self.holder()), (0, held))
        self.assertIn("FLAG the holder is not ready: mergeStateStatus is BEHIND, not CLEAN; base is 'dev'", out)


class NoGuessTests(QueueSyncTestCase):
    def assert_nothing_written(self, gh, exit_code, message):
        before = self.seed([1, 2, 3], holder=4)
        code, out, err = self.sync("--yes", gh=gh)
        self.assertEqual(code, exit_code)
        self.assertIn(message, err)
        self.assertIn("nothing was written", err)
        self.assertEqual(Path(self.state).read_text(), before)
        self.assertNotIn("written:", out)

    def test_failed_pr_view_writes_nothing(self):
        self.assert_nothing_written(Gh({1: pr(draft=True), 3: (1, "HTTP 502")}), queue_sync.EXIT_GH, "HTTP 502")

    def test_timed_out_pr_view_exits_4(self):
        gh = Gh({1: pr(state="MERGED"), 2: (merge_green.GH_TIMED_OUT, "gh did not answer in 120 s")})
        self.assert_nothing_written(gh, merge_green.EXIT_GH_TIMEOUT, "timed out")

    def test_unreadable_pr_view_writes_nothing(self):
        self.assert_nothing_written(Gh({2: (0, "not json")}), queue_sync.EXIT_GH, "no JSON object")

    def test_unknown_pr_state_writes_nothing(self):
        self.assert_nothing_written(Gh({2: pr(state=None)}), queue_sync.EXIT_GH, "unknown state")

    def test_oversized_answer_writes_nothing(self):
        too_long = (merge_green.GH_TOO_LONG, "gh answered with over 1000000 bytes")
        self.assert_nothing_written(Gh({2: too_long}), queue_sync.EXIT_GH, "over 1000000 bytes")

    def test_malformed_pr_fields_write_nothing(self):
        for field, value in (("statusCheckRollup", ["x"]), ("statusCheckRollup", "SUCCESS"),
                             ("statusCheckRollup", [{"name": 5, "conclusion": "SUCCESS"}]),
                             ("statusCheckRollup", [{"context": 5, "state": "FAILURE"}]),
                             ("statusCheckRollup", [{"name": "t", "conclusion": 1}]),
                             ("statusCheckRollup", [{"context": "t", "state": 1}]),
                             ("statusCheckRollup", [{"name": "t", "status": 1}]),
                             ("isDraft", "false"), ("baseRefName", None), ("mergeStateStatus", 1),
                             ("headRefOid", [])):
            with self.subTest(field=field, value=value):
                self.assert_nothing_written(Gh({2: {**pr(), field: value}}), queue_sync.EXIT_GH,
                                            f"unreadable fields: {field}")

    def test_null_rollup_is_read_as_no_checks(self):
        self.seed([1, 2])
        code, out, _ = self.sync("--yes", gh=Gh({1: {**pr(), "statusCheckRollup": None}}))
        self.assertEqual((code, self.queue()), (0, [2, 1]))
        self.assertIn("has no checks", out)

    def test_failed_holder_view_writes_nothing(self):
        self.assert_nothing_written(Gh({4: (1, "not found"), 1: pr(state="MERGED")}), queue_sync.EXIT_GH,
                                    "not found")

    def test_failed_repo_view_writes_nothing(self):
        self.assert_nothing_written(Gh(repo_answer=(1, "no repo")), queue_sync.EXIT_GH, "no repo")

    def test_repo_view_without_default_branch_writes_nothing(self):
        for ref in (None, "main", ["main"], {"name": ""}, {"name": 7}):
            with self.subTest(ref=ref):
                self.assert_nothing_written(Gh(repo_answer=(0, json.dumps({"defaultBranchRef": ref}))),
                                            queue_sync.EXIT_GH, "no default branch")

    def test_damaged_state_exits_2(self):
        Path(self.state).write_text("{broken")
        code, _, err = self.sync("--yes")
        self.assertEqual(code, merge_slot.EXIT_BAD)
        self.assertIn("damaged", err)
        self.assertEqual(Path(self.state).read_text(), "{broken")

    def test_bad_gh_timeout_is_a_usage_error(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(value=value), self.assertRaises(SystemExit) as raised:
                queue_sync.main(["--gh-timeout", value], runner=Gh(), out=lambda _: None, err=lambda _: None)
            self.assertEqual(raised.exception.code, 2)

    def test_gh_timeout_reaches_every_gh_call(self):
        self.seed([1])
        gh, timeouts = Gh(), []

        def recording_run_gh(args, timeout=merge_green.GH_TIMEOUT):
            timeouts.append(timeout)
            return gh(args)

        with mock.patch.object(merge_green, "run_gh", recording_run_gh):
            code = queue_sync.main(["--gh-timeout", "0.5", "--state", self.state], out=lambda _: None,
                                   err=lambda _: None)
        self.assertEqual((code, timeouts), (0, [0.5, 0.5]))


class ConcurrencyTests(QueueSyncTestCase):
    """gh runs outside the lock: what other lanes write meanwhile is kept."""

    def setUp(self):
        super().setUp()
        clock = mock.patch.dict(os.environ, {"MERGE_SLOT_NOW": "2030-01-01T10:05:00+00:00"})  # seeded lease alive
        clock.start()
        self.addCleanup(clock.stop)

    def request(self, number):
        merge_slot.main(["request", str(number), "--lane", f"l{number}", "--state", self.state],
                        runner=lambda args: (0, json.dumps({"state": "OPEN"})), out=lambda _: None)

    def test_pr_that_joined_during_gh_calls_is_kept_at_the_end(self):
        self.seed([1, 2], holder=9)
        joined = []

        def join_once(number):
            if not joined:
                joined.append(number)
                self.request(5)

        code, out, _ = self.sync("--yes", gh=Gh({1: pr(draft=True)}, before_pr=join_once))
        self.assertEqual((code, self.queue()), (0, [2, 1, 5]))
        self.assertIn("kept at the end, not checked: #5", out)

    def test_pr_that_left_during_gh_calls_is_not_brought_back(self):
        self.seed([1, 2, 3])

        def leave(number):
            if number == 3:
                state = json.loads(Path(self.state).read_text())
                state["queue"] = [q for q in state["queue"] if q["pr"] != 1]
                Path(self.state).write_text(json.dumps(state))

        code, _, _ = self.sync("--yes", gh=Gh({1: pr(merge="BEHIND")}, before_pr=leave))
        self.assertEqual((code, self.queue()), (0, [2, 3]))

    def test_dropped_pr_that_was_queued_again_during_gh_calls_is_kept(self):
        self.seed([1, 2], refusals={"1": 3})
        requeued = {"pr": 1, "lane": "l1", "queued_at": "2030-01-01T10:04:00+00:00", "refusals": 1}

        def requeue(number):
            if number == 2:
                state = json.loads(Path(self.state).read_text())
                state["queue"] = [q for q in state["queue"] if q["pr"] != 1] + [requeued]
                Path(self.state).write_text(json.dumps(state))

        code, out, _ = self.sync("--yes", gh=Gh({1: pr(state="CLOSED")}, before_pr=requeue))
        state = json.loads(Path(self.state).read_text())
        self.assertEqual((code, state["queue"][-1], state["refusals"]), (0, requeued, {"1": 3}))
        self.assertEqual(self.queue(), [2, 1])
        self.assertIn("kept at the end, not checked: #1 (l1)", out)


if __name__ == "__main__":
    unittest.main()
