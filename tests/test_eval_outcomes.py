"""Unit tests for the eval cases, their outcome checks (scripts/eval_outcomes.py) and the fallback test runner."""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_outcomes  # noqa: E402

EVALS = ROOT / "evals"
RUNNER = ROOT / "scripts" / "eval_test_runner.py"
CASES_WITH_OUTCOMES = sorted(path.parent for path in EVALS.glob("*/outcome.json"))
# The grader types and fields `claude plugin eval` (schema 1.x) accepts; anything else fails to load there.
COMMON_FIELDS = {"type", "name", "weight", "arm"}
GRADER_FIELDS = {
    "regex": {"target", "pattern", "flags", "match"},
    "tool_order": {"before", "after"},
    "tool_used": {"tool", "input_match", "min", "max"},
    "file_exists": {"path", "exists"},
    "llm": {"criteria", "focus"},
    "baseline": {"baseline_file", "criteria"},
}
PYTHON_FLAGS = {"i": re.IGNORECASE, "s": re.DOTALL, "m": re.MULTILINE}
PASSING_TEST = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n"


def frontmatter(path):
    """Top-level `key: value` pairs of a markdown file's frontmatter, and the body after it."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text.strip()
    end = text.index("\n---\n", 4)
    fields = dict(line.split(":", 1) for line in text[4:end].splitlines() if re.match(r"\w+:", line))
    return {key: value.strip() for key, value in fields.items()}, text[end + 5:].strip()


def tools(case):
    return [tool.strip() for tool in frontmatter(case / "prompt.md")[0].get("allowed_tools", "[]").strip("[]").split(",")]


def write(root, files):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")


class WithoutPytest(unittest.TestCase):
    """Outcome checks behave the same on every machine once the pytest shortcut is off."""

    def setUp(self):
        patcher = mock.patch.object(eval_outcomes, "pytest_installed", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temp = Path(directory.name)

    def solved(self, case, extra=None):
        """The case's fixture with its reference solution (and extra files) laid over it."""
        workspace = self.temp / f"workspace-{case.name}"
        eval_outcomes.build_original(case, workspace)
        eval_outcomes.copy_tree(case / "outcome" / "reference", workspace)
        write(workspace, extra or {})
        return workspace

    def statuses(self, case, workspace):
        return {name: check["status"] for name, check in eval_outcomes.check_workspace(case, workspace).items()}


