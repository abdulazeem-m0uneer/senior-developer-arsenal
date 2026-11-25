"""merge_slot.py ready-first rule: a CLEAN, green, fresh PR overtakes a pending holder; the holder keeps its place."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_merge_slot import SlotTestCase  # noqa: E402  (also puts the scripts on sys.path)
import queue_sync  # noqa: E402
import test_queue_sync  # noqa: E402

CLEAN = {"state": "OPEN", "mergeStateStatus": "CLEAN", "headRefOid": "abc12345", "baseRefName": "development",
         "statusCheckRollup": [{"name": "ci", "conclusion": "SUCCESS"}]}
PENDING = {**CLEAN, "mergeStateStatus": "BLOCKED", "statusCheckRollup": [{"name": "ci", "status": "IN_PROGRESS"}]}
BEHIND = {**CLEAN, "mergeStateStatus": "BEHIND"}
MERGED = {**CLEAN, "state": "MERGED"}
UNKNOWN_STATE = {**CLEAN, "mergeStateStatus": "UNKNOWN"}
FAILED = {**PENDING, "statusCheckRollup": [{"name": "ci", "status": "COMPLETED", "conclusion": "FAILURE"}]}
FAILED_WHILE_RUNNING = {**PENDING, "statusCheckRollup": [{"name": "ci", "status": "COMPLETED", "conclusion": "FAILURE"},
                                                         {"name": "e2e", "status": "IN_PROGRESS"}]}
SAME_NAME = {**PENDING, "statusCheckRollup": [{"name": "build", "status": "COMPLETED", "conclusion": "FAILURE"},
                                              {"name": "build", "status": "IN_PROGRESS", "conclusion": ""}]}
SKIPPED = {**CLEAN, "statusCheckRollup": [{"name": "ci", "conclusion": "SKIPPED"}]}
STALE_HEAD = {**CLEAN, "headRefOid": "stale001"}
GH_ERROR = (1, "boom")


def at(minute):
    return f"2030-01-01T{10 + minute // 60:02d}:{minute % 60:02d}:00+00:00"


class ViewGh:
    """Answers `gh pr view N --json ...` with a whole view per PR; a tuple value is a failed call.

    The freshness inputs of the merge script's freshness gate come through `gh api`:
    commits/BASE -> "tip sha, tip committer date"; compare/TIP...HEAD -> compare[HEAD] (default "ahead");
    actions/runs?head_sha=HEAD&event=pull_request -> pr_run[HEAD] (earliest created_at);
    actions/runs?head_sha=TIP&event=push -> push_run (the tip's ci.yml push run created_at)."""

    TIP = "d" * 40

    def __init__(self, views, compare=None, tip_date="2030-01-01T09:00:00Z", pr_run=None,
                 push_run="2030-01-01T08:00:00Z"):
        self.views, self.compare, self.tip_date, self.pr_run, self.push_run = dict(views), compare or {}, tip_date, pr_run or {}, push_run
        self.calls = []

    def api(self, path):
        if "/commits/" in path:
            return f"{self.TIP}\n{self.tip_date}"
        if "/compare/" in path:
            return self.compare.get(path.rsplit("...", 1)[1], "ahead")
        sha = path.split("head_sha=")[1].split("&")[0]
        if path.endswith("event=push&per_page=100"):
            return self.push_run
        return self.pr_run.get(sha, "2030-01-01T09:30:00Z")

    def __call__(self, args):
        self.calls.append(args)
        if args[0] == "api":
            answer = self.api(args[1])
            return answer if isinstance(answer, tuple) else (0, answer)
        value = self.views.get(int(args[2]), PENDING)
        return value if isinstance(value, tuple) else (0, json.dumps(value))


class ReadyFirstCase(SlotTestCase):
    def queue_up(self, *prs):
        for pr in prs:
            self.run_cmd("request", str(pr), "--lane", f"l{pr}", gh=ViewGh({}))

    def sync(self, views, now=None, **seam):
        gh = ViewGh(views, **seam)
        self.run_cmd("status", gh=gh, now=now)
        return gh

    def order(self):
        return self.data()["holder"]["pr"], [q["pr"] for q in self.data()["queue"]]

    def claimed_holder(self, pr=1):
        self.run_cmd("may-update", str(pr), "--lane", f"l{pr}", gh=ViewGh({}), now=at(0))

    def write_state(self, state):
        Path(self.state).write_text(json.dumps(state))


class ReadinessTests(ReadyFirstCase):
    """Only a PENDING holder is displaced, and only by a CLEAN, green candidate; anything unknown means no."""

    def test_clean_pr_overtakes_a_pending_holder(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: CLEAN})
        self.assertEqual(self.order(), (2, [1]))
        self.assertEqual(self.run_cmd("may-update", "2", gh=ViewGh({1: PENDING, 2: CLEAN}))[0], 0)

    def test_pending_pr_does_not_overtake_a_pending_holder(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: PENDING})
        self.assertEqual(self.order(), (1, [2]))

    def test_behind_pr_is_not_ready(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: BEHIND})
        self.assertEqual(self.order(), (1, [2]))

    def test_clean_pr_does_not_overtake_a_clean_holder(self):
        self.queue_up(1, 2)
        self.sync({1: CLEAN, 2: CLEAN})
        self.assertEqual(self.order(), (1, [2]))

    def test_gh_error_on_the_candidate_means_no_overtake(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: GH_ERROR})
        self.assertEqual(self.order(), (1, [2]))

    def test_gh_error_on_the_holder_means_no_overtake(self):
        self.queue_up(1, 2)
        self.sync({1: GH_ERROR, 2: CLEAN})
        self.assertEqual(self.order(), (1, [2]))

    def test_view_without_check_data_means_no_overtake(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: {"state": "OPEN"}})
        self.assertEqual(self.order(), (1, [2]))

    def test_clean_pr_with_no_checks_is_not_green(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: {**CLEAN, "statusCheckRollup": []}})
        self.assertEqual(self.order(), (1, [2]))

    def test_unknown_merge_state_on_the_holder_means_no_overtake(self):
        # GitHub answers UNKNOWN while it recomputes mergeability.
        self.queue_up(1, 2)
        self.sync({1: UNKNOWN_STATE, 2: CLEAN})
        self.assertEqual(self.order(), (1, [2]))

    def test_holder_with_an_unrecognised_or_missing_merge_state_is_never_displaced(self):
        for value in ("UNKNOWN", "SOMETHING_NEW", None):
            with self.subTest(value=value):
                self.run_cmd("reset", "--yes")
                self.queue_up(1, 2)
                self.sync({1: {**PENDING, "mergeStateStatus": value}, 2: CLEAN})
                self.assertEqual(self.order(), (1, [2]))

    def test_clean_holder_without_checks_is_never_overtaken(self):
        self.queue_up(1, 2)
        self.sync({1: {**CLEAN, "statusCheckRollup": []}, 2: CLEAN})
        self.assertEqual(self.order(), (1, [2]))

    def test_clean_holder_with_null_rollup_is_never_overtaken(self):
        self.queue_up(1, 2)
        self.sync({1: {**CLEAN, "statusCheckRollup": None}, 2: CLEAN})
        self.assertEqual(self.order(), (1, [2]))

    def test_clean_holder_with_only_skipped_checks_is_never_displaced(self):
        self.queue_up(1, 2)
        self.sync({1: SKIPPED, 2: CLEAN})
        self.assertEqual(self.order(), (1, [2]))

    def test_holder_with_a_failed_check_is_not_pending_and_is_not_displaced(self):
        self.queue_up(1, 2)
        self.sync({1: FAILED_WHILE_RUNNING, 2: CLEAN})
        self.assertEqual(self.order(), (1, [2]))

    def test_holder_with_a_failed_check_sharing_a_running_check_name_is_not_displaced(self):
        self.queue_up(1, 2)
        self.sync({1: SAME_NAME, 2: CLEAN})
        self.assertEqual(self.order(), (1, [2]))


