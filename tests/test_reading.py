"""reading.py: a value read from a file is quoted with its age; stale, future and unreadable readings are refused."""
import json
import multiprocessing
import os
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "multi-session-delivery" / "scripts"))

import reading  # noqa: E402

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None

NOW = "2026-11-20T14:17:00+03:00"
EPOCH_1105Z = 1795172700  # 2026-11-20 11:05:00 UTC = 14:05 +03:00, 12 minutes before NOW


class ReadingTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        patcher = unittest.mock.patch.dict(os.environ, {"READING_NOW": NOW})
        patcher.start()
        self.addCleanup(patcher.stop)

    def path(self, name="quota.json"):
        return Path(self.dir.name) / name

    def put(self, content, name="quota.json", mtime=EPOCH_1105Z):
        target = self.path(name)
        target.write_text(content if isinstance(content, str) else json.dumps(content))
        os.utime(target, (mtime, mtime))
        return str(target)

    def run_cmd(self, *args):
        out, err = [], []
        code = reading.main(list(args), out=out.append, err=err.append)
        return code, "\n".join(out), "\n".join(err)


class GetFreshnessTests(ReadingTestCase):
    def test_fresh_json_value_prints_value_time_and_age(self):
        f = self.put({"quota": "98%", "as_of": "2026-11-20T14:05:00+03:00"})
        self.assertEqual(
            self.run_cmd("get", f, "--key", "quota", "--max-age", "30m"),
            (0, "98% (as of 2026-11-20 14:05 +03:00, 12 min old)", ""),
        )

    def test_stale_reports_age_and_limit(self):
        f = self.put({"quota": "80%", "as_of": "2026-11-20T13:00:00+03:00"})
        code, out, _ = self.run_cmd("get", f, "--key", "quota", "--max-age", "30m")
        self.assertEqual(
            (code, out), (1, "STALE: 80% (as of 2026-11-20 13:00 +03:00, 1 h 17 min old; limit 30 min)")
        )

    def test_exactly_max_age_is_fresh(self):
        f = self.put({"quota": "1", "as_of": "2026-11-20T13:47:00+03:00"})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota", "--max-age", "30m")[0], 0)

    def test_one_second_past_max_age_is_stale(self):
        f = self.put({"quota": "1", "as_of": "2026-11-20T13:46:59+03:00"})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota", "--max-age", "30m")[0], 1)

    def test_no_max_age_never_stale(self):
        f = self.put({"quota": "1", "as_of": "2026-11-10T14:17:00+03:00"})
        code, out, _ = self.run_cmd("get", f, "--key", "quota")
        self.assertEqual((code, out), (0, "1 (as of 2026-11-10 14:17 +03:00, 10 d old)"))

    def test_max_age_units_hours_days_seconds(self):
        f = self.put({"quota": "1", "as_of": "2026-11-20T12:17:00+03:00"})  # 2 h old
        self.assertEqual(self.run_cmd("get", f, "--key", "quota", "--max-age", "2h")[0], 0)
        self.assertEqual(self.run_cmd("get", f, "--key", "quota", "--max-age", "119m")[0], 1)
        self.assertEqual(self.run_cmd("get", f, "--key", "quota", "--max-age", "1d")[0], 0)
        self.assertEqual(self.run_cmd("get", f, "--key", "quota", "--max-age", "7199s")[0], 1)

    def test_age_under_a_minute_shows_zero_min(self):
        f = self.put({"quota": "1", "as_of": "2026-11-20T14:16:30+03:00"})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota")[1], "1 (as of 2026-11-20 14:16 +03:00, 0 min old)")

    def test_days_age_format(self):
        f = self.put({"quota": "1", "as_of": "2026-11-18T12:17:00+03:00"})  # 2 d 2 h
        code, out, _ = self.run_cmd("get", f, "--key", "quota", "--max-age", "1d")
        self.assertEqual((code, out), (1, "STALE: 1 (as of 2026-11-18 12:17 +03:00, 2 d 2 h old; limit 1 d)"))

    def test_whole_hours_drop_the_minutes(self):
        f = self.put({"quota": "1", "as_of": "2026-11-20T11:17:00+03:00"})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota")[1], "1 (as of 2026-11-20 11:17 +03:00, 3 h old)")


