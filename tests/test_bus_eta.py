"""Tests for the session bus ETA rules: send_check.py, send.sh records and events, and overdue.py reports."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".agents" / "skills" / "multi-session-delivery"


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
        (self.bus / "send_check.py").write_text("raise RuntimeError('broken check')\n")  # a crash: exit 1
        self.assertIn("line sent unchecked", self.assert_sent("START T-1 build the page"))
        self.assertEqual(len(self.inbox_lines()), 1)
        self.assertFalse(self.items.exists())

    def test_any_refusal_code_from_the_check_refuses_the_line(self):
        # a code in send_check's refusal range that send.sh has no name for is still a refusal, never "unchecked"
        (self.bus / "send_check.py").write_text("import sys\nprint('refused: a new rule', file=sys.stderr)\nsys.exit(9)\n")
        done = subprocess.run(["bash", str(self.bus / "send.sh"), "pm", "backend", "START T-1 x ETA 11-19 10:00"],
                              capture_output=True, text=True, env=self.base_env())
        self.assertEqual(done.returncode, 9, done.stderr)
        self.assertNotIn("sent unchecked", done.stderr)
        self.assertEqual(self.inbox_lines(), [])
        self.assertEqual([e["outcome"] for e in self.events()], ["refused-9"])

    def test_refusal_codes_are_one_list(self):
        import re
        bus = SKILL / "templates" / "bus"
        check = (bus / "send_check.py").read_text(encoding="utf-8")
        send = (bus / "send.sh").read_text(encoding="utf-8")
        raised = {int(code) for code in re.findall(r"Refused\((\d+)", check)}
        documented = {int(code) for code in re.findall(r"^exit (\d+) ", check, re.M)} - {0, 2}
        self.assertEqual(raised, documented)  # every code raised is in the header, and only those
        low, high = (int(n) for n in re.search(r"REFUSAL_LOW=(\d+); REFUSAL_HIGH=(\d+)", send).groups())
        self.assertTrue(all(low <= code <= high for code in raised), (raised, low, high))
        header = re.search(r"^# exit 0 sent;(.*)$", send, re.M).group(1)
        self.assertTrue(all(re.search(rf"\b{code}\b", header) for code in raised), header)

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
        self.assert_sent("BLOCKER: #740: rebase conflict again ETA: 11-19 9:00 because the plan changed")  # a re-date
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
            self.assert_sent(f"START R-1 x ETA {eta} because the plan changed")
        _, out, _ = self.overdue("2026-11-18T17:30:00", "--all")
        self.assertIn("re-dated 2x | ESCALATE", out)  # two re-dates escalate even inside the ETA
        self.assert_sent("START R-2 x ETA 11-18 17:00")
        _, out, _ = self.overdue("2026-11-18T17:30:00")
        self.assertIn("OVERDUE r-2 | owner backend | ETA 2026-11-18 17:00 | open 1.5h | past first ETA 0.5h | "
                      "re-dated 0x | START", out)
        _, out, _ = self.overdue("2026-11-18T17:30:00", "--escalate-hours", "0.5")
        self.assertIn("past first ETA 0.5h | re-dated 0x | ESCALATE", out)  # the bound is inclusive
        _, out, _ = self.overdue("2026-11-18T17:30:00", "--escalate-hours", "1")
        self.assertNotIn("r-2 | owner backend | ETA 2026-11-18 17:00 | open 1.5h | past first ETA 0.5h | re-dated 0x"
                         " | ESCALATE", out)  # 1.5 h open but only 0.5 h past the promise
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
        self.assert_sent("START K-2 later - ETA 11-19 11:00 because the plan changed")
        self.assert_sent("START K-2 later again - ETA 11-19 12:00 because the plan changed")
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
        self.assert_sent("START H-1 later ETA 11-19 11:00 because the plan changed", now="2026-11-18T20:00:00")
        self.assertIn("open 19.0h", self.overdue("2026-11-19T11:00:00", "--all")[1])
        self.assertEqual(self.overdue("2026-11-19T11:00:00")[1], "none")  # at the ETA minute: not yet late
        self.assertIn("OVERDUE h-1", self.overdue("2026-11-19T11:01:00")[1])
        self.assert_sent("START E-1 x ETA 11-18 18:00")
        self.assertIn("open 6.0h | past first ETA 4.0h | re-dated 0x | ESCALATE", self.overdue("2026-11-18T22:00:00")[1])
        self.assertNotIn("ESCALATE", self.overdue("2026-11-18T21:59:00")[1].split("\n")[0])

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
            "open past first ETA 0",
            "UNREADABLE first ETA 1 | web 1"])  # w2's unreadable first ETA is left out, and counted
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
            "open past first ETA 0",
            "UNREADABLE first ETA 1 | mm 1"])

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
        (self.bus / "send_check.py").write_text("raise RuntimeError('broken check')\n")  # a crash: exit 1
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
        (self.bus / "send_check.py").write_text("raise RuntimeError('broken check')\n")  # a crash: exit 1
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

    def test_bus_now_stamps_every_line_so_tests_never_depend_on_the_real_clock(self):
        def send(now, line="START C-1 x ETA 11-19 10:00"):
            env = {**self.base_env(), "TZ": "Asia/Riyadh", "BUS_LOCK_TRIES": "3"}  # UTC+3, no daylight saving
            if now:
                env["BUS_NOW"] = now
            return subprocess.run(["bash", str(self.bus / "send.sh"), "pm", "backend", line], capture_output=True,
                                  text=True, env=env)
        self.assertEqual(send("2026-11-18T16:00:00").returncode, 0)  # local time, read in Riyadh
        self.assertEqual(self.events()[-1]["time"], "2026-11-18T13:00:00Z")
        self.assertTrue(self.inbox_lines()[-1].startswith("2026-11-18T13:00:00Z | from backend |"))
        self.assertEqual(send("2026-11-18T16:00:00+05:00").returncode, 0)  # an explicit offset wins
        self.assertEqual(self.events()[-1]["time"], "2026-11-18T11:00:00Z")
        bad = send("not-a-time")
        self.assertEqual(bad.returncode, 6)  # send_check.py refuses the clock
        self.assertIn("BUS_NOW", bad.stderr)
        self.assertEqual(self.events()[-1]["outcome"], "refused-eta")
        self.assert_real_clock(self.events()[-1]["time"])
        self.assertEqual(send(None, "plain note").returncode, 0)
        self.assert_real_clock(self.events()[-1]["time"])

    def assert_real_clock(self, stamp):
        written = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        self.assertLess(abs((datetime.now(timezone.utc) - written).total_seconds()), 60, stamp)

    def test_escalation_counts_hours_past_the_first_eta(self):
        # P-1: one re-date into the future, but its first promise (11:00) is now 5 h past
        self.assert_sent("START P-1 x ETA 11-18 11:00", now="2026-11-18T10:00:00")
        self.assert_sent("START P-1 moved ETA 11-18 20:00 because the plan changed", now="2026-11-18T12:00:00")  # re-dated 1x, into the future
        self.assert_sent("START P-2 fresh ETA 11-18 22:00", now="2026-11-18T10:00:00")  # open long, promise still ahead
        self.assert_sent("START P-3 x ETA 11-18 15:50", now="2026-11-18T10:00:00")  # late, but only 10 min past
        rows = {row.split(" | ")[0]: row for row in self.overdue("2026-11-18T16:00:00", "--all")[1].splitlines()}
        self.assertIn("| past first ETA 5.0h | re-dated 1x | ESCALATE |", rows["open p-1"])
        self.assertIn("| past first ETA 0.0h | re-dated 0x | START P-2", rows["open p-2"])
        self.assertIn("| past first ETA 0.2h | re-dated 0x | START P-3", rows["OVERDUE p-3"])
        self.assertIn("past first ETA 4.0h | re-dated 0x | ESCALATE",
                      self.overdue("2026-11-18T19:50:00")[1])  # P-3 exactly 4 h past its first ETA

    def test_an_unreadable_first_eta_escalates_by_hours_open(self):
        self.items.write_text("2026-11-18T10:00:00\tb\tk1\tgarbage\tSTART k1 damaged\n", encoding="utf-8")
        self.assertIn("open 6.0h | past first ETA 6.0h | re-dated 0x | ESCALATE",
                      self.overdue("2026-11-18T16:00:00")[1])
        self.assertNotIn("ESCALATE", self.overdue("2026-11-18T13:00:00")[1])  # 3 h open: not yet

    # short ETA forms written by hand ("MM-DD HH:MM", "HH:MM"), read against each record's send time
    def write_items(self, *records):
        self.items.write_text("".join(f"{record}\n" for record in records), encoding="utf-8")

    def test_short_form_etas_are_listed_by_their_resolved_time(self):
        self.write_items("2026-11-18T09:00:00\tqa\ts1\t11-19 14:30\tSTART s1",
                         "2026-11-18T09:00:00\tqa\ts2\t10:00\tSTART s2",
                         "2026-11-18T15:00:00\tqa\ts3\t09:30\tSTART s3 past at send: tomorrow")
        code, out, err = self.overdue(self.NOW, "--all")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), [
            "OVERDUE s2 | owner qa | ETA 10:00 | open 7.0h | past first ETA 6.0h | re-dated 0x | ESCALATE | START s2",
            "open s3 | owner qa | ETA 09:30 | open 1.0h | past first ETA 0.0h | re-dated 0x | "
            "START s3 past at send: tomorrow",
            "open s1 | owner qa | ETA 11-19 14:30 | open 7.0h | past first ETA 0.0h | re-dated 0x | START s1"])
        self.assertEqual(self.overdue(self.NOW)[1].split(" | ")[0], "OVERDUE s2")  # only s2 is late

    def test_a_redate_compares_short_and_full_forms_by_their_resolved_time(self):
        self.write_items(
            "2026-11-18T09:00:00\tqa\tr1\t11-18 12:00\tSTART r1",
            "2026-11-18T10:00:00\tqa\tr1\t2026-11-18 12:00\tSTART r1 same time, full form: no re-date",
            "2026-11-18T11:00:00\tqa\tr1\t13:00\tSTART r1 later: re-date",
            "2026-11-18T11:30:00\tqa\tr1\t2026-11-18 12:30\tSTART r1 earlier: no re-date",
            "2026-11-18T14:00:00\tqa\tr1\tDONE\tDONE r1 x",
            "2026-11-18T09:00:00\tqa\tr2\t2026-11-18 13:00\tSTART r2",
            "2026-11-18T13:30:00\tqa\tr2\t13:00\tSTART r2 13:00 is past at send, so tomorrow: re-date",
            "2026-11-18T15:00:00\tqa\tr2\tDONE\tDONE r2 x")
        self.assertEqual(self.overdue(self.NOW, "--accuracy")[1].splitlines(), [
            "ACCURACY qa | finished 2 | on first ETA 0 of 2 (0%) | median late 120 min | re-dated 2x | "
            "open past first ETA 0"])  # both 2 h past their first ETAs (12:00 and 13:00)

    def test_the_previous_eta_keeps_the_send_time_it_was_written_at(self):
        self.write_items("2026-11-18T09:00:00\tqa\tp1\t13:00\tSTART p1 today 13:00",
                         "2026-11-18T14:00:00\tqa\tp1\t2026-11-18 15:00\tSTART p1 later than 13:00: re-date")
        self.assertIn("| re-dated 1x |", self.overdue(self.NOW)[1])  # not 13:00 re-read at 14:00 as tomorrow

    def test_a_readable_eta_after_an_unreadable_one_counts_as_a_redate(self):
        # an unreadable earlier ETA counts as the earliest, so any readable new ETA is later
        self.write_items("2026-11-18T09:00:00\tqa\tu1\tsoon\tSTART u1",
                         "2026-11-18T10:00:00\tqa\tu1\t11-19 14:30\tSTART u1 dated",
                         "2026-11-18T09:00:00\tqa\tu2\t13-40 10:00\tSTART u2",
                         "2026-11-18T10:00:00\tqa\tu2\t2026-11-18 12:00\tSTART u2 dated",
                         "2026-11-18T13:00:00\tqa\tu2\tDONE\tDONE u2 x")
        self.assertEqual(self.overdue(self.NOW, "--all", "--escalate-hours", "100", "--escalate-redates", "1"), (
            0, "open u1 | owner qa | ETA 11-19 14:30 | open 7.0h | past first ETA 7.0h | re-dated 1x | ESCALATE | "
               "START u1 dated", ""))
        self.assertEqual(self.overdue(self.NOW, "--accuracy")[1].splitlines(), [
            "ACCURACY qa | finished 0 | on first ETA 0 of 0 (n/a) | median late 0 min | re-dated 1x | "
            "open past first ETA 0",
            "UNREADABLE first ETA 2 | qa 2"])

    def test_accuracy_on_a_bus_written_in_short_forms(self):
        rows = self.accuracy_of(
            "2026-11-18T09:00:00\tweb\tw1\t11-18 10:00\tSTART w1", "2026-11-18T09:45:00\tweb\tw1\tDONE\tDONE w1 x",
            "2026-11-18T09:00:00\tweb\tw2\t10:30\tSTART w2", "2026-11-18T11:00:00\tweb\tw2\tDONE\tDONE w2 x",
            "2026-11-18T09:05:00\tweb\tw3\t09:00\tSTART w3 means tomorrow",
            "2026-11-18T11:00:00\tweb\tw3\tDONE\tDONE w3 x",
            "2026-11-18T09:00:00\tweb\tw4\t11:00\tSTART w4 open past",
            "2026-11-18T09:00:00\tqa\tq1\t13-40 10:00\tSTART q1", "2026-11-18T10:00:00\tqa\tq1\tDONE\tDONE q1 x",
            "2026-11-18T09:00:00\tqa\tq2\t29:99\tSTART q2 still open",
            "2026-11-18T09:00:00\tqa\tq3\t12/31 23:00\tSTART q3", "2026-11-18T10:00:00\tqa\tq3\tDONE\tDONE q3 x")
        self.assertEqual(rows, [
            "ACCURACY qa | finished 1 | on first ETA 1 of 1 (100%) | median late 0 min | re-dated 0x | "
            "open past first ETA 0",
            "ACCURACY web | finished 3 | on first ETA 2 of 3 (67%) | median late 30 min | re-dated 0x | "
            "open past first ETA 1",
            "UNREADABLE first ETA 2 | qa 2"])

    def test_health_counts_unreadable_open_etas_and_degrades(self):
        self.write_items("2026-11-18T09:00:00\tqa\th1\t11-19 10:00\tSTART h1",
                         "2026-11-18T09:00:00\tqa\th2\t17:00\tSTART h2")
        self.assertEqual(self.health("2026-11-18T18:00:00"), (
            0, "HEALTH ok | open 2 | overdue 1 | escalate 0 | sent 0 | refused 0 | unchecked 0 | untracked 0 | "
               "damaged 0 | since 24h", ""))
        with open(self.items, "a", encoding="utf-8") as handle:
            handle.write("2026-11-18T09:00:00\tqa\th3\t02-30 10:00\tSTART h3\n"
                         "2026-11-18T09:00:00\tqa\th4\t2026-11-19 10:00\tSTART h4\n"
                         "2026-11-18T09:30:00\tqa\th4\tsoon\tSTART h4 re-dated to nothing\n")
        self.assertEqual(self.health("2026-11-18T18:00:00"), (
            1, "HEALTH degraded | open 4 | overdue 3 | escalate 1 | sent 0 | refused 0 | unchecked 0 | untracked 0 | "
               "damaged 0 | unreadable 2 | since 24h", ""))


    def test_a_send_time_at_the_edge_of_the_date_range_never_stops_a_listing(self):
        # Riyadh is UTC+3: the first send time is past year 9999 locally; the naive one is before year 1 in UTC
        self.write_items("9999-12-31T23:59:00+00:00\tqa\te1\t10:00\tSTART e1 x - ETA 10:00",
                         "0001-01-01T00:00:00\tqa\te2\t2026-11-19 10:00\tSTART e2",
                         "2026-11-19T09:00:00+03:00\tqa\te3\t11-19 10:00\tSTART e3",
                         "2026-11-19T09:30:00+03:00\tqa\te3\tDONE\tDONE e3 ok")
        now, skipped = "2026-11-19T13:00:00+03:00", f"overdue.py: 1 damaged line(s) in {self.items} skipped\n"
        with mock.patch.dict(os.environ, {"TZ": "Asia/Riyadh"}):
            self.assertEqual(self.overdue(now, "--accuracy"), (0, "\n".join([
                "ACCURACY qa | finished 1 | on first ETA 1 of 1 (100%) | median late 0 min | re-dated 0x | "
                "open past first ETA 0",
                "UNREADABLE first ETA 1 | qa 1"]), skipped))
            self.assertEqual(self.health(now), (
                1, "HEALTH degraded | open 1 | overdue 1 | escalate 0 | sent 0 | refused 0 | unchecked 0 | "
                   "untracked 0 | damaged 1 | unreadable 1 | since 24h", skipped))
            code, out, err = self.overdue(now)
            self.assertEqual((code, out.startswith("OVERDUE e1 | owner qa | ETA 10:00 (unreadable) | open -"), err),
                             (0, True, skipped))

    def test_a_short_eta_that_falls_before_year_one_in_local_time_is_unreadable(self):
        # in Riyadh 0001-01-01 01:00 local is still year 0 in UTC
        self.write_items("0001-01-01T03:30:00+03:00\tqa\te1\t01-01 01:00\tSTART e1")
        with mock.patch.dict(os.environ, {"TZ": "Asia/Riyadh"}):
            self.assertEqual(self.overdue("2026-11-19T13:00:00+03:00", "--accuracy"), (0, "\n".join([
                "ACCURACY qa | finished 0 | on first ETA 0 of 0 (n/a) | median late 0 min | re-dated 0x | "
                "open past first ETA 0",
                "UNREADABLE first ETA 1 | qa 1"]), ""))

    def test_docs_on_health_exit_1_name_every_degrading_cause(self):
        # a coordinator clears a degraded health from these lines, so each cause in overdue.health must be named
        readme = (SKILL / "templates" / "bus" / "README.md").read_text(encoding="utf-8")
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for name, text, marker in (("README.md", readme, "exits 1 (`degraded`) when"),
                                   ("SKILL.md", skill, "exit 1 means")):
            sentence = text.split(marker, 1)[1].split(":", 1)[0].split(", so", 1)[0]
            for cause in ("unchecked", "untracked", "damaged", "unreadable"):
                with self.subTest(doc=name, cause=cause):
                    self.assertIn(cause, sentence)

class ShortEtaFormTests(unittest.TestCase):
    """overdue.due_at on each ETA form; send times and expected values are local wall-clock times."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("bus_overdue", SKILL / "templates" / "bus" / "overdue.py")
        cls.overdue = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.overdue)

    def due(self, eta, sent):
        return self.overdue.due_at(eta, datetime.fromisoformat(sent).astimezone())

    def assert_due(self, eta, sent, expected):
        self.assertEqual(self.due(eta, sent), datetime.fromisoformat(expected).astimezone(), (eta, sent))

    def test_each_form(self):
        self.assert_due("2026-11-19 14:30", "2026-11-18T09:00:00", "2026-11-19T14:30:00")
        self.assert_due("2026-11-17 14:30", "2026-11-18T09:00:00", "2026-11-17T14:30:00")  # full form: as written
        self.assert_due("11-19 14:30", "2026-11-18T09:00:00", "2026-11-19T14:30:00")
        self.assert_due("11/19 7:05", "2026-11-18T09:00:00", "2026-11-19T07:05:00")
        self.assert_due("14:30", "2026-11-18T09:00:00", "2026-11-18T14:30:00")
        self.assert_due(" 14:30 ", "2026-11-18T09:00:00", "2026-11-18T14:30:00")

    def test_a_month_day_takes_the_year_nearest_the_send_time(self):
        self.assert_due("01-02 09:00", "2026-12-30T10:00:00", "2027-01-02T09:00:00")  # year end: next year
        self.assert_due("12-30 09:00", "2027-01-02T10:00:00", "2026-12-30T09:00:00")  # year start: last year
        self.assert_due("11-17 09:00", "2026-11-18T10:00:00", "2026-11-17T09:00:00")  # a day before stays this year
        self.assert_due("05-10 10:00", "2026-11-18T10:00:00", "2027-05-10T10:00:00")  # 192 days before, 173 after
        self.assert_due("06-01 10:00", "2026-11-18T10:00:00", "2026-06-01T10:00:00")  # 170 days before, 195 after

    def test_a_time_alone_rolls_to_the_next_day_only_once_past_the_send_minute(self):
        self.assert_due("10:00", "2026-11-18T10:00:59", "2026-11-18T10:00:00")  # the send minute itself: same day
        self.assert_due("10:00", "2026-11-18T10:01:00", "2026-11-19T10:00:00")
        self.assert_due("09:59", "2026-11-18T10:00:00", "2026-11-19T09:59:00")
        self.assert_due("00:00", "2026-12-31T23:30:00", "2027-01-01T00:00:00")  # rolls over the year too

    def test_impossible_or_other_text_is_unreadable(self):
        for eta in ("13-40 10:00", "02-30 10:00", "00-10 10:00", "11-00 10:00", "29:99", "24:00", "10:60",
                    "11-19 24:00", "soon", "", "10", "11-19", "10:00 pm", "11-19 10:00:30", "2026-13-01 10:00",
                    "\u0661\u0660:\u0660\u0660"):
            self.assertIsNone(self.due(eta, "2026-11-18T09:00:00"), eta)


    def test_a_send_time_at_the_edge_of_the_date_range_is_unreadable_not_fatal(self):
        last = datetime(9999, 12, 31, 23, 59, tzinfo=timezone.utc)  # local time is past it or the next day is
        first = datetime(1, 1, 1, 0, 30, tzinfo=timezone(timedelta(hours=5)))  # year 0 in UTC
        for eta, sent in (("10:00", last), ("12-31 23:59", last), ("01-01 00:00", first), ("00:00", first)):
            due = self.overdue.due_at(eta, sent)
            self.assertTrue(due is None or due.tzinfo is not None, (eta, sent, due))
        self.assertIsNone(self.overdue.due_at("10:00", last))
        self.assertEqual(self.overdue.due_at("2026-11-19 10:00", last), datetime(2026, 11, 19, 10, 0).astimezone())


    def test_a_send_time_in_another_offset_is_read_in_local_time(self):
        local = datetime(2026, 11, 18, 12, 0).astimezone().utcoffset()
        sent = datetime(2026, 11, 18, 9, 0, tzinfo=timezone(local + timedelta(hours=5)))  # 04:00 local
        self.assertEqual(self.overdue.due_at("06:00", sent), datetime(2026, 11, 18, 6, 0).astimezone())
        self.assertEqual(self.overdue.due_at("03:00", sent), datetime(2026, 11, 19, 3, 0).astimezone())

    def test_a_leap_day_needs_a_leap_year_within_a_year_of_the_send_time(self):
        self.assert_due("02-29 10:00", "2027-11-18T09:00:00", "2028-02-29T10:00:00")
        self.assertIsNone(self.due("02-29 10:00", "2026-11-18T09:00:00"))  # 2025, 2026, 2027: none is a leap year

    def test_it_matches_send_check_on_lines_send_check_accepts(self):
        spec = importlib.util.spec_from_file_location("bus_send_check", SKILL / "templates" / "bus" / "send_check.py")
        send_check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(send_check)
        for sent, eta in (("2026-11-18T09:00:00", "11-19 14:30"), ("2026-11-18T10:00:30", "10:00"),
                          ("2026-11-18T10:01:00", "10:00"), ("2026-12-30T10:00:00", "01-02 09:00"),
                          ("2026-11-18T09:00:00", "2026-11-20 08:00")):
            now = datetime.fromisoformat(sent)
            expected = send_check.eta_of(f"START k x - ETA {eta}", now)
            self.assertEqual(self.due(eta, sent), expected.astimezone(), (sent, eta))


if __name__ == "__main__":
    unittest.main()