class FreshnessTests(ReadyFirstCase):
    """A candidate is READY only when fresh by the merge script's freshness gate."""

    def stale_case(self, **seam):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: {**CLEAN, "headRefOid": "diverge1"}}, compare={"diverge1": "diverged"}, **seam)
        return self.order()

    def test_candidate_behind_development_does_not_overtake(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: STALE_HEAD}, compare={"stale001": "behind"}, tip_date="2030-01-01T10:00:00Z")
        self.assertEqual(self.order(), (1, [2]))

    def test_candidate_whose_pr_run_is_newer_than_the_tip_and_its_push_run_is_fresh(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: STALE_HEAD}, compare={"stale001": "diverged"},
                  pr_run={"stale001": "2030-01-01T09:30:00Z"})
        self.assertEqual(self.order(), (2, [1]))

    def test_candidate_whose_pr_run_is_older_than_the_tip_is_stale(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: STALE_HEAD}, compare={"stale001": "diverged"},
                  pr_run={"stale001": "2030-01-01T08:30:00Z"})
        self.assertEqual(self.order(), (1, [2]))

    def test_freshness_gh_error_means_no_overtake(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: STALE_HEAD}, compare={"stale001": GH_ERROR})
        self.assertEqual(self.order(), (1, [2]))

    def test_candidate_without_a_base_name_is_not_fresh(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: {k: v for k, v in CLEAN.items() if k != "baseRefName"}})
        self.assertEqual(self.order(), (1, [2]))

    def test_pr_run_created_after_the_tip_and_its_push_run_is_fresh(self):
        self.assertEqual(self.stale_case(pr_run={"diverge1": "2030-01-01T09:30:00Z"}), (2, [1]))

    def test_pr_run_older_than_the_tips_push_run_is_stale_even_when_newer_than_its_commit_date(self):
        self.assertEqual(self.stale_case(pr_run={"diverge1": "2030-01-01T09:30:00Z"},
                                         push_run="2030-01-01T09:45:00Z"), (1, [2]))

    def test_tip_without_a_push_run_is_stale(self):
        self.assertEqual(self.stale_case(pr_run={"diverge1": "2030-01-01T09:30:00Z"}, push_run=""), (1, [2]))

    def test_head_without_pull_request_runs_is_stale(self):
        self.assertEqual(self.stale_case(pr_run={"diverge1": ""}), (1, [2]))

    def test_unreadable_tip_is_stale(self):
        self.assertEqual(self.stale_case(tip_date=" "), (1, [2]))


