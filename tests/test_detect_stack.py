"""Unit tests for the repo-scan skill's stack detector."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "repo-scan" / "scripts"))

import detect_stack  # noqa: E402


class DetectStackTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repo = Path(directory.name)

    def write(self, relative, content=""):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def report(self):
        return detect_stack.build_report(self.repo)

    def signals(self):
        return {row["signal"] for row in self.report()["detected"]}

    def test_empty_directory_detects_nothing_and_reports_gaps(self):
        report = self.report()
        self.assertEqual(report["detected"], [])
        self.assertEqual(report["long_files"], [])
        gaps = " ".join(report["gaps"])
        self.assertIn("No tests found", gaps)
        self.assertIn("No CI pipeline found", gaps)

    def test_fullstack_node_project(self):
        self.write("package.json", json.dumps({"dependencies": {"react": "19", "express": "5"}}))
        self.write("Dockerfile", "FROM node:22\n")
        self.write("db/schema.sql", "select 1;\n")
        self.assertLessEqual({"node", "frontend", "database", "fullstack", "docker"}, self.signals())

    def test_python_dotnet_and_ci_are_detected(self):
        self.write("requirements.txt", "fastapi\nsqlalchemy\n")
        self.write("app/main.py", "print('x')\n")
        self.write("Api/Api.csproj", "<Project />")
        self.write(".github/workflows/ci.yml", "on: push\n")
        self.write("tests/test_main.py", "def test_x(): pass\n")
        report = self.report()
        self.assertLessEqual({"python", "dotnet", "ci", "tests"}, {row["signal"] for row in report["detected"]})
        self.assertNotIn("No tests found", " ".join(report["gaps"]))
        self.assertNotIn("No CI pipeline found", " ".join(report["gaps"]))

    def test_unparseable_and_non_object_package_json_do_not_crash(self):
        for content in ('{"dependencies": ', "[1, 2]", ""):
            with self.subTest(content=content):
                self.write("package.json", content)
                self.assertIn("node", self.signals())

    def test_long_files_are_reported_and_skipped_directories_ignored(self):
        self.write("src/big.ts", "x\n" * 1200)
        self.write("src/ok.ts", "x\n" * 1000)
        self.write("node_modules/lib/huge.js", "x\n" * 5000)
        self.assertEqual(self.report()["long_files"], [{"path": "src/big.ts", "lines": 1200}])

    def test_every_recommendation_names_an_existing_arsenal_item(self):
        manifest = json.loads((ROOT / ".agents/subagents/subagent-definitions.json").read_text(encoding="utf-8"))
        known = {
            "skills": {path.name for path in (ROOT / ".agents/skills").iterdir() if path.is_dir()},
            "rules": {path.stem for path in (ROOT / ".agents/rules").glob("*.md")},
            "subagents": {entry["name"] for entry in manifest["subagents"]},
        }
        groups = [dict(zip(detect_stack.KINDS, detect_stack.ALWAYS_APPLICABLE))]
        groups += [dict(zip(detect_stack.KINDS, value[1:])) for value in detect_stack.RECOMMENDATIONS.values()]
        for group in groups:
            for kind, names in group.items():
                unknown = set(names.replace(",", " ").split()) - {"-"} - known[kind]
                self.assertEqual(unknown, set(), f"unknown {kind}: {unknown}")

    def test_cli_exit_codes_and_json_output(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(detect_stack.main([str(self.repo), "--json"]), 0)
        self.assertEqual(json.loads(output.getvalue())["path"], str(self.repo.resolve()))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(detect_stack.main([str(self.repo / "missing")]), 2)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(detect_stack.main([str(self.repo)]), 0)


if __name__ == "__main__":
    unittest.main()
