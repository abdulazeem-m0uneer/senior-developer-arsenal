#!/usr/bin/env python3
"""Run test files without a third-party runner and report counts as one JSON line.

Usage:
  eval_test_runner.py ROOT TEST_FILE [TEST_FILE ...]

Used by eval_outcomes.py when pytest is not installed. Runs `unittest.TestCase` classes, module-level
`test*` functions and methods of plain `Test*` classes. Tests that need a runner feature this script does
not have (arguments such as fixtures or parameters, or `import pytest` where pytest is missing) are counted
as `unsupported`, never as passed or failed. The last line of stdout is
{"ran": N, "failed": N, "unsupported": N}, plus "broken": N when files could not be imported (also counted in ran and failed); test output goes to stderr. Always exits 0. Standard library only.
"""
import importlib.util
import inspect
import json
import sys
import unittest
from pathlib import Path


def takes_no_arguments(function):
    return all(parameter.default is not inspect.Parameter.empty
               or parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
               for parameter in inspect.signature(function).parameters.values())


def plain_tests(module):
    """The pytest-style tests of a module: its `test*` functions and the `test*` methods of `Test*` classes."""
    for name, member in vars(module).items():
        if getattr(member, "__module__", None) != module.__name__:
            continue
        if inspect.isfunction(member) and name.startswith("test"):
            yield member
        elif inspect.isclass(member) and name.startswith("Test") and not issubclass(member, unittest.TestCase):
            instance = member()
            yield from (getattr(instance, method) for method in dir(member)
                        if method.startswith("test") and callable(getattr(instance, method)))


def load(path, index):
    spec = importlib.util.spec_from_file_location(f"_eval_tests_{index}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def collect(paths):
    """A suite of everything runnable, plus counts of import failures and unsupported tests."""
    suite, broken, unsupported = unittest.TestSuite(), 0, 0
    for index, path in enumerate(paths):
        sys.path.insert(0, str(Path(path).resolve().parent))
        try:
            module = load(path, index)
        except ModuleNotFoundError as error:
            if error.name == "pytest":
                unsupported += 1
            else:
                broken += 1
            continue
        except Exception:  # a test file that cannot be imported is a failing test file
            broken += 1
            continue
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        for test in plain_tests(module):
            if takes_no_arguments(test):
                suite.addTest(unittest.FunctionTestCase(test))
            else:
                unsupported += 1
    return suite, broken, unsupported


def main(argv):
    root, paths = argv[0], argv[1:]
    sys.path.insert(0, str(Path(root).resolve()))
    real_stdout, sys.stdout = sys.stdout, sys.stderr  # keep the JSON line the only thing on stdout
    suite, broken, unsupported = collect(paths)
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=0).run(suite)
    counts = {"ran": result.testsRun + broken, "failed": len(result.failures) + len(result.errors) + broken,
              "unsupported": unsupported}
    if broken:
        counts["broken"] = broken
    print(json.dumps(counts), file=real_stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