class QueueOrderTests(ReadyFirstCase):
    """The first READY PR overtakes; the overtaken holder goes to the queue head; the rest stay FIFO."""

    def test_overtaker_is_the_first_ready_pr_and_the_rest_stay_fifo(self):
        self.queue_up(1, 2, 3, 4)
        self.sync({1: PENDING, 2: PENDING, 3: CLEAN, 4: CLEAN})
        self.assertEqual(self.order(), (3, [1, 2, 4]))

    def test_all_pending_keeps_plain_fifo(self):
        self.queue_up(1, 2, 3)
        self.sync({1: PENDING, 2: PENDING, 3: PENDING})
        self.assertEqual(self.order(), (1, [2, 3]))
        self.run_cmd("release", "1", gh=ViewGh({}))
        self.assertEqual(self.order(), (2, [3]))

    def test_holder_takes_the_slot_back_ahead_of_the_others_when_the_overtaker_merges(self):
        self.queue_up(1, 2, 3)
        self.sync({1: PENDING, 2: PENDING, 3: CLEAN})
        self.assertEqual(self.order(), (3, [1, 2]))
        self.sync({1: PENDING, 2: PENDING, 3: MERGED})
        self.assertEqual(self.order(), (1, [2]))

    def test_holder_takes_the_slot_back_when_the_overtaker_closes(self):
        self.queue_up(1, 2, 3)
        self.sync({1: PENDING, 2: PENDING, 3: CLEAN})
        self.assertEqual(self.order(), (3, [1, 2]))
        self.sync({1: PENDING, 2: PENDING, 3: {**CLEAN, "state": "CLOSED"}})
        self.assertEqual(self.order(), (1, [2]))

    def test_holder_takes_the_slot_back_when_the_overtaker_releases(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: CLEAN})
        self.run_cmd("release", "2", gh=ViewGh({1: PENDING, 2: CLEAN}))
        self.assertEqual(self.order(), (1, []))

    def test_overtaker_that_is_overtaken_queues_behind_the_original_holder(self):
        self.queue_up(1, 2, 3)
        self.sync({1: PENDING, 2: CLEAN, 3: CLEAN})
        self.assertEqual(self.order(), (2, [1, 3]))
        self.sync({1: PENDING, 2: PENDING, 3: CLEAN})
        self.assertEqual(self.order(), (3, [1, 2]))

    def test_overtaker_that_closes_hands_back_to_the_original_through_a_second_overtaker(self):
        self.queue_up(1, 2, 3)
        self.sync({1: PENDING, 2: CLEAN, 3: CLEAN})
        self.sync({1: PENDING, 2: PENDING, 3: CLEAN})
        self.sync({1: PENDING, 2: PENDING, 3: MERGED})
        self.assertEqual(self.order(), (1, [2]))


