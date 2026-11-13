"""Tests for scripts/token_benchmark.py. Run: python3 -m unittest discover -s tests -p "test_*.py" """
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa: E402
import token_benchmark as bench  # noqa: E402

RESULT = None


def setUpModule():
    global RESULT
    RESULT = bench.measure()


def run_main(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = bench.main(list(argv))
        except SystemExit as stop:
            code = stop.code
    return code, out.getvalue(), err.getvalue()


def table_numbers(report, label):
    """The numeric cells of the report row whose first cell starts with `label`."""
    rows = [line for line in report.splitlines() if line.startswith(f"| {label}")]
    assert len(rows) == 1, (label, rows)
    return [int(cell.replace(",", "")) for cell in rows[0].strip("| ").split(" | ")[1:]]


def part(name):
    return next(row for row in RESULT["always_on"] if name in row["component"])


class MeasuredFromFilesTests(unittest.TestCase):
    def test_skill_listing_is_built_from_every_skill_description(self):
        names = sorted(p.name for p in (ROOT / ".agents" / "skills").iterdir() if p.is_dir())
        rows = bench.skill_files(names)
        self.assertEqual(part("Skill listing")["chars"], len(bench.listing((n, d) for n, d, _, _ in rows)))
        self.assertIn(f"({len(names)} names", part("Skill listing")["component"])
        self.assertGreater(sum(len(d) for _, d, _, _ in rows), 0)

    def test_listing_format_and_empty_listing(self):
        self.assertEqual(bench.listing([("a", "does a"), ("b", "does b")]), "- arsenal:a: does a\n- arsenal:b: does b")
        self.assertEqual(bench.listing([]), "")

    def test_core_hook_size_is_the_core_file(self):
        core = (ROOT / "hooks" / "core.md").read_text(encoding="utf-8").strip()
        self.assertEqual(part("session_core.py")["chars"], len(core))

    def test_unconditional_rules_are_the_generated_claude_rules_without_paths(self):
        files = sorted((ROOT / "dist" / "claude" / "rules").glob("*.md"))
        unscoped = [f for f in files if not f.read_text(encoding="utf-8").startswith("---\npaths:")]
        self.assertEqual(RESULT["unconditional_rules"], [f.stem for f in unscoped])
        self.assertEqual(part("Rules without a path scope")["chars"],
                         sum(len(f.read_text(encoding="utf-8")) for f in unscoped))
        self.assertEqual(len(RESULT["unconditional_rules"]) + len(RESULT["path_scoped_rules"]), len(files))

    def test_project_scope_adds_the_instruction_blocks_and_global_scope_does_not(self):
        sources = build.load_sources()
        self.assertEqual(bench.claude_install(sources, "global")[2], {})
        blocks = bench.claude_install(sources, "project")[2]
        self.assertEqual(blocks["AGENTS.md"], (ROOT / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(part("`AGENTS.md` block")["chars"], len(blocks["AGENTS.md"]))

    def test_routes_are_sums_of_their_components(self):
        plugin, with_rules, project = RESULT["routes"]
        plugin_chars = sum(row["chars"] for row in RESULT["always_on"]
                           if "Rules" not in row["component"] and "block" not in row["component"])
        self.assertEqual(plugin["chars"], plugin_chars)
        self.assertEqual(with_rules["chars"], plugin_chars + part("Rules without")["chars"])
        self.assertEqual(project["chars"], sum(row["chars"] for row in RESULT["always_on"]))
        for row in RESULT["routes"]:
            self.assertEqual(row["tokens"], round(row["chars"] / 4))
            self.assertGreater(row["worst_chars"], row["chars"])

    def test_on_demand_sizes_match_the_files(self):
        sizes = [len(p.read_text(encoding="utf-8")) for p in (ROOT / ".agents" / "skills").glob("*/SKILL.md")]
        skills = RESULT["on_demand"][0]
        self.assertEqual((skills["files"], skills["min"], skills["max"], skills["total"]),
                         (len(sizes), min(sizes), max(sizes), sum(sizes)))
        self.assertTrue(skills["min"] <= skills["median"] <= skills["max"])

    def test_result_has_no_machine_specific_text(self):
        self.assertNotIn(str(ROOT), json.dumps(RESULT))
        self.assertNotIn(str(ROOT), bench.render(RESULT))


class ReportTests(unittest.TestCase):
    def test_table_and_json_agree(self):
        report = bench.render(RESULT)
        for row in RESULT["always_on"]:
            self.assertEqual(table_numbers(report, f"{row['component']} ({row['source']})"),
                             [row["chars"], row["tokens"]])
        for row in RESULT["worst_case_hooks"]:
            self.assertEqual(table_numbers(report, f"{row['component']} ({row['source']})"),
                             [row["chars"], row["tokens"]])
        for row in RESULT["routes"]:
            self.assertEqual(table_numbers(report, f"{row['route']} |"),
                             [row["chars"], row["tokens"], row["worst_chars"], row["worst_tokens"]])
        for row in RESULT["on_demand"]:
            self.assertEqual(table_numbers(report, row["component"]),
                             [row[key] for key in ("files", "min", "median", "max", "total", "total_tokens")])

    def test_report_states_the_estimate_and_how_to_regenerate(self):
        report = bench.render(RESULT)
        self.assertTrue(report.startswith(bench.NOTICE))
        self.assertIn("python3 scripts/token_benchmark.py", bench.NOTICE)
        self.assertIn("an estimate, not a tokenizer count", report)
        self.assertNotIn("upper bound", report)  # the recorded live run is above the estimate
        self.assertNotIn("—", report)

    def test_json_mode_prints_the_measurement(self):
        code, out, _ = run_main("--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), json.loads(json.dumps(RESULT)))

    def test_committed_report_is_current(self):
        self.assertEqual((ROOT / "docs" / "BENCHMARK.md").read_text(encoding="utf-8"), bench.render(RESULT))

    def test_check_detects_drift_and_a_missing_report(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(bench, "REPORT", Path(temp) / "B.md"), \
                mock.patch.object(bench, "ROOT", Path(temp)), mock.patch.object(bench, "measure", lambda: RESULT):
            self.assertEqual(run_main("--check")[0], 1)
            self.assertEqual(run_main()[0], 0)
            self.assertEqual(run_main("--check")[0], 0)
            bench.REPORT.write_text(bench.REPORT.read_text(encoding="utf-8").replace("8", "9", 1), encoding="utf-8")
            code, _, err = run_main("--check")
            self.assertEqual(code, 1)
            self.assertIn("stale docs/BENCHMARK.md", err)

    def test_source_error_exits_one_without_writing(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(bench, "REPORT", Path(temp) / "B.md"), \
                mock.patch.object(bench, "measure", side_effect=build.SourceError("bad source")):
            code, _, err = run_main()
            self.assertEqual(code, 1)
            self.assertIn("bad source", err)
            self.assertFalse(bench.REPORT.exists())


class HookMeasurementTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project, self.state = Path(temp.name) / "project", Path(temp.name) / "state"
        self.project.mkdir()
        self.state.mkdir()

    def test_every_session_start_command_runs_in_an_empty_project(self):
        outputs = bench.run_session_start(self.project, self.state)
        self.assertEqual(len(outputs), len(bench.session_start_commands()))
        self.assertIn("(no lessons yet)", outputs["lessons.py active --hook"])
        self.assertIn(bench.PLUGIN_ROOT_VAR, outputs["lessons.py active --hook"])
        self.assertNotIn(str(ROOT), "".join(outputs.values()))
        self.assertTrue(outputs["session_core.py"])
        self.assertEqual(list(self.project.iterdir()), [], "a hook wrote into the measured project")

    def test_a_crashing_hook_is_an_error_not_zero_characters(self):
        crashing = 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/no_such_hook.py" || python x'
        with mock.patch.object(bench, "session_start_commands", return_value=[crashing]):
            with self.assertRaisesRegex(RuntimeError, r"`no_such_hook\.py` exited [1-9]"):
                bench.run_session_start(self.project, self.state)
            with mock.patch.object(bench, "REPORT", self.state / "B.md"):
                code, _, err = run_main()
                self.assertEqual(code, 1)
                self.assertIn("error: SessionStart hook", err)
                self.assertFalse(bench.REPORT.exists())

    def test_full_ledger_holds_the_active_cap_and_is_cut_at_the_context_cap(self):
        count = bench.fill_ledger(self.project)
        text = bench.run_session_start(self.project, self.state)["lessons.py active --hook"]
        ledger = (self.project / ".agents" / "lessons.md").read_text(encoding="utf-8")
        self.assertEqual(ledger.count("\n- L"), count)
        self.assertNotIn("(no lessons yet)", text)
        self.assertLessEqual(len(text), bench.HOOK_CONTEXT_CAP)

    def test_matcher_selects_commands_by_source(self):
        startup, compact = bench.session_start_commands("startup"), bench.session_start_commands("compact")
        self.assertTrue(any("guard.py" in command for command in startup))
        self.assertFalse(any("guard.py" in command for command in compact))
        self.assertEqual(bench.session_start_commands("no-such-source"), [])

    def test_hook_argv_takes_the_first_alternative_with_this_interpreter(self):
        argv = bench.hook_argv('python3 "${CLAUDE_PLUGIN_ROOT}/hooks/x.py" show || python "${CLAUDE_PLUGIN_ROOT}/hooks/x.py" show')
        self.assertEqual(argv, [sys.executable, f"{ROOT.as_posix()}/hooks/x.py", "show"])

    def test_hook_context_reads_json_falls_back_to_text_and_caps(self):
        payload = json.dumps({"hookSpecificOutput": {"additionalContext": f"run {ROOT}/a.py"}})
        self.assertEqual(bench.hook_context(payload), "run ${CLAUDE_PLUGIN_ROOT}/a.py")
        self.assertEqual(bench.hook_context(" plain text \n"), "plain text")
        self.assertEqual(bench.hook_context(""), "")
        self.assertEqual(bench.hook_context('{"decision": "block"}'), '{"decision": "block"}')
        self.assertEqual(len(bench.hook_context("x" * (bench.HOOK_CONTEXT_CAP + 5))), bench.HOOK_CONTEXT_CAP)


def completed(stdout, returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="boom")


def recorded(creation):
    """One arm's run as live_run returns it."""
    return {"input_tokens": 2, "cache_creation_input_tokens": creation, "cache_read_input_tokens": 100,
            "output_tokens": 4, "total_cost_usd": 0.002, "num_turns": 1}


def usage(creation):
    """The part of the `claude -p --output-format json` result that live_run reads, plus a field it ignores."""
    run = recorded(creation)
    return {"is_error": False, "total_cost_usd": run["total_cost_usd"], "num_turns": run["num_turns"],
            "usage": {**{field: run[field] for field in bench.USAGE_FIELDS}, "service_tier": "standard"}}


class LiveModeTests(unittest.TestCase):
    def test_only_the_with_arm_loads_the_plugin_and_both_are_isolated_and_capped(self):
        task = bench.LIVE_TASKS["bugfix"]
        with_plugin = bench.live_command(task, "haiku", 0.1, True)
        without = bench.live_command(task, "haiku", 0.1, False)
        self.assertEqual([a for a in with_plugin if a not in without], ["--plugin-dir", str(ROOT)])
        for flag in ("--max-budget-usd", "--strict-mcp-config", "--setting-sources", "--no-session-persistence"):
            self.assertIn(flag, without)
        self.assertEqual(without[-len(task["flags"]):], task["flags"])

    def test_live_run_keeps_only_the_reported_usage_fields(self):
        with mock.patch.object(bench.subprocess, "run", return_value=completed(json.dumps(usage(7000)))) as run:
            got = bench.live_run(bench.LIVE_TASKS["bugfix"], "haiku", 0.1, False)
        self.assertEqual(got, recorded(7000))
        self.assertEqual(run.call_args.kwargs["input"], bench.LIVE_TASKS["bugfix"]["prompt"])

    def test_live_run_keeps_hook_state_out_of_the_real_temp_dir(self):
        with mock.patch.object(bench.subprocess, "run", return_value=completed(json.dumps(usage(1)))) as run:
            bench.live_run(bench.LIVE_TASKS["overhead"], "haiku", 0.1, True)
        env = run.call_args.kwargs["env"]
        self.assertEqual(len({env["TMPDIR"], env["TEMP"], env["TMP"]}), 1)
        self.assertNotIn(env["TMPDIR"], (tempfile.gettempdir(), run.call_args.kwargs["cwd"]))
        self.assertFalse(Path(env["TMPDIR"]).exists())  # removed with the run
        self.assertEqual(env["PATH"], bench.os.environ["PATH"])

    def test_live_run_fails_on_error_result_bad_json_and_missing_fields(self):
        for stdout in (json.dumps({**usage(1), "is_error": True}), "not json", "{}", json.dumps({"is_error": False})):
            with self.subTest(stdout=stdout), mock.patch.object(bench.subprocess, "run",
                                                                return_value=completed(stdout, 1)):
                with self.assertRaisesRegex(RuntimeError, "claude -p failed"):
                    bench.live_run(bench.LIVE_TASKS["overhead"], "haiku", 0.1, True)

    def test_live_records_each_arm_and_the_report_shows_means_and_unrun_tasks(self):
        runs = [recorded(17000), recorded(19000), recorded(7000), recorded(9000)]
        with tempfile.TemporaryDirectory() as temp, \
                mock.patch.object(bench, "LIVE_RECORD", Path(temp) / "live.json"), \
                mock.patch.object(bench, "REPORT", Path(temp) / "B.md"), mock.patch.object(bench, "ROOT", Path(temp)), \
                mock.patch.object(bench, "measure", lambda: {**RESULT, "live": bench.load_live()}), \
                mock.patch.object(bench.shutil, "which", return_value="/bin/claude"), \
                mock.patch.object(bench, "live_run", side_effect=runs), \
                mock.patch.object(bench.subprocess, "run", return_value=completed("2.1.0 (Claude Code)\n")):
            (Path(temp) / "VERSION").write_text("9.9.9\n", encoding="utf-8")
            self.assertEqual(run_main("--live", "--task", "overhead", "--runs", "2")[0], 0)
            record = json.loads(bench.LIVE_RECORD.read_text(encoding="utf-8"))
            report = bench.REPORT.read_text(encoding="utf-8")
        self.assertEqual((record["claude_version"], record["model"], record["arsenal_version"]),
                         ("2.1.0", "haiku", "9.9.9"))
        self.assertEqual([len(record["tasks"]["overhead"][arm]) for arm in ("with", "without")], [2, 2])
        self.assertIn("| `overhead`, with plugin | 2 | 2 | 18,000 | 100 | 4 | 0.0020 |", report)
        self.assertIn("| `overhead`, without plugin | 2 | 2 | 8,000 | 100 | 4 | 0.0020 |", report)
        self.assertIn("the plugin added 10,000 input-side tokens", report)
        self.assertIn("| `bugfix` | not yet run |", report)

    def run_live(self, temp, *argv, version="2.1.0"):
        with mock.patch.object(bench, "LIVE_RECORD", Path(temp) / "live.json"), \
                mock.patch.object(bench, "REPORT", Path(temp) / "B.md"), mock.patch.object(bench, "ROOT", Path(temp)), \
                mock.patch.object(bench, "measure", lambda: {**RESULT, "live": bench.load_live()}), \
                mock.patch.object(bench.shutil, "which", return_value="/bin/claude"), \
                mock.patch.object(bench, "live_run", return_value=recorded(5)), \
                mock.patch.object(bench.subprocess, "run", return_value=completed(f"{version} (Claude Code)\n")):
            (Path(temp) / "VERSION").write_text("9.9.9\n", encoding="utf-8")
            self.assertEqual(run_main("--live", *argv)[0], 0)
            return json.loads(bench.LIVE_RECORD.read_text(encoding="utf-8"))["tasks"]

    def test_a_single_task_run_keeps_the_other_tasks_only_under_the_same_conditions(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(sorted(self.run_live(temp, "--task", "overhead")), ["overhead"])
            self.assertEqual(sorted(self.run_live(temp, "--task", "bugfix")), ["bugfix", "overhead"])
            self.assertEqual(sorted(self.run_live(temp, "--task", "bugfix", "--model", "sonnet")), ["bugfix"])
            self.assertEqual(sorted(self.run_live(temp, "--task", "overhead", "--model", "sonnet")), ["bugfix", "overhead"])
            self.assertEqual(sorted(self.run_live(temp, "--task", "overhead", "--model", "sonnet", version="2.2.0")),
                             ["overhead"])
            (Path(temp) / "live.json").write_text("{damaged", encoding="utf-8")
            self.assertEqual(sorted(self.run_live(temp, "--task", "bugfix", "--model", "sonnet", version="2.2.0")),
                             ["bugfix"])

    def test_a_damaged_record_is_an_error_message_not_a_traceback(self):
        good = {"recorded": "2026-01-01", "claude_version": "2.1.0", "model": "haiku", "arsenal_version": "1.0.0",
                "tasks": {"overhead": {"with": [recorded(2)], "without": [recorded(1)]}}}
        damaged = [{**good, "tasks": {"overhead": {"with": [], "without": [recorded(1)]}}},
                   {**good, "tasks": {"overhead": {"with": [recorded(2)]}}},
                   {**good, "tasks": {"overhead": {"with": [{"input_tokens": 1}], "without": [recorded(1)]}}},
                   {**good, "tasks": {"overhead": {"with": "x", "without": [recorded(1)]}}},
                   {**good, "tasks": ["overhead"]}, {**good, "model": None}, {"tasks": {}}, [1], "text"]
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(bench, "LIVE_RECORD", Path(temp) / "live.json"):
            bench.LIVE_RECORD.write_text(json.dumps(good), encoding="utf-8")
            self.assertEqual(bench.load_live(), good)
            for record in damaged:
                bench.LIVE_RECORD.write_text(json.dumps(record), encoding="utf-8")
                with self.subTest(record=record):
                    code, _, err = run_main("--check")
                    self.assertEqual(code, 1)
                    self.assertIn("error: live.json: each task needs a non-empty", err)

    def test_live_only_options_are_refused_without_live(self):
        for argv in (["--check", "--task", "bugfix"], ["--runs", "5"], ["--json", "--model", "sonnet"],
                     ["--check", "--max-budget-usd", "1"]):
            code, out, err = run_main(*argv)
            self.assertEqual((code, out), (2, ""), argv)
            self.assertIn("apply only with --live", err)

    def test_no_record_is_reported_as_not_yet_run(self):
        self.assertIn("Not yet run", "\n".join(bench.render_live(None, 1)))

    def test_missing_cli_and_bad_arguments_fail_without_a_record(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(bench, "LIVE_RECORD", Path(temp) / "live.json"), \
                mock.patch.object(bench.shutil, "which", return_value=None):
            code, _, err = run_main("--live")
            self.assertEqual(code, 1)
            self.assertIn("`claude` CLI is not on PATH", err)
            self.assertFalse(bench.LIVE_RECORD.exists())
        self.assertEqual(run_main("--live", "--runs", "0")[0], 2)
        self.assertEqual(run_main("--live", "--task", "no-such-task")[0], 2)


if __name__ == "__main__":
    unittest.main()
