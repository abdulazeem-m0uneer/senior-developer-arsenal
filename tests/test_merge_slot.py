"""merge_slot.py: FIFO merge slot, refresh from gh, clock, lock, damaged state. No real gh is ever called."""
import json
import multiprocessing
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "multi-session-delivery" / "scripts"))

import merge_green  # noqa: E402
import merge_slot  # noqa: E402

T0 = "2030-01-01T10:00:00+00:00"


class Gh:
    """Answers `gh pr view N --json state` from a dict; a tuple value is a failed call."""

    def __init__(self, states=None):
        self.states, self.calls = states or {}, []

    def __call__(self, args):
        self.calls.append(args)
        value = self.states.get(int(args[2]), "OPEN")
        return value if isinstance(value, tuple) else (0, json.dumps({"state": value}))


def worker(path, pr):
    os.environ["MERGE_SLOT_NOW"] = T0
    merge_slot.main(["request", str(pr), "--lane", f"l{pr}", "--state", path], runner=Gh(), out=lambda _: None)


class SlotTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.state = str(Path(self.dir.name) / "slot.json")
        patcher = unittest.mock.patch.dict(os.environ, {"MERGE_SLOT_NOW": T0})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cmd(self, *args, gh=None, now=None):
        if now:
            os.environ["MERGE_SLOT_NOW"] = now
        out, err = [], []
        code = merge_slot.main([*args, "--state", self.state], runner=gh or Gh(), out=out.append, err=err.append)
        return code, "\n".join(out), "\n".join(err)

    def data(self):
        return json.loads(Path(self.state).read_text())