class AskerTests(ReadyFirstCase):
    """The PR asking may-update counts as a candidate even when it never queued."""

    def test_fresh_ready_asker_that_never_queued_overtakes_a_pending_holder(self):
        self.claimed_holder(1)
        code, out, _ = self.run_cmd("may-update", "2", "--lane", "l2", gh=ViewGh({1: PENDING, 2: CLEAN}))
        self.assertEqual((code, self.order()), (0, (2, [1])), out)
        self.assertEqual(self.data()["ready_first"]["overtaken"], [1])

    def test_asker_that_is_pending_or_unknown_does_not_overtake(self):
        for name, view in (("pending", PENDING), ("unknown", UNKNOWN_STATE), ("gh error", GH_ERROR)):
            with self.subTest(name):
                self.run_cmd("reset", "--yes")
                self.claimed_holder(1)
                code, _, _ = self.run_cmd("may-update", "2", "--lane", "l2", gh=ViewGh({1: PENDING, 2: view}))
                self.assertEqual((code, self.order()), (1, (1, [])))

    def test_asker_does_not_overtake_a_clean_holder(self):
        self.claimed_holder(1)
        code, _, _ = self.run_cmd("may-update", "2", "--lane", "l2", gh=ViewGh({1: CLEAN, 2: CLEAN}))
        self.assertEqual((code, self.order()), (1, (1, [])))

    def test_queued_ready_pr_is_served_before_a_never_queued_asker(self):
        self.claimed_holder(1)
        self.queue_up(3)
        code, _, _ = self.run_cmd("may-update", "2", "--lane", "l2", gh=ViewGh({1: PENDING, 2: CLEAN, 3: CLEAN}))
        self.assertEqual((code, self.order()), (1, (3, [1])))


