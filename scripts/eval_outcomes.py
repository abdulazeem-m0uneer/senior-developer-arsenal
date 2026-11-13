#!/usr/bin/env python3
"""Outcome checks for the task-* eval cases: run the code each eval run left behind instead of asking a judge.

Usage:
  eval_outcomes.py --results harness.json [--out outcomes.json]

`harness.json` is what `claude plugin eval ... --keep-temp --json harness.json` wrote. `claude plugin eval`
has no grader that executes code, so this script is the closest supported mechanism: it finds each run's kept
workspace through the run's `tracePath`, rebuilds the untouched fixture with the case's `fixture.sh`, and
applies the checks listed in `evals/<case>/outcome.json`:

  acceptance             hidden tests from the case directory pass against the workspace
  regression_test        test files the run added pass on the workspace AND fail on the untouched fixture
  characterization_test  test files the run added pass on the workspace AND on the untouched fixture
  original_tests         the fixture's own copies of the named test files pass against the workspace
  first_new_file_lacks   the first new file matching a glob does not match a pattern (SQL comments ignored);
                         with `require_match: true` a run that wrote no such file fails

Each check is `pass`, `fail` or `inconclusive` (the tests need a runner feature that is not installed);
a run whose workspace is gone is reported as `unavailable`. Tests run with pytest when it is installed,
otherwise with eval_test_runner.py.

This EXECUTES test code written by the model, as you and outside the eval sandbox: run it only on results
from cases you trust, or on a throwaway machine such as a CI runner. Time budget: a few seconds per run,
120 seconds at most per test invocation. Standard library only.
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
RUNNER = Path(__file__).resolve().parent / "eval_test_runner.py"
TEST_TIMEOUT = 120
ARMS = ("with", "without")
SUPPORT_FILES = ("conftest.py", "__init__.py")  # copied with new tests so they import the same way
SQL_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


def hidden(relative):
    return any(part.startswith(".") or part in ("__pycache__", "node_modules") for part in relative.parts)


def files_in(tree):
    """Relative paths of the regular files in a tree, skipping dot directories and caches."""
    return sorted(path.relative_to(tree) for path in tree.rglob("*")
                  if path.is_file() and not path.is_symlink() and not hidden(path.relative_to(tree)))


def copy_tree(source, target):
    target.mkdir(parents=True, exist_ok=True)
    for relative in files_in(source):
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target / relative)


def build_original(case_dir, target):
    """The fixture exactly as the run received it."""
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(["bash", str((case_dir / "fixture.sh").resolve())], cwd=target, check=True, capture_output=True,
                   timeout=TEST_TIMEOUT)


def is_test_file(relative):
    return relative.suffix == ".py" and (relative.name.startswith("test") or relative.stem.endswith("_test"))


def new_files(workspace, original):
    return [relative for relative in files_in(workspace) if not (original / relative).exists()]


def pytest_installed():
    return importlib.util.find_spec("pytest") is not None


def test_command(tree, tests):
    if pytest_installed():
        return [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *map(str, tests)]
    return [sys.executable, str(RUNNER), str(tree), *map(str, tests)]


def verdict(done, with_pytest):
    """`green`, `red`, `empty` (no test ran), `broken` (nothing could be collected, for example an import error:
    not evidence that a test fails for the right reason) or `unsupported` from a finished test process."""
    if with_pytest:
        return {0: "green", 5: "empty", 2: "broken"}.get(done.returncode, "red")
    try:
        counts = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return "red"  # the runner itself died: the tests took the interpreter down
    if counts["failed"]:
        return "broken" if counts["failed"] == counts.get("broken", 0) else "red"
    if counts["unsupported"]:
        return "unsupported"
    return "green" if counts["ran"] else "empty"


def run_tests(tree, tests):
    """Run test files (paths relative to `tree`) from the tree's root."""
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(tree), "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        done = subprocess.run(test_command(tree, tests), cwd=tree, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=TEST_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        return "red"
    return verdict(done, pytest_installed())


def result(status, detail=""):
    return {"status": status, "detail": detail}


def scratch_copy(source, scratch, name):
    target = Path(scratch) / name
    copy_tree(source, target)
    return target


def check_acceptance(check, case_dir, workspace, original, scratch):
    tree = scratch_copy(workspace, scratch, "acceptance")
    copy_tree(case_dir / check["tests"], tree / "_acceptance")
    copy_tree(original, tree / "_acceptance" / "_original")
    tests = [relative for relative in files_in(tree) if relative.parts[:1] == ("_acceptance",)
             and len(relative.parts) == 2 and is_test_file(relative)]
    outcome = run_tests(tree, tests)
    return result("pass" if outcome == "green" else "fail", f"hidden tests: {outcome}")


