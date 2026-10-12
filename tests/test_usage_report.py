"""Unit tests for the autonomous-run skill's token usage report."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "autonomous-run" / "scripts"))

import usage_report  # noqa: E402

SINCE = datetime(2024, 3, 10, 12, 0, tzinfo=timezone.utc)
AFTER = "2024-03-10T13:00:00.000Z"


def entry(message_id="m1", request_id="r1", timestamp=AFTER, **usage):
    message = {"usage": usage}
    if message_id is not None:
        message["id"] = message_id
    record = {"timestamp": timestamp, "message": message}
    if request_id is not None:
        record["requestId"] = request_id
    return json.dumps(record)


class UsageReportTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def write(self, relative, *lines):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def report(self, top=5):
        files = usage_report.transcript_files(self.root)
        return usage_report.summarise(usage_report.read_lines(self.root, files, SINCE), SINCE, top)

    def run_cli(self, *arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            status = usage_report.main(["--dir", str(self.root), *arguments])
        return status, output.getvalue()

    def test_empty_directory_reports_zero(self):
        report = self.report()
        self.assertEqual(report["requests"], 0)
        self.assertEqual(report["groups"], [])
        self.assertEqual(set(report["totals"].values()), {0})
        status, text = self.run_cli("--since", "2024-03-10T12:00:00Z")
        self.assertEqual(status, 0)
        self.assertIn("files 0 | requests 0", text)

    def test_malformed_lines_are_ignored_and_counted(self):
        self.write(
            "a/s.jsonl",
            '{"message": {"usage": ',
            '["usage"]',
            '{"message": "usage", "note": "usage"}',
            '{"timestamp": "not a time", "message": {"usage": {"output_tokens": 9}}}',
            '{"timestamp": 5, "message": {"usage": {"output_tokens": 9}}}',
            '{"timestamp": "' + AFTER + '", "message": {"usage": "none"}}',
            "",
            "plain text without the marker",
            entry(output_tokens=7),
        )
        (self.root / "a" / "binary.jsonl").write_bytes(b'\xff\xfe"usage"\x00\n')
        (self.root / "a" / "notes.txt").write_text(entry("other", output_tokens=100), encoding="utf-8")
        report = self.report()
        self.assertEqual(report["requests"], 1)
        self.assertEqual(report["totals"]["output"], 7)
        self.assertEqual(report["ignored_lines"], 7)

    def test_duplicates_count_once(self):
        self.write("a/one.jsonl", entry(output_tokens=5), entry(output_tokens=5))
        self.write("b/two.jsonl", entry(output_tokens=5), entry("m1", "r2", output_tokens=3),
                   entry("m2", "r1", output_tokens=2))
        report = self.report()
        self.assertEqual(report["requests"], 3)
        self.assertEqual(report["totals"]["output"], 10)

    def test_lines_without_any_id_are_each_counted(self):
        self.write("a/s.jsonl", entry(None, None, output_tokens=4), entry(None, None, output_tokens=4),
                   entry("m1", None, output_tokens=1), entry("m1", None, output_tokens=1))
        report = self.report()
        self.assertEqual(report["requests"], 3)
        self.assertEqual(report["totals"]["output"], 9)

    def test_since_cut_off_includes_the_boundary(self):
        self.write("a/s.jsonl",
                   entry("before", timestamp="2024-03-10T11:59:59.999Z", output_tokens=100),
                   entry("boundary", timestamp="2024-03-10T12:00:00Z", output_tokens=10),
                   entry("offset", timestamp="2024-03-10T14:00:00+02:00", output_tokens=1),
                   entry("naive-utc", timestamp="2024-03-10T11:00:00", output_tokens=1000))
        report = self.report()
        self.assertEqual(report["requests"], 2)
        self.assertEqual(report["totals"]["output"], 11)
        self.assertEqual(report["since"], "2024-03-10T12:00:00+00:00")

    def test_since_hour_resolves_in_the_named_time_zone(self):
        zone = ZoneInfo("Africa/Cairo")  # UTC+2 with no daylight saving on these dates
        afternoon = datetime(2024, 1, 15, 13, 30, tzinfo=timezone.utc)
        self.assertEqual(usage_report.resolve_since(afternoon, zone, since_hour=14),
                         datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc))
        morning = datetime(2024, 1, 15, 11, 59, tzinfo=timezone.utc)
        self.assertEqual(usage_report.resolve_since(morning, zone, since_hour=14),
                         datetime(2024, 1, 14, 12, 0, tzinfo=timezone.utc))
        exact = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(usage_report.resolve_since(exact, zone, since_hour=14), exact)
        self.assertEqual(usage_report.resolve_since(afternoon, zone),
                         datetime(2024, 1, 14, 22, 0, tzinfo=timezone.utc))

    def test_explicit_since_uses_its_offset_or_the_named_zone(self):
        now = datetime(2024, 7, 1, tzinfo=timezone.utc)
        new_york = ZoneInfo("America/New_York")  # UTC-4 in July
        self.assertEqual(usage_report.resolve_since(now, new_york, "2024-07-01T08:00:00"),
                         datetime(2024, 7, 1, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(usage_report.resolve_since(now, new_york, "2024-07-01T08:00:00Z"),
                         datetime(2024, 7, 1, 8, 0, tzinfo=timezone.utc))
        for since_text, since_hour in (("yesterday", None), (None, 24), (None, -1)):
            with self.subTest(since_text=since_text, since_hour=since_hour):
                with self.assertRaises(ValueError):
                    usage_report.resolve_since(now, new_york, since_text, since_hour)

    def test_missing_and_invalid_usage_fields_count_as_zero(self):
        self.write("a/s.jsonl",
                   entry("empty"),
                   entry("partial", input_tokens=3, cache_read_input_tokens=40),
                   entry("odd", input_tokens="12", output_tokens=None, cache_creation_input_tokens=-5,
                         cache_read_input_tokens=True),
                   entry("full", input_tokens=1, output_tokens=2, cache_creation_input_tokens=3,
                         cache_read_input_tokens=4))
        report = self.report()
        self.assertEqual(report["requests"], 4)
        self.assertEqual(report["totals"], {"input": 4, "output": 2, "cache_write": 3, "cache_read": 44})
        self.assertEqual(report["fresh_input"], 7)

    def test_top_n_groups_by_first_folder_ordered_by_output(self):
        self.write("small/s.jsonl", entry("s", output_tokens=1))
        self.write("big/nested/deep/s.jsonl", entry("b1", output_tokens=50))
        self.write("big/other.jsonl", entry("b2", output_tokens=25, input_tokens=5))
        self.write("mid/s.jsonl", entry("m", output_tokens=30))
        self.write("top.jsonl", entry("t", output_tokens=2))
        groups = self.report(top=3)["groups"]
        self.assertEqual([group["name"] for group in groups], ["big", "mid", "."])
        self.assertEqual(groups[0], {"name": "big", "requests": 2, "input": 5, "output": 75,
                                     "cache_write": 0, "cache_read": 0})
        self.assertEqual(len(self.report(top=10)["groups"]), 4)
        self.assertEqual(self.report(top=0)["groups"], [])

    def test_cli_output_and_exit_codes(self):
        self.write("a/s.jsonl", entry(output_tokens=2_500_000, input_tokens=1_000_000))
        status, text = self.run_cli("--since", "2024-03-10T12:00:00Z", "--json", "--top", "1")
        self.assertEqual(status, 0)
        parsed = json.loads(text)
        self.assertEqual((parsed["files"], parsed["requests"], parsed["groups"][0]["name"]), (1, 1, "a"))
        status, text = self.run_cli("--since", "2024-03-10T14:00:00", "--tz", "Africa/Cairo")
        self.assertEqual(status, 0)
        self.assertIn("output 2.50M | fresh input 1.00M", text)
        self.assertIn("  a: requests 1, output 2.50M", text)
        self.assertEqual(self.run_cli("--tz", "Nowhere/Missing")[0], 2)
        self.assertEqual(self.run_cli("--since", "yesterday")[0], 2)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(usage_report.main(["--dir", str(self.root / "missing")]), 2)
            with self.assertRaises(SystemExit):
                usage_report.main(["--dir", str(self.root), "--since", "2024-03-10", "--since-hour", "3"])


if __name__ == "__main__":
    unittest.main()
