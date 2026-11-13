"""Unit tests for scripts/eval_report.py (results file and docs/EVALS.md table) and the paid Evals workflow."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_report  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "evals.yml"
USAGE = {"input_tokens": 10, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 2000, "output_tokens": 300}


def grader(name, passed, scored=True):
    return {"name": name, "passed": passed, "weight": 1, "explanation": "", "withOnly": not scored, "scored": scored}


def run(score, cost, turns, graders, trace=None, judge=0.001):
    return {"score": score, "passed": score == 1, "turns": turns, "costUsd": cost, "judgeCostUsd": judge,
            "durationSeconds": 30, "error": None, "tracePath": trace, "graders": graders}


def harness(with_runs, without_runs, partial=False):
    """The fields of a `claude plugin eval --json` result that the report reads (shape of Claude Code 2.1.321)."""
    return {
        "schemaVersion": 1, "claudeVersion": "2.1.321", "startedAt": "2026-11-13T09:11:43.367Z",
        "costUsd": sum(item["costUsd"] for item in with_runs + without_runs), "partial": partial,
        "suite": {"modelOverride": "haiku", "judgeModel": "haiku", "plugins": [{"name": "arsenal", "version": "1.3.1"}]},
        "cases": [{"name": "task-bugfix", "arms": {"with": with_runs, "without": without_runs}}],
    }


class ReportCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temp = Path(directory.name)
        self.doc = self.temp / "EVALS.md"
        self.doc.write_text(f"# Evals\n\nintro\n\n{eval_report.START}\n{eval_report.END}\n\ntail\n", encoding="utf-8")
        for name, path in (("RESULTS", self.temp / "eval-results.json"), ("DOC", self.doc)):
            patcher = mock.patch.object(eval_report, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)

    def trace(self, name, usage=USAGE):
        path = self.temp / f"{name}.jsonl"
        lines = [{"type": "system"}, "not json", {"type": "result", "usage": {**usage, "service_tier": "standard"}}]
        path.write_text("\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines) + "\n")
        return str(path)

    def write_json(self, name, value):
        path = self.temp / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return str(path)

    def main(self, *argv):
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = eval_report.main(list(argv))
        return code, stderr.getvalue()

    def two_arm_harness(self):
        with_runs = [run(1, 0.02, 10, [grader("any-skill-fired", True, scored=False), grader("fix-correct", True)],
                         self.trace("a")),
                     run(0.5, 0.04, 14, [grader("any-skill-fired", False, scored=False), grader("fix-correct", False)],
                         self.trace("b", {**USAGE, "output_tokens": 500}))]
        without_runs = [run(1, 0.01, 6, [grader("fix-correct", True)], str(self.temp / "gone.jsonl"))]
        return harness(with_runs, without_runs)


class RecordTest(ReportCase):
    def record(self, label="smoke", outcomes=None, note="A note."):
        argv = ["--record", self.write_json("harness.json", self.two_arm_harness()), "--label", label, "--note", note]
        if outcomes is not None:
            argv += ["--outcomes", self.write_json("outcomes.json", outcomes)]
        self.assertEqual(self.main(*argv), (0, ""))
        return json.loads(eval_report.RESULTS.read_text())

    def test_cost_tokens_and_verdicts_are_saved_per_arm_and_run(self):
        outcomes = {"task-bugfix": {"with": [{"acceptance": {"status": "pass", "detail": ""}},
                                              {"acceptance": {"status": "inconclusive", "detail": ""}}],
                                    "without": [{"acceptance": {"status": "fail", "detail": ""}}]}}
        saved = self.record(outcomes=outcomes)["runs"][0]
        self.assertEqual({key: saved[key] for key in ("label", "recorded", "claude_version", "arsenal_version",
                                                      "model", "judge_model", "runs_per_arm", "partial")},
                         {"label": "smoke", "recorded": "2026-11-13", "claude_version": "2.1.321",
                          "arsenal_version": "1.3.1", "model": "haiku", "judge_model": "haiku", "runs_per_arm": 2,
                          "partial": False})
        self.assertAlmostEqual(saved["cost_usd"], 0.07)
        first, second = saved["cases"]["task-bugfix"]["with"]
        self.assertEqual((first["cost_usd"], first["judge_cost_usd"], first["turns"], first["tokens"]),
                         (0.02, 0.001, 10, USAGE))
        self.assertEqual(first["graders"]["any-skill-fired"], {"passed": True, "scored": False})
        self.assertEqual((first["outcomes"], second["outcomes"]),
                         ({"acceptance": "pass"}, {"acceptance": "inconclusive"}))
        baseline = saved["cases"]["task-bugfix"]["without"][0]
        self.assertIsNone(baseline["tokens"])  # the trace was not kept: unknown, never zero
        self.assertEqual(baseline["outcomes"], {"acceptance": "fail"})

    def test_without_outcomes_the_runs_carry_none(self):
        saved = self.record()["runs"][0]
        self.assertEqual(saved["cases"]["task-bugfix"]["with"][0]["outcomes"], {})

    def test_same_label_replaces_and_a_new_label_is_appended(self):
        self.record(label="smoke", note="first")
        self.record(label="weekly")
        runs = self.record(label="smoke", note="second")["runs"]
        self.assertEqual([(entry["label"], entry["note"]) for entry in runs],
                         [("weekly", "A note."), ("smoke", "second")])

    def test_record_rewrites_the_block_and_check_then_passes(self):
        self.record()
        text = self.doc.read_text()
        self.assertTrue(text.startswith("# Evals\n\nintro\n\n") and text.endswith("\n\ntail\n"))
        self.assertIn("### `smoke` (2026-11-13)", text)
        self.assertEqual(self.main("--check"), (0, ""))

    def test_a_result_that_is_not_harness_json_is_refused_and_nothing_is_written(self):
        for value in ({"cases": []}, [1, 2], "text"):
            code, stderr = self.main("--record", self.write_json("bad.json", value), "--label", "x")
            self.assertEqual(code, 1, value)
            self.assertIn("error:", stderr)
        code, _ = self.main("--record", str(self.temp / "missing.json"), "--label", "x")
        self.assertEqual(code, 1)
        self.assertFalse(eval_report.RESULTS.exists())

    def test_label_and_record_need_each_other(self):
        for argv in (["--label", "x"], ["--record", "h.json"], ["--note", "n"], ["--outcomes", "o.json"],
                     ["--check", "--record", "h.json", "--label", "x"]):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                eval_report.main(argv)


class RenderTest(ReportCase):
    def rendered(self, outcomes=None, **changes):
        entry = eval_report.entry({**self.two_arm_harness(), **changes}, outcomes or {}, "smoke", "A note.")
        return eval_report.render({"runs": [entry]})

    def test_rows_report_means_per_arm(self):
        outcomes = {"task-bugfix": {"with": [{"acceptance": {"status": "pass"}}, {"acceptance": {"status": "inconclusive"}}],
                                    "without": [{"acceptance": {"status": "fail"}}]}}
        lines = self.rendered(outcomes).splitlines()
        self.assertIn("Claude Code 2.1.321, arsenal 1.3.1, model `haiku`, judge `haiku`, 2 run(s) per arm, "
                      "total cost 0.0700 USD.", lines)
        self.assertIn("A note.", lines)
        self.assertIn("| `task-bugfix` | with plugin | 2 | 0.75 | `any-skill-fired` 1/2 (indicator, not scored)<br>"
                      "`fix-correct` 1/2 | `acceptance` 1/2 (1 inconclusive) | 0.0300 | 3,010 | 400 | 12.0 |", lines)
        self.assertIn("| `task-bugfix` | without plugin | 1 | 1.00 | `fix-correct` 1/1 | `acceptance` 0/1 | 0.0100 | "
                      "not recorded | not recorded | 6.0 |", lines)

    def test_cases_without_outcome_checks_say_so(self):
        self.assertIn("| none defined |", self.rendered())

    def test_partial_run_is_flagged(self):
        self.assertIn("(PARTIAL: the cost ceiling stopped the run)", self.rendered(partial=True))

    def test_an_arm_that_did_not_run_has_no_row(self):
        single = harness([run(1, 0.02, 10, [grader("fix-correct", True)])], [])
        text = eval_report.render({"runs": [eval_report.entry(single, {}, "one-arm", "")]})
        self.assertIn("| with plugin |", text)
        self.assertNotIn("without plugin", text)

    def test_no_recorded_run(self):
        self.assertEqual(self.main(), (0, ""))
        self.assertIn("No run is recorded yet.", self.doc.read_text())

    def test_check_fails_on_drift_without_rewriting(self):
        eval_report.RESULTS.write_text(json.dumps({"runs": [eval_report.entry(self.two_arm_harness(), {}, "s", "")]}))
        before = self.doc.read_text()
        code, stderr = self.main("--check")
        self.assertEqual(code, 1)
        self.assertIn("out of date", stderr)
        self.assertEqual(self.doc.read_text(), before)
        self.assertEqual(self.main(), (0, ""))
        self.assertEqual(self.main("--check"), (0, ""))

    def test_missing_or_doubled_markers_are_an_error(self):
        for text in ("# Evals\n", f"{eval_report.START}\n{eval_report.END}\n{eval_report.START}\n{eval_report.END}\n",
                     f"{eval_report.END}\n{eval_report.START}\n"):
            self.doc.write_text(text)
            code, stderr = self.main()
            self.assertEqual(code, 1, text)
            self.assertIn("markers", stderr)
            self.assertEqual(self.doc.read_text(), text)

    def test_damaged_results_file_is_an_error(self):
        for text in ("{not json", "[]", '{"runs": {}}'):
            eval_report.RESULTS.write_text(text)
            self.assertEqual(self.main("--check")[0], 1, text)


class TraceUsageTest(ReportCase):
    def test_usage_comes_from_the_last_result_event(self):
        self.assertEqual(eval_report.trace_usage(self.trace("t")), USAGE)

    def test_missing_trace_or_trace_without_a_result_is_none(self):
        empty = self.temp / "empty.jsonl"
        empty.write_text('{"type": "assistant"}\n[1]\n')
        for path in (None, "", str(self.temp / "gone.jsonl"), str(empty)):
            self.assertIsNone(eval_report.trace_usage(path), path)


class CommittedResultsTest(unittest.TestCase):
    def test_committed_table_matches_the_committed_results(self):
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(eval_report.main(["--check"]), 0, stderr.getvalue())

    def test_smoke_run_is_recorded_with_cost_and_tokens_for_both_arms(self):
        runs = {entry["label"]: entry for entry in json.loads(eval_report.RESULTS.read_text())["runs"]}
        smoke = runs["smoke"]
        self.assertGreater(smoke["cost_usd"], 0)
        self.assertIn("Smoke run", smoke["note"])
        for arm in ("with", "without"):
            for item in smoke["cases"]["task-bugfix"][arm]:
                self.assertGreater(item["cost_usd"], 0)
                self.assertGreater(item["tokens"]["output_tokens"], 0)


class EvalsWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.triggers = self.text[self.text.index("\non:\n"):self.text.index("\npermissions:\n")]

    def test_runs_on_demand_and_weekly_only(self):
        self.assertIn("workflow_dispatch:", self.triggers)
        self.assertRegex(self.triggers, r'cron: "\d+ \d+ \* \* [0-6]"')
        for trigger in ("push", "pull_request", "pull_request_target", "workflow_run"):
            self.assertNotRegex(self.triggers, rf"(?m)^\s*{trigger}:")

    def test_runs_per_arm_is_an_input_defaulting_to_ten(self):
        self.assertRegex(self.triggers, r'runs:\n\s+description: [^\n]+\n\s+default: "10"')
        self.assertIn("RUNS: ${{ inputs.runs || '10' }}", self.text)
        self.assertIn('--runs "$RUNS"', self.text)

    def test_suite_runs_under_a_cost_ceiling(self):
        self.assertIn('--max-cost-usd "$MAX_COST_USD"', self.text)

    def test_skips_with_a_notice_when_the_key_is_absent(self):
        self.assertIn('if [ -z "$ANTHROPIC_API_KEY" ]; then', self.text)
        self.assertIn("::notice::", self.text)
        steps = self.text.split("\n      - ")[1:]
        self.assertIn("id: key", steps[0])
        for step in steps[1:]:
            self.assertRegex(step, r"if: (always\(\) && )?steps\.key\.outputs\.present == 'true'", step.splitlines()[0])
        self.assertIn("if: always() && steps.key.outputs.present == 'true'", steps[-1])  # partial results are kept

    def test_the_api_key_is_not_visible_to_the_step_that_runs_model_written_tests(self):
        steps = self.text[self.text.index("    steps:"):].split("\n      - ")
        holders = [step.splitlines()[0] for step in steps if "secrets.ANTHROPIC_API_KEY" in step]
        self.assertEqual(holders, ["name: Skip when the API key secret is absent", "name: Run the eval suite"])
        self.assertNotIn("ANTHROPIC_API_KEY", self.text[:self.text.index("    steps:")])
        self.assertIn("persist-credentials: false", self.text)

    def test_arguments_are_validated_before_they_reach_the_cli(self):
        self.assertIn("max_cost_usd must be a decimal number", self.text)
        self.assertIn("must not be empty or start with a dash", self.text)
        self.assertIn("runs must be 1 to 20", self.text)

    def test_inputs_reach_the_shell_only_through_the_environment(self):
        run_blocks = self.text[self.text.index("    steps:"):]
        self.assertNotIn("${{ inputs.", run_blocks)

    def test_results_are_uploaded(self):
        self.assertIn("actions/upload-artifact@", self.text)
        for name in ("harness.json", "outcomes.json", "eval-results.json"):
            self.assertIn(f"eval-out/{name}", self.text)

    def test_read_only_token(self):
        self.assertIn("permissions:\n  contents: read\n", self.text)


if __name__ == "__main__":
    unittest.main()