class QueueTests(SlotTestCase):
    def test_refusals_queue_at_the_threshold_and_not_before(self):
        code, _, _ = self.run_cmd("refused", "5", "--lane", "a", "--after", "3")
        self.assertEqual((code, self.data()["queue"], self.data()["holder"]), (0, [], None))
        self.run_cmd("refused", "5", "--lane", "a", "--after", "3")
        self.assertIsNone(self.data()["holder"])
        self.assertEqual(self.data()["refusals"], {"5": 2})
        _, out, _ = self.run_cmd("refused", "5", "--lane", "a", "--after", "3")
        self.assertEqual(self.data()["holder"]["pr"], 5)  # free slot: granted at once
        self.assertIn("granted: #5", out)

    def test_default_threshold_is_two(self):
        self.run_cmd("refused", "5", "--lane", "a")
        self.assertIsNone(self.data()["holder"])
        self.run_cmd("refused", "5", "--lane", "a")
        self.assertEqual(self.data()["holder"]["pr"], 5)

    def test_refusals_after_queueing_do_not_duplicate(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("request", "2", "--lane", "b")
        for _ in range(3):
            self.run_cmd("refused", "2", "--lane", "b")
        self.assertEqual([q["pr"] for q in self.data()["queue"]], [2])

    def test_fifo_grant_order_and_times(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("request", "2", "--lane", "b")
        self.run_cmd("request", "3", "--lane", "c")
        self.assertEqual(self.data()["holder"], {"pr": 1, "lane": "a", "granted_at": T0, "claimed": False,
                                                 "expires_at": "2030-01-01T10:10:00+00:00"})
        self.assertEqual([q["pr"] for q in self.data()["queue"]], [2, 3])
        self.run_cmd("release", "1", now="2030-01-01T10:08:00+00:00")
        self.assertEqual(self.data()["holder"]["pr"], 2)
        self.assertEqual(self.data()["holder"]["expires_at"], "2030-01-01T10:18:00+00:00")
        self.run_cmd("release", "2")
        self.assertEqual(self.data()["holder"]["pr"], 3)

    def test_slot_minutes_sets_the_grant_length(self):
        self.run_cmd("may-update", "1", "--slot-minutes", "5")
        self.assertEqual(self.data()["holder"]["expires_at"], "2030-01-01T10:05:00+00:00")

    def test_duplicate_request_is_a_noop(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("request", "2", "--lane", "b")
        code, out, _ = self.run_cmd("request", "2", "--lane", "b")
        self.assertEqual((code, len(self.data()["queue"])), (0, 1))
        self.assertIn("already queued", out)
        code, out, _ = self.run_cmd("request", "1", "--lane", "a")
        self.assertIn("already holds", out)
        self.assertEqual(len(self.data()["queue"]), 1)

    def test_queue_entry_carries_its_refusal_count(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("refused", "2", "--lane", "b", "--after", "2")
        self.run_cmd("refused", "2", "--lane", "b", "--after", "2")
        self.assertEqual(self.data()["queue"], [{"pr": 2, "lane": "b", "queued_at": T0, "refusals": 2}])


class RefreshTests(SlotTestCase):
    def setUp(self):
        super().setUp()
        for pr, lane in ((1, "a"), (2, "b"), (3, "c")):
            self.run_cmd("request", str(pr), "--lane", lane)

    def test_expired_holder_hands_the_slot_to_the_next(self):
        _, out, _ = self.run_cmd("status", now="2030-01-01T10:40:00+00:00")
        self.assertEqual((self.data()["holder"]["pr"], [q["pr"] for q in self.data()["queue"]]), (2, [3]))
        self.assertIn("expired: #1", out)

    def test_not_yet_expired_holder_keeps_the_slot(self):
        self.run_cmd("may-update", "1")  # claim: the 40-minute lease starts
        self.run_cmd("status", now="2030-01-01T10:39:00+00:00")
        self.assertEqual(self.data()["holder"]["pr"], 1)

    def test_merged_holder_is_dropped_and_next_granted(self):
        _, out, _ = self.run_cmd("status", gh=Gh({1: "MERGED"}))
        self.assertEqual(self.data()["holder"]["pr"], 2)
        self.assertIn("dropped: #1 is MERGED", out)

    def test_closed_queued_pr_is_dropped(self):
        _, out, _ = self.run_cmd("status", gh=Gh({2: "CLOSED"}))
        self.assertEqual([q["pr"] for q in self.data()["queue"]], [3])
        self.assertIn("dropped: #2 is CLOSED", out)

    def test_every_watched_pr_is_read_with_the_repo(self):
        gh = Gh()
        self.run_cmd("status", "-R", "o/r", gh=gh)
        self.assertEqual(gh.calls, [["pr", "view", str(n), "-R", "o/r", "--json", "state"] for n in (1, 2, 3)])

    def test_gh_failure_or_timeout_drops_nothing(self):
        gh = Gh({1: (1, "boom"), 2: (merge_green.GH_TIMED_OUT, "gh did not answer in 120 s"), 3: (0, "not json")})
        code, _, err = self.run_cmd("status", gh=gh)
        self.assertEqual((code, self.data()["holder"]["pr"], [q["pr"] for q in self.data()["queue"]]), (0, 1, [2, 3]))
        self.assertEqual(err.count("state unknown"), 3)

    def test_may_update_answers_from_known_state_when_gh_fails(self):
        gh = Gh({1: (1, "boom"), 2: (1, "boom"), 3: (1, "boom")})
        self.assertEqual(self.run_cmd("may-update", "1", gh=gh)[0], 0)
        self.assertEqual(self.run_cmd("may-update", "2", gh=gh)[0], 1)

    def test_dropped_pr_loses_its_refusal_count(self):
        self.run_cmd("refused", "9", "--lane", "z")
        self.run_cmd("request", "9", "--lane", "z")
        self.run_cmd("status", gh=Gh({9: "CLOSED"}))
        self.assertNotIn("9", self.data()["refusals"])

    def test_merged_pr_is_listed_once_even_if_requested_twice(self):
        self.run_cmd("request", "2", "--lane", "b")
        self.assertEqual([q["pr"] for q in self.data()["queue"]], [2, 3])


class MayUpdateAndReleaseTests(SlotTestCase):
    def test_free_slot_and_unknown_pr_may_update(self):
        code, out, _ = self.run_cmd("may-update", "7")
        self.assertEqual(code, 0)
        self.assertIn("now holds the slot", out)

    def test_may_update_on_a_free_slot_takes_it_so_the_second_caller_holds(self):
        self.assertEqual(self.run_cmd("may-update", "7", "--lane", "a")[0], 0)
        self.assertEqual(self.data()["holder"], {"pr": 7, "lane": "a", "granted_at": T0, "claimed": True,
                                                 "expires_at": "2030-01-01T10:40:00+00:00"})
        code, out, _ = self.run_cmd("may-update", "8", "--lane", "b")
        self.assertEqual(code, 1)
        self.assertIn("#7 holds", out)
        self.assertEqual(self.run_cmd("may-update", "7")[0], 0)  # the holder asking again still gets 0

    def test_may_update_without_lane_records_an_empty_lane(self):
        self.run_cmd("may-update", "7")
        self.assertEqual(self.data()["holder"]["lane"], "")

    def test_taken_slot_frees_for_the_next_caller_on_release(self):
        self.run_cmd("may-update", "7")
        self.run_cmd("release", "7")
        self.assertEqual(self.run_cmd("may-update", "8")[0], 0)
        self.assertEqual(self.data()["holder"]["pr"], 8)

    def test_holder_may_update_and_others_hold(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("request", "2", "--lane", "b")
        self.assertEqual(self.run_cmd("may-update", "1")[0], 0)
        code, out, _ = self.run_cmd("may-update", "2")
        self.assertEqual(code, 1)
        self.assertIn("position 1", out)
        code, out, _ = self.run_cmd("may-update", "8")
        self.assertEqual(code, 1)
        self.assertIn("not queued", out)

    def test_release_by_holder_then_non_holder(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("request", "2", "--lane", "b")
        code, out, _ = self.run_cmd("release", "2")
        self.assertEqual((code, self.data()["holder"]["pr"]), (1, 1))
        self.assertIn("#1 holds it", out)
        self.assertEqual(self.run_cmd("release", "1")[0], 0)
        self.assertEqual(self.data()["holder"]["pr"], 2)

    def test_release_after_the_merge_succeeds_for_the_dropped_holder(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("request", "2", "--lane", "b")
        code, out, _ = self.run_cmd("release", "1", gh=Gh({1: "MERGED"}))
        self.assertEqual(code, 0)
        self.assertIn("released: #1 (already merged)", out)
        self.assertEqual(self.data()["holder"]["pr"], 2)

    def test_release_of_a_closed_holder_says_closed(self):
        self.run_cmd("request", "1", "--lane", "a")
        code, out, _ = self.run_cmd("release", "1", gh=Gh({1: "CLOSED"}))
        self.assertEqual(code, 0)
        self.assertIn("released: #1 (already closed)", out)

    def test_release_of_a_merged_pr_that_never_held_the_slot_is_refused(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("request", "2", "--lane", "b")
        code, _, _ = self.run_cmd("release", "2", gh=Gh({2: "MERGED"}))  # queued, never held
        self.assertEqual(code, 1)
        self.run_cmd("release", "1")
        code, _, _ = self.run_cmd("release", "9", gh=Gh({9: "MERGED"}))
        self.assertEqual(code, 1)

    def test_release_with_no_holder_is_refused(self):
        code, out, _ = self.run_cmd("release", "1")
        self.assertEqual(code, 1)
        self.assertIn("nobody holds it", out)

    def test_grant_clears_the_granted_prs_refusal_count(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("refused", "2", "--lane", "b", "--after", "2")
        self.run_cmd("request", "2", "--lane", "b")
        self.assertEqual(self.data()["refusals"], {"2": 1})
        self.run_cmd("release", "1")
        self.assertEqual((self.data()["holder"]["pr"], self.data()["refusals"]), (2, {}))

    def test_release_forgets_refusals(self):
        self.run_cmd("refused", "1", "--lane", "a", "--after", "1")
        self.run_cmd("release", "1")
        self.assertEqual(self.data()["refusals"], {})


class OutsideTheLockTests(SlotTestCase):
    def test_gh_runs_without_the_lock_and_concurrent_writes_survive(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("request", "2", "--lane", "b")
        seen = []

        def gh(args):
            if not seen:  # while the first lane waits on gh, another lane takes the lock and writes
                seen.append(merge_slot.main(["request", "3", "--lane", "c", "--state", self.state],
                                            runner=Gh(), out=lambda _: None))
            return 0, json.dumps({"state": "MERGED" if args[2] == "1" else "OPEN"})
        _, out, _ = self.run_cmd("status", gh=gh)
        self.assertEqual(seen, [0])
        self.assertEqual(self.data()["holder"]["pr"], 2)
        self.assertEqual([q["pr"] for q in self.data()["queue"]], [3])
        self.assertIn("dropped: #1 is MERGED", out)

    def test_verdict_for_an_entry_that_changed_meanwhile_is_ignored(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("request", "2", "--lane", "b")

        def gh(args):
            if args[2] == "2":  # #2 leaves and re-joins behind a new entry while gh answers MERGED for the old one
                self.run_cmd("release", "1")
                self.run_cmd("release", "2")
                self.run_cmd("request", "2", "--lane", "b2", now="2030-01-01T10:05:00+00:00")
            return 0, json.dumps({"state": "MERGED" if args[2] == "2" else "OPEN"})
        _, out, _ = self.run_cmd("status", gh=gh, now="2030-01-01T10:06:00+00:00")
        self.assertNotIn("dropped", out)
        self.assertEqual(self.data()["holder"]["lane"], "b2")

    def test_verdict_for_a_queue_entry_replaced_meanwhile_is_ignored(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("request", "2", "--lane", "b")

        def gh(args):
            if args[2] == "2":  # another lane re-queued #2 under a new entry while gh answers for the old one
                data = self.data()
                data["queue"][0]["lane"] = "b2"
                Path(self.state).write_text(json.dumps(data))
            return 0, json.dumps({"state": "MERGED" if args[2] == "2" else "OPEN"})
        _, out, _ = self.run_cmd("status", gh=gh)
        self.assertNotIn("dropped", out)
        self.assertEqual([q["lane"] for q in self.data()["queue"]], ["b2"])

    def test_clock_is_read_again_after_a_slow_gh(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("request", "2", "--lane", "b")

        def gh(args):
            os.environ["MERGE_SLOT_NOW"] = "2030-01-01T10:41:00+00:00"  # gh took 41 minutes
            return 0, json.dumps({"state": "OPEN"})
        code, out, _ = self.run_cmd("may-update", "1", gh=gh)
        self.assertEqual(code, 1)  # #1 expired during gh, so it must not be told it holds the slot
        self.assertEqual(self.data()["holder"], {"pr": 2, "lane": "b", "granted_at": "2030-01-01T10:41:00+00:00",
                                                 "claimed": False, "expires_at": "2030-01-01T10:51:00+00:00"})

    def test_pr_that_left_the_state_meanwhile_is_not_reported_dropped(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("request", "2", "--lane", "b")

        def gh(args):
            if args[2] == "1":
                self.run_cmd("release", "1")
            return 0, json.dumps({"state": "MERGED"})
        _, out, _ = self.run_cmd("status", gh=gh)
        self.assertNotIn("dropped: #1", out)

    def test_only_the_short_phases_hold_the_lock(self):
        self.run_cmd("request", "1", "--lane", "a")
        held = []

        def gh(args):
            with unittest.mock.patch.object(merge_slot, "LOCK_WAIT", 0.05):
                held.append(merge_slot.main(["status", "--state", self.state], runner=Gh(), out=lambda _: None))
            return 0, json.dumps({"state": "OPEN"})
        self.run_cmd("status", gh=gh)
        self.assertEqual(held, [0])


class FileErrorTests(SlotTestCase):
    def test_unwritable_state_dir_exits_2_with_one_line(self):
        blocker = Path(self.dir.name) / "file"
        blocker.write_text("x")
        out, err = [], []
        code = merge_slot.main(["status", "--state", str(blocker / "slot.json")], runner=Gh(),
                               out=out.append, err=err.append)
        self.assertEqual(code, 2)
        self.assertEqual(len(err), 1)
        self.assertTrue(err[0].startswith("error: "))

    def test_failed_write_exits_2_and_leaves_no_state(self):
        with unittest.mock.patch.object(merge_slot.os, "replace", side_effect=OSError("disk full")):
            code, _, err = self.run_cmd("request", "1", "--lane", "a")
        self.assertEqual((code, err), (2, "error: disk full"))
        self.assertEqual([p.name for p in Path(self.dir.name).iterdir() if p.name.endswith(".tmp")], [])

    def test_failed_reset_write_exits_2(self):
        with unittest.mock.patch.object(merge_slot.os, "replace", side_effect=OSError("disk full")):
            self.assertEqual(self.run_cmd("reset", "--yes")[0], 2)


class GoneHoldersTests(SlotTestCase):
    def setUp(self):
        super().setUp()
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("may-update", "1")  # claim
        self.run_cmd("request", "2", "--lane", "b")

    def test_release_after_another_lane_already_dropped_the_merged_holder(self):
        self.run_cmd("status", gh=Gh({1: "MERGED"}))  # another lane sees the merge first and persists it
        self.assertEqual(self.data()["holder"]["pr"], 2)
        code, out, _ = self.run_cmd("release", "1")
        self.assertEqual(code, 0)
        self.assertIn("released: #1 (already merged)", out)
        self.assertEqual(self.data()["holder"]["pr"], 2)
        self.assertEqual(self.data()["gone"], [])

    def test_closed_holder_is_remembered_as_closed(self):
        self.run_cmd("status", gh=Gh({1: "CLOSED"}))
        self.assertIn("already closed", self.run_cmd("release", "1")[1])

    def test_next_grant_does_not_clear_the_remembered_holder(self):
        self.run_cmd("status", gh=Gh({1: "MERGED"}))
        self.run_cmd("release", "2")  # grants nobody; #3 joins and is granted
        self.run_cmd("request", "3", "--lane", "c")
        self.assertEqual(self.data()["gone"], [{"pr": 1, "reason": "merged", "at": T0}])

    def test_late_release_of_an_expired_holder_exits_0_and_spares_the_current_holder(self):
        self.run_cmd("status", now="2030-01-01T10:41:00+00:00")
        self.assertEqual(self.data()["holder"]["pr"], 2)
        code, out, _ = self.run_cmd("release", "1", now="2030-01-01T10:42:00+00:00")
        self.assertEqual(code, 0)
        self.assertIn("slot had expired", out)
        self.assertEqual(self.data()["holder"]["pr"], 2)

    def test_late_release_of_an_unclaimed_grant_exits_0(self):
        self.run_cmd("release", "1")  # #2 is now granted, unclaimed
        self.run_cmd("status", now="2030-01-01T10:11:00+00:00")
        self.assertEqual(self.data()["gone"][0]["reason"], "unclaimed")
        self.assertEqual(self.run_cmd("release", "2", now="2030-01-01T10:12:00+00:00")[0], 0)

    def test_pr_that_never_held_the_slot_is_still_refused(self):
        self.run_cmd("status", gh=Gh({1: "MERGED"}))
        self.assertEqual(self.run_cmd("release", "9")[0], 1)
        self.assertEqual(self.run_cmd("release", "1")[0], 0)
        self.assertEqual(self.run_cmd("release", "1")[0], 1)  # already acknowledged: gone from the list

    def test_entries_older_than_a_day_are_pruned(self):
        self.run_cmd("status", gh=Gh({1: "MERGED"}))
        self.run_cmd("status", now="2030-01-02T10:00:01+00:00")
        self.assertNotIn(1, [g["pr"] for g in self.data()["gone"]])
        self.assertEqual(self.run_cmd("release", "1", now="2030-01-02T10:00:02+00:00")[0], 1)

    def test_entry_just_inside_a_day_is_kept(self):
        self.run_cmd("status", gh=Gh({1: "MERGED"}))
        self.run_cmd("status", now="2030-01-02T10:00:00+00:00")
        self.assertIn(1, [g["pr"] for g in self.data()["gone"]])

    def test_only_the_last_twenty_are_kept(self):
        path = Path(self.state)
        data = self.data()
        data["gone"] = [{"pr": 100 + i, "reason": "merged", "at": T0} for i in range(25)]
        path.write_text(json.dumps(data))
        self.run_cmd("status")
        self.assertEqual([g["pr"] for g in self.data()["gone"]], list(range(105, 125)))

    def test_requeueing_a_remembered_pr_forgets_its_old_entry(self):
        self.run_cmd("status", gh=Gh({1: "MERGED"}))
        self.run_cmd("request", "1", "--lane", "a")
        self.assertEqual(self.data()["gone"], [])

    def test_granting_a_remembered_pr_directly_forgets_its_old_entry(self):
        self.run_cmd("status", gh=Gh({1: "MERGED"}))
        self.run_cmd("release", "2")
        self.run_cmd("may-update", "1", "--lane", "a")
        self.assertEqual(self.data()["holder"]["pr"], 1)
        self.assertEqual(self.data()["gone"], [])

    def test_state_without_a_gone_list_still_loads(self):
        Path(self.state).write_text(json.dumps({"holder": None, "queue": [], "refusals": {}}))
        self.assertEqual(self.run_cmd("status")[0], 0)

    def test_malformed_gone_list_is_damaged_state(self):
        data = self.data()
        data["gone"] = [{"pr": "x"}]
        Path(self.state).write_text(json.dumps(data))
        self.assertEqual(self.run_cmd("status")[0], 2)


class ClaimTests(SlotTestCase):
    def test_queue_grant_is_a_short_claim_window(self):
        _, out, _ = self.run_cmd("request", "1", "--lane", "a")
        self.assertEqual(self.data()["holder"], {"pr": 1, "lane": "a", "granted_at": T0, "claimed": False,
                                                 "expires_at": "2030-01-01T10:10:00+00:00"})
        self.assertIn("claim", out)

    def test_claim_minutes_flag_sets_the_window(self):
        self.run_cmd("request", "1", "--lane", "a", "--claim-minutes", "3")
        self.assertEqual(self.data()["holder"]["expires_at"], "2030-01-01T10:03:00+00:00")

    def test_first_may_update_claims_and_starts_the_full_lease(self):
        self.run_cmd("request", "1", "--lane", "a")
        code, out, _ = self.run_cmd("may-update", "1", now="2030-01-01T10:07:00+00:00")
        self.assertEqual(code, 0)
        self.assertIn("claimed", out)
        self.assertEqual(self.data()["holder"], {"pr": 1, "lane": "a", "granted_at": T0, "claimed": True,
                                                 "expires_at": "2030-01-01T10:47:00+00:00"})

    def test_second_may_update_does_not_extend_the_lease(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("may-update", "1", now="2030-01-01T10:07:00+00:00")
        self.run_cmd("may-update", "1", now="2030-01-01T10:30:00+00:00")
        self.assertEqual(self.data()["holder"]["expires_at"], "2030-01-01T10:47:00+00:00")

    def test_slot_minutes_applies_at_the_claim(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("may-update", "1", "--slot-minutes", "5")
        self.assertEqual(self.data()["holder"]["expires_at"], "2030-01-01T10:05:00+00:00")

    def test_unclaimed_grant_expires_and_the_next_head_is_granted(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("request", "2", "--lane", "b")
        self.run_cmd("status", now="2030-01-01T10:09:00+00:00")
        self.assertEqual(self.data()["holder"]["pr"], 1)
        _, out, _ = self.run_cmd("status", now="2030-01-01T10:10:00+00:00")
        self.assertIn("did not claim", out)
        self.assertIn("granted: #2", out)
        self.assertEqual(self.data()["holder"]["pr"], 2)
        self.assertEqual(self.data()["holder"]["expires_at"], "2030-01-01T10:20:00+00:00")

    def test_claimed_lease_is_not_cut_to_the_claim_window(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("may-update", "1")
        self.run_cmd("status", now="2030-01-01T10:30:00+00:00")
        self.assertEqual(self.data()["holder"]["pr"], 1)

    def test_direct_grant_on_a_free_slot_is_already_claimed(self):
        self.run_cmd("may-update", "7")
        self.assertTrue(self.data()["holder"]["claimed"])
        self.assertEqual(self.data()["holder"]["expires_at"], "2030-01-01T10:40:00+00:00")

    def test_other_pr_does_not_claim_for_the_head(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.assertEqual(self.run_cmd("may-update", "2")[0], 1)
        self.assertFalse(self.data()["holder"]["claimed"])

    def test_status_text_tells_waiting_from_holding(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.assertEqual(self.run_cmd("status")[1].splitlines()[0],
                         "holder: #1 (a) granted, waiting for claim until 10:10 (10 min left)")
        self.run_cmd("may-update", "1")
        self.assertEqual(self.run_cmd("status")[1].splitlines()[0], "holder: #1 (a) holds until 10:40 (40 min left)")

    def test_old_holder_without_a_claimed_field_counts_as_claimed(self):
        self.run_cmd("may-update", "1")
        data = self.data()
        del data["holder"]["claimed"]
        Path(self.state).write_text(json.dumps(data))
        self.run_cmd("status", now="2030-01-01T10:30:00+00:00")
        self.assertEqual(self.data()["holder"]["pr"], 1)


class StatusTests(SlotTestCase):
    def test_json_shape(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("may-update", "1")
        self.run_cmd("request", "2", "--lane", "b")
        _, out, _ = self.run_cmd("status", "--json", now="2030-01-01T10:15:30+00:00")
        self.assertEqual(json.loads(out), {
            "holder": {"pr": 1, "lane": "a", "granted_at": T0, "expires_at": "2030-01-01T10:40:00+00:00",
                       "claimed": True, "minutes_left": 24},
            "queue": [{"pr": 2, "lane": "b", "queued_at": T0, "refusals": 0}], "refusals": {}, "gone": []})

    def test_text_status(self):
        self.assertEqual(self.run_cmd("status")[1], "holder: none\nqueue: empty")
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("may-update", "1")
        self.run_cmd("request", "2", "--lane", "b")
        _, out, _ = self.run_cmd("status")
        self.assertEqual(out.splitlines(), ["holder: #1 (a) holds until 10:40 (40 min left)", f"1. #2 (b) queued {T0}, refusals 0"])

    def test_status_without_a_file_does_not_create_one(self):
        self.run_cmd("status")
        self.assertFalse(Path(self.state).exists())


class SafetyTests(SlotTestCase):
    def test_damaged_state_exits_2_and_is_never_reset(self):
        for text in ("{not json", "[]", '{"holder": 3, "queue": [], "refusals": {}}',
                     '{"holder": null, "queue": [{"pr": "x"}], "refusals": {}}', '{"holder": null}'):
            Path(self.state).write_text(text)
            code, _, err = self.run_cmd("status")
            self.assertEqual(code, 2, text)
            self.assertIn("reset --yes", err)
            self.assertEqual(Path(self.state).read_text(), text)

    def test_reset_requires_yes_then_clears_even_a_damaged_file(self):
        Path(self.state).write_text("garbage")
        with self.assertRaises(SystemExit) as raised:
            self.run_cmd("reset")
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(Path(self.state).read_text(), "garbage")
        self.assertEqual(self.run_cmd("reset", "--yes")[0], 0)
        self.assertEqual(self.data(), {"holder": None, "queue": [], "refusals": {}, "gone": []})

    def test_reset_clears_a_live_queue(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.run_cmd("reset", "--yes")
        self.assertEqual(self.data()["holder"], None)

    def test_two_writers_in_sequence_keep_both_updates(self):
        self.run_cmd("request", "1", "--lane", "a")
        merge_slot.main(["request", "2", "--lane", "b", "--state", self.state], runner=Gh(), out=lambda _: None)
        self.run_cmd("request", "3", "--lane", "c")
        self.assertEqual([q["pr"] for q in self.data()["queue"]], [2, 3])

    def test_concurrent_processes_lose_no_update(self):
        context = multiprocessing.get_context("fork")
        procs = [context.Process(target=worker, args=(self.state, pr)) for pr in range(1, 9)]
        for proc in procs:
            proc.start()
        for proc in procs:
            proc.join()
        data = self.data()
        seen = sorted([data["holder"]["pr"]] + [q["pr"] for q in data["queue"]])
        self.assertEqual(seen, list(range(1, 9)))

    def test_lock_busy_exits_2_without_writing(self):
        with unittest.mock.patch.object(merge_slot, "LOCK_WAIT", 0.05), \
                unittest.mock.patch.object(merge_slot, "_try_lock", lambda handle: False):
            code, _, err = self.run_cmd("request", "1", "--lane", "a")
        self.assertEqual(code, 2)
        self.assertIn("locked", err)
        self.assertFalse(Path(self.state).exists())

    def test_write_leaves_no_temp_file(self):
        self.run_cmd("request", "1", "--lane", "a")
        self.assertEqual(sorted(p.name for p in Path(self.dir.name).iterdir()),
                         [".slot.json.lock", "slot.json"])

    def test_default_path_is_the_bus_dir(self):
        out = []
        merge_slot.main(["request", "1", "--lane", "a", "--bus-dir", self.dir.name], runner=Gh(), out=out.append)
        self.assertTrue((Path(self.dir.name) / "merge-slot.json").exists())

    def test_bad_clock_exits_2(self):
        code, _, err = self.run_cmd("status", now="yesterday")
        self.assertEqual(code, 2)
        self.assertIn("MERGE_SLOT_NOW", err)

    def test_naive_clock_is_read_as_local_time(self):
        self.assertEqual(self.run_cmd("request", "1", "--lane", "a", now="2030-01-01T10:00:00")[0], 0)
        self.assertIn("granted_at", self.data()["holder"])

    def test_unreadable_stored_time_exits_2(self):
        self.run_cmd("request", "1", "--lane", "a")
        data = self.data()
        data["holder"]["expires_at"] = "soon"
        Path(self.state).write_text(json.dumps(data))
        self.assertEqual(self.run_cmd("status")[0], 2)


class ArgumentTests(SlotTestCase):
    def assert_usage_error(self, *args):
        with self.assertRaises(SystemExit) as raised:
            self.run_cmd(*args)
        self.assertEqual(raised.exception.code, 2, args)
        self.assertFalse(Path(self.state).exists())

    def test_invalid_arguments_exit_2(self):
        for args in (("request", "x", "--lane", "a"), ("request", "0", "--lane", "a"),
                     ("request", "-3", "--lane", "a"), ("request", "1"), ("refused", "1"),
                     ("refused", "1", "--lane", "a", "--after", "0"),
                     ("request", "1", "--lane", "a", "--slot-minutes", "0"),
                     ("request", "1", "--lane", "a", "--slot-minutes", "nan"),
                     ("request", "1", "--lane", "a", "--claim-minutes", "0"),
                     ("status", "--gh-timeout", "0"), ("status", "--gh-timeout", "inf"), ("nope",), ()):
            with self.subTest(args=args):
                self.assert_usage_error(*args)

    def test_default_runner_is_merge_green_run_gh_with_the_timeout(self):
        seen = []

        def fake(args, timeout):
            seen.append(timeout)
            return 0, json.dumps({"state": "OPEN"})
        self.run_cmd("request", "1", "--lane", "a")
        with unittest.mock.patch.object(merge_green, "run_gh", fake):
            merge_slot.main(["status", "--state", self.state, "--gh-timeout", "7.5"], out=lambda _: None)
        self.assertEqual(seen, [7.5])


if __name__ == "__main__":
    unittest.main()
