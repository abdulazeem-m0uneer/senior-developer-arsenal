"""unseen-time: a clock time in outbound text must have been printed by a tool in this session (lesson G015)."""
import itertools
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "hooks"))
import guard_lessons  # noqa: E402
import guard_unseen_time as unseen_time  # noqa: E402

PLUS_THREE = "XXX-3"  # a POSIX zone three hours ahead of UTC, no tzdata needed
NEW_YORK = "EST5EDT,M3.2.0,M11.1.0"  # UTC-5, UTC-4 in summer


def tool_use(tool_id, name, tool_input):
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}]}}


def tool_result(tool_id, content):
    return {"type": "user", "message": {"role": "user", "content": [
        {"tool_use_id": tool_id, "type": "tool_result", "content": content}]}}


def assistant_text(text):
    return {"type": "assistant", "timestamp": "2026-11-25T09:09:09.000Z",
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def user_text(text, **fields):
    return {"type": "user", "message": {"role": "user", "content": text}, **fields}


class ZoneCase(unittest.TestCase):
    """Runs in a fixed local zone; the zone is restored afterwards."""
    zone = PLUS_THREE

    def setUp(self):
        patch = mock.patch.dict(os.environ, {"TZ": self.zone})
        patch.start()
        time.tzset()
        self.addCleanup(time.tzset)
        self.addCleanup(patch.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.transcript = self.dir / "session.jsonl"

    def write(self, *entries, raw=""):
        self.transcript.write_text(raw + "".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
        return str(self.transcript)

    def unseen(self, text, *entries, **kwargs):
        return unseen_time.unseen([text], self.write(*entries), **kwargs)


class WhatIsATimeTests(unittest.TestCase):
    def test_hh_mm_in_range_is_a_time(self):
        self.assertEqual(unseen_time.times(["at 16:36 and 00:00, 23:59"]), ["16:36", "00:00", "23:59"])
        self.assertEqual(unseen_time.times(["24:00 25:10 12:60 1:30 9:05 7:5"]), [])

    def test_seconds_and_iso_forms_give_their_hh_mm(self):
        self.assertEqual(unseen_time.times(["16:36:44"]), ["16:36"])
        self.assertEqual(unseen_time.times(["2026-11-25T16:36:44Z"]), ["16:36"])

    def test_minutes_and_seconds_of_a_longer_time_are_not_a_time(self):
        self.assertEqual(unseen_time.times(["10:11:12 and 10:20:30:40:50:60"]), ["10:11"])
        self.assertEqual(unseen_time.times(["took 1:11:12, 99:11:12"]), [])  # h:mm:ss durations

    def test_repeats_are_dropped_and_the_count_is_bounded(self):
        self.assertEqual(unseen_time.times(["16:36 16:36 at 16:36"]), ["16:36"])
        many = " ".join(f"{hour:02d}:00" for hour in range(24))
        self.assertEqual(unseen_time.times([many]), [f"{hour:02d}:00" for hour in range(16)])

    def test_eta_clauses_are_exempt(self):
        for text in ("ETA 11-26 16:00", "eta 16:00", "ETA: 16:00", "ETA 2026-11-26 16:00", "ETA  11-26   16:00"):
            self.assertEqual(unseen_time.times([text]), [], text)

    def test_by_until_before_and_at_the_latest_are_exempt(self):
        for text in ("done by 17:00", "wait until 18:00", "Before 19:00 please", "at the latest 20:00",
                     "by 11-27 09:00", "UNTIL 2026-11-27 09:00"):
            self.assertEqual(unseen_time.times([text]), [], text)

    def test_a_day_word_or_tilde_may_stand_before_the_clause_time(self):
        for text in ("ETA Fri 09:00", "ETA ~09:00", "by Fri 18:00", "until ~18:00", "by tomorrow 09:00",
                     "ETA Friday 11-27 09:00", "before today 18:00"):
            self.assertEqual(unseen_time.times([text]), [], text)

    def test_ranges_and_durations_are_not_past_times(self):
        for text in ("hours 09:00-17:00", "22:00-06:00", "open 09:00 - 17:00", "09:00\u201317:00", "build took 02:15",
                     "elapsed: 01:30", "duration 00:45", "lasted 03:10"):
            self.assertEqual(unseen_time.times([text]), [], text)
        self.assertEqual(unseen_time.times(["merged 16:36, took 02:15"]), ["16:36"])

    def test_only_the_clause_time_is_exempt(self):
        self.assertEqual(unseen_time.times(["ETA 16:00, merged 16:36"]), ["16:36"])
        self.assertEqual(unseen_time.times(["by 17:00 but it ran at 16:36"]), ["16:36"])
        self.assertEqual(unseen_time.times(["the eta is slow, at 16:36"]), ["16:36"])
        self.assertEqual(unseen_time.times(["standby 16:36"]), ["16:36"])  # "by" inside a word is not the word

    def test_code_spans_fences_and_urls_are_exempt(self):
        self.assertEqual(unseen_time.times(["run `date 16:36` now"]), [])
        self.assertEqual(unseen_time.times(["```\nlog 16:36\n```\nthen 17:36"]), ["17:36"])
        self.assertEqual(unseen_time.times(["see https://example.com/a/16:36/b and http://x.io/17:36?q=1 at 18:36"]),
                         ["18:36"])

    def test_the_allow_list_drops_its_words(self):
        self.assertEqual(unseen_time.times(["16:36 17:36"], allow=["16:36"]), ["17:36"])
        self.assertEqual(unseen_time.times(["16:36"], allow=None), ["16:36"])

    def test_the_refusal_names_three_then_counts(self):
        self.assertEqual(unseen_time.named(["01:00", "02:00"]), "01:00, 02:00")
        self.assertEqual(unseen_time.named(["01:00", "02:00", "03:00", "04:00", "05:00"]),
                         "01:00, 02:00, 03:00 and 2 more")


class SeenTests(ZoneCase):
    def test_a_time_a_tool_printed_is_seen(self):
        self.assertEqual(self.unseen("merged at 16:36", tool_result("t1", "Wed Nov 26 16:36:44 UTC 2026")), [])

    def test_a_time_never_printed_is_unseen(self):
        self.assertEqual(self.unseen("merged at 16:36", tool_result("t1", "Wed Nov 26 16:37:44 UTC 2026")), ["16:36"])

    def test_the_assistants_own_text_and_inputs_do_not_count(self):
        entries = (assistant_text("it is 16:36"), tool_use("t1", "Bash", {"command": "echo 16:36"}),
                   {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "16:36"}]}})
        self.assertEqual(self.unseen("merged at 16:36", *entries), ["16:36"])

    def test_user_text_counts(self):
        self.assertEqual(self.unseen("at 16:36", user_text("the call is at 16:36")), [])

    def test_the_entrys_own_timestamp_field_does_not_count(self):
        self.assertEqual(self.unseen("at 09:09", assistant_text("hello")), ["09:09"])

    def test_the_minutes_and_seconds_of_a_longer_time_are_not_seen(self):
        self.assertEqual(self.unseen("at 11:12", tool_result("t1", "10:11:12")), ["11:12"])

    def test_a_utc_timestamp_counts_as_its_utc_and_its_local_time(self):
        printed = tool_result("t1", '{"mergedAt":"2026-11-25T16:36:44Z"}')
        self.assertEqual(self.unseen("merged 16:36", printed), [])
        self.assertEqual(self.unseen("merged 19:36", printed), [])  # the local zone is UTC+3
        self.assertEqual(self.unseen("merged 17:36", printed), ["17:36"])
        self.assertEqual(self.unseen("merged 13:36", printed), ["13:36"])

    def test_a_timestamp_with_an_offset_counts_as_written_utc_and_local(self):
        printed = tool_result("t1", "2026-11-25T19:36:44+03:00")
        for shown in ("19:36", "16:36"):
            self.assertEqual(self.unseen(f"at {shown}", printed), [], shown)
        self.assertEqual(self.unseen("at 22:36", printed), ["22:36"])
        self.assertEqual(self.unseen("at 18:36", tool_result("t1", "2026-11-25T18:36:44+02:00")), [])  # written

    def test_offset_spellings(self):
        for stamp in ("2026-11-25 19:36:44 +0300", "2026-11-25T19:36:44.123456+0300", "2026-11-25T19:36+03",
                      "2026-11-25T19:36:44+03:00"):
            self.assertEqual(self.unseen("at 16:36", tool_result("t1", stamp)), [], stamp)

    def test_the_machines_own_offset_stamp_counts_as_utc(self):
        # `date +%FT%T%z` prints the local time with its offset: the UTC reading of it is seen too
        self.assertEqual(self.unseen("at 16:36", tool_result("t1", "2026-11-25T19:36:44+0300")), [])

    def test_a_timestamp_without_a_zone_counts_as_written_only(self):
        printed = tool_result("t1", "2026-11-25T16:36:44")
        self.assertEqual(self.unseen("at 16:36", printed), [])
        self.assertEqual(self.unseen("at 19:36", printed), ["19:36"])

    def test_a_malformed_timestamp_is_ignored(self):
        self.assertEqual(self.unseen("at 16:36", tool_result("t1", "2026-13-45T16:36:44Z")), [])  # written time only
        self.assertEqual(self.unseen("at 19:36", tool_result("t1", "2026-13-45T16:36:44Z")), ["19:36"])

    def test_a_line_that_is_a_refusal_by_this_rule_shows_nothing(self):
        refusal = "arsenal lesson guard G015 (unseen-time): Time 16:36 appears in no tool output"
        self.assertEqual(self.unseen("at 16:36", tool_result("t1", refusal)), ["16:36"])

    def test_text_blocks_and_lists_in_a_tool_result_count(self):
        self.assertEqual(self.unseen("at 16:36", tool_result("t1", [{"type": "text", "text": "now 16:36"}])), [])

    def test_a_time_before_the_window_is_not_seen(self):
        path = self.write(tool_result("t1", "16:36"), tool_result("t2", "x" * 2_000_000))
        self.assertEqual(unseen_time.unseen(["at 16:36"], path, window_mb=1), ["16:36"])
        self.assertEqual(unseen_time.unseen(["at 16:36"], path), [])

    def test_a_call_without_a_time_reads_nothing(self):
        self.assertEqual(unseen_time.unseen(["no time here"], str(self.dir / "missing.jsonl")), [])

    def test_several_times_are_judged_each(self):
        printed = tool_result("t1", "16:36 and 2026-11-25T10:00:00Z")
        self.assertEqual(self.unseen("16:36 17:36 10:00 13:00 04:00", printed), ["17:36", "04:00"])