class ReturningHolderTests(ReadyFirstCase):
    """An overtaken holder that regains the slot gets a claim window to max(old expiry, now + claim minutes),
    claims a fresh lease with its first may-update, and is never displaced again."""

    def test_returning_holder_takes_the_slot_back_when_the_overtaker_merges(self):
        # not displaced again in the same refresh
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: CLEAN})
        self.run_cmd("request", "4", "--lane", "l4", gh=ViewGh({}))
        self.sync({1: BEHIND, 2: MERGED, 4: CLEAN})
        self.assertEqual(self.order(), (1, [4]))

    def test_returning_holder_is_not_displaced_before_it_claims(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: CLEAN})
        self.run_cmd("request", "4", "--lane", "l4", gh=ViewGh({}))
        self.sync({1: PENDING, 2: MERGED, 4: CLEAN})
        self.assertEqual(self.order(), (1, [4]))
        self.sync({1: PENDING, 4: CLEAN})  # and not by later ready PRs either, claimed or not
        self.assertEqual(self.order(), (1, [4]))

    def test_returning_holder_makes_its_one_restamp_without_a_second_displacement(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: CLEAN})
        self.sync({1: BEHIND, 2: MERGED})
        gh = ViewGh({1: BEHIND})
        self.assertEqual(self.run_cmd("may-update", "1", gh=gh)[0], 0)  # the restamp lease
        self.run_cmd("request", "5", "--lane", "l5", gh=ViewGh({}))
        gh = self.sync({1: PENDING, 5: CLEAN})  # CI after the push is pending: 5 still waits
        self.assertEqual(self.order(), (1, [5]))
        self.assertEqual(self.run_cmd("may-update", "5", gh=gh)[0], 1)
        self.assertFalse([c for c in gh.calls if "update-branch" in " ".join(c)])

    def test_returned_holder_can_finish_the_restamp_the_overtake_forced(self):
        self.run_cmd("may-update", "1", "--lane", "l1", gh=ViewGh({}), now=at(0))  # lease to 10:40
        code, _, _ = self.run_cmd("may-update", "2", "--lane", "l2", gh=ViewGh({1: PENDING, 2: CLEAN}), now=at(20))
        self.assertEqual(code, 0)
        self.run_cmd("release", "2", gh=ViewGh({1: PENDING, 2: MERGED}), now=at(21))
        self.assertEqual(self.data()["holder"]["pr"], 1)
        code, _, _ = self.run_cmd("may-update", "1", "--lane", "l1", gh=ViewGh({1: CLEAN}), now=at(25))
        self.assertEqual(code, 0)  # behind after #2's merge: its lane asks to restamp
        self.run_cmd("status", gh=ViewGh({1: PENDING}), now=at(41))  # the forced second CI is still running
        self.assertEqual(self.data()["holder"]["pr"], 1)

    def test_returned_holder_claims_a_fresh_lease_with_its_first_may_update(self):
        self.run_cmd("may-update", "1", "--lane", "a", gh=ViewGh({}), now=at(0))
        self.run_cmd("request", "3", "--lane", "c", gh=ViewGh({1: PENDING, 3: PENDING}), now=at(5))
        self.run_cmd("may-update", "2", "--lane", "b", gh=ViewGh({1: PENDING, 2: CLEAN, 3: PENDING}), now=at(20))
        self.run_cmd("release", "2", gh=ViewGh({1: PENDING, 3: PENDING}), now=at(22))
        holder = self.data()["holder"]
        self.assertEqual((holder["pr"], holder["claimed"], holder["expires_at"]), (1, False, at(40)))
        self.run_cmd("may-update", "1", "--lane", "a", gh=ViewGh({1: BEHIND, 3: PENDING}), now=at(25))
        self.assertEqual(self.data()["holder"]["expires_at"], at(65))  # a fresh 40 min from the claim
        code, _, _ = self.run_cmd("may-update", "1", "--lane", "a", gh=ViewGh({1: CLEAN, 3: PENDING}), now=at(47))
        self.assertEqual((code, self.data()["holder"]["pr"]), (0, 1))

    def test_returned_holder_that_never_asks_again_lapses_at_the_end_of_its_window(self):
        self.run_cmd("may-update", "1", "--lane", "a", gh=ViewGh({}), now=at(0))
        self.run_cmd("may-update", "2", "--lane", "b", gh=ViewGh({1: PENDING, 2: CLEAN}), now=at(20))
        self.run_cmd("release", "2", gh=ViewGh({1: PENDING}), now=at(22))
        self.run_cmd("status", gh=ViewGh({1: PENDING}), now=at(41))
        self.assertIsNone(self.data()["holder"])

    def test_unclaimed_holder_overtaken_returns_unclaimed_with_its_claim_window(self):
        self.queue_up(1, 2, 3)
        self.sync({1: MERGED, 2: PENDING, 3: CLEAN})
        self.assertEqual(self.order(), (3, [2]))
        self.sync({2: PENDING, 3: MERGED})
        holder = self.data()["holder"]
        self.assertEqual((holder["pr"], holder["claimed"], holder["expires_at"]), (2, False, at(10)))

    def test_claimed_holder_returns_to_its_old_expiry_as_a_claim_window_not_a_new_lease(self):
        self.claimed_holder(1)
        self.queue_up(2)
        self.sync({1: PENDING, 2: CLEAN})
        self.sync({1: PENDING, 2: MERGED}, now=at(20))
        holder = self.data()["holder"]
        self.assertEqual((holder["pr"], holder["claimed"], holder["expires_at"]), (1, False, at(40)))

    def test_overtaken_holder_whose_ci_fails_while_it_waits_gets_no_new_lease(self):
        self.claimed_holder(1)
        self.queue_up(2)
        self.sync({1: PENDING, 2: CLEAN})
        self.sync({1: FAILED, 2: MERGED}, now=at(35))
        self.assertEqual(self.data()["holder"]["expires_at"], at(45))  # max(5 min left, 10 min claim window)
        self.sync({1: FAILED}, now=at(50))  # nobody drives it: the lease lapses
        self.assertIsNone(self.data()["holder"])

    def test_overtaken_holder_whose_lease_ran_out_returns_with_the_claim_window(self):
        self.claimed_holder(1)
        self.queue_up(2)
        self.sync({1: PENDING, 2: CLEAN})
        self.sync({1: PENDING, 2: MERGED}, now=at(50))
        self.assertEqual(self.data()["holder"]["expires_at"], at(60))

    def test_overtaken_holder_that_overtakes_back_returns_as_a_returning_holder(self):
        self.claimed_holder(1)  # lease to 10:40
        self.run_cmd("request", "2", "--lane", "l2", gh=ViewGh({1: PENDING}), now=at(1))
        self.sync({1: PENDING, 2: CLEAN}, now=at(2))  # #2 overtakes: its claim window runs to 10:12
        self.sync({1: CLEAN, 2: PENDING}, now=at(3))  # #1 overtakes back
        holder = self.data()["holder"]
        self.assertEqual((holder["pr"], holder["claimed"], holder.get("returned"), holder["expires_at"]),
                         (1, False, True, at(40)))  # max(old expiry, 10:03 + claim window)
        self.assertEqual(self.data()["ready_first"]["leases"], {"2": {"expires_at": at(12)}})
        _, out, _ = self.run_cmd("status", gh=ViewGh({1: PENDING, 2: CLEAN}), now=at(4))
        self.assertNotIn("claimed:", out)  # never turned into a lease without its own may-update
        holder = self.data()["holder"]
        self.assertEqual((holder["pr"], holder["claimed"], holder["expires_at"]), (1, False, at(40)))
        self.run_cmd("may-update", "1", gh=ViewGh({1: CLEAN, 2: PENDING}), now=at(5))
        self.assertEqual(self.data()["holder"]["expires_at"], at(45))  # a fresh lease from its claim
        self.sync({1: MERGED, 2: PENDING}, now=at(6))  # #2 returns as a returning holder too
        holder = self.data()["holder"]
        self.assertEqual((holder["pr"], holder["claimed"], holder.get("returned"), holder["expires_at"]),
                         (2, False, True, at(16)))

    def test_returned_unclaimed_holder_that_nobody_claims_lapses_at_its_claim_window(self):
        self.queue_up(1, 2, 3)
        self.sync({1: MERGED, 2: PENDING, 3: CLEAN})
        self.sync({2: PENDING, 3: MERGED})
        self.sync({2: PENDING}, now=at(15))
        self.assertIsNone(self.data()["holder"])

    def test_unclaimed_holder_that_was_never_overtaken_still_expires(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: PENDING}, now=at(15))
        self.assertEqual(self.order(), (2, []))


