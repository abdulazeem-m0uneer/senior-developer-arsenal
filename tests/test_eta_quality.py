"""Tests for ETA quality on the session bus: overdue.py --suggest and the re-date cause rule of send_check.py."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUS_SRC = ROOT / ".agents" / "skills" / "multi-session-delivery" / "templates" / "bus"
NOW = "2026-11-18T16:00:00"  # a Wednesday


class BusCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.bus = Path(directory.name)
        for name in ("send.sh", "send_check.py", "overdue.py", "lock.sh", "lanes.txt"):
            shutil.copy(BUS_SRC / name, self.bus / name)
        (self.bus / "lanes.txt").write_text("qa\nweb\n", encoding="utf-8")
        self.items = self.bus / "open-items.tsv"

    @staticmethod
    def env(now):
        env = {key: value for key, value in os.environ.items() if not key.startswith("BUS_")}
        return {**env, "BUS_NOW": now, "BUS_LOCK_TRIES": "3"}

    def record(self, sent, sender, key, eta, text="x"):
        with self.items.open("a", encoding="utf-8") as out:
            out.write("\t".join([sent, sender, key, eta, text]) + "\n")

    def finished(self, sender, key, eta, closed):
        """One START whose first ETA is `eta` (YYYY-MM-DD HH:MM) and its DONE at `closed` (ISO)."""
        self.record("2026-11-01T08:00:00", sender, key, eta, "START " + key)
        self.record(closed, sender, key, "DONE", "DONE " + key + " proof")

    def send(self, line, sender="qa", now=NOW):
        done = subprocess.run(["bash", str(self.bus / "send.sh"), "pm", sender, line], capture_output=True,
                              text=True, check=False, env=self.env(now))
        return done.returncode, done.stderr


class SuggestTests(BusCase):
    def setUp(self):
        super().setUp()
        # qa: lateness 10, 50, 30 min and one early finish (counts 0): sorted 0, 10, 30, 50, lower median 10
        self.finished("qa", "a1", "2026-11-10 10:00", "2026-11-10T10:10:00")
        self.finished("qa", "a2", "2026-11-11 10:00", "2026-11-11T10:50:00")
        self.finished("qa", "a3", "2026-11-12 10:00", "2026-11-12T10:30:00")
        self.finished("qa", "a4", "2026-11-13 10:00", "2026-11-13T09:30:00")

    def suggest(self, sender, estimate, *extra, now=NOW, env_extra=None):
        done = subprocess.run([sys.executable, "-I", str(self.bus / "overdue.py"), "--suggest", sender,
                               "--estimate", estimate, *extra], capture_output=True, text=True, check=False,
                              env={**self.env(now), "BUS_OPEN_ITEMS": str(self.items), **(env_extra or {})})
        return done.returncode, done.stdout.strip().splitlines(), done.stderr

    def test_adds_median_lateness_and_names_the_derivation(self):
        rc, out, _ = self.suggest("qa", "2h")
        self.assertEqual((rc, out), (0, ["ETA 11-18 18:15",
                                         "estimate 2h + median lateness 10 min over 4 finished items (3 late)"]))

    def test_rounds_up_to_the_next_quarter_hour(self):
        # 16:07 + 90 min + 10 min = 17:47 -> 18:00
        self.assertEqual(self.suggest("qa", "90m", now="2026-11-18T16:07:00")[1][0], "ETA 11-18 18:00")
        # 15:30:30 + 90 + 10 min = 17:10:30, 30 s past the quarter -> 17:15
        self.assertEqual(self.suggest("qa", "90m", now="2026-11-18T15:30:30")[1][0], "ETA 11-18 17:15")

    def test_crosses_midnight_month_and_year_end(self):
        self.assertEqual(self.suggest("qa", "2h", now="2026-12-31T22:10:00")[1][0], "ETA 01-01 00:30")
        self.assertEqual(self.suggest("qa", "1h", now="2026-11-30T23:00:00")[1][0], "ETA 12-01 00:15")
        self.assertEqual(self.suggest("qa", "1d", now="2026-11-18T16:00:00")[1][0], "ETA 11-19 16:15")

    def test_too_little_history_suggests_the_estimate_only(self):
        rc, out, _ = self.suggest("qa", "2h", "--min-history", "5")
        self.assertEqual((rc, out), (0, ["ETA 11-18 18:00",
                                         "estimate 2h only: 4 finished items, 5 needed (--min-history)"]))

    def test_min_history_defaults_to_three(self):
        self.finished("web", "w1", "2026-11-10 10:00", "2026-11-10T12:00:00")
        self.finished("web", "w2", "2026-11-11 10:00", "2026-11-11T12:00:00")
        out = self.suggest("web", "1h")[1]
        self.assertEqual(out, ["ETA 11-18 17:00", "estimate 1h only: 2 finished items, 3 needed (--min-history)"])

    def test_unknown_sender_gets_the_estimate_only(self):
        rc, out, _ = self.suggest("ghost", "2h")
        self.assertEqual((rc, out), (0, ["ETA 11-18 18:00", "estimate 2h only: no finished items from ghost"]))

    def test_sender_name_is_read_in_lower_case(self):
        self.assertEqual(self.suggest("QA", "2h")[1][0], "ETA 11-18 18:15")

    def test_early_finishes_never_shorten_the_estimate(self):
        for number in range(3):
            self.finished("fast", f"f{number}", "2026-11-10 10:00", "2026-11-10T08:00:00")
        rc, out, _ = self.suggest("fast", "2h")
        self.assertEqual((rc, out), (0, ["ETA 11-18 18:00",
                                         "estimate 2h + median lateness 0 min over 3 finished items (0 late)"]))

    def test_one_big_miss_among_eleven_adds_nothing(self):
        for number in range(10):
            self.finished("steady", f"s{number}", "2026-11-10 10:00", "2026-11-10T09:50:00")
        self.finished("steady", "s10", "2026-11-11 10:00", "2026-11-11T13:00:00")  # 180 min late
        rc, out, _ = self.suggest("steady", "2h")
        self.assertEqual((rc, out), (0, ["ETA 11-18 18:00",
                                         "estimate 2h + median lateness 0 min over 11 finished items (1 late)"]))

    def test_median_of_zero_thirty_and_ninety_is_thirty(self):
        for number, closed in enumerate(("10:00", "10:30", "11:30")):
            self.finished("trio", f"t{number}", "2026-11-10 10:00", f"2026-11-10T{closed}:00")
        rc, out, _ = self.suggest("trio", "2h")
        self.assertEqual((rc, out), (0, ["ETA 11-18 18:30",
                                         "estimate 2h + median lateness 30 min over 3 finished items (2 late)"]))

    def test_seconds_late_round_up_to_one_minute(self):
        for number in range(3):
            self.finished("tick", f"k{number}", "2026-11-10 10:00", "2026-11-10T10:00:30")
        out = self.suggest("tick", "2h", now="2026-11-18T16:00:00")[1]
        self.assertEqual(out, ["ETA 11-18 18:15",
                               "estimate 2h + median lateness 1 min over 3 finished items (3 late)"])

    def test_item_with_unreadable_first_eta_is_left_out(self):
        self.finished("odd", "o1", "whenever", "2026-11-10T12:00:00")
        self.assertEqual(self.suggest("odd", "1h")[1], ["ETA 11-18 17:00", "estimate 1h only: no finished items from odd"])

    def test_json_form(self):
        rc, out, _ = self.suggest("qa", "2h", "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads("\n".join(out)), {
            "sender": "qa", "eta": "2026-11-18 18:15", "eta_text": "ETA 11-18 18:15", "estimate_min": 120,
            "median_late_min": 10, "finished": 4, "late": 3, "min_history": 3, "basis": "history",
            "derivation": "estimate 2h + median lateness 10 min over 4 finished items (3 late)"})

    def test_json_form_without_history(self):
        data = json.loads(self.suggest("ghost", "30m", "--json")[1][0])
        self.assertEqual((data["basis"], data["median_late_min"], data["finished"], data["eta"]),
                         ("estimate-only", 0, 0, "2026-11-18 16:30"))

    def test_bad_estimate_is_a_usage_error(self):
        for bad in ("soon", "0m", "-5m", "2"):
            rc, out, err = self.suggest("qa", bad)
            self.assertEqual((rc, out), (2, []), bad)
            self.assertIn("estimate", err)

    def test_estimate_beyond_the_eta_horizon_is_a_usage_error(self):
        self.assertEqual(self.suggest("qa", "89d")[0], 0)
        for text in ("91d", "99999999999d", "2200000h"):
            rc, out, err = self.suggest("qa", text)
            self.assertEqual((rc, out), (2, []), text)
            self.assertIn("90 days", err)

    def test_horizon_follows_bus_eta_max_days(self):
        self.assertEqual(self.suggest("qa", "9d", env_extra={"BUS_ETA_MAX_DAYS": "10"})[0], 0)
        rc, _, err = self.suggest("qa", "11d", env_extra={"BUS_ETA_MAX_DAYS": "10"})
        self.assertEqual(rc, 2)
        self.assertIn("10 days", err)

    def test_the_suggested_eta_itself_stays_inside_the_horizon(self):
        # qa's median lateness is 10 min: a 90-day estimate plus it lands past 90 days, which send_check refuses
        rc, out, err = self.suggest("qa", "90d")
        self.assertEqual((rc, out), (2, []))
        self.assertIn("suggested ETA", err)
        self.assertIn("90 days", err)

    def test_a_suggested_eta_is_accepted_by_the_bus(self):
        rc, out, _ = self.suggest("qa", "89d")
        self.assertEqual(rc, 0)
        eta_text = next(line for line in out if line.startswith("ETA "))
        self.assertEqual(self.send(f"START far-1 long job - {eta_text}"), (0, ""))

    def test_unusable_bus_eta_max_days_falls_back_to_ninety(self):
        for value in ("0", "abc", "36501", "-3"):
            rc, _, err = self.suggest("qa", "91d", env_extra={"BUS_ETA_MAX_DAYS": value})
            self.assertEqual(rc, 2, value)
            self.assertIn("90 days", err)

    def test_date_overflow_is_a_usage_error_not_a_crash(self):
        rc, out, err = self.suggest("qa", "36500d", now="9999-12-31T00:00:00+00:00",
                                    env_extra={"BUS_ETA_MAX_DAYS": "36500"})
        self.assertEqual((rc, out), (2, []))
        self.assertIn("estimate", err)

    def test_estimate_is_required_with_suggest(self):
        done = subprocess.run([sys.executable, "-I", str(self.bus / "overdue.py"), "--suggest", "qa"],
                               capture_output=True, text=True, check=False, env=self.env(NOW))
        self.assertEqual(done.returncode, 2)

    def test_suggestion_is_accepted_by_send_check(self):
        eta = self.suggest("qa", "2h")[1][0]
        rc, err = self.send(f"START t-1 thing - {eta}")
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(self.items.read_text().splitlines()[-1].split("\t")[3], "2026-11-18 18:15")


class RedateCauseTests(BusCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.send("START t-1 build - ETA 17:00"), (0, ""))

    def refused(self, line, **kwargs):
        rc, err = self.send(line, **kwargs)
        self.assertEqual(rc, 7, f"{line!r}: {err}")
        self.assertIn("cause", err)

    def test_later_eta_without_cause_is_refused(self):
        self.refused("START t-1 build - ETA 19:00")
        self.assertEqual(len(self.items.read_text().splitlines()), 1)

    def test_refusal_is_logged_and_not_delivered(self):
        self.refused("START t-1 build - ETA 19:00")
        self.assertIn('"outcome":"refused-redate"', (self.bus / "events.jsonl").read_text())
        self.assertFalse((self.bus / "inbox-pm.md").read_text().count("19:00"))

    def test_a_blocker_never_loads_overdue(self):
        # a BLOCKER cannot be refused by the re-date rule, so it must not pay for reading open-items.tsv
        (self.bus / "overdue.py").write_text("raise SystemExit(9)\n", encoding="utf-8")
        self.assertEqual(self.send("START t-9 work - ETA 18:00")[0] in (0,), True)
        self.assertEqual(self.send("BLOCKER t-9 ci red - lead - ETA 19:00"), (0, ""))

    def test_blocker_with_later_eta_needs_no_cause(self):
        # a BLOCKER line already carries its exact cause
        self.assertEqual(self.send("BLOCKER t-1 ci red - lead - ETA 19:00"), (0, ""))
        self.assertEqual(self.items.read_text().splitlines()[-1].split("\t")[3], "2026-11-18 19:00")

    def test_start_after_a_blocker_still_needs_a_cause(self):
        self.assertEqual(self.send("BLOCKER t-1 ci red - lead - ETA 18:00"), (0, ""))
        self.refused("START t-1 build - ETA 19:00")

    def test_because_with_three_words_is_accepted(self):
        self.assertEqual(self.send("START t-1 build - because CI was red - ETA 19:00"), (0, ""))
        self.assertEqual(self.items.read_text().splitlines()[-1].split("\t")[3], "2026-11-18 19:00")

    def test_cause_colon_form_is_accepted(self):
        self.assertEqual(self.send("START t-1 build - cause: review found a race - ETA 19:00"), (0, ""))

    def test_cause_after_the_eta_is_accepted(self):
        self.assertEqual(self.send("START t-1 build - ETA 19:00 because CI was red"), (0, ""))

    def test_cause_too_short_is_refused(self):
        self.refused("START t-1 build - because CI red - ETA 19:00")
        self.refused("START t-1 build - because - ETA 19:00")

    def test_eta_words_do_not_count_as_cause(self):
        self.refused("START t-1 build because - ETA 19:00")

    def test_eta_clause_right_after_the_marker_is_not_a_cause(self):
        self.refused("START t-1 build because CI red ETA 19:00")

    def test_dash_inside_a_cause_does_not_break_the_count(self):
        self.assertEqual(self.send("START t-1 build - because CI - again - failed - ETA 19:00"), (0, ""))

    def test_cause_words_must_follow_the_marker(self):
        self.refused("START t-1 the old build was red for a while - ETA 19:00")

    def test_earlier_or_equal_eta_needs_no_cause(self):
        self.assertEqual(self.send("START t-1 build - ETA 16:30"), (0, ""))
        self.assertEqual(self.send("START t-1 build - ETA 16:30"), (0, ""))

    def test_first_start_needs_no_cause(self):
        self.assertEqual(self.send("START t-2 other - ETA 23:00"), (0, ""))

    def test_same_key_of_another_sender_is_not_a_redate(self):
        self.assertEqual(self.send("START t-1 build - ETA 19:00", sender="web"), (0, ""))

    def test_key_compares_in_lower_case(self):
        self.refused("START T-1 build - ETA 19:00")

    def test_closed_then_reopened_is_not_a_redate(self):
        self.assertEqual(self.send("DONE t-1 merged abc"), (0, ""))
        self.assertEqual(self.send("START t-1 again - ETA 23:00"), (0, ""))

    def test_reopened_item_is_compared_with_its_new_eta(self):
        self.assertEqual(self.send("DONE t-1 merged abc"), (0, ""))
        self.assertEqual(self.send("START t-1 again - ETA 18:00"), (0, ""))
        self.refused("START t-1 again - ETA 19:00")

    def test_date_form_eta_is_compared_by_instant(self):
        self.refused("START t-1 build - ETA 11-19 09:00")

    def test_missing_items_file_does_not_refuse(self):
        self.items.unlink()
        rc, err = self.send("START t-1 build - ETA 19:00")
        self.assertEqual(rc, 0, err)

    def test_garbled_items_file_does_not_refuse(self):
        self.items.write_bytes(b"\xff\xfe garbage\n\x00\n\tonly\ttabs\n")
        rc, err = self.send("START t-1 build - ETA 19:00")
        self.assertEqual(rc, 0, err)

    def test_unreadable_items_file_does_not_refuse_and_says_so(self):
        self.items.unlink()
        self.items.mkdir()  # reading a directory raises OSError
        rc, err = self.send("START t-1 build - ETA 19:00")
        self.assertEqual(rc, 0, err)
        self.assertIn("open-items.tsv", err)

    def test_missing_overdue_py_does_not_refuse(self):
        (self.bus / "overdue.py").unlink()
        rc, err = self.send("START t-1 build - ETA 19:00")
        self.assertEqual(rc, 0, err)
        self.assertIn("re-date", err)

    def test_unreadable_open_eta_does_not_refuse(self):
        self.items.write_text("2026-11-18T15:00:00\tqa\tt-1\tsoonish\tSTART t-1 x\n", encoding="utf-8")
        rc, err = self.send("START t-1 build - ETA 19:00")
        self.assertEqual(rc, 0, err)


if __name__ == "__main__":
    unittest.main()
