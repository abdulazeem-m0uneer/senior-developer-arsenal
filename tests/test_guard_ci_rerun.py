"""rerun-after-red for CI: gh run rerun and gh workflow run need a cause note after the run was seen red."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_guard_rerun import CAUSE, RerunCase  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import guard_ci_rerun  # noqa: E402

RED_VIEW = "X main CI · 9876543211\nTriggered via push\n\nJOBS\nX test in 20s (ID 9)\n"
GREEN_VIEW = "✓ main CI · 9876543211\nTriggered via push\n\nJOBS\n✓ test in 20s (ID 9)\n"
PR_CHECKS_RED = ("test\tfail\t20s\thttps://github.com/o/r/actions/runs/9876543211/job/9\n"
                 "lint\tpass\t5s\thttps://github.com/o/r/actions/runs/9876543211/job/10\n")
RUN_LIST_RED = "completed\tfailure\tfix tax\tCI\tmain\tpush\t9876543211\t30s\t1m\ncompleted\tsuccess\tdocs\tCI\tmain\tpush\t9876543212\t30s\t2m\n"
REFUSED = "rerun-after-red"


class CiRerunCase(RerunCase):
    def view(self, text=RED_VIEW, command="gh run view 9876543211"):
        self.bash(command, tool_response={"stdout": text, "stderr": ""})


class RerunOfARedRunTest(CiRerunCase):
    def test_every_rerun_form_of_a_run_seen_red_is_refused(self):
        self.view()
        for command in ("gh run rerun 9876543211", "gh run rerun 9876543211 --failed", "gh run rerun 9876543211 --job 9",
                        "gh run rerun 9876543211 -j 9", "gh -R o/r run rerun 9876543211", "cd web && gh run rerun 9876543211"):
            self.assertIn(REFUSED, self.pre(command), command)

    def test_the_refusal_names_the_cause_command(self):
        self.view()
        reason = self.pre("gh run rerun 9876543211")
        self.assertIn("cause", reason)
        self.assertIn("L083", reason)

    def test_a_workflow_redispatch_is_refused_after_a_red_run(self):
        self.view()
        self.assertIn(REFUSED, self.pre("gh workflow run ci.yml"))
        self.assertIn(REFUSED, self.pre("gh workflow run ci.yml --ref main"))

    def test_a_job_rerun_without_a_run_id_is_refused_after_a_red_run(self):
        self.view()
        self.assertIn(REFUSED, self.pre("gh run rerun --job 9"))

    def test_a_cancelled_run_counts_as_red(self):
        self.view("- main CI · 9876543211 (cancelled)\n")
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))

    def test_a_json_conclusion_counts_as_red(self):
        self.view('{"conclusion":"failure"}', "gh run view 9876543211 --json conclusion")
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))


class SeenRedTest(CiRerunCase):
    def test_a_run_never_seen_red_may_be_rerun(self):
        for command in ("gh run rerun 9876543211", "gh run rerun 9876543211 --failed", "gh workflow run ci.yml"):
            self.assertEqual(self.pre(command), "", command)

    def test_a_run_seen_green_may_be_rerun(self):
        self.view(GREEN_VIEW)
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")

    def test_another_run_than_the_red_one_may_be_rerun(self):
        self.view()
        self.assertEqual(self.pre("gh run rerun 4999"), "")

    def test_a_zero_failing_summary_is_not_red(self):
        self.bash("gh pr checks", tool_response={"stdout": "0 failing, 3 successful, 0 skipped\n", "stderr": ""})
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")

    def test_pr_checks_that_failed_name_the_run_in_their_url(self):
        self.bash("gh pr checks 7", failed=True, error="Exit code 8\n" + PR_CHECKS_RED)
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))
        self.assertEqual(self.pre("gh run rerun 4999"), "")

    def test_pr_checks_that_passed_do_not_refuse(self):
        self.bash("gh pr checks 7", tool_response={"stdout": "test\tpass\t20s\thttps://github.com/o/r/actions/runs/9876543211/job/9\n",
                                                  "stderr": ""})
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")

    def test_red_pr_checks_without_a_run_id_refuse_any_rerun(self):
        self.bash("gh pr checks 7", failed=True, error="Exit code 8\ntest\tfail\t20s\t\n")
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))

    def test_a_run_list_shows_the_red_run_id(self):
        self.bash("gh run list --limit 5", tool_response={"stdout": RUN_LIST_RED, "stderr": ""})
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))
        self.assertEqual(self.pre("gh run rerun 9876543212"), "")

    def test_a_cancelled_run_list_row_counts(self):
        self.bash("gh run list", tool_response={"stdout": "completed\tcancelled\tx\tCI\tmain\tpush\t9876543213\t1s\t1m\n",
                                                "stderr": ""})
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543213"))


class CauseNoteTest(CiRerunCase):
    def test_a_cause_note_after_the_red_allows_one_rerun(self):
        self.view()
        self.bash(CAUSE)
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")
        self.assertEqual(self.pre("gh workflow run ci.yml"), "")

    def test_a_cause_note_before_the_red_does_not_count(self):
        self.bash(CAUSE)
        self.view()
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))

    def test_a_second_rerun_of_the_same_run_needs_a_new_note(self):
        self.view()
        self.bash(CAUSE)
        self.bash("gh run rerun 9876543211")
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211 --failed"))
        self.bash(CAUSE)
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")

    def test_a_rerun_of_a_run_never_seen_red_does_not_lock_the_next_one(self):
        self.bash("gh run rerun 9876543211")
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")

    def test_a_second_dispatch_needs_a_new_note(self):
        self.view()
        self.bash(CAUSE)
        self.bash("gh workflow run ci.yml")
        self.assertIn(REFUSED, self.pre("gh workflow run ci.yml"))

    def test_a_dispatch_with_no_red_run_seen_does_not_lock_the_next(self):
        self.bash("gh workflow run ci.yml")
        self.assertEqual(self.pre("gh workflow run ci.yml"), "")

    def test_a_dispatch_that_failed_to_start_is_not_a_dispatch(self):
        self.view()
        self.bash(CAUSE)
        self.bash("gh workflow run ci.yml", failed=True, error="Exit code 1\nHTTP 422")
        self.assertEqual(self.pre("gh workflow run ci.yml"), "")

    def test_a_rerun_that_failed_to_start_is_not_a_rerun(self):
        self.view()
        self.bash(CAUSE)
        self.bash("gh run rerun 9876543211", failed=True, error="Exit code 1\nHTTP 403")
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")


class FalseRedTest(CiRerunCase):
    def test_a_green_check_named_fail_fast_is_not_red(self):
        self.view("✓ main CI · 9876543211\n\nJOBS\n✓ fail-fast-lint in 5s (ID 9)\n")
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")

    def test_a_green_log_that_says_failed_zero_is_not_red(self):
        self.view("lint\tRun\t2026-01-01T00:00:00Z tests failed: 0\n", "gh run view 9876543211 --log")
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")

    def test_a_run_view_with_the_web_flag_still_names_its_run(self):
        self.view(RED_VIEW, "gh run view -w 9876543211")
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))
        self.assertEqual(self.pre("gh run rerun 4999"), "")


class WorkflowScopeTest(CiRerunCase):
    def test_a_dispatch_of_another_workflow_than_the_red_one_passes(self):
        self.bash("gh run list", tool_response={"stdout": RUN_LIST_RED, "stderr": ""})
        self.assertEqual(self.pre("gh workflow run docs.yml"), "")
        self.assertIn(REFUSED, self.pre("gh workflow run ci.yml"))
        self.assertIn(REFUSED, self.pre("gh workflow run CI"))

    def test_a_dispatch_whose_workflow_is_unknown_is_refused(self):
        self.bash("gh pr checks 7", failed=True, error="Exit code 8\n" + PR_CHECKS_RED)
        self.assertIn(REFUSED, self.pre("gh workflow run docs.yml"))


class ClosingTest(CiRerunCase):
    def test_a_rerun_that_went_green_closes_its_workflow(self):
        self.view()
        self.bash(CAUSE)
        self.bash("gh run rerun 9876543211")
        self.assertIn(REFUSED, self.pre("gh workflow run ci.yml"))
        self.view(GREEN_VIEW)
        self.assertEqual(self.pre("gh workflow run ci.yml"), "")
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")

    def test_a_newer_passing_run_of_the_workflow_closes_it(self):
        newer_first = "completed\tsuccess\tfix\tCI\tmain\tpush\t9876543299\t30s\t1m\n" + RUN_LIST_RED.splitlines(True)[0]
        self.bash("gh run list", tool_response={"stdout": newer_first, "stderr": ""})
        self.assertEqual(self.pre("gh workflow run ci.yml"), "")

    def test_a_newer_red_run_stays_open_after_an_older_pass(self):
        older_pass = "completed\tfailure\tfix\tCI\tmain\tpush\t9876543299\t30s\t1m\n" + \
                     "completed\tsuccess\tfix\tCI\tmain\tpush\t9876543211\t30s\t2m\n"
        self.bash("gh run list", tool_response={"stdout": older_pass, "stderr": ""})
        self.assertIn(REFUSED, self.pre("gh workflow run ci.yml"))


class OtherSourcesTest(CiRerunCase):
    def test_a_failed_run_watch_counts_as_seen_red(self):
        self.bash("gh run watch 9876543211 --exit-status", failed=True, error="Exit code 1\nX main CI · 9876543211\n")
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))

    def test_the_api_rerun_forms_are_refused_after_a_red_run(self):
        self.view()
        for command in ("gh api -X POST repos/o/r/actions/runs/9876543211/rerun",
                        "gh api --method POST repos/o/r/actions/runs/9876543211/rerun-failed-jobs"):
            self.assertIn(REFUSED, self.pre(command), command)
        self.assertEqual(self.pre("gh api -X POST repos/o/r/actions/runs/4999/rerun"), "")
        self.assertEqual(self.pre("gh api repos/o/r/actions/runs/9876543211"), "")

    def test_an_api_rerun_that_started_needs_a_new_note(self):
        self.view()
        self.bash(CAUSE)
        self.bash("gh api -X POST repos/o/r/actions/runs/9876543211/rerun")
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))


HOUR = 3600
NOW = 1_800_000_000


def red_event(runs, at=None):
    event = {"event": "ci_red", "runs": runs, "workflows": ["ci"]}
    return {**event, "time": at} if at is not None else event


class StaleUnknownRedTest(unittest.TestCase):
    """A red with no run id ("*") refuses a named run only while it is at most 2 hours old."""

    def refused(self, events, target="45633452030"):
        return guard_ci_rerun.refused(["run", "rerun", target, "--failed"], events, now=NOW)

    def test_a_fresh_unknown_red_refuses_a_named_run(self):
        self.assertTrue(self.refused([red_event(["*"], NOW - HOUR)]))

    def test_exactly_two_hours_still_refuses(self):
        self.assertTrue(self.refused([red_event(["*"], NOW - 2 * HOUR)]))

    def test_an_unknown_red_older_than_two_hours_does_not_refuse(self):
        self.assertFalse(self.refused([red_event(["*"], NOW - 2 * HOUR - 1)]))

    def test_the_replay_of_the_nov_25_false_refusal_passes(self):
        oct_30 = NOW - 26 * 24 * HOUR
        self.assertFalse(self.refused([red_event(["*"], oct_30)]))

    def test_a_named_run_seen_red_stays_open_however_old(self):
        self.assertTrue(self.refused([red_event(["45633452030"], NOW - 30 * 24 * HOUR)]))

    def test_an_old_unknown_red_still_refuses_a_rerun_with_no_id(self):
        self.assertTrue(guard_ci_rerun.refused(["run", "rerun"], [red_event(["*"], NOW - 30 * HOUR)], now=NOW))

    def test_a_fresh_unknown_red_after_an_old_one_refuses(self):
        self.assertTrue(self.refused([red_event(["*"], NOW - 30 * HOUR), red_event(["*"], NOW - 60)]))

    def test_an_event_without_a_time_counts_as_fresh(self):
        self.assertTrue(self.refused([red_event(["*"])]))


class StaleUnknownWorkflowRedTest(unittest.TestCase):
    """A red whose workflow is unknown ("*") refuses a dispatch only while it is at most 2 hours old."""

    @staticmethod
    def red(at=None):
        event = {"event": "ci_red", "runs": ["9876543211"], "workflows": ["*"]}
        return {**event, "time": at} if at is not None else event

    def dispatch(self, events, target="docs.yml"):
        return guard_ci_rerun.refused(["workflow", "run", target], events, now=NOW)

    def test_a_fresh_unknown_workflow_red_refuses_a_dispatch(self):
        self.assertTrue(self.dispatch([self.red(NOW - HOUR)]))

    def test_exactly_two_hours_still_refuses(self):
        self.assertTrue(self.dispatch([self.red(NOW - 2 * HOUR)]))

    def test_older_than_two_hours_passes(self):
        self.assertFalse(self.dispatch([self.red(NOW - 2 * HOUR - 1)]))

    def test_a_named_workflow_red_stays_open_however_old(self):
        old = {"event": "ci_red", "runs": ["1"], "workflows": ["ci"], "time": NOW - 30 * 24 * HOUR}
        self.assertTrue(self.dispatch([old], "ci.yml"))
        self.assertFalse(self.dispatch([old], "docs.yml"))

    def test_an_old_unknown_workflow_red_beside_a_fresh_named_one_refuses_the_named_only(self):
        named = {"event": "ci_red", "runs": ["2"], "workflows": ["ci"], "time": NOW - 60}
        events = [self.red(NOW - 30 * HOUR), named]
        self.assertTrue(self.dispatch(events, "ci.yml"))
        self.assertFalse(self.dispatch(events, "docs.yml"))

    def test_a_dispatch_with_no_workflow_still_refuses_while_any_red_is_open(self):
        self.assertTrue(guard_ci_rerun.refused(["workflow", "run"], [self.red(NOW - 30 * HOUR)], now=NOW))

    def test_an_event_without_a_time_counts_as_fresh(self):
        self.assertTrue(self.dispatch([self.red()]))


class StaleUnknownRerunReopenTest(unittest.TestCase):
    """A successful rerun re-opens its target after an unknown ("*") red only while that red is at most 2 hours old."""

    def rerun_events(self, red_at, field="runs"):
        red = {"event": "ci_red", "runs": ["*"] if field == "runs" else ["1"],
               "workflows": ["ci"] if field == "runs" else ["*"], "time": red_at}
        return [red, {"event": "ci_rerun", "runs": ["777"], "time": NOW - 10},
                {"event": "ci_rerun", "runs": [], "workflow": "docs", "time": NOW - 10}]

    def run_refused(self, events):
        return guard_ci_rerun.refused(["run", "rerun", "777"], events, now=NOW)

    def flow_refused(self, events):
        return guard_ci_rerun.refused(["workflow", "run", "docs.yml"], events, now=NOW)

    def test_the_rerun_target_reopens_while_the_unknown_red_is_fresh(self):
        self.assertTrue(self.run_refused(self.rerun_events(NOW - HOUR)))

    def test_the_rerun_target_does_not_reopen_after_the_window(self):
        self.assertFalse(self.run_refused(self.rerun_events(NOW - 2 * HOUR - 1)))

    def test_the_reviewers_case_at_t_9000(self):
        events = [{"event": "ci_red", "runs": ["*"], "workflows": ["ci"], "time": 0},
                  {"event": "ci_rerun", "runs": ["777"], "time": 8990}]
        self.assertFalse(guard_ci_rerun.refused(["run", "rerun", "777"], events, now=9000))
        self.assertTrue(guard_ci_rerun.refused(["run", "rerun", "777"], events, now=7000))

    def test_the_dispatch_target_does_not_reopen_after_the_window_of_an_unknown_workflow_red(self):
        self.assertTrue(self.flow_refused(self.rerun_events(NOW - HOUR, "workflows")))
        self.assertFalse(self.flow_refused(self.rerun_events(NOW - 2 * HOUR - 1, "workflows")))


class PrChecksGreenTest(CiRerunCase):
    def row(self, state, job, run="9876543211"):
        return f"job{job}\t{state}\t5s\thttps://github.com/o/r/actions/runs/{run}/job/{job}\n"

    def checks(self, *rows, red=True):
        if red:
            self.bash("gh pr checks 7", failed=True, error="Exit code 8\n" + "".join(rows))
        else:
            self.bash("gh pr checks 7", tool_response={"stdout": "".join(rows), "stderr": ""})

    def test_an_all_pass_output_closes_the_red_run(self):
        self.checks(self.row("fail", 1), self.row("pass", 2))
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))
        self.checks(self.row("pass", 1), self.row("pass", 2), red=False)
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")

    def test_pass_and_skipping_rows_of_a_run_close_it(self):
        self.checks(self.row("fail", 1))
        self.checks(self.row("pass", 1), self.row("skipping", 2), red=False)
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")

    def test_a_run_with_a_pending_row_stays_open(self):
        self.checks(self.row("fail", 1))
        self.checks(self.row("pass", 1), self.row("pending", 2), red=False)
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))

    def test_mixed_pass_and_fail_rows_of_the_same_run_do_not_close_it(self):
        self.checks(self.row("fail", 1))
        self.checks(self.row("pass", 1), self.row("fail", 2))
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))

    def test_a_passing_other_run_leaves_the_red_run_open(self):
        self.checks(self.row("fail", 1))
        self.checks(self.row("pass", 3, run="4999"), red=False)
        self.assertIn(REFUSED, self.pre("gh run rerun 9876543211"))

    def test_a_fully_passing_output_closes_the_unknown_reds_and_workflows(self):
        self.bash("gh pr checks 7", failed=True, error="Exit code 8\ntest\tfail\t20s\t\n")
        self.assertIn(REFUSED, self.pre("gh workflow run docs.yml"))
        self.checks(self.row("pass", 1), self.row("skipping", 2), red=False)
        self.assertEqual(self.pre("gh workflow run docs.yml"), "")
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")

    def test_a_partly_passing_output_leaves_the_unknown_red_open(self):
        self.bash("gh pr checks 7", failed=True, error="Exit code 8\ntest\tfail\t20s\t\n")
        self.checks(self.row("pass", 1), self.row("pending", 2), red=False)
        self.assertIn(REFUSED, self.pre("gh workflow run docs.yml"))

    def test_a_run_closed_by_pass_rows_does_not_close_the_unknown_workflow_while_another_run_fails(self):
        self.bash("gh pr checks 7", failed=True, error="Exit code 8\n" + self.row("fail", 1, run="123"))
        self.assertIn(REFUSED, self.pre("gh workflow run ci.yml"))
        self.checks(self.row("pass", 1, run="123"), self.row("fail", 2, run="456"))
        self.assertIn(REFUSED, self.pre("gh workflow run ci.yml"))
        self.assertIn(REFUSED, self.pre("gh run rerun 456"))

    def test_the_same_output_with_every_row_passing_closes_the_unknown_workflow(self):
        self.bash("gh pr checks 7", failed=True, error="Exit code 8\n" + self.row("fail", 1, run="123"))
        self.checks(self.row("pass", 1, run="123"), self.row("pass", 2, run="456"), red=False)
        self.assertEqual(self.pre("gh workflow run ci.yml"), "")

    def test_a_run_closed_by_pass_rows_closes_its_workflow(self):
        self.bash("gh run list", tool_response={"stdout": RUN_LIST_RED, "stderr": ""})
        self.assertIn(REFUSED, self.pre("gh workflow run ci.yml"))
        self.checks(self.row("pass", 1), red=False)
        self.assertEqual(self.pre("gh workflow run ci.yml"), "")


class RerunWithoutAnIdTest(CiRerunCase):
    def test_a_job_rerun_with_no_red_seen_does_not_open_a_refusal(self):
        self.bash("gh api -X POST repos/o/r/actions/jobs/123/rerun")
        self.assertEqual(self.pre("gh run rerun 99999"), "")

    def test_an_unknown_red_expiry_is_not_skipped_when_no_unknown_red_exists(self):
        self.assertFalse(guard_ci_rerun.unknown_red_is_fresh([], NOW))
        self.assertFalse(guard_ci_rerun.unknown_red_is_fresh([red_event(["5"], NOW)], NOW))

    def test_an_id_less_rerun_after_a_fresh_unknown_red_still_reopens_it(self):
        events = [red_event(["*"], NOW - 60), {"event": "ci_rerun", "runs": ["*"], "time": NOW - 30}]
        self.assertTrue(guard_ci_rerun.refused(["run", "rerun", "99999"], events, now=NOW))


class SharedWorkflowTest(unittest.TestCase):
    def test_closing_one_red_run_keeps_the_workflow_open_while_another_run_of_it_is_red(self):
        events = [{"event": "ci_red", "runs": ["11111"], "workflows": ["ci"]},
                  {"event": "ci_red", "runs": ["22222"], "workflows": ["ci"]},
                  {"event": "ci_green", "runs": ["11111"], "workflows": [], "from_checks": True}]
        self.assertTrue(guard_ci_rerun.refused(["workflow", "run", "ci.yml"], events, now=NOW))

    def test_closing_the_last_red_run_closes_the_workflow(self):
        events = [{"event": "ci_red", "runs": ["11111"], "workflows": ["ci"]},
                  {"event": "ci_red", "runs": ["22222"], "workflows": ["ci"]},
                  {"event": "ci_green", "runs": ["11111", "22222"], "workflows": [], "from_checks": True}]
        self.assertFalse(guard_ci_rerun.refused(["workflow", "run", "ci.yml"], events, now=NOW))


class PrefilterTest(unittest.TestCase):
    def test_a_command_without_the_gh_word_is_not_parsed(self):
        parsed = []
        for command in ("echo high light right", "ls"):
            self.assertEqual(guard_ci_rerun.observe(command, "X test", lambda c: parsed.append(c) or [], True), [])
        self.assertEqual(parsed, [])


class AlwaysPassesTest(CiRerunCase):
    def test_reading_commands_are_never_refused(self):
        self.view()
        for command in ("gh run view 9876543211", "gh run view 9876543211 --log-failed", "gh run watch 9876543211", "gh pr checks 7",
                        "gh pr checks 7 --watch", "gh run list", "gh pr view 7", "gh workflow list", "gh workflow view ci.yml"):
            self.assertEqual(self.pre(command), "", command)

    def test_nothing_is_refused_without_the_registry_entry(self):
        self.registry.unlink()
        self.view()
        self.assertEqual(self.pre("gh run rerun 9876543211"), "")

    def test_the_lesson_guard_switch_lifts_it(self):
        self.view()
        self.assertEqual(self.pre("gh run rerun 9876543211", env={"ARSENAL_LESSON_GUARDS": "off"}), "")

    def test_other_commands_that_mention_a_rerun_pass(self):
        self.view()
        for command in ('echo "gh run rerun 9876543211"', 'git commit -m "gh run rerun 9876543211"', "gh issue list"):
            self.assertEqual(self.pre(command), "", command)


if __name__ == "__main__":
    unittest.main()