class DaylightSavingTests(ZoneCase):
    zone = NEW_YORK

    def test_the_local_reading_follows_the_stamps_own_date(self):
        summer = tool_result("t1", "2026-07-01T16:36:00Z")  # 12:36 in New York in July
        winter = tool_result("t2", "2026-12-01T16:36:00Z")  # 11:36 in December
        self.assertEqual(self.unseen("at 12:36", summer, winter), [])
        self.assertEqual(self.unseen("at 11:36", summer, winter), [])
        self.assertEqual(self.unseen("at 12:36", winter), ["12:36"])
        self.assertEqual(self.unseen("at 11:36", summer), ["11:36"])

    def test_a_negative_offset_counts_as_its_utc_time(self):
        self.assertEqual(self.unseen("at 16:36", tool_result("t1", "2026-12-01T11:36:44-05:00")), [])
        self.assertEqual(self.unseen("at 15:36", tool_result("t1", "2026-12-01T11:36:44-05:00")), ["15:36"])


class FailOpenTests(ZoneCase):
    def test_a_missing_unreadable_or_empty_transcript_passes(self):
        text = ["at 16:36"]
        self.assertEqual(unseen_time.unseen(text, None), [])
        self.assertEqual(unseen_time.unseen(text, ""), [])
        self.assertEqual(unseen_time.unseen(text, str(self.dir / "missing.jsonl")), [])
        self.assertEqual(unseen_time.unseen(text, str(self.dir)), [])  # a directory
        self.assertEqual(unseen_time.unseen(text, 5), [])

    def test_a_fifo_is_not_read(self):
        fifo = self.dir / "pipe"
        os.mkfifo(fifo)
        self.assertEqual(unseen_time.unseen(["at 16:36"], str(fifo)), [])

    def test_garbage_lines_are_skipped(self):
        path = self.write(tool_result("t1", "at 16:36"), raw="not json 16:36\n{broken\n")
        self.assertEqual(unseen_time.unseen(["at 17:36"], path), ["17:36"])
        self.assertEqual(unseen_time.unseen(["at 16:36"], path), [])

    def test_bad_texts_pass(self):
        path = self.write(tool_result("t1", "x"))
        self.assertEqual(unseen_time.unseen(None, path), [])
        self.assertEqual(unseen_time.unseen([None, 5], path), [])

    def test_a_timeout_before_any_time_was_judged_unseen_passes(self):
        path = self.write(tool_result("t1", "16:36"))
        ticks = itertools.count()
        self.assertEqual(unseen_time.unseen(["at 16:36"], path, clock=lambda: next(ticks) * 10, budget=0.2), [])

    def test_times_judged_before_the_budget_ran_out_are_still_refused(self):
        # 17:36 is printed nowhere (judged by the cheap absence search); 16:36 sits on a line that must be parsed
        path = self.write(tool_result("t1", "16:36"))
        ticks = itertools.count()
        clock = lambda: 0 if next(ticks) < 2 else 99  # noqa: E731
        self.assertEqual(unseen_time.unseen(["at 17:36 and 16:36"], path, clock=clock, budget=0.2), ["17:36"])

    def test_an_error_inside_the_check_passes(self):
        path = self.write(tool_result("t1", "x"))
        with mock.patch.object(unseen_time, "read_tail", side_effect=RuntimeError("boom")):
            self.assertEqual(unseen_time.unseen(["at 16:36"], path), [])

    def test_a_wild_window_uses_the_default(self):
        path = self.write(tool_result("t1", "16:36"))
        for window in (0, -1, 10_000, True, "x", float("nan")):
            self.assertEqual(unseen_time.unseen(["at 16:36"], path, window_mb=window), [], window)