class TimeSourceTests(ReadingTestCase):
    def test_epoch_seconds_field(self):
        f = self.put({"quota": "98%", "as_of": EPOCH_1105Z})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota")[1], "98% (as of 2026-11-20 14:05 +03:00, 12 min old)")

    def test_z_suffix_and_other_offset_shown_in_its_own_offset(self):
        f = self.put({"quota": "98%", "as_of": "2026-11-20T11:05:00Z"})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota")[1], "98% (as of 2026-11-20 11:05 +00:00, 12 min old)")

    def test_default_time_keys(self):
        for key in ("as_of", "updated_at", "timestamp", "time"):
            f = self.put({"quota": "1", key: "2026-11-20T14:05:00+03:00"})
            self.assertEqual(self.run_cmd("get", f, "--key", "quota")[1][:2], "1 ", key)
            self.assertIn("(as of 2026-11-20 14:05", self.run_cmd("get", f, "--key", "quota")[1], key)

    def test_as_of_wins_over_later_default_keys(self):
        f = self.put({"quota": "1", "as_of": "2026-11-20T14:05:00+03:00", "time": "2020-01-01T00:00:00+00:00"})
        self.assertIn("14:05", self.run_cmd("get", f, "--key", "quota")[1])

    def test_updated_at_wins_over_timestamp_and_time(self):
        f = self.put({"quota": "1", "updated_at": "2026-11-20T14:05:00+03:00", "timestamp": "2020-01-01T00:00:00+00:00"})
        self.assertIn("14:05", self.run_cmd("get", f, "--key", "quota")[1])

    def test_explicit_time_key(self):
        f = self.put({"quota": "1", "as_of": "2020-01-01T00:00:00+00:00", "seen": "2026-11-20T14:05:00+03:00"})
        self.assertIn("14:05", self.run_cmd("get", f, "--key", "quota", "--time-key", "seen")[1])

    def test_missing_explicit_time_key_is_unreadable(self):
        f = self.put({"quota": "1", "as_of": "2026-11-20T14:05:00+03:00"})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota", "--time-key", "seen")[0], 2)

    def test_no_time_field_falls_back_to_mtime_and_says_so(self):
        f = self.put({"quota": "98%"})
        self.assertEqual(
            self.run_cmd("get", f, "--key", "quota", "--max-age", "30m"),
            (0, "98% (file modified 2026-11-20 14:05 +03:00, 12 min old)", ""),
        )

    def test_stale_by_mtime(self):
        f = self.put({"quota": "98%"}, mtime=EPOCH_1105Z - 3600)
        code, out, _ = self.run_cmd("get", f, "--key", "quota", "--max-age", "30m")
        self.assertEqual(
            (code, out), (1, "STALE: 98% (file modified 2026-11-20 13:05 +03:00, 1 h 12 min old; limit 30 min)")
        )

    def test_unparseable_time_value_is_unreadable_not_mtime(self):
        f = self.put({"quota": "1", "as_of": "yesterday"})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota")[0], 2)

    def test_time_without_offset_is_unreadable(self):
        f = self.put({"quota": "1", "as_of": "2026-11-20T14:05:00"})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota")[0], 2)

    def test_boolean_time_is_unreadable(self):
        f = self.put({"quota": "1", "as_of": True})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota")[0], 2)

    def test_out_of_range_epoch_is_unreadable(self):
        f = self.put({"quota": "1", "as_of": 1e30})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota")[0], 2)


class PlainTextTests(ReadingTestCase):
    def test_plain_text_value_is_whole_stripped_content_with_mtime(self):
        f = self.put("  98%\n", name="quota.txt")
        self.assertEqual(self.run_cmd("get", f), (0, "98% (file modified 2026-11-20 14:05 +03:00, 12 min old)", ""))

    def test_multiline_text_kept_inside(self):
        f = self.put("a\nb\n", name="s.txt")
        self.assertTrue(self.run_cmd("get", f)[1].startswith("a\nb (file modified"))

    def test_bare_number_file_is_text(self):
        f = self.put("98", name="n.txt")
        self.assertTrue(self.run_cmd("get", f)[1].startswith("98 (file modified"))

    def test_key_on_plain_text_is_unreadable(self):
        f = self.put("98%", name="quota.txt")
        self.assertEqual(self.run_cmd("get", f, "--key", "quota")[0], 2)

    def test_empty_text_is_unreadable(self):
        f = self.put("  \n", name="e.txt")
        self.assertEqual(self.run_cmd("get", f)[0], 2)

    def test_oversized_file_is_unreadable(self):
        f = self.put("x" * (64 * 1024 + 1), name="big.txt")
        self.assertEqual(self.run_cmd("get", f)[0], 2)

    def test_file_of_exactly_the_limit_is_read(self):
        f = self.put("x" * (64 * 1024), name="max.txt")
        self.assertEqual(self.run_cmd("get", f)[0], 0)

    def test_binary_file_is_unreadable(self):
        target = self.path("b.bin")
        target.write_bytes(b"\xff\xfe\x00")
        self.assertEqual(self.run_cmd("get", str(target))[0], 2)


class UnreadableTests(ReadingTestCase):
    def test_missing_file(self):
        code, _, err = self.run_cmd("get", str(self.path("nope.json")), "--key", "quota")
        self.assertEqual(code, 2)
        self.assertIn("nope.json", err)

    def test_missing_key(self):
        f = self.put({"other": 1, "as_of": "2026-11-20T14:05:00+03:00"})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota")[0], 2)

    def test_null_value_counts_as_missing(self):
        f = self.put({"quota": None, "as_of": "2026-11-20T14:05:00+03:00"})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota")[0], 2)

    def test_json_object_needs_a_key(self):
        f = self.put({"quota": "1", "as_of": "2026-11-20T14:05:00+03:00"})
        self.assertEqual(self.run_cmd("get", f)[0], 2)

    def test_directory_is_unreadable(self):
        self.assertEqual(self.run_cmd("get", self.dir.name)[0], 2)

    def test_bad_clock_env(self):
        f = self.put({"quota": "1", "as_of": NOW})
        with unittest.mock.patch.dict(os.environ, {"READING_NOW": "soon"}):
            self.assertEqual(self.run_cmd("get", f, "--key", "quota")[0], 2)

    def test_bad_max_age_values(self):
        f = self.put({"quota": "1", "as_of": NOW})
        for bad in ("", "30", "m", "-5m", "1.5h", "0m", "5w", "abc", "30 m"):
            self.assertEqual(self.run_cmd("get", f, "--key", "quota", "--max-age", bad)[0], 2, repr(bad))

    def test_unknown_command_is_a_usage_error(self):
        self.assertEqual(self.run_cmd("frobnicate")[0], 2)