class GraderFormatTest(unittest.TestCase):
    def test_every_grader_uses_a_supported_type_and_only_its_fields(self):
        for path in sorted(EVALS.glob("*/graders/*.md")):
            fields, _ = frontmatter(path)
            self.assertIn(fields.get("type"), GRADER_FIELDS, path)
            self.assertEqual(set(fields) - COMMON_FIELDS - GRADER_FIELDS[fields["type"]], set(), path)

    def test_every_regex_grader_has_a_pattern_that_compiles(self):
        for path in sorted(EVALS.glob("*/graders/*.md")):
            fields, body = frontmatter(path)
            if fields["type"] != "regex":
                continue
            self.assertTrue(body, path)
            flags = 0
            for letter in fields.get("flags", ""):
                flags |= PYTHON_FLAGS[letter]
            re.compile(body, flags)

    def test_tools_follow_graders(self):
        for case in sorted(path.parent for path in EVALS.glob("*/prompt.md")):
            allowed = tools(case)
            for path in sorted(case.glob("graders/*.md")):
                fields, _ = frontmatter(path)
                if fields["type"] == "tool_used" and fields.get("max") != "0":
                    self.assertIn(fields["tool"], allowed, f"{path}: the case must allow the tool it grades")
                if fields["type"] == "file_exists" and fields.get("exists") != "false":
                    self.assertIn("Write", allowed, f"{path}: a file can only appear when Write is allowed")

    def test_tests_run_grader_ignores_commands_that_only_mention_a_runner(self):
        pattern = frontmatter(EVALS / "task-bugfix" / "graders" / "tests-run.md")[0]["input_match"].strip("'")
        for command in ("pytest -q", "python3 -m unittest", "cd src && python test_pricing.py", "python -m pytest tests"):
            self.assertRegex(json.dumps({"command": command}), pattern)
        for command in ('python3 -c "import pytest; print(pytest.__version__)"', "ls tests test", "pip list"):
            self.assertNotRegex(json.dumps({"command": command}), pattern)

    def test_every_tests_run_grader_is_the_same(self):
        texts = {path.read_text(encoding="utf-8") for path in EVALS.glob("task-*/graders/tests-run.md")}
        self.assertEqual(len(texts), 1)

    def test_failing_ci_assertion_grader_matches_the_fixture_and_not_a_weakened_copy(self):
        fields, pattern = frontmatter(EVALS / "task-failing-ci" / "graders" / "original-assertions-kept.md")
        with tempfile.TemporaryDirectory() as temp:
            eval_outcomes.build_original(EVALS / "task-failing-ci", Path(temp))
            original = (Path(temp) / "tests" / "test_paging.py").read_text(encoding="utf-8")
        self.assertEqual(fields["flags"], "s")
        self.assertRegex(original, re.compile(pattern, re.DOTALL))
        weakened = original.replace("list(range(0, 10))", "list(range(10, 20))")
        self.assertNotRegex(weakened, re.compile(pattern, re.DOTALL))

    def test_review_defect_graders_match_how_each_defect_is_named(self):
        wording = {"defect-sql-injection": "This is open to SQL injection.",
                   "defect-n-plus-one": "The loop issues one query per order (N+1).",
                   "defect-swallowed-exception": "refund swallows every exception."}
        for name, sentence in wording.items():
            _, pattern = frontmatter(EVALS / "task-review" / "graders" / f"{name}.md")
            self.assertRegex(sentence, re.compile(pattern, re.IGNORECASE))
            self.assertNotRegex("Looks good to merge.", re.compile(pattern, re.IGNORECASE))


class CaseOutcomeTest(WithoutPytest):
    def test_cases_that_change_code_have_outcome_checks(self):
        names = {case.name for case in CASES_WITH_OUTCOMES}
        for expected in ("task-bugfix", "task-legacy-change", "task-feature-multifile", "task-failing-ci",
                         "task-risky-migration", "task-cross-module-bug", "task-legacy-refactor",
                         "task-feature-fullstack"):
            self.assertIn(expected, names)

    def test_reference_solution_passes_every_check(self):
        for case in CASES_WITH_OUTCOMES:
            statuses = self.statuses(case, self.solved(case))
            self.assertTrue(statuses, case.name)
            self.assertEqual(set(statuses.values()), {"pass"}, f"{case.name}: {statuses}")

    def test_untouched_fixture_fails_a_check(self):
        for case in CASES_WITH_OUTCOMES:
            untouched = self.temp / f"untouched-{case.name}"
            eval_outcomes.build_original(case, untouched)
            self.assertIn("fail", self.statuses(case, untouched).values(), case.name)

    def test_fixture_is_deterministic(self):
        for case in CASES_WITH_OUTCOMES:
            first, second = self.temp / f"a-{case.name}", self.temp / f"b-{case.name}"
            eval_outcomes.build_original(case, first)
            eval_outcomes.build_original(case, second)
            files = eval_outcomes.files_in(first)
            self.assertEqual(files, eval_outcomes.files_in(second))
            for relative in files:
                self.assertEqual((first / relative).read_bytes(), (second / relative).read_bytes(), relative)

    def test_symptom_patched_where_it_shows_fails_acceptance(self):
        case = EVALS / "task-cross-module-bug"
        workspace = self.temp / "symptom"
        eval_outcomes.build_original(case, workspace)
        invoice = workspace / "shop" / "invoice.py"
        invoice.write_text(invoice.read_text().replace("format_cents(cart.total_cents())",
                                                       "format_cents(cart.total_cents() + 1)"))
        self.assertEqual(self.statuses(case, workspace)["acceptance"], "fail")

    def test_refactor_that_drops_a_quirk_fails_acceptance(self):
        case = EVALS / "task-legacy-refactor"
        broken = (case / "outcome" / "reference" / "billing_legacy.py").read_text().replace(
            "return amount + FRAGILE_FEE if item.get(\"fragile\") else amount",
            "return amount + FRAGILE_FEE * quantity if item.get(\"fragile\") else amount")
        workspace = self.solved(case, {"billing_legacy.py": broken})
        self.assertEqual(self.statuses(case, workspace)["acceptance"], "fail")

    def test_feature_without_the_migration_fails_acceptance(self):
        case = EVALS / "task-feature-fullstack"
        workspace = self.solved(case)
        (workspace / "migrations" / "002_add_due_date.sql").unlink()
        self.assertEqual(self.statuses(case, workspace)["acceptance"], "fail")

    def test_feature_that_edits_the_first_migration_fails_acceptance(self):
        case = EVALS / "task-feature-fullstack"
        workspace = self.solved(case)
        (workspace / "migrations" / "002_add_due_date.sql").unlink()
        init = workspace / "migrations" / "001_init.sql"
        init.write_text(init.read_text().replace("done INTEGER NOT NULL DEFAULT 0",
                                                 "done INTEGER NOT NULL DEFAULT 0,\n    due_date TEXT"))
        self.assertEqual(self.statuses(case, workspace)["acceptance"], "fail")