class SubagentTests(ZoneCase):
    def test_a_subagent_is_judged_on_its_own_transcript(self):
        session = self.write(tool_result("t1", "16:36"))
        agent = self.dir / "session" / "subagents" / "agent-a9.jsonl"
        agent.parent.mkdir(parents=True)
        agent.write_text(json.dumps(tool_result("t1", "17:36")) + "\n", encoding="utf-8")
        self.assertEqual(unseen_time.unseen(["at 17:36"], session, agent_id="a9"), [])
        self.assertEqual(unseen_time.unseen(["at 16:36"], session, agent_id="a9"), ["16:36"])
        self.assertEqual(unseen_time.unseen(["at 16:36"], session, agent_id="missing"), [])  # not found: passes


class RuleCase(ZoneCase):
    ENTRY = {"rule": "unseen-time", "lesson": "G015", "min_version": "1.33.5"}

    def setUp(self):
        super().setUp()
        self.project = self.dir / "project"
        self.project.mkdir()
        env = {"LESSONS_GUARDS_GLOBAL_FILE": str(self.dir / "home" / "lesson-guards.json"),
               "LESSONS_GUARD_HITS_FILE": str(self.dir / "home" / "hits.jsonl")}
        for patch in (mock.patch.dict(os.environ, env), mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 33, 5))):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.path = self.write(tool_result("t1", "Wed Nov 26 16:36:44 UTC 2026"), tool_result("t2", '"mergedAt":"2026-11-25T16:36:44Z"'))

    def registry(self, *guards):
        path = self.project / ".agents" / "lesson-guards.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"guards": list(guards)}), encoding="utf-8")