class FutureTests(ReadingTestCase):
    def test_future_beyond_tolerance_is_reported_not_fresh(self):
        f = self.put({"quota": "98%", "as_of": "2026-11-20T14:30:00+03:00"})
        code, out, _ = self.run_cmd("get", f, "--key", "quota", "--max-age", "30m")
        self.assertEqual((code, out), (1, "FUTURE: 98% (as of 2026-11-20 14:30 +03:00, 13 min ahead of the clock)"))

    def test_future_reported_even_without_max_age(self):
        f = self.put({"quota": "98%", "as_of": "2026-11-20T14:30:00+03:00"})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota")[0], 1)

    def test_two_minutes_ahead_is_tolerated_as_zero_age(self):
        f = self.put({"quota": "1", "as_of": "2026-11-20T14:19:00+03:00"})
        self.assertEqual(
            self.run_cmd("get", f, "--key", "quota", "--max-age", "5m"),
            (0, "1 (as of 2026-11-20 14:19 +03:00, 0 min old)", ""),
        )

    def test_just_over_tolerance_is_future(self):
        f = self.put({"quota": "1", "as_of": "2026-11-20T14:19:01+03:00"})
        self.assertEqual(self.run_cmd("get", f, "--key", "quota")[0], 1)

    def test_future_mtime(self):
        f = self.put({"quota": "1"}, mtime=EPOCH_1105Z + 3600)
        code, out, _ = self.run_cmd("get", f, "--key", "quota")
        self.assertEqual((code, out[:7]), (1, "FUTURE:"))
        self.assertIn("file modified", out)


class JsonOutputTests(ReadingTestCase):
    def test_fresh_shape(self):
        f = self.put({"quota": "98%", "as_of": "2026-11-20T14:05:00+03:00"})
        code, out, _ = self.run_cmd("get", f, "--key", "quota", "--max-age", "30m", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out),
            {
                "value": "98%",
                "time": "2026-11-20T14:05:00+03:00",
                "source": "field:as_of",
                "age_seconds": 720,
                "max_age_seconds": 1800,
                "status": "fresh",
            },
        )

    def test_stale_and_future_status_with_exit(self):
        f = self.put({"quota": 98, "as_of": "2026-11-20T13:00:00+03:00"})
        code, out, _ = self.run_cmd("get", f, "--key", "quota", "--max-age", "30m", "--json")
        data = json.loads(out)
        self.assertEqual((code, data["status"], data["value"], data["age_seconds"]), (1, "stale", 98, 4620))
        g = self.put({"quota": 1, "as_of": "2026-11-20T14:30:00+03:00"}, name="g.json")
        code, out, _ = self.run_cmd("get", g, "--key", "quota", "--json")
        self.assertEqual((code, json.loads(out)["status"]), (1, "future"))

    def test_mtime_source_and_no_limit(self):
        f = self.put({"quota": "x"})
        _, out, _ = self.run_cmd("get", f, "--key", "quota", "--json")
        data = json.loads(out)
        self.assertEqual(
            (data["source"], data["max_age_seconds"], data["time"]),
            ("file modified", None, "2026-11-20T14:05:00+03:00"),
        )

    def test_structured_value_text_form_is_json(self):
        f = self.put({"quota": {"a": 1}, "as_of": "2026-11-20T14:05:00+03:00"})
        self.assertTrue(self.run_cmd("get", f, "--key", "quota")[1].startswith('{"a": 1} (as of'))


def write_worker(path, number):
    os.environ["READING_NOW"] = NOW
    code = reading.main(["write", path, "--key", f"k{number}", "--value", str(number)], out=lambda _: None)
    os._exit(code)