class ReleaseTests(ReadyFirstCase):
    def test_release_by_a_holder_whose_ci_runs_counts_as_released(self):
        self.claimed_holder(1)
        self.queue_up(2)
        code, out, _ = self.run_cmd("release", "1", gh=ViewGh({1: PENDING, 2: CLEAN}))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.order(), (2, []))
        self.assertEqual(self.data()["ready_first"]["overtaken"], [])
        self.sync({1: PENDING, 2: MERGED})
        self.assertIsNone(self.data()["holder"])

    def test_release_by_an_overtaken_queued_pr_counts_as_released(self):
        self.claimed_holder(1)
        self.queue_up(2, 3)
        self.sync({1: PENDING, 2: CLEAN, 3: PENDING})
        code, _, _ = self.run_cmd("release", "1", gh=ViewGh({1: PENDING, 2: CLEAN, 3: PENDING}))
        self.assertEqual((code, self.order(), self.data()["ready_first"]["overtaken"]), (0, (2, [3]), []))


class StaleVerdictTests(ReadyFirstCase):
    """A verdict read before the holder's last may-update yes is dropped."""

    def test_holder_is_not_displaced_by_a_view_read_before_its_go_ahead(self):
        # lane B read #1 pending, then #1 went green and its lane got may-update yes (and merges); B's stale
        # verdict must not hand the slot to #2 while #1 merges.
        self.run_cmd("may-update", "1", "--lane", "l1", gh=ViewGh({}))  # free slot: #1 holds, claimed
        self.run_cmd("request", "2", "--lane", "l2", gh=ViewGh({1: PENDING}))
        go_ahead = []

        def lane_b(args):
            if args[0] == "pr" and int(args[2]) == 2 and not go_ahead:
                go_ahead.append(self.run_cmd("may-update", "1", gh=ViewGh({1: CLEAN, 2: CLEAN}))[0])
            return ViewGh({1: PENDING, 2: CLEAN})(args)

        self.run_cmd("status", gh=lane_b)
        self.assertEqual(go_ahead, [0])
        self.assertEqual(self.order(), (1, [2]))

    def test_go_ahead_is_stamped_and_a_may_update_yes_counts_every_time(self):
        self.run_cmd("may-update", "1", "--lane", "l1")
        first = self.data()["ready_first"]["go_ahead"]
        self.run_cmd("may-update", "1")
        self.assertNotEqual(self.data()["ready_first"]["go_ahead"], first)