class AddedTestsTest(WithoutPytest):
    CASE = EVALS / "task-bugfix"
    CHECK = "regression-test-red-then-green"

    def test_no_added_test_fails(self):
        workspace = self.solved(self.CASE)
        (workspace / "test_pricing.py").unlink()
        self.assertEqual(self.statuses(self.CASE, workspace)[self.CHECK], "fail")

    def test_added_test_that_also_passes_on_the_unfixed_code_fails(self):
        workspace = self.solved(self.CASE, {"test_pricing.py": PASSING_TEST})
        check = eval_outcomes.check_workspace(self.CASE, workspace)[self.CHECK]
        self.assertEqual(check["status"], "fail")
        self.assertIn("green on the untouched fixture", check["detail"])

    def test_added_test_that_fails_on_the_final_code_fails(self):
        failing = PASSING_TEST.replace("assertTrue(True)", "assertTrue(False)")
        workspace = self.solved(self.CASE, {"test_pricing.py": failing})
        self.assertEqual(self.statuses(self.CASE, workspace)[self.CHECK], "fail")

    def test_added_test_that_cannot_be_imported_is_inconclusive_not_a_red_test(self):
        # on the untouched fixture it is red only because the helper it imports does not exist yet
        workspace = self.solved(self.CASE, {"test_pricing.py": "import module_that_does_not_exist\n"})
        self.assertEqual(self.statuses(self.CASE, workspace)[self.CHECK], "inconclusive")

    def test_a_hung_test_is_red(self):
        with mock.patch.object(eval_outcomes, "TEST_TIMEOUT", 1):
            tree = self.temp / "hang"
            tree.mkdir()
            (tree / "test_hang.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
            self.assertEqual(eval_outcomes.run_tests(tree, [Path("test_hang.py")]), "red")

    def test_added_test_that_hangs_fails(self):
        workspace = self.solved(self.CASE, {"test_pricing.py": "import time\ntime.sleep(60)\n"})
        with mock.patch.object(eval_outcomes, "TEST_TIMEOUT", 2):
            self.assertEqual(self.statuses(self.CASE, workspace)[self.CHECK], "fail")

    def test_pytest_style_tests_run_without_pytest(self):
        plain = ("from pricing import apply_discount\n\n\ndef test_coupon_above_100_is_rejected():\n"
                 "    try:\n        apply_discount(80, 150)\n    except ValueError:\n        return\n"
                 "    assert False, 'no error'\n\n\nclass TestNormal:\n    def test_discount(self):\n"
                 "        assert apply_discount(50, 20) == 40\n")
        workspace = self.solved(self.CASE, {"test_pricing.py": plain})
        self.assertEqual(self.statuses(self.CASE, workspace)[self.CHECK], "pass")

    def test_tests_that_need_a_missing_runner_are_inconclusive(self):
        for text in ("import pytest\n\n\ndef test_x():\n    assert True\n",
                     "def test_needs_a_fixture(tmp_path):\n    assert tmp_path\n"):
            workspace = self.solved(self.CASE, {"test_pricing.py": text})
            self.assertEqual(self.statuses(self.CASE, workspace)[self.CHECK], "inconclusive", text)

    def test_tests_in_a_subdirectory_and_suffix_named_files_count(self):
        workspace = self.solved(self.CASE)
        (workspace / "tests").mkdir()
        (workspace / "test_pricing.py").rename(workspace / "tests" / "pricing_test.py")
        self.assertEqual(self.statuses(self.CASE, workspace)[self.CHECK], "pass")

    def test_hidden_directories_are_ignored(self):
        workspace = self.solved(self.CASE, {".claude/test_noise.py": "raise SystemExit(1)\n",
                                            "__pycache__/test_stale.py": "raise SystemExit(1)\n"})
        self.assertEqual(self.statuses(self.CASE, workspace)[self.CHECK], "pass")

    def test_characterization_test_must_pass_on_the_untouched_code_too(self):
        case = EVALS / "task-legacy-refactor"
        wrong = PASSING_TEST.replace("self.assertTrue(True)",
                                     "from billing_legacy import tax\n        self.assertEqual(tax({}, 1), 0)")
        workspace = self.solved(case, {"test_billing_legacy.py": wrong})
        self.assertEqual(self.statuses(case, workspace)["characterization-test-green-before-and-after"], "fail")


class OriginalTestsTest(WithoutPytest):
    CASE = EVALS / "task-failing-ci"

    def test_weakening_the_tests_does_not_make_the_check_pass(self):
        workspace = self.temp / "weakened"
        eval_outcomes.build_original(self.CASE, workspace)
        write(workspace, {"tests/test_paging.py": "def test_nothing():\n    assert True\n"})
        self.assertEqual(self.statuses(self.CASE, workspace), {"original-tests-green": "fail"})

    def test_deleting_the_tests_does_not_make_the_check_pass(self):
        workspace = self.temp / "deleted"
        eval_outcomes.build_original(self.CASE, workspace)
        (workspace / "tests" / "test_paging.py").unlink()
        self.assertEqual(self.statuses(self.CASE, workspace), {"original-tests-green": "fail"})


class MigrationCheckTest(WithoutPytest):
    CASE = EVALS / "task-risky-migration"
    CHECK = "first-step-keeps-old-version-working"

    def status(self, files):
        workspace = self.temp / f"migration-{len(list(self.temp.iterdir()))}"
        eval_outcomes.build_original(self.CASE, workspace)
        write(workspace, files)
        return self.statuses(self.CASE, workspace)[self.CHECK]

    def test_one_step_drop_or_rename_fails(self):
        self.assertEqual(self.status({"migrations/002_cleanup.sql": "ALTER TABLE users DROP COLUMN legacy_email;\n"}), "fail")
        self.assertEqual(self.status({"migrations/002_rename.sql": "alter table users\n  rename column username to handle;\n"}), "fail")
        self.assertEqual(self.status({"migrations/002_r.sql": "ALTER TABLE users RENAME username TO handle;\n"}), "fail")

    def test_expand_first_passes_even_when_a_later_file_contracts(self):
        self.assertEqual(self.status({
            "migrations/002_expand.sql": "ALTER TABLE users ADD COLUMN handle TEXT;\n",
            "migrations/003_contract.sql": "ALTER TABLE users DROP COLUMN legacy_email;\n"}), "pass")

    def test_destructive_statement_only_in_a_comment_passes(self):
        self.assertEqual(self.status({"migrations/002_expand.sql": (
            "-- Do NOT DROP COLUMN legacy_email yet.\n/* later: RENAME COLUMN username TO handle */\n"
            "ALTER TABLE users ADD COLUMN handle TEXT;\n")}), "pass")

    def test_no_migration_written_fails_because_doing_nothing_is_not_a_pass(self):
        self.assertEqual(self.status({"NOTES.md": "I need to ask before dropping a column.\n"}), "fail")

    def test_drop_without_the_column_keyword_is_destructive(self):
        self.assertEqual(self.status({"migrations/002.sql": "ALTER TABLE users DROP legacy_email;\n"}), "fail")


class KeptRunTest(WithoutPytest):
    def kept_run(self, sealed):
        """A directory shaped like one `claude plugin eval --keep-temp` leaves, holding the bugfix reference."""
        root = self.temp / f"claude-eval-{'sealed' if sealed else 'open'}"
        (root / "out").mkdir(parents=True)
        (root / "out" / "trace.jsonl").write_text("{}\n")
        workspace = root / ("sealed" if sealed else "") / "home" / "cwd"
        workspace.parent.mkdir(parents=True)
        self.solved(EVALS / "task-bugfix").rename(workspace)
        if sealed:
            os.chmod(root / "sealed", 0)
            os.chmod(root, 0o500)
            self.addCleanup(os.chmod, root / "sealed", 0o700)
            self.addCleanup(os.chmod, root, 0o700)  # runs first: cleanups are last in, first out
        return str(root / "out" / "trace.jsonl")

    def harness(self, **arms):
        return {"cases": [{"name": "task-bugfix", "arms": {arm: [{"tracePath": path} for path in paths]
                                                             for arm, paths in arms.items()}},
                          {"name": "task-ambiguous", "arms": {"with": [{"tracePath": ""}]}}]}

    def test_sealed_and_unsealed_runs_are_checked(self):
        harness = self.harness(**{"with": [self.kept_run(sealed=True)], "without": [self.kept_run(sealed=False)]})
        outcomes = eval_outcomes.check_results(harness)
        self.assertEqual(list(outcomes), ["task-bugfix"])  # a case without outcome.json is left out
        for arm in ("with", "without"):
            self.assertEqual({check["status"] for check in outcomes["task-bugfix"][arm][0].values()}, {"pass"})

    def test_run_that_was_not_kept_is_unavailable(self):
        harness = self.harness(**{"with": [str(self.temp / "gone" / "out" / "trace.jsonl"), ""]})
        outcomes = eval_outcomes.check_results(harness)["task-bugfix"]
        self.assertEqual(outcomes["without"], [])
        for run in outcomes["with"]:
            self.assertEqual({check["status"] for check in run.values()}, {"unavailable"})

    def test_main_writes_the_outcomes_file(self):
        results, out = self.temp / "harness.json", self.temp / "outcomes.json"
        results.write_text(json.dumps(self.harness(**{"with": [self.kept_run(sealed=False)]})))
        self.assertEqual(eval_outcomes.main(["--results", str(results), "--out", str(out)]), 0)
        self.assertEqual(json.loads(out.read_text())["task-bugfix"]["with"][0]["acceptance"]["status"], "pass")

    def test_main_reports_unreadable_results(self):
        bad = self.temp / "bad.json"
        bad.write_text("{not json")
        for path in (bad, self.temp / "missing.json"):
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(eval_outcomes.main(["--results", str(path)]), 1)
            self.assertIn("error:", stderr.getvalue())

    def test_unknown_check_kind_is_an_error(self):
        case = self.temp / "task-x"
        write(case, {"outcome.json": json.dumps({"checks": [{"name": "x", "kind": "run_a_script"}]})})
        with self.assertRaisesRegex(ValueError, "unknown check kind run_a_script"):
            eval_outcomes.load_checks(case)


class TestCommandTest(unittest.TestCase):
    def test_pytest_is_used_when_installed_and_the_fallback_runner_otherwise(self):
        with mock.patch.object(eval_outcomes, "pytest_installed", return_value=True):
            self.assertEqual(eval_outcomes.test_command(Path("t"), [Path("a.py")])[1:3], ["-m", "pytest"])
        with mock.patch.object(eval_outcomes, "pytest_installed", return_value=False):
            self.assertEqual(eval_outcomes.test_command(Path("t"), [Path("a.py")])[1:], [str(RUNNER), "t", "a.py"])

    def test_pytest_exit_codes(self):
        done = lambda code: subprocess.CompletedProcess([], code, "", "")  # noqa: E731
        self.assertEqual([eval_outcomes.verdict(done(code), True) for code in (0, 1, 2, 5)],
                         ["green", "red", "broken", "empty"])  # 2: nothing collected

    def test_fallback_runner_that_died_is_red(self):
        self.assertEqual(eval_outcomes.verdict(subprocess.CompletedProcess([], 1, "", "boom"), False), "red")


class FallbackRunnerTest(unittest.TestCase):
    def counts(self, files):
        with tempfile.TemporaryDirectory() as temp:
            write(Path(temp), files)
            tests = sorted(name for name in files if Path(name).name.startswith("test_"))
            done = subprocess.run([sys.executable, str(RUNNER), temp, *tests], cwd=temp,
                                  capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_counts_unittest_plain_functions_and_plain_classes(self):
        counts = self.counts({"test_mixed.py": (
            PASSING_TEST + "\n\ndef test_plain():\n    assert 1 + 1 == 2\n\n\ndef test_plain_fails():\n"
            "    assert 1 + 1 == 3\n\n\nclass TestPlain:\n    def test_method(self):\n        assert True\n\n\n"
            "def helper():\n    raise RuntimeError('not a test')\n")})
        self.assertEqual(counts, {"ran": 4, "failed": 1, "unsupported": 0})

    def test_test_output_does_not_corrupt_the_result_line(self):
        self.assertEqual(self.counts({"test_noisy.py": "def test_prints():\n    print('{\"ran\": 99}')\n"}),
                         {"ran": 1, "failed": 0, "unsupported": 0})

    def test_import_error_is_a_failure(self):
        self.assertEqual(self.counts({"test_broken.py": "import nope_not_here\n"}),
                         {"ran": 1, "failed": 1, "unsupported": 0, "broken": 1})
        self.assertEqual(self.counts({"test_crash.py": "raise RuntimeError('at import')\n"}),
                         {"ran": 1, "failed": 1, "unsupported": 0, "broken": 1})

    def test_fixture_arguments_and_a_missing_pytest_are_unsupported(self):
        self.assertEqual(self.counts({"test_fixture.py": "def test_needs(tmp_path):\n    assert tmp_path\n"}),
                         {"ran": 0, "failed": 0, "unsupported": 1})
        missing = "raise ModuleNotFoundError(\"No module named 'pytest'\", name='pytest')\n"
        self.assertEqual(self.counts({"test_needs_pytest.py": missing}), {"ran": 0, "failed": 0, "unsupported": 1})

    def test_no_tests_is_reported_as_nothing_ran(self):
        self.assertEqual(self.counts({"test_empty.py": "VALUE = 1\n"}), {"ran": 0, "failed": 0, "unsupported": 0})

    def test_tests_import_modules_beside_them_and_from_the_root(self):
        counts = self.counts({"lib.py": "X = 1\n", "tests/helper.py": "Y = 2\n",
                              "tests/test_paths.py": "import helper\nimport lib\n\n\ndef test_sum():\n"
                                                     "    assert lib.X + helper.Y == 3\n"})
        self.assertEqual(counts, {"ran": 1, "failed": 0, "unsupported": 0})


if __name__ == "__main__":
    unittest.main()