def added_tests_on_both(workspace, original, scratch):
    """How the test files a run added behave on its own workspace and on the untouched fixture."""
    added = new_files(workspace, original)
    tests = [relative for relative in added if is_test_file(relative)]
    if not tests:
        return None, None
    after = run_tests(scratch_copy(workspace, scratch, "after"), tests)
    before_tree = scratch_copy(original, scratch, "before")
    for relative in added:
        if relative in tests or relative.name in SUPPORT_FILES:
            (before_tree / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(workspace / relative, before_tree / relative)
    return after, run_tests(before_tree, tests)


def judge_added_tests(after, before, wanted_before):
    if after is None:
        return result("fail", "the run added no test file")
    detail = f"added tests: {before} on the untouched fixture, {after} on the final code"
    if "unsupported" in (after, before) or wanted_before == "red" and before == "broken":
        return result("inconclusive", detail)
    return result("pass" if (after, before) == ("green", wanted_before) else "fail", detail)


def check_regression_test(check, case_dir, workspace, original, scratch):
    return judge_added_tests(*added_tests_on_both(workspace, original, scratch), wanted_before="red")


def check_characterization_test(check, case_dir, workspace, original, scratch):
    return judge_added_tests(*added_tests_on_both(workspace, original, scratch), wanted_before="green")


def check_original_tests(check, case_dir, workspace, original, scratch):
    tree = scratch_copy(workspace, scratch, "original-tests")
    for path in check["paths"]:
        (tree / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original / path, tree / path)
    outcome = run_tests(tree, [Path(path) for path in check["paths"]])
    if outcome == "unsupported":
        return result("inconclusive", "the fixture's tests need a runner that is not installed")
    return result("pass" if outcome == "green" else "fail", f"the fixture's own tests: {outcome}")


def check_first_new_file_lacks(check, case_dir, workspace, original, scratch):
    matching = [relative for relative in new_files(workspace, original) if relative.match(check["glob"])]
    if not matching:  # an exemption unless the case requires the file: doing nothing must not look like a pass
        return result("fail" if check.get("require_match") else "pass", f"no new file matches {check['glob']}")
    text = (workspace / matching[0]).read_text(encoding="utf-8", errors="replace")
    found = re.search(check["pattern"], SQL_COMMENT.sub("", text))
    return result("fail" if found else "pass", f"{matching[0].as_posix()}: {'matches' if found else 'clean'}")


CHECKS = {
    "acceptance": check_acceptance,
    "regression_test": check_regression_test,
    "characterization_test": check_characterization_test,
    "original_tests": check_original_tests,
    "first_new_file_lacks": check_first_new_file_lacks,
}


def load_checks(case_dir):
    """The checks of a case, or [] when it has no outcome.json; ValueError for an unknown kind."""
    spec = case_dir / "outcome.json"
    if not spec.is_file():
        return []
    checks = json.loads(spec.read_text(encoding="utf-8"))["checks"]
    unknown = sorted({check["kind"] for check in checks} - set(CHECKS))
    if unknown:
        raise ValueError(f"{spec}: unknown check kind {', '.join(unknown)} (known: {', '.join(sorted(CHECKS))})")
    return checks


def check_workspace(case_dir, workspace):
    """{check name: {"status", "detail"}} for one workspace of one case."""
    checks = load_checks(case_dir)
    if not checks:
        return {}
    with tempfile.TemporaryDirectory() as scratch:
        original = Path(scratch) / "original"
        build_original(case_dir, original)
        outcomes = {}
        for number, check in enumerate(checks):
            step = Path(scratch) / f"check-{number}"
            outcomes[check["name"]] = CHECKS[check["kind"]](check, case_dir, Path(workspace), original, step)
        return outcomes


def kept_workspace(trace_path):
    """The working directory an eval run left behind, or None when the run was not kept.

    `--keep-temp` leaves <root>/out/trace.jsonl and moves what the run wrote to <root>/sealed (mode 000).
    """
    if not trace_path:
        return None
    root = Path(trace_path).parent.parent
    if not root.is_dir():
        return None
    sealed = root / "sealed"
    if sealed.is_dir():
        os.chmod(root, 0o700)
        os.chmod(sealed, 0o700)
    for candidate in (sealed / "home" / "cwd", root / "home" / "cwd"):
        if candidate.is_dir():
            return candidate
    return None


def check_run(case_dir, run):
    workspace = kept_workspace(run.get("tracePath") or "")
    if workspace is None:
        return {check["name"]: result("unavailable", "the run's workspace was not kept (use --keep-temp)")
                for check in load_checks(case_dir)}
    return check_workspace(case_dir, workspace)


def check_results(harness, evals=EVALS):
    """{case: {arm: [outcomes per run]}} for every case in a harness result that has an outcome.json."""
    outcomes = {}
    for case in harness["cases"]:
        case_dir = evals / case["name"]
        if not load_checks(case_dir):
            continue
        outcomes[case["name"]] = {arm: [check_run(case_dir, run) for run in case["arms"].get(arm, [])]
                                  for arm in ARMS}
    return outcomes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", required=True, type=Path, help="JSON written by `claude plugin eval --json`")
    parser.add_argument("--out", type=Path, help="write the outcomes here instead of printing them")
    options = parser.parse_args(argv)
    try:
        harness = json.loads(options.results.read_text(encoding="utf-8"))
        text = json.dumps(check_results(harness), indent=2) + "\n"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if options.out:
        options.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