class OlderWriterTests(ReadyFirstCase):
    """An older merge_slot.py keeps the top-level ready_first key but drops per-entry flags."""

    def test_protection_survives_a_writer_that_drops_the_per_entry_flags(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: CLEAN})
        self.sync({1: PENDING, 2: MERGED})
        state = self.data()
        state["holder"] = {k: state["holder"][k] for k in ("pr", "lane", "granted_at", "claimed", "expires_at")}
        state["holder"]["claimed"] = False
        self.write_state(state)
        self.run_cmd("request", "5", "--lane", "l5", gh=ViewGh({}))
        self.sync({1: PENDING, 5: CLEAN})
        self.assertEqual(self.order(), (1, [5]))

    def test_unclaimed_overtaken_holder_granted_by_an_old_writer_keeps_its_place(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: CLEAN})
        self.sync({1: PENDING, 2: MERGED})
        state = self.data()  # what an older writer leaves: an unclaimed claim-window grant, flags kept
        state["holder"] = {"pr": 1, "lane": "l1", "granted_at": at(0), "claimed": False, "expires_at": at(10)}
        self.write_state(state)
        self.sync({1: PENDING}, now=at(15))
        holder = self.data()["holder"]
        self.assertEqual((holder["pr"], holder["claimed"], holder["expires_at"]), (1, True, at(40)))
        self.assertEqual(self.data()["ready_first"]["overtaken"], [1])


