"""Tests for `lessons.py metrics` (metrics.py), the events log add and bump write (lesson_events.py) and the guard-hit
entries it reads. Clock: lessons.today is fixed at 2026-11-19; the bus clock is $BUS_NOW. Every file is in a temp dir."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "lessons-learned" / "scripts"))

import guard_hits  # noqa: E402
import lesson_events  # noqa: E402
import lessons  # noqa: E402
import metrics  # noqa: E402

TODAY = "2026-11-19"
HEADER = "# Lessons Learned\n\n## Active\n"


def lesson_line(ident, tags, hits, when, promoted=""):
    return (f"- {ident} [{tags}] hits:{hits} | {when} | Mistake: m{ident} | Cause: c | Rule: rule {ident} | "
            f"Check: k" + (f" | Promoted: {promoted}" if promoted else ""))


def event(day, kind, ident, tags=""):
    return json.dumps({"time": f"{day}T10:00:00+0000", "date": day, "event": kind, "id": ident, "tags": tags})


def local_noon(day):
    return datetime.fromisoformat(f"{day}T12:00:00").timestamp()


class MetricsCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.file = self.dir / "project" / "lessons.md"
        self.file.parent.mkdir()
        self.shared = self.dir / "home" / "lessons.md"
        self.hits = self.dir / "home" / "hits.jsonl"
        self.env = {"LESSONS_GLOBAL_FILE": str(self.shared), "LESSONS_GUARD_HITS_FILE": str(self.hits),
                    "LESSONS_PROMOTE_AT": "3", "BUS_NOW": "2026-11-18T12:00:00"}
        for patch in (mock.patch.dict(os.environ, self.env), mock.patch.object(lessons, "today", return_value=TODAY)):
            patch.start()
            self.addCleanup(patch.stop)

    def write_ledger(self, *lines, path=None):
        path = path or self.file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(HEADER + "".join(line + "\n" for line in lines), encoding="utf-8")

    def write_events(self, *lines, path=None):
        lesson_events.path(path or self.file).write_text("".join(line + "\n" for line in lines), encoding="utf-8")

    def run_cli(self, *argv, path=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lessons.main(["--file", str(path or self.file), *argv])
        return code, out.getvalue(), err.getvalue()

    def metrics_json(self, *argv):
        code, out, err = self.run_cli("metrics", "--json", *argv)
        self.assertEqual((code, err), (0, ""))
        return json.loads(out)

    def lanes(self, data, project=0):
        return {row["lane"]: row for row in data["projects"][project]["lanes"]}

    def read_events(self, path=None):
        return [json.loads(line) for line in lesson_events.path(path or self.file).read_text().splitlines()]


class EventsLogTest(MetricsCase):
    def add(self, mistake, rule, tags="sql,session:api"):
        return self.run_cli("add", "--tags", tags, "--mistake", mistake, "--cause", "assumed", "--rule", rule)

    def test_add_logs_add_and_a_duplicate_add_logs_repeat(self):
        self.assertEqual(self.add("migration ran without dry run", "run the migration dry run first")[0], 0)
        self.assertEqual(self.add("migration ran without dry run again", "run the migration dry run first")[0], 0)
        self.assertEqual(self.add("cache key forgot tenant", "include tenant in cache keys", tags="cache")[0], 0)
        logged = self.read_events()
        self.assertEqual([(e["date"], e["event"], e["id"], e["tags"]) for e in logged],
                         [(TODAY, "add", "L001", "sql,session:api"), (TODAY, "repeat", "L001", "sql,session:api"),
                          (TODAY, "add", "L002", "cache")])
        self.assertEqual({e["ledger"] for e in logged}, {"lessons.md"})
        self.assertEqual(self.file.parent / "lessons.events.jsonl", lesson_events.path(self.file))

    def test_each_line_has_a_local_time_and_no_machine_path(self):
        lesson_events.append(self.dir / "project" / "team.md", "add", {"id": "L001", "tags": ""}, TODAY)
        text = (self.file.parent / "team.events.jsonl").read_text()
        logged = json.loads(text)
        self.assertRegex(logged["time"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4}$")
        self.assertEqual(logged["ledger"], "team.md")
        self.assertNotIn(str(self.dir), text)

    def test_globalize_logs_a_move_beside_the_global_ledger(self):
        self.assertEqual(self.add("migration ran without dry run", "run the migration dry run first")[0], 0)
        self.assertEqual(self.run_cli("globalize", "L001")[0], 0)
        self.assertEqual([(e["date"], e["event"], e["id"], e["tags"]) for e in self.read_events(self.shared)],
                         [(TODAY, "move", "G001", "sql,session:api")])
        self.assertEqual([(e["event"], e["id"]) for e in self.read_events()], [("add", "L001"), ("move", "L001")])

    def test_globalize_into_a_matching_global_lesson_logs_a_move_of_that_lesson(self):
        mistake, rule = "force pushed shared branch main", "never force push main"
        self.write_ledger(lesson_line("G001", "git", 1, "2026-11-01").replace("mG001", mistake)
                          .replace("rule G001", rule), path=self.shared)
        self.write_ledger(lesson_line("L002", "git", 1, TODAY).replace("mL002", mistake).replace("rule L002", rule))
        self.assertIn("duplicate of G001", self.run_cli("globalize", "L002")[1])
        self.assertEqual([(e["event"], e["id"]) for e in self.read_events(self.shared)], [("move", "G001")])

    def test_a_failed_move_log_write_warns_and_never_fails_globalize(self):
        self.write_ledger(lesson_line("L001", "ops", 2, TODAY))
        with mock.patch.object(lesson_events.os, "open", side_effect=PermissionError("read-only")):
            code, out, err = self.run_cli("globalize", "L001")
        self.assertEqual(code, 0)
        self.assertIn("moved L001", out)
        self.assertIn("warning: events log", err)
        self.assertIn("Promoted: global G001", self.file.read_text())

    def test_a_symlinked_global_ledger_logs_and_reads_beside_its_target(self):
        target = self.dir / "dotfiles" / "lessons.md"
        self.write_ledger(path=target)
        self.shared.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.shared.symlink_to(target)
        except OSError:
            self.skipTest("symlinks are not available here")
        self.assertEqual(self.run_cli("add", "--global", "--tags", "git", "--mistake", "force pushed main",
                                      "--cause", "c", "--rule", "never force push main")[0], 0)
        self.assertEqual(self.run_cli("bump", "G001")[0], 0)
        self.assertEqual([e["event"] for e in self.read_events(target)], ["add", "repeat"])
        self.assertFalse((self.shared.parent / "lessons.events.jsonl").exists())
        entry = self.metrics_json("--days", "2")["projects"][1]
        self.assertEqual((entry["events_log_found"], entry["events_from"], entry["day_source"]),
                         (True, TODAY, ["ledger", "events"]))
        row = {r["lane"]: r for r in entry["lanes"]}["(no lane)"]
        self.assertEqual((row["added"], row["repeated"]), ([0, 1], [0, 1]))

    def test_bump_logs_repeat_and_a_global_bump_logs_beside_the_global_ledger(self):
        self.write_ledger(lesson_line("L001", "ops", 1, "2026-11-01"))
        self.write_ledger(lesson_line("G001", "git", 2, "2026-11-01"), path=self.shared)
        self.assertEqual(self.run_cli("bump", "L001")[0], 0)
        self.assertEqual(self.run_cli("bump", "G001")[0], 0)
        self.assertEqual([(e["event"], e["id"], e["tags"]) for e in self.read_events()], [("repeat", "L001", "ops")])
        self.assertEqual([(e["event"], e["id"], e["date"]) for e in self.read_events(self.shared)],
                         [("repeat", "G001", TODAY)])

    def test_a_failed_log_write_warns_and_never_fails_add_or_bump(self):
        with mock.patch.object(lesson_events.os, "open", side_effect=PermissionError("read-only")):
            code, out, err = self.add("deploy skipped smoke", "run smoke after deploy")
            self.assertEqual((code, out.strip()), (0, "added L001"))
            self.assertIn("warning: events log", err)
            self.assertIn("read-only", err)
            code, out, err = self.run_cli("bump", "L001")
            self.assertEqual((code, out.strip()), (0, "L001 hits:2"))
            self.assertIn("warning: events log", err)
        self.assertIn("hits:2", self.file.read_text())
        self.assertFalse(lesson_events.path(self.file).exists())

    def test_refused_add_and_unknown_bump_log_nothing(self):
        self.assertEqual(self.add("leaked sk-abcdefghijklmnopqrstuvwx", "never paste keys")[0], 2)
        self.write_ledger(lesson_line("L001", "ops", 1, "2026-11-01"))
        self.assertEqual(self.run_cli("bump", "L009")[0], 2)
        self.assertFalse(lesson_events.path(self.file).exists())

    def test_read_skips_damaged_lines_and_reads_a_missing_log_as_none(self):
        self.assertEqual(lesson_events.read(self.file), (None, 0))
        self.write_events("not json", "[1, 2]", json.dumps({"date": "2026-13-01", "event": "add", "id": "L1"}),
                          json.dumps({"date": TODAY, "event": 5, "id": "L1"}), json.dumps({"date": TODAY, "id": "L1"}),
                          "", json.dumps({"date": TODAY, "event": "add", "id": "L1", "tags": 7}),
                          json.dumps({"date": TODAY, "event": "add", "id": 7}))
        events, skipped = lesson_events.read(self.file)
        self.assertEqual(skipped, 6)
        self.assertEqual([(e["id"], e["tags"], e["day"].isoformat()) for e in events], [("L1", "", TODAY)])


class PerDayTest(MetricsCase):
    def test_without_a_log_every_day_comes_from_ledger_dates_and_says_so(self):
        self.write_ledger(lesson_line("L001", "session:api", 1, "2026-11-19"),
                          lesson_line("L002", "session:api", 3, "2026-11-17"),
                          lesson_line("L003", "session:api", 1, "2026-11-12"),   # day before the 7-day window
                          lesson_line("L004", "session:api", 1, "2026-11-13"),   # first day of the window
                          lesson_line("L005", "session:api", 2, "2026-11-20"),   # after today
                          lesson_line("L006", "session:api", 2, "2026-11-18"))   # hits 2: a repeat
        data = self.metrics_json()
        self.assertEqual(data["window"]["dates"], ["2026-11-13", "2026-11-14", "2026-11-15", "2026-11-16",
                                                   "2026-11-17", "2026-11-18", "2026-11-19"])
        entry = data["projects"][0]
        self.assertEqual((entry["events_log_found"], entry["events_from"], entry["day_source"]),
                         (False, None, ["ledger"] * 7))
        self.assertEqual(entry["skipped"]["future_ledger_date"], 1)
        api = self.lanes(data)["api"]
        self.assertEqual(api["added"], [1, 0, 0, 0, 0, 0, 1])
        self.assertEqual(api["repeated"], [0, 0, 0, 0, 1, 1, 0])
        self.assertEqual((api["added_total"], api["repeated_total"], api["lessons"], api["repeats"]), (2, 2, 6, 4))
        out = self.run_cli("metrics")[1]
        self.assertIn("every day is from ledger dates: last change only", out)
        self.assertIn("| api | 1/0 | 0/0 | 0/0 | 0/0 | 0/1 | 0/1 | 1/0 |", out)
        self.assertIn("skipped: 1 future ledger date", out)

    def test_the_log_counts_from_its_first_event_and_older_days_fall_back(self):
        self.write_ledger(lesson_line("L001", "session:web", 1, "2026-11-16"),   # before the log: from the ledger
                          lesson_line("L002", "session:web", 2, "2026-11-19"),   # after: only its events count
                          lesson_line("L003", "session:web", 1, "2026-11-18"))   # after, no event: not counted
        self.write_events(event("2026-11-17", "add", "L002", "session:web"),
                          event("2026-11-19", "repeat", "L002", "session:web"),
                          event("2026-11-19", "repeat", "L002", "session:web"),
                          "garbage", event("2026-11-19", "archive", "L002"),
                          event("2026-11-20", "add", "L008", "session:web"),
                          event("2026-11-21", "add", "L009", "session:web"))
        data = self.metrics_json("--days", "5")
        entry = data["projects"][0]
        self.assertEqual(entry["events_from"], "2026-11-17")
        self.assertEqual(entry["day_source"], ["ledger", "ledger", "events", "events", "events"])
        self.assertEqual(entry["skipped"], {"malformed": 1, "unknown_event": 1, "future_event": 2,
                                            "future_ledger_date": 0})
        web = self.lanes(data)["web"]
        self.assertEqual((web["added"], web["repeated"]), ([0, 1, 1, 0, 0], [0, 0, 0, 0, 2]))
        out = self.run_cli("metrics", "--days", "5")[1]
        self.assertIn("per day from the events log from 2026-11-17; 2026-11-15 to 2026-11-16 from ledger dates: "
                      "last change only", out)
        self.assertIn("skipped: 1 malformed, 1 unknown event, 2 future event", out)

    def test_a_single_fallback_day_is_named_alone(self):
        self.write_ledger()
        self.write_events(event("2026-11-18", "add", "L001"))
        self.assertIn("from 2026-11-18; 2026-11-17 from ledger dates: last change only",
                      self.run_cli("metrics", "--days", "3")[1])

    def test_a_log_older_than_the_window_covers_every_day(self):
        self.write_ledger(lesson_line("L001", "", 1, "2026-11-19"))
        self.write_events(event("2026-10-01", "add", "L000"), event("2026-11-19", "add", "L001"))
        data = self.metrics_json("--days", "2")
        self.assertEqual(data["projects"][0]["day_source"], ["events", "events"])
        self.assertEqual(self.lanes(data)["(no lane)"]["added"], [0, 1])
        out = self.run_cli("metrics", "--days", "2")[1]
        self.assertIn("- per day from the events log from 2026-10-01\n", out)

    def test_a_log_with_no_usable_event_falls_back_and_says_so(self):
        self.write_ledger(lesson_line("L001", "", 1, "2026-11-19"))
        self.write_events("{oops", event("2026-11-19", "rename", "L001"))
        data = self.metrics_json("--days", "1")
        self.assertEqual((data["projects"][0]["events_from"], self.lanes(data)["(no lane)"]["added"]), (None, [1]))
        self.assertIn("holds no usable event: every day is from ledger dates: last change only",
                      self.run_cli("metrics", "--days", "1")[1])

    def test_an_unreadable_events_log_is_one_line_and_falls_back_to_ledger_dates(self):
        self.write_ledger(lesson_line("L001", "", 1, TODAY))
        self.write_ledger(lesson_line("G001", "", 2, TODAY), path=self.shared)
        lesson_events.path(self.shared).mkdir()
        code, out, err = self.run_cli("metrics", "--days", "1")
        self.assertEqual((code, err), (0, ""))
        self.assertIn(f"- events log {lesson_events.path(self.shared)} not read (Is a directory): every day is "
                      "from ledger dates: last change only", out)
        data = self.metrics_json("--days", "1")
        project, shared = data["projects"]
        self.assertEqual((project["events_log_error"], shared["events_log_error"]), (None, "Is a directory"))
        self.assertEqual((shared["events_log_found"], shared["day_source"]), (False, ["ledger"]))
        self.assertEqual((self.lanes(data)["(no lane)"]["added"], self.lanes(data, 1)["(no lane)"]["repeated"]),
                         ([1], [1]))
        with mock.patch.object(lesson_events, "read", side_effect=PermissionError(13, "Permission denied")):
            code, out, err = self.run_cli("metrics", "--days", "1")
        self.assertEqual((code, err), (0, ""))
        self.assertIn(f"- events log {lesson_events.path(self.file)} not read (Permission denied)", out)

    def test_a_one_day_window_is_today_only(self):
        self.write_ledger(lesson_line("L001", "", 1, "2026-11-18"), lesson_line("L002", "", 1, TODAY))
        data = self.metrics_json("--days", "1")
        self.assertEqual((data["window"]["start"], data["window"]["end"]), (TODAY, TODAY))
        self.assertEqual(self.lanes(data)["(no lane)"]["added"], [1])


class GroupingTest(MetricsCase):
    def test_lanes_by_the_session_tag_sorted_with_no_lane_last(self):
        self.write_ledger(lesson_line("L001", "web,session:web", 1, TODAY), lesson_line("L002", "session:api", 2, TODAY),
                          lesson_line("L003", "sql", 1, TODAY), lesson_line("L004", "session:", 1, TODAY),
                          lesson_line("L005", "session:api,session:web", 4, TODAY))
        data = self.metrics_json()
        self.assertEqual([row["lane"] for row in data["projects"][0]["lanes"]], ["api", "web", "(no lane)"])
        self.assertEqual({lane: row["lessons"] for lane, row in self.lanes(data).items()},
                         {"api": 2, "web": 1, "(no lane)": 2})
        self.assertEqual(self.lanes(data)["api"]["repeats"], 4)

    def test_an_event_takes_the_lane_it_was_logged_with(self):
        self.write_ledger(lesson_line("L001", "session:web", 2, TODAY))
        self.write_events(event(TODAY, "add", "L001", "session:api"), event(TODAY, "repeat", "L001", "session:web"))
        lanes = self.lanes(self.metrics_json("--days", "1"))
        self.assertEqual((lanes["api"]["added"], lanes["api"]["lessons"]), ([1], 0))
        self.assertEqual((lanes["web"]["repeated"], lanes["web"]["lessons"]), ([1], 1))

    def test_a_custom_lane_prefix(self):
        self.write_ledger(lesson_line("L001", "lane:ops,session:web", 1, TODAY), lesson_line("L002", "session:web", 1, TODAY))
        data = self.metrics_json("--lane-tag", "Lane:")
        self.assertEqual(data["lane_tag"], "lane:")
        self.assertEqual(sorted(self.lanes(data)), ["(no lane)", "ops"])
        self.assertIn("Lane: tag `lane:<name>`", self.run_cli("metrics", "--lane-tag", "lane:")[1])

    def test_a_lane_prefix_without_its_colon_gets_one(self):
        self.write_ledger(lesson_line("L001", "sql,session:api", 1, TODAY), lesson_line("L002", "sessions:x", 1, TODAY),
                          lesson_line("L003", "session-notes", 1, TODAY))
        data = self.metrics_json("--lane-tag", "session")
        self.assertEqual(data["lane_tag"], "session:")
        self.assertEqual({lane: row["lessons"] for lane, row in self.lanes(data).items()}, {"api": 1, "(no lane)": 2})

    def test_spaces_around_tags_are_ignored(self):
        self.assertEqual(metrics.lane_of("sql, session:api", "session:"), "api")
        self.assertEqual(metrics.lane_of(" session: web ,x", "session:"), "web")

    def test_a_pipe_in_a_logged_lane_cannot_break_the_table(self):
        self.write_ledger()
        self.write_events(event(TODAY, "add", "L001", "session:a|b"))
        self.assertIn("| a/b | 0 |", self.run_cli("metrics", "--days", "1")[1])

    def test_each_ledger_is_its_own_project_in_source_order(self):
        extra = self.dir / "other" / "lessons.md"
        self.write_ledger(lesson_line("L001", "", 1, TODAY))
        self.write_ledger(lesson_line("L001", "", 2, TODAY), path=extra)
        self.write_ledger(lesson_line("G001", "session:qa", 3, TODAY), path=self.shared)
        data = self.metrics_json("--ledger", str(extra), str(self.file))  # the project ledger named again: once
        self.assertEqual([p["ledger"] for p in data["projects"]], [str(self.file), str(extra), str(self.shared)])
        self.assertEqual([self.lanes(data, n).get("(no lane)", {}).get("repeats") for n in range(3)], [0, 1, None])
        self.assertEqual(self.lanes(data, 2)["qa"]["repeats"], 2)


class GuardCoverageTest(MetricsCase):
    def test_guarded_unguarded_and_exempt_follow_lessons_rules(self):
        self.write_ledger(lesson_line("L001", "", 1, TODAY),                                   # unguarded
                          lesson_line("L002", "", 4, TODAY),                                   # unguarded, 3+
                          lesson_line("L003", "", 5, TODAY, "tests/test_x.py"),                # guarded
                          lesson_line("L004", "", 3, TODAY, "exempt@3: no mechanical check"),  # exempt holds
                          lesson_line("L005", "", 4, TODAY, "exempt@2: no mechanical check"),  # outgrown: unguarded 3+
                          "", "## Archive",
                          lesson_line("L006", "", 3, TODAY, "global G004"))                    # moved: own column
        row = self.lanes(self.metrics_json())["(no lane)"]
        self.assertEqual((row["guarded"], row["unguarded"], row["exempt"], row["unguarded_repeats"], row["moved"]),
                         (1, 3, 1, 2, 1))
        self.assertEqual((row["lessons"], row["repeats"], row["repeated"][-1]), (5, 12, 4))
        out = self.run_cli("metrics")[1]
        self.assertIn("| Lane | Lessons | Repeats | Guarded | Unguarded | Unguarded 3+ | Exempt | Moved | Added | "
                      "Repeated |", out)
        self.assertIn("| (no lane) | 5 | 12 | 1 | 3 | 2 | 1 | 1 | 1 | 4 |", out)

    def test_a_globalized_lesson_counts_once_in_the_global_ledger(self):
        code = self.run_cli("add", "--tags", "session:api", "--mistake", "skipped the dry run", "--cause", "c",
                            "--rule", "run the dry run")[0]
        self.assertEqual([code, self.run_cli("bump", "L001")[0], self.run_cli("bump", "L001")[0],
                          self.run_cli("globalize", "L001")[0]], [0, 0, 0, 0])
        data = self.metrics_json("--days", "2")
        local, shared = self.lanes(data, 0)["api"], self.lanes(data, 1)["api"]
        self.assertEqual({key: local[key] for key in ("lessons", "moved", "repeats", "guarded", "unguarded", "added",
                                                      "repeated")},
                         {"lessons": 0, "moved": 1, "repeats": 0, "guarded": 0, "unguarded": 0, "added": [0, 1],
                          "repeated": [0, 2]})
        self.assertEqual({key: shared[key] for key in ("lessons", "moved", "repeats", "guarded", "unguarded", "added",
                                                       "repeated")},
                         {"lessons": 1, "moved": 0, "repeats": 2, "guarded": 0, "unguarded": 1, "added": [0, 0],
                          "repeated": [0, 0]})

    def test_a_stub_that_recurs_after_its_move_counts_its_repeats_in_the_project(self):
        add = ("add", "--tags", "session:api", "--mistake", "skipped the dry run", "--cause", "c", "--rule",
               "run the dry run")
        self.assertEqual([self.run_cli(*add)[0], self.run_cli("bump", "L001")[0], self.run_cli("bump", "L001")[0],
                          self.run_cli("globalize", "L001")[0]], [0, 0, 0, 0])
        code, out, _ = self.run_cli(*add)
        self.assertEqual(code, 0)
        self.assertIn("GUARD FAILED L001", out)
        data = self.metrics_json("--days", "2")
        local, shared = self.lanes(data, 0)["api"], self.lanes(data, 1)["api"]
        self.assertEqual({key: local[key] for key in ("lessons", "moved", "moved_recurred", "repeats", "added",
                                                      "repeated")},
                         {"lessons": 0, "moved": 1, "moved_recurred": 1, "repeats": 1, "added": [0, 1],
                          "repeated": [0, 3]})
        self.assertEqual((shared["repeats"], shared["moved_recurred"]), (2, 0))
        self.assertEqual(data["projects"][0]["recurred_after_move"], [{"id": "L001", "repeats": 1}])
        report = self.run_cli("metrics", "--days", "2")[1]
        self.assertIn("- recurred after globalize (the guard failed; counted in Repeats here): L001 x1", report)
        self.assertIn("| api | 0 | 1 | 0 | 0 | 0 | 0 | 1 (1 recurred) | 1 | 3 |", report)

    def test_a_stub_back_in_active_without_a_move_event_is_flagged_with_an_unknown_count(self):
        self.file.write_text(HEADER + lesson_line("L001", "session:api", 3, "2026-11-18", promoted="global G001")
                             + "\n\n## Archive\n" + lesson_line("L002", "session:api", 2, "2026-11-10",
                                                              promoted="global G002") + "\n", encoding="utf-8")
        data = self.metrics_json("--days", "2")
        api = self.lanes(data)["api"]
        self.assertEqual((api["moved"], api["moved_recurred"], api["repeats"], api["repeated"]), (2, 1, 0, [0, 0]))
        self.assertEqual(data["projects"][0]["recurred_after_move"], [{"id": "L001", "repeats": None}])
        self.assertIn("L001 (how often is not in the events log)", self.run_cli("metrics", "--days", "2")[1])

    def test_a_lesson_the_log_names_is_not_also_counted_on_its_ledger_date(self):
        self.write_ledger(lesson_line("G001", "", 3, "2026-11-17"), lesson_line("G002", "", 2, "2026-11-17"),
                          path=self.shared)
        self.write_events(event(TODAY, "move", "G001"), path=self.shared)
        entry = self.metrics_json("--days", "3")["projects"][1]
        self.assertEqual((entry["day_source"], entry["skipped"]["unknown_event"]), (["ledger", "ledger", "events"], 0))
        row = {r["lane"]: r for r in entry["lanes"]}["(no lane)"]
        self.assertEqual((row["added"], row["repeated"], row["repeats"]), ([0, 0, 0], [1, 0, 0], 3))

    def test_the_threshold_follows_lessons_promote_at(self):
        self.write_ledger(lesson_line("L001", "", 2, TODAY), lesson_line("L002", "", 1, TODAY))
        with mock.patch.dict(os.environ, {"LESSONS_PROMOTE_AT": "2"}):
            data = self.metrics_json()
            out = self.run_cli("metrics")[1]
        self.assertEqual((data["threshold"], self.lanes(data)["(no lane)"]["unguarded_repeats"]), (2, 1))
        self.assertIn("| Unguarded 2+ |", out)


class GuardFiresTest(MetricsCase):
    def test_fires_per_local_day_in_the_window(self):
        self.hits.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps({"time": local_noon(day), "lesson": "G001", "rule": "r", "cwd": "/w"})
                 for day in ("2026-11-19", "2026-11-19", "2026-11-17", "2026-11-12", "2026-11-20")]
        lines += ["broken", json.dumps({"time": 1e20, "lesson": "G001", "rule": "r"})]
        self.hits.write_text("\n".join(lines) + "\n", encoding="utf-8")
        fires = self.metrics_json("--days", "3")["guard_fires"]
        self.assertEqual((fires["per_day"], fires["total"], fires["damaged"]), ([1, 0, 2], 3, 2))
        out = self.run_cli("metrics", "--days", "3")[1]
        self.assertIn("| 1 | 0 | 2 | 3 |", out)
        self.assertIn("- 2 damaged lines skipped", out)

    @unittest.skipUnless(hasattr(time, "tzset"), "needs time.tzset")
    def test_a_fire_just_after_local_midnight_counts_on_that_local_day(self):
        with mock.patch.dict(os.environ, {"TZ": "XYZ-9"}):  # POSIX: UTC+9, no tz database needed
            time.tzset()
            self.addCleanup(time.tzset)
            self.hits.parent.mkdir(parents=True, exist_ok=True)
            # 2026-11-19 00:30 at UTC+9 is 2026-11-18 15:30 UTC
            guard_hits.append("G1", "r", "/w", now=datetime(2026, 11, 18, 15, 30, tzinfo=timezone.utc).timestamp())
            fires = self.metrics_json("--days", "2")["guard_fires"]
        self.assertEqual(fires["per_day"], [0, 1])

    def test_a_timestamp_the_platform_rejects_with_oserror_is_one_damaged_line(self):
        self.hits.parent.mkdir(parents=True, exist_ok=True)
        guard_hits.append("G1", "r", "/w", now=local_noon(TODAY))
        with mock.patch.object(metrics, "datetime") as clock:
            clock.fromtimestamp.side_effect = OSError(22, "Invalid argument")
            fires = self.metrics_json()["guard_fires"]
        self.assertEqual((fires["damaged"], fires["total"]), (1, 0))

    def test_an_unreadable_hit_log_is_one_line_never_an_error(self):
        self.hits.mkdir(parents=True)
        code, out, err = self.run_cli("metrics")
        self.assertEqual((code, err), (0, ""))
        self.assertIn(f"- hit log {self.hits} not read (Is a directory)", out)
        self.assertNotIn("no hit log", out)
        fires = self.metrics_json()["guard_fires"]
        self.assertEqual((fires["error"], fires["total"], fires["per_day"]), ("Is a directory", 0, [0] * 7))

    def test_a_clean_hit_log_and_bus_print_no_damaged_note(self):
        self.hits.parent.mkdir(parents=True, exist_ok=True)
        guard_hits.append("G1", "r", "/w", now=local_noon(TODAY))
        folder = self.dir / "bus"
        folder.mkdir()
        (folder / "open-items.tsv").write_text("2026-11-18T09:00:00\tqa\ta1\t2026-11-18 10:00\tSTART a1 x\n"
                                               "2026-11-18T09:50:00\tqa\ta1\tDONE\tDONE a1 ok\n", encoding="utf-8")
        out = self.run_cli("metrics", "--bus", str(folder))[1]
        self.assertIn("| qa | 1 | 1 of 1 (100%) |", out)
        self.assertIn("| 1 |\n", out + "\n")
        self.assertNotIn("damaged", out)

    def test_no_hit_log_is_one_line(self):
        fires = self.metrics_json()["guard_fires"]
        self.assertEqual((fires["log_found"], fires["total"], fires["per_day"]), (False, 0, [0] * 7))
        self.assertIn(f"- no hit log at {self.hits}", self.run_cli("metrics")[1])

    def test_counts_include_both_window_edges(self):
        self.hits.parent.mkdir(parents=True, exist_ok=True)
        for when in (399, 400, 1000, 1001):
            guard_hits.append("G1", "r", "/w", now=when)
        self.assertEqual(guard_hits.counts(600, now=1000), ({("G1", "r"): 2}, 0))

    def test_entries_keep_counts_working(self):
        self.hits.parent.mkdir(parents=True, exist_ok=True)
        guard_hits.append("G1", "r", "/w", now=100)
        guard_hits.append(None, "r", "/w", now=150)
        self.assertEqual(guard_hits.entries(), ([(100.0, "G1", "r"), (150.0, "-", "r")], 0))


class BusTest(MetricsCase):
    def bus(self, *records):
        folder = self.dir / "bus"
        folder.mkdir(exist_ok=True)
        (folder / "open-items.tsv").write_text("".join(record + "\n" for record in records), encoding="utf-8")
        return folder

    def test_eta_accuracy_per_session(self):
        folder = self.bus("2026-11-18T09:00:00\tqa\ta1\t2026-11-18 10:00\tSTART a1 x",
                          "2026-11-18T09:50:00\tqa\ta1\tDONE\tDONE a1 ok",
                          "2026-11-18T09:00:00\tqa\ta2\t2026-11-18 10:00\tSTART a2 x",
                          "2026-11-18T11:30:00\tqa\ta2\tDONE\tDONE a2 late",
                          "2026-11-18T09:00:00\tqa\ta3\t2026-11-18 11:00\tSTART a3 open past",
                          "2026-11-18T09:00:00\tweb\tw1\tsoon\tSTART w1 unreadable",
                          "2026-11-18T10:00:00\tweb\tw1\tDONE\tDONE w1 x",
                          "damaged")
        eta = self.metrics_json("--bus", str(folder))["eta_accuracy"]
        self.assertEqual((eta["status"], eta["damaged"]), ("ok", 1))
        self.assertEqual(eta["sessions"], [
            {"session": "qa", "finished": 2, "on_time": 1, "pct": 50, "median_late_min": 90, "redates": 0,
             "open_late": 1},
            {"session": "web", "finished": 0, "on_time": 0, "pct": None, "median_late_min": 0, "redates": 0,
             "open_late": 0}])
        out = self.run_cli("metrics", "--bus", str(folder))[1]
        self.assertIn("| qa | 2 | 1 of 2 (50%) | 90 | 0 | 1 |", out)
        self.assertIn("| web | 0 | 0 of 0 (n/a) | 0 | 0 | 0 |", out)
        self.assertIn("- 1 damaged bus records skipped", out)

    def test_a_missing_or_empty_bus_is_one_line_never_an_error(self):
        code, out, err = self.run_cli("metrics", "--bus", str(self.dir / "nowhere"))
        self.assertEqual((code, err), (0, ""))
        self.assertIn(f"- no open-items.tsv in {self.dir / 'nowhere'}: no ETA data", out)
        folder = self.bus()
        code, out, _ = self.run_cli("metrics", "--bus", str(folder))
        self.assertEqual(code, 0)
        self.assertIn("- no finished or overdue items in", out)
        self.assertEqual(self.metrics_json("--bus", str(folder))["eta_accuracy"]["status"], "empty")

    def test_a_bus_of_only_damaged_records_is_empty_and_says_how_many_were_skipped(self):
        folder = self.bus("damaged", "also\tdamaged")
        eta = self.metrics_json("--bus", str(folder))["eta_accuracy"]
        self.assertEqual((eta["status"], eta["damaged"], eta["sessions"]), ("empty", 2, []))
        self.assertIn("- 2 damaged bus records skipped", self.run_cli("metrics", "--bus", str(folder))[1])

    def test_a_bad_bus_clock_an_unreadable_file_or_a_folder_in_its_place_is_one_line(self):
        folder = self.bus("2026-11-18T09:00:00\tqa\ta1\t2026-11-18 10:00\tSTART a1 x")
        with mock.patch.dict(os.environ, {"BUS_NOW": "yesterday"}):
            eta = self.metrics_json("--bus", str(folder))["eta_accuracy"]
            self.assertIn("- ETA accuracy not read:", self.run_cli("metrics", "--bus", str(folder))[1])
        self.assertEqual(eta["status"], "unreadable")
        with mock.patch.object(metrics.Path, "read_text", side_effect=PermissionError("denied")):
            eta = metrics.eta_accuracy(folder)
        self.assertEqual((eta["status"], eta["note"]), ("unreadable", "ETA accuracy not read: denied"))
        (folder / "open-items.tsv").unlink()
        (folder / "open-items.tsv").mkdir()
        self.assertEqual(self.metrics_json("--bus", str(folder))["eta_accuracy"]["status"], "missing")

    def test_without_bus_no_eta_section(self):
        self.assertIsNone(self.metrics_json()["eta_accuracy"])
        self.assertNotIn("ETA accuracy", self.run_cli("metrics")[1])

    def test_missing_overdue_template_is_one_line(self):
        with mock.patch.object(metrics, "OVERDUE", self.dir / "absent.py"):
            eta = self.metrics_json("--bus", str(self.bus()))["eta_accuracy"]
        self.assertEqual(eta["status"], "unavailable")


class CommandTest(MetricsCase):
    def test_json_shape(self):
        self.write_ledger(lesson_line("L001", "session:api", 1, TODAY))
        data = self.metrics_json("--days", "2")
        self.assertEqual(sorted(data), ["eta_accuracy", "guard_fires", "lane_tag", "projects", "threshold", "window"])
        self.assertEqual(sorted(data["projects"][0]), ["day_source", "events_from", "events_log", "events_log_error",
                                                       "events_log_found", "lanes", "ledger", "ledger_found",
                                                       "recurred_after_move", "skipped"])
        self.assertEqual(sorted(data["projects"][0]["lanes"][0]),
                         ["added", "added_total", "exempt", "guarded", "lane", "lessons", "moved", "moved_recurred",
                          "repeated", "repeated_total", "repeats", "unguarded", "unguarded_repeats"])
        self.assertEqual(sorted(data["guard_fires"]), ["damaged", "error", "log", "log_found", "per_day",
                                                       "total"])

    def test_an_empty_or_missing_ledger_reports_no_lessons(self):
        code, out, err = self.run_cli("metrics")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("- no ledger file yet", out)
        self.assertIn("- no lessons", out)
        self.assertTrue(out.startswith("## Lesson metrics: 2026-11-13 to 2026-11-19 (7 days)"))
        self.write_ledger()
        self.assertEqual(self.metrics_json()["projects"][0]["lanes"], [])

    def test_bad_usage_is_refused(self):
        for argv, message in ((("--days", "0"), "--days must be 1 to 366"), (("--days", "367"), "1 to 366"),
                              (("--lane-tag", " "), "--lane-tag must not be empty"),
                              (("--ledger", str(self.dir / "none.md")), "no ledger at")):
            code, out, err = self.run_cli("metrics", *argv)
            self.assertEqual((code, out), (2, ""), argv)
            self.assertIn(message, err)

    def test_output_is_deterministic(self):
        self.write_ledger(lesson_line("L002", "session:b", 2, TODAY), lesson_line("L001", "session:a", 1, TODAY))
        first, second = self.run_cli("metrics")[1], self.run_cli("metrics")[1]
        self.assertEqual(first, second)
        self.assertLess(first.index("| a |"), first.index("| b |"))

    def test_metrics_writes_nothing(self):
        self.write_ledger(lesson_line("L001", "", 1, TODAY))
        before = sorted(p.name for p in self.file.parent.iterdir())
        self.run_cli("metrics")
        self.assertEqual(sorted(p.name for p in self.file.parent.iterdir()), before)

    def test_the_script_runs_as_a_command(self):
        self.write_ledger(lesson_line("L001", "session:api", 1, "2026-01-01"))
        env = {**{k: v for k, v in os.environ.items() if not k.startswith(("LESSONS_", "BUS_"))}, **self.env}
        done = subprocess.run([sys.executable, str(Path(lessons.__file__).resolve()), "--file", str(self.file),
                               "metrics", "--json", "--days", "1"], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["projects"][0]["lanes"][0]["lessons"], 1)


if __name__ == "__main__":
    unittest.main()