class PerKeyTimeTests(ReadingTestCase):
    A, B = "2026-11-20T14:05:00+03:00", "2026-11-20T13:00:00+03:00"

    def get(self, data, *extra):
        return self.run_cmd("get", self.put(data), "--key", "quota", *extra)

    def test_entry_written_by_write_uses_its_own_time(self):
        code, out, _ = self.get({"quota": {"value": "98%", "as_of": self.A}, "as_of": self.B})
        self.assertEqual((code, out), (0, "98% (as of 2026-11-20 14:05 +03:00, 12 min old)"))

    def test_key_specific_field_beats_file_wide_time(self):
        self.assertIn("14:05", self.get({"quota": "1", "quota_as_of": self.A, "as_of": self.B})[1])
        self.assertIn("14:05", self.get({"quota": "1", "quota_updated_at": self.A, "time": self.B})[1])

    def test_key_specific_names_in_order(self):
        data = {"quota": "1", "quota_time": self.B, "quota_updated_at": self.A}
        self.assertIn("14:05", self.get(data)[1])

    def test_own_entry_beats_key_specific_field(self):
        data = {"quota": {"value": "1", "as_of": self.A}, "quota_as_of": self.B}
        self.assertIn("14:05", self.get(data)[1])

    def test_explicit_time_key_applies_to_entry_key_specific_and_file_wide(self):
        self.assertIn("14:05", self.get({"quota": {"value": "1", "seen": self.A}}, "--time-key", "seen")[1])
        self.assertIn("14:05", self.get({"quota": "1", "quota_seen": self.A, "seen": self.B}, "--time-key", "seen")[1])
        self.assertIn("14:05", self.get({"quota": "1", "seen": self.A}, "--time-key", "seen")[1])

    def test_sources_name_where_the_time_came_from(self):
        def source(data):
            return json.loads(self.get(data, "--json")[1])["source"]
        self.assertEqual(source({"quota": {"value": "1", "as_of": self.A}}), "field:quota.as_of")
        self.assertEqual(source({"quota": "1", "quota_as_of": self.A}), "field:quota_as_of")
        self.assertEqual(source({"quota": "1", "as_of": self.A}), "field:as_of")

    def test_entry_value_is_unwrapped_and_structured_values_kept(self):
        self.assertTrue(self.get({"quota": {"value": {"a": 1}, "as_of": self.A}})[1].startswith('{"a": 1} (as of'))

    def test_dict_with_value_but_no_time_is_a_plain_structured_value(self):
        out = self.get({"quota": {"value": 1}, "as_of": self.A})[1]
        self.assertTrue(out.startswith('{"value": 1} (as of 2026-11-20 14:05'))

    def test_unreadable_own_time_is_an_error_not_a_fallback(self):
        self.assertEqual(self.get({"quota": {"value": "1", "as_of": "soon"}, "as_of": self.A})[0], 2)
        self.assertEqual(self.get({"quota": "1", "quota_as_of": "soon", "as_of": self.A})[0], 2)

    def test_null_time_fields_are_skipped(self):
        self.assertIn("14:05", self.get({"quota": "1", "as_of": None, "time": self.A})[1])
        self.assertIn("14:05", self.get({"quota": "1", "quota_as_of": None, "as_of": self.A})[1])

    def test_object_value_with_its_own_time_field_uses_it_and_hides_it(self):
        code, out, _ = self.get({"quota": {"pct": 80, "updated_at": self.A}})
        self.assertEqual((code, out), (0, '{"pct": 80} (as of 2026-11-20 14:05 +03:00, 12 min old)'))

    def test_object_time_beats_file_wide_time_and_mtime(self):
        out = self.get({"quota": {"pct": 80, "time": self.A}, "as_of": self.B})[1]
        self.assertIn("(as of 2026-11-20 14:05", out)

    def test_object_with_a_value_member_prints_that_member(self):
        self.assertEqual(self.get({"quota": {"value": "98%", "extra": 1, "timestamp": self.A}})[1],
                         "98% (as of 2026-11-20 14:05 +03:00, 12 min old)")

    def test_object_time_names_and_source(self):
        data = {"quota": {"pct": 80, "seen": self.A, "as_of": self.B}}
        self.assertEqual(json.loads(self.get(data, "--time-key", "seen", "--json")[1])["source"], "field:quota.seen")
        self.assertEqual(json.loads(self.get(data, "--json")[1])["source"], "field:quota.as_of")

    def test_unreadable_time_inside_an_object_is_an_error(self):
        self.assertEqual(self.get({"quota": {"pct": 80, "updated_at": "soon"}, "as_of": self.A})[0], 2)

    def test_entry_with_null_value_is_missing(self):
        self.assertEqual(self.get({"quota": {"value": None, "as_of": self.A}})[0], 2)

    def test_key_without_any_time_falls_to_mtime_even_when_another_key_has_one(self):
        out = self.get({"quota": "1", "other": {"value": "2", "as_of": self.A}})[1]
        self.assertIn("file modified", out)