class QueueSyncTests(ReadyFirstCase):
    """queue_sync.py keeps overtaken holders at the queue head."""

    def test_queue_sync_keeps_the_overtaken_holder_at_the_head(self):
        self.queue_up(1, 2, 3)
        self.sync({1: PENDING, 2: PENDING, 3: CLEAN})
        self.assertEqual(self.order(), (3, [1, 2]))
        pending = test_queue_sync.pr(merge="BLOCKED", checks=[{"name": "ci", "status": "IN_PROGRESS"}])
        gh = test_queue_sync.Gh({1: pending, 2: test_queue_sync.pr(), 3: test_queue_sync.pr()})
        code = queue_sync.main(["--yes", "--state", self.state], runner=gh, out=lambda _: None, err=lambda _: None)
        self.assertEqual(code, 0)
        self.assertEqual([q["pr"] for q in self.data()["queue"]][0], 1)

    def test_queue_sync_pins_two_overtaken_entries_in_order(self):
        self.queue_up(1, 2, 3, 4)
        self.sync({1: PENDING, 2: CLEAN, 3: PENDING, 4: PENDING})
        self.sync({1: PENDING, 2: PENDING, 3: CLEAN, 4: PENDING})
        self.assertEqual(self.order(), (3, [1, 2, 4]))
        pending = test_queue_sync.pr(merge="BLOCKED", checks=[{"name": "ci", "status": "IN_PROGRESS"}])
        gh = test_queue_sync.Gh({1: pending, 2: pending, 3: test_queue_sync.pr(), 4: test_queue_sync.pr()})
        queue_sync.main(["--yes", "--state", self.state], runner=gh, out=lambda _: None, err=lambda _: None)
        self.assertEqual([q["pr"] for q in self.data()["queue"]], [1, 2, 4])

    def test_queue_sync_write_keeps_the_overtaken_holder_at_the_head_when_an_overtake_lands_mid_sync(self):
        self.queue_up(1, 2, 3)
        raced = []

        def overtake_once(pr):
            if not raced:
                raced.append(pr)
                self.run_cmd("status", gh=ViewGh({1: PENDING, 2: PENDING, 3: CLEAN}))

        gh = test_queue_sync.Gh({}, before_pr=overtake_once)
        queue_sync.main(["--yes", "--state", self.state], runner=gh, out=lambda _: None, err=lambda _: None)
        self.assertEqual(self.order(), (3, [1, 2]))
        self.run_cmd("release", "3", gh=ViewGh({1: PENDING, 2: PENDING}))
        self.assertEqual(self.data()["holder"]["pr"], 1)


class GhCostTests(ReadyFirstCase):
    """Freshness is asked only when an overtake is possible, and only down to the first fresh candidate."""

    def test_clean_holder_costs_one_gh_call_per_watched_pr(self):
        self.queue_up(1, 2, 3, 4)
        gh = self.sync({1: CLEAN, 2: CLEAN, 3: CLEAN, 4: CLEAN}, compare={"abc12345": "behind"})
        self.assertEqual(len(gh.calls), 4)

    def test_protected_holder_costs_no_freshness_lookup(self):
        self.queue_up(1, 2)
        self.sync({1: PENDING, 2: CLEAN})
        self.sync({1: PENDING, 2: MERGED})
        self.run_cmd("request", "3", "--lane", "l3", gh=ViewGh({}))
        gh = self.sync({1: PENDING, 3: CLEAN})
        self.assertEqual([c for c in gh.calls if c[0] == "api"], [])

    def test_freshness_is_looked_up_only_down_to_the_first_ready_candidate(self):
        views = {1: PENDING, 2: {**CLEAN, "headRefOid": "head2"}, 3: {**CLEAN, "headRefOid": "head3"},
                 4: {**CLEAN, "headRefOid": "head4"}}
        self.queue_up(1, 2, 3, 4)
        gh = self.sync(views, compare={"head2": "behind"}, tip_date="2030-01-01T10:00:00Z")
        self.assertEqual(self.order(), (3, [1, 2, 4]))
        self.assertFalse([c for c in gh.calls if "head4" in " ".join(c)])


class DamagedStateTests(ReadyFirstCase):
    def assert_damaged(self):
        code, _, err = self.run_cmd("status")
        self.assertEqual(code, 2)
        self.assertIn("damaged", err)

    def test_go_ahead_without_n_is_damaged_state(self):
        self.claimed_holder(1)
        state = self.data()
        state["ready_first"]["go_ahead"] = {"pr": 1}
        self.write_state(state)
        self.assert_damaged()

    def test_a_lease_that_is_not_an_object_is_damaged_state(self):
        for value in ([], "x", {"1": 5}, {"1": "x"}):
            with self.subTest(value=value):
                self.run_cmd("reset", "--yes")
                self.run_cmd("may-update", "1", "--lane", "l1", gh=ViewGh({}))
                state = self.data()
                state["ready_first"]["leases"] = value
                self.write_state(state)
                self.assert_damaged()


if __name__ == "__main__":
    unittest.main()