class RuleTests(RuleCase):
    def judge(self, command):
        return guard_lessons.judge(command, str(self.project), transcript=self.path)

    def test_off_until_a_registry_entry_names_it(self):
        self.assertIsNone(self.judge('gh pr comment 5 -b "merged at 17:36"'))

    def test_off_below_its_min_version(self):
        self.registry({**self.ENTRY, "min_version": "1.33.6"})
        self.assertIsNone(self.judge('gh pr comment 5 -b "merged at 17:36"'))

    def test_an_unseen_time_is_refused_with_what_to_do(self):
        self.registry(self.ENTRY)
        hit = self.judge('gh pr comment 5 -b "merged at 16:36, then 17:36"')
        self.assertEqual((hit.lesson, hit.rule), ("G015", "unseen-time"))
        self.assertIn("17:36", hit.reason)
        self.assertNotIn("16:36", hit.reason)
        self.assertIn("date +%H:%M", hit.reason)
        self.assertIn("timestamp", hit.reason)

    def test_a_seen_time_passes(self):
        self.registry(self.ENTRY)
        self.assertIsNone(self.judge('gh pr comment 5 -b "merged at 16:36"'))
        self.assertIsNone(self.judge('gh pr comment 5 -b "merged at 19:36"'))  # the local reading of 16:36 UTC

    def test_exempt_clauses_pass(self):
        self.registry(self.ENTRY)
        for body in ("ETA 11-27 17:36", "ETA 17:36", "done by 17:36", "until 17:36", "at the latest 17:36",
                     "see https://x.io/17:36"):
            self.assertIsNone(self.judge(f"gh pr comment 5 -b '{body}'"), body)

    def test_a_code_span_in_an_mcp_text_is_exempt(self):
        self.registry(self.ENTRY)
        self.assertIsNone(guard_lessons.judge_outbound("mcp__chat__send_message", {"text": "run `date 17:36`"},
                                                       str(self.project), transcript=self.path))

    def test_only_the_message_of_a_commit_is_judged(self):
        self.registry(self.ENTRY)
        self.assertEqual(self.judge('git commit -m "fix at 17:36"').rule, "unseen-time")
        self.assertEqual(self.judge("git commit -F - <<'EOF'\nfix at 17:36\nEOF").rule, "unseen-time")
        self.assertIsNone(self.judge('git commit --author "A 17:36 <a@b.c>" -m "fix"'))
        self.assertIsNone(self.judge("git log --since 17:36"))

    def test_programs_are_judged_and_other_commands_are_not(self):
        self.registry({**self.ENTRY, "programs": ["send.sh"]})
        self.assertEqual(self.judge('./send.sh team "merged at 17:36"').rule, "unseen-time")
        self.assertIsNone(self.judge('echo "17:36"'))
        self.assertIsNone(self.judge('./other.sh team "17:36"'))

    def test_the_allow_list_is_honoured(self):
        self.registry({**self.ENTRY, "allow": ["17:36"]})
        self.assertIsNone(self.judge('gh pr comment 5 -b "17:36"'))
        self.assertEqual(self.judge('gh pr comment 5 -b "17:37"').rule, "unseen-time")

    def test_a_custom_reason_replaces_the_built_in_one(self):
        self.registry({**self.ENTRY, "reason": "copy it"})
        self.assertEqual(self.judge('gh pr comment 5 -b "17:36"').reason, "copy it")

    def test_without_a_transcript_the_call_passes(self):
        self.registry(self.ENTRY)
        self.assertIsNone(guard_lessons.judge('gh pr comment 5 -b "17:36"', str(self.project)))

    def test_outbound_mcp_and_send_message_calls_are_judged(self):
        self.registry(self.ENTRY)
        out = guard_lessons.judge_outbound("mcp__chat__send_message", {"text": "merged at 17:36"}, str(self.project),
                                           transcript=self.path)
        self.assertEqual(out.rule, "unseen-time")
        out = guard_lessons.judge_outbound("SendMessage", {"to": "pm", "message": "at 17:36"}, str(self.project),
                                           transcript=self.path)
        self.assertEqual(out.rule, "unseen-time")
        self.assertIsNone(guard_lessons.judge_outbound("mcp__chat__send_message", {"text": "at 16:36"},
                                                       str(self.project), transcript=self.path))
        self.assertIsNone(guard_lessons.judge_outbound("mcp__chat__get_message", {"text": "at 17:36"},
                                                       str(self.project), transcript=self.path))


class RegistryTests(RuleCase):
    def problems(self, entry):
        self.registry(entry)
        return guard_lessons.registry_problems(str(self.project))

    def test_a_valid_entry_has_no_problem(self):
        self.assertEqual(self.problems(self.ENTRY), [])
        self.assertEqual(self.problems({**self.ENTRY, "programs": ["send.sh"], "allow": ["10:00"], "window_mb": 4}), [])

    def test_bad_allow_and_window_are_problems(self):
        for allow in ("10:00", [], [""], [1]):
            self.assertTrue(self.problems({**self.ENTRY, "allow": allow}), allow)
        for window in (0, -1, 17, True, "4"):
            self.assertTrue(self.problems({**self.ENTRY, "window_mb": window}), window)

    def test_allow_and_window_stay_refused_for_other_rules(self):
        self.assertTrue(self.problems({"rule": "help-probe", "allow": ["a"]}))
        self.assertTrue(self.problems({"rule": "help-probe", "window_mb": 4}))


if __name__ == "__main__":
    unittest.main()