class WriteTests(ReadingTestCase):
    def test_write_then_get_is_fresh_with_the_clock_time(self):
        f = str(self.path("w.json"))
        code, out, _ = self.run_cmd("write", f, "--key", "quota", "--value", "98%")
        self.assertEqual((code, out), (0, "ok w.json quota as of 2026-11-20 14:17 +03:00"))
        self.assertEqual(
            json.loads(Path(f).read_text()), {"quota": {"value": "98%", "as_of": "2026-11-20T14:17:00+03:00"}}
        )
        self.assertEqual(
            self.run_cmd("get", f, "--key", "quota", "--max-age", "30m"),
            (0, "98% (as of 2026-11-20 14:17 +03:00, 0 min old)", ""),
        )

    def test_write_keeps_other_keys_and_the_file_wide_time_untouched(self):
        f = self.put({"quota": "80%", "release": "r1", "as_of": "2026-11-20T10:00:00+03:00"})
        self.assertEqual(self.run_cmd("write", f, "--key", "quota", "--value", "98%")[0], 0)
        self.assertEqual(
            json.loads(Path(f).read_text()),
            {
                "quota": {"value": "98%", "as_of": "2026-11-20T14:17:00+03:00"},
                "release": {"value": "r1", "as_of": "2026-11-20T10:00:00+03:00"},
                "as_of": "2026-11-20T10:00:00+03:00",
            },
        )

    def test_write_leaves_no_temp_file(self):
        f = str(self.path("w.json"))
        self.run_cmd("write", f, "--key", "quota", "--value", "1")
        self.assertEqual(sorted(os.listdir(self.dir.name)), [".w.json.lock", "w.json"])

    def test_write_time_has_whole_seconds_only(self):
        f = str(self.path("w.json"))
        with unittest.mock.patch.dict(os.environ, {"READING_NOW": "2026-11-20T14:17:05.987654+03:00"}):
            self.run_cmd("write", f, "--key", "quota", "--value", "1")
        self.assertEqual(json.loads(Path(f).read_text())["quota"]["as_of"], "2026-11-20T14:17:05+03:00")

    def test_write_keeps_an_existing_file_mode_and_creates_new_ones_readable(self):
        f = self.put({"quota": "1"})
        os.chmod(f, 0o640)
        self.run_cmd("write", f, "--key", "quota", "--value", "2")
        self.assertEqual(os.stat(f).st_mode & 0o777, 0o640)
        g = str(self.path("new.json"))
        self.run_cmd("write", g, "--key", "quota", "--value", "2")
        self.assertEqual(os.stat(g).st_mode & 0o777, 0o644)

    def test_write_refuses_damaged_or_non_object_file(self):
        for body in ("[1]", "not json"):
            f = self.put(body, name="d.json")
            self.assertEqual(self.run_cmd("write", f, "--key", "quota", "--value", "1")[0], 2, body)
            self.assertEqual(Path(f).read_text(), body)

    def test_write_refuses_a_time_field_name_as_value_key(self):
        f = str(self.path("w.json"))
        for name in ("as_of", "updated_at", "timestamp", "time"):
            self.assertEqual(self.run_cmd("write", f, "--key", name, "--value", "1")[0], 2, name)
        self.assertFalse(Path(f).exists())

    def test_writing_one_key_never_refreshes_another(self):
        f = str(self.path("w.json"))
        with unittest.mock.patch.dict(os.environ, {"READING_NOW": "2026-11-19T20:17:00+03:00"}):
            self.run_cmd("write", f, "--key", "quota", "--value", "80%")
        self.run_cmd("write", f, "--key", "release", "--value", "r5")
        self.assertEqual(
            self.run_cmd("get", f, "--key", "quota", "--max-age", "30m"),
            (1, "STALE: 80% (as of 2026-11-19 20:17 +03:00, 18 h old; limit 30 min)", ""),
        )
        self.assertEqual(self.run_cmd("get", f, "--key", "release", "--max-age", "30m")[0], 0)

    def test_rewriting_a_key_refreshes_only_that_key(self):
        f = str(self.path("w.json"))
        with unittest.mock.patch.dict(os.environ, {"READING_NOW": "2026-11-19T20:17:00+03:00"}):
            self.run_cmd("write", f, "--key", "a", "--value", "1")
            self.run_cmd("write", f, "--key", "b", "--value", "2")
        self.run_cmd("write", f, "--key", "a", "--value", "3")
        self.assertEqual(self.run_cmd("get", f, "--key", "a", "--max-age", "30m"),
                         (0, "3 (as of 2026-11-20 14:17 +03:00, 0 min old)", ""))
        self.assertEqual(self.run_cmd("get", f, "--key", "b", "--max-age", "30m")[0], 1)

    def test_write_over_a_flat_file_keeps_its_old_reading_as_old(self):
        f = self.put({"quota": "80%", "as_of": "2026-11-20T10:00:00+03:00"})
        self.run_cmd("write", f, "--key", "release", "--value", "r5")
        self.assertEqual(json.loads(Path(f).read_text())["as_of"], "2026-11-20T10:00:00+03:00")
        self.assertEqual(self.run_cmd("get", f, "--key", "quota", "--max-age", "30m")[0], 1)

    def test_write_of_another_key_does_not_reset_a_flat_keys_age_from_mtime(self):
        f = self.put({"quota": "80%"}, mtime=EPOCH_1105Z - 2 * 86400)
        self.run_cmd("write", f, "--key", "other", "--value", "1")
        self.assertEqual(
            self.run_cmd("get", f, "--key", "quota", "--max-age", "30m"),
            (1, "STALE: 80% (as of 2026-11-18 14:05 +03:00, 2 d old; limit 30 min)", ""),
        )
        self.assertEqual(json.loads(Path(f).read_text())["quota"],
                         {"value": "80%", "as_of": "2026-11-18T14:05:00+03:00"})

    def test_write_stamps_flat_keys_from_their_own_time_source(self):
        f = self.put({
            "a": 1, "b": 2, "b_updated_at": "2026-11-20T09:00:00+03:00", "c": None, "d": {"x": 1},
            "e": {"value": 5, "as_of": "2026-11-20T08:00:00+03:00"}, "as_of": 1795172700,
        })
        self.run_cmd("write", f, "--key", "new", "--value", "n")
        data = json.loads(Path(f).read_text())
        stamp = "2026-11-20T14:05:00+03:00"
        self.assertEqual(data["a"], {"value": 1, "as_of": stamp})
        self.assertEqual(data["b"], {"value": 2, "as_of": "2026-11-20T09:00:00+03:00"})
        self.assertIsNone(data["c"])
        self.assertEqual(data["d"], {"value": {"x": 1}, "as_of": stamp})
        self.assertEqual(data["e"], {"value": 5, "as_of": "2026-11-20T08:00:00+03:00"})
        self.assertEqual((data["b_updated_at"], data["as_of"]), ("2026-11-20T09:00:00+03:00", 1795172700))
        self.assertEqual(data["new"], {"value": "n", "as_of": "2026-11-20T14:17:00+03:00"})

    def test_write_leaves_an_object_valued_key_with_its_own_time_alone(self):
        f = self.put({"quota": {"pct": 80, "updated_at": "2026-11-20T09:00:00+03:00"}})
        self.run_cmd("write", f, "--key", "new", "--value", "n")
        self.assertEqual(json.loads(Path(f).read_text())["quota"],
                         {"pct": 80, "updated_at": "2026-11-20T09:00:00+03:00"})

    def test_write_overwriting_a_flat_key_replaces_it_whole(self):
        f = self.put({"quota": "80%"}, mtime=EPOCH_1105Z - 86400)
        self.run_cmd("write", f, "--key", "quota", "--value", "99%")
        self.assertEqual(json.loads(Path(f).read_text()),
                         {"quota": {"value": "99%", "as_of": "2026-11-20T14:17:00+03:00"}})

    def test_overwriting_a_key_ignores_its_own_unreadable_old_time(self):
        f = self.put({"quota": "1", "quota_as_of": "soon"})
        self.assertEqual(self.run_cmd("write", f, "--key", "quota", "--value", "2")[0], 0)

    def test_stamped_time_has_whole_seconds_even_from_a_fractional_mtime(self):
        f = self.put({"quota": "80%"}, mtime=EPOCH_1105Z + 0.5)
        self.run_cmd("write", f, "--key", "other", "--value", "1")
        self.assertEqual(json.loads(Path(f).read_text())["quota"]["as_of"], "2026-11-20T14:05:00+03:00")

    def test_write_refuses_when_a_flat_keys_time_is_unreadable_and_changes_nothing(self):
        f = self.put({"quota": "80%", "as_of": "soon"})
        before = Path(f).read_text()
        self.assertEqual(self.run_cmd("write", f, "--key", "new", "--value", "1")[0], 2)
        self.assertEqual(Path(f).read_text(), before)

    def test_write_through_a_symlink_keeps_the_link_and_updates_the_target(self):
        real = self.path("real.json")
        real.write_text("{}")
        link = self.path("link.json")
        link.symlink_to(real)
        code, out, _ = self.run_cmd("write", str(link), "--key", "quota", "--value", "1")
        self.assertEqual((code, out), (0, "ok link.json quota as of 2026-11-20 14:17 +03:00"))
        self.assertTrue(link.is_symlink())
        self.assertEqual(json.loads(real.read_text())["quota"]["value"], "1")
        self.assertEqual(sorted(os.listdir(self.dir.name)), [".real.json.lock", "link.json", "real.json"])

    def test_write_through_a_dangling_symlink_creates_the_target(self):
        real, link = self.path("real.json"), self.path("link.json")
        link.symlink_to(real)
        self.assertEqual(self.run_cmd("write", str(link), "--key", "quota", "--value", "1")[0], 0)
        self.assertTrue(link.is_symlink() and real.exists())

    def test_get_through_a_symlink(self):
        real = self.put({"quota": "1", "as_of": NOW}, name="real.json")
        link = self.path("link.json")
        link.symlink_to(real)
        self.assertEqual(self.run_cmd("get", str(link), "--key", "quota")[0], 0)

    @unittest.skipUnless(fcntl, "flock only")
    def test_two_spellings_of_one_file_share_one_lock(self):
        real = self.path("real.json")
        link = self.path("link.json")
        real.write_text("{}")
        link.symlink_to(real)
        with open(self.path(".real.json.lock"), "a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            with unittest.mock.patch.object(reading, "LOCK_WAIT", 0.1):
                self.assertEqual(self.run_cmd("write", str(link), "--key", "q", "--value", "1")[0], 2)
                self.assertEqual(self.run_cmd("write", str(self.path("x/../real.json")), "--key", "q", "--value", "1")[0], 2)

    def test_parallel_writes_of_distinct_keys_are_all_kept(self):
        f = str(self.path("p.json"))
        context = multiprocessing.get_context("fork")
        procs = [context.Process(target=write_worker, args=(f, n)) for n in range(24)]
        for proc in procs:
            proc.start()
        for proc in procs:
            proc.join()
        self.assertEqual([p.exitcode for p in procs], [0] * 24)
        self.assertEqual(sorted(json.loads(Path(f).read_text())), sorted(f"k{n}" for n in range(24)))

    @unittest.skipUnless(fcntl, "flock only")
    def test_write_gives_up_when_the_lock_is_held(self):
        f = str(self.path("w.json"))
        with open(self.path(".w.json.lock"), "a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            with unittest.mock.patch.object(reading, "LOCK_WAIT", 0.1):
                code, _, err = self.run_cmd("write", f, "--key", "quota", "--value", "1")
        self.assertEqual(code, 2)
        self.assertIn("locked", err)
        self.assertFalse(Path(f).exists())

    def test_write_into_missing_directory_is_unwritable(self):
        f = str(self.path("no/dir/w.json"))
        self.assertEqual(self.run_cmd("write", f, "--key", "quota", "--value", "1")[0], 2)

    def test_write_with_bad_clock_writes_nothing(self):
        f = str(self.path("w.json"))
        with unittest.mock.patch.dict(os.environ, {"READING_NOW": "soon"}):
            self.assertEqual(self.run_cmd("write", f, "--key", "quota", "--value", "1")[0], 2)
        self.assertFalse(Path(f).exists())


class CheckReportTests(ReadingTestCase):
    def check(self, text, *args):
        return self.run_cmd("check-report", self.put(text, name="report.md"), *args)

    def test_clean_report_exits_zero(self):
        code, out, _ = self.check("Plan is on track.\nNext review tomorrow.\n")
        self.assertEqual((code, out), (0, "ok: no unmarked or stale readings"))

    def test_fresh_marker_with_full_time_passes(self):
        self.assertEqual(self.check("Quota 98% (as of 2026-11-20 14:05 +03:00)\n")[0], 0)

    def test_get_output_quoted_verbatim_passes(self):
        self.assertEqual(self.check("Quota 98% (as of 2026-11-20 14:05 +03:00, 12 min old)\n")[0], 0)
        self.assertEqual(self.check("Quota 98% (file modified 2026-11-20 14:05 +03:00, 12 min old)\n")[0], 0)

    def test_stale_marker_is_listed_with_line_number(self):
        code, out, _ = self.check("ok\nQuota 80% (as of 2026-11-20 08:00 +03:00)\n", "--max-age", "30m")
        self.assertEqual(code, 1)
        self.assertIn("STALE line 2: as of 2026-11-20 08:00 +03:00 is 6 h 17 min old (limit 30 min): Quota 80%", out)

    def test_stale_boundary_exactly_max_age_passes(self):
        self.assertEqual(self.check("x (as of 2026-11-20 13:47 +03:00)\n", "--max-age", "30m")[0], 0)
        self.assertEqual(self.check("x (as of 2026-11-20 13:46 +03:00)\n", "--max-age", "30m")[0], 1)

    def test_default_max_age_is_thirty_minutes(self):
        self.assertEqual(self.check("x (as of 2026-11-20 13:47 +03:00)\n")[0], 0)
        self.assertEqual(self.check("x (as of 2026-11-20 13:40 +03:00)\n")[0], 1)

    def test_time_only_marker_means_today_in_the_clock_offset(self):
        self.assertEqual(self.check("x (as of 14:05)\n")[0], 0)
        self.assertEqual(self.check("x (as of 13:00)\n")[0], 1)

    def test_time_with_offset_but_no_date_uses_that_offset(self):
        self.assertEqual(self.check("x (as of 11:05 +00:00)\n")[0], 0)

    def test_date_and_time_without_offset_uses_the_clock_offset(self):
        self.assertEqual(self.check("x (as of 2026-11-20 14:05)\n")[0], 0)

    def test_compact_offset_and_z(self):
        self.assertEqual(self.check("x (as of 2026-11-20 14:05 +0300)\n")[0], 0)
        self.assertEqual(self.check("x (as of 2026-11-20 11:05 Z)\n")[0], 0)

    def test_future_marker_is_flagged(self):
        code, out, _ = self.check("x (as of 2026-11-20 15:00 +03:00)\n")
        self.assertEqual(code, 1)
        self.assertIn("FUTURE line 1:", out)

    def test_time_only_later_today_is_future(self):
        self.assertEqual(self.check("x (as of 23:50)\n")[1].count("FUTURE line 1"), 1)

    def test_unreadable_marker_is_flagged(self):
        code, out, _ = self.check("x (as of lunchtime)\n")
        self.assertEqual(code, 1)
        self.assertIn("BAD-MARKER line 1:", out)

    def test_impossible_time_is_unreadable(self):
        self.assertIn("BAD-MARKER", self.check("x (as of 2026-13-40 25:61 +03:00)\n")[1])

    def test_percentage_without_marker_is_flagged(self):
        code, out, _ = self.check("Coverage is 91%\n")
        self.assertEqual(code, 1)
        self.assertIn("NO-MARKER line 1 (91%): Coverage is 91%", out)

    def test_decimal_percentage_and_space_before_sign(self):
        self.assertEqual(self.check("used 97.5 %\n")[0], 1)

    def test_default_status_words_flagged_case_insensitively_as_whole_words(self):
        for line in ("Quota fine", "usage high", "Release r5 out", "Deployed to staging", "CI is up", "build GREEN",
                     "pipeline red", "tests passing"):
            self.assertEqual(self.check(line + "\n")[0], 1, line)

    def test_substrings_of_status_words_are_not_flagged(self):
        for line in ("The reduced scope", "a greenfield start", "tired of it", "precision matters"):
            self.assertEqual(self.check(line + "\n")[0], 0, line)

    def test_custom_words_replace_the_default(self):
        self.assertEqual(self.check("CI is up\n", "--words", "queue,backlog")[0], 0)
        self.assertEqual(self.check("backlog is long\n", "--words", "queue, backlog")[0], 1)

    def test_empty_words_is_a_usage_error(self):
        self.assertEqual(self.check("x\n", "--words", " , ")[0], 2)

    def test_live_with_command_opts_a_line_out(self):
        self.assertEqual(self.check("CI green 100% (live: gh pr checks 12)\n")[0], 0)

    def test_bare_live_does_not_opt_out(self):
        code, out, _ = self.check("CI green (live)\n")
        self.assertEqual(code, 1)
        self.assertIn("NO-MARKER line 1", out)

    def test_live_with_empty_command_does_not_opt_out(self):
        self.assertEqual(self.check("CI green (live: )\n")[0], 1)

    def test_live_does_not_hide_a_stale_marker_on_the_same_line(self):
        code, out, _ = self.check("CI green (as of 2026-11-20 08:00 +03:00) (live: gh run list)\n")
        self.assertEqual(code, 1)
        self.assertIn("STALE line 1", out)

    def test_marked_line_with_flag_words_passes_when_fresh(self):
        self.assertEqual(self.check("CI green 100% (as of 2026-11-20 14:10 +03:00)\n")[0], 0)

    def test_a_fresh_marker_does_not_hide_a_second_reading_after_it(self):
        code, out, _ = self.check("quota 80% (as of 2026-11-20 14:10 +03:00); usage 98%\n")
        self.assertEqual(code, 1)
        self.assertIn("NO-MARKER line 1 (usage)", out)

    def test_a_semicolon_ends_the_text_a_marker_covers(self):
        code, out, _ = self.check("quota 80%; usage 98% (as of 2026-11-20 14:10 +03:00)\n")
        self.assertEqual(code, 1)
        self.assertIn("NO-MARKER line 1 (quota)", out)

    def test_two_markers_cover_two_readings(self):
        self.assertEqual(
            self.check("quota 80% (as of 14:10), usage 98% (as of 2026-11-20 14:12 +03:00)\n")[0], 0
        )

    def test_two_markers_but_a_third_reading_unmarked(self):
        code, out, _ = self.check("quota 80% (as of 14:10), usage 98% (as of 14:12) and CI green\n")
        self.assertEqual(code, 1)
        self.assertIn("NO-MARKER line 1 (CI)", out)

    def test_marker_then_unrelated_word_is_flagged(self):
        code, out, _ = self.check("Disk 50 GB (as of 14:10) and the release was fine\n")
        self.assertEqual(code, 1)
        self.assertIn("NO-MARKER line 1 (release)", out)

    def test_reading_before_its_marker_across_several_words_is_covered(self):
        self.assertEqual(self.check("the CI run is green and red at 100% (as of 14:10)\n")[0], 0)

    def test_reading_placed_after_its_marker_is_not_covered(self):
        self.assertEqual(self.check("(as of 14:10) quota 98%\n")[0], 1)

    def test_text_inside_a_marker_is_not_a_second_reading(self):
        code, out, _ = self.check("x (as of 14:10 passing)\n")
        self.assertEqual((code, out.count("NO-MARKER")), (1, 0))
        self.assertEqual(self.check("x (as of 14:10, the CI is green)\n")[0], 0)

    def test_live_still_silences_the_whole_line(self):
        self.assertEqual(self.check("quota 80% (as of 14:10); usage 98% (live: cat /run/usage)\n")[0], 0)

    def test_every_finding_listed_with_total(self):
        text = "a 50%\nb ok\nc quota (as of 2026-11-20 08:00 +03:00)\nd (as of nope)\n"
        code, out, _ = self.check(text)
        lines = out.splitlines()
        self.assertEqual(code, 1)
        self.assertEqual(
            [x.split(":")[0] for x in lines[:3]], ["NO-MARKER line 1 (50%)", "STALE line 3", "BAD-MARKER line 4"]
        )
        self.assertEqual(lines[-1], "3 finding(s)")

    def test_two_markers_one_stale(self):
        code, out, _ = self.check("a 1% (as of 14:10) b 2% (as of 08:00)\n")
        self.assertEqual((code, out.count("STALE")), (1, 1))

    def test_long_line_is_truncated_in_the_listing(self):
        _, out, _ = self.check("quota " + "z" * 300 + "\n")
        self.assertLess(len(out.splitlines()[0]), 200)

    def test_missing_report_and_bad_max_age_exit_two(self):
        self.assertEqual(self.run_cmd("check-report", str(self.path("nope.md")))[0], 2)
        self.assertEqual(self.check("x\n", "--max-age", "soon")[0], 2)

    def timed(self, text):
        started = time.monotonic()
        result = self.check(text)
        return result, time.monotonic() - started

    def test_a_huge_digit_line_is_a_finding_and_finishes_fast(self):
        (code, out, _), seconds = self.timed("1" * 200_000 + "\n")
        self.assertEqual(code, 1)
        self.assertIn("TOO-LONG line 1", out)
        self.assertLess(seconds, 1)

    def test_a_huge_marker_line_is_a_finding_and_finishes_fast(self):
        (code, out, _), seconds = self.timed("(as of " + " " * 100_000 + "\n")
        self.assertEqual(code, 1)
        self.assertIn("TOO-LONG line 1", out)
        self.assertLess(seconds, 1)

    def test_line_length_boundary(self):
        at_limit = "quota " + "z" * (reading.MAX_LINE - 6)
        self.assertEqual(len(at_limit), 4000)
        self.assertIn("NO-MARKER line 1", self.check(at_limit + "\n")[1])
        over = self.check(at_limit + "z\n")[1]
        self.assertIn("TOO-LONG line 1", over)
        self.assertNotIn("NO-MARKER", over)

    def test_a_long_line_does_not_hide_the_lines_after_it(self):
        code, out, _ = self.check("z" * 5000 + "\nquota 5%\n")
        self.assertEqual(code, 1)
        self.assertEqual([x.split(":")[0].split(" (")[0] for x in out.splitlines()[:2]],
                         ["TOO-LONG line 1", "NO-MARKER line 2"])

    def test_patterns_stay_linear_on_adversarial_text_far_beyond_the_cap(self):
        size = 100_000
        for text in ("1" * size, "(as of " + " " * size, "(as of 14:10," + "x" * size, "(live:" + " " * size,
                     "(live: x" * 50_000, "(as of 1" * (size // 8)):
            started = time.monotonic()
            reading.PERCENT_RE.search(text)
            reading.MARKER_RE.search(text)
            reading.LIVE_RE.search(text)
            self.assertLess(time.monotonic() - started, 1, text[:12])

    def test_empty_report_is_clean(self):
        self.assertEqual(self.check("")[0], 0)

    def test_report_bigger_than_the_bound_is_unreadable(self):
        self.assertEqual(self.check("x" * (1024 * 1024 + 1))[0], 2)

    def test_bad_clock_exit_two(self):
        with unittest.mock.patch.dict(os.environ, {"READING_NOW": "soon"}):
            self.assertEqual(self.check("x\n")[0], 2)



class HostileContentTests(ReadingTestCase):
    def test_deeply_nested_json_is_unreadable_not_stale(self):
        path = self.put("[" * 60000)
        self.assertEqual(self.run_cmd("get", path)[0], 2)
        written = self.put('{"a": ' + "[" * 30000 + "]" * 30000 + "}", name="deep.json")
        before = Path(written).read_text()
        self.assertEqual(self.run_cmd("write", written, "--key", "b", "--value", "1")[0], 2)
        self.assertEqual(Path(written).read_text(), before)  # untouched

    def test_a_lone_surrogate_value_prints_escaped_and_keeps_its_exit_code(self):
        import subprocess
        path = self.put('{"b": "\\ud800", "as_of": "2026-11-20T11:00:00+00:00"}')
        script = ROOT / ".agents" / "skills" / "multi-session-delivery" / "scripts" / "reading.py"
        env = {**os.environ, "READING_NOW": "2026-11-20T11:05:00+00:00", "PYTHONIOENCODING": "utf-8"}
        done = subprocess.run([sys.executable, str(script), "get", path, "--key", "b"], capture_output=True,
                              text=True, env=env, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("\\ud800", done.stdout)

if __name__ == "__main__":
    unittest.main()
