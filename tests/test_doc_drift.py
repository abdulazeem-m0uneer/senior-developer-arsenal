"""Unit tests for the git-release skill's doc-drift check."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "git-release" / "scripts" / "doc_drift.py"
sys.path.insert(0, str(SCRIPT.parent))

import doc_drift  # noqa: E402

CLI = '''import argparse
import os

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="report.txt")
    token = os.environ.get("API_TOKEN")
    return parser, token
'''
README = "# Tool\n\nRun `tool --out file`. Set `API_TOKEN` to call the API.\n\nRoutes: `GET /users/{id}`.\n"
APP = '''app.get("/users/:id", handler);
'''


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                   capture_output=True)


class DriftCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(os.path.realpath(self.tmp.name))
        git(self.dir, "init", "-q")
        self.write("cli.py", CLI)
        self.write("server.js", APP)
        self.write("README.md", README)
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-qm", "base")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def drift(self, *docs):
        return {(d.status, d.kind, d.name) for d in doc_drift.drift(str(self.dir), "HEAD", docs)}


class DriftTest(DriftCase):
    def test_clean_when_nothing_changed(self):
        self.assertEqual(self.drift(), set())

    def test_clean_when_new_surface_is_documented(self):
        self.write("cli.py", CLI.replace('parser.add_argument("--out", default="report.txt")',
                                         'parser.add_argument("--out", default="report.txt")\n'
                                         '    parser.add_argument("--verbose", action="store_true")'))
        self.write("README.md", README + "\nUse `--verbose` for more output.\n")
        self.assertEqual(self.drift(), set())

    def test_renamed_flag_is_undocumented_and_the_old_one_is_stale(self):
        self.write("cli.py", CLI.replace('"--out"', '"--output"'))
        self.assertEqual(self.drift(), {("undocumented", "flag", "--output"), ("stale", "flag", "--out")})

    def test_removed_env_var_that_docs_still_mention_is_stale(self):
        self.write("cli.py", CLI.replace('    token = os.environ.get("API_TOKEN")\n', "    token = None\n"))
        found = doc_drift.drift(str(self.dir), "HEAD")
        self.assertEqual([(d.status, d.kind, d.name, d.path, d.line) for d in found],
                         [("stale", "env", "API_TOKEN", "README.md", 3)])

    def test_an_env_var_still_read_elsewhere_is_not_stale(self):
        self.write("cli.py", CLI.replace('    token = os.environ.get("API_TOKEN")\n', "    token = None\n"))
        self.write("auth.py", 'import os\nTOKEN = os.getenv("API_TOKEN")\n')
        self.assertEqual(self.drift(), set())

    def test_new_route_is_undocumented_and_parameter_styles_match(self):
        self.write("server.js", APP + 'app.post("/orders", create);\napp.delete("/users/{userId}", remove);\n')
        self.assertEqual(self.drift(), {("undocumented", "route", "/orders")})

    def test_each_surface_kind_and_language_is_read(self):
        self.write("svc.ts", 'export function createOrder() {}\nconst port = process.env.PORT;\n'
                             'program.option("-q, --quiet", "less");\nconst ttl = config.get("cache.ttl");\n')
        self.write("Api.cs", '[HttpGet("api/items")]\nvar key = Environment.GetEnvironmentVariable("SIGNING_KEY");\n'
                             'app.MapPost("/api/items", Create);\nvar c = Configuration["Store:Url"];\n')
        self.write("main.go", 'http.HandleFunc("/health", h)\nv := os.Getenv("GO_ENV")\nflag.String("listen", ":80", "")\n')
        self.write("lib.rs", 'let k = std::env::var("RUST_KEY");\n')
        self.write("pkg.py", '__all__ = ["public_api"]\n')
        self.assertEqual(self.drift(), {
            ("undocumented", "export", "createOrder"), ("undocumented", "env", "PORT"), ("undocumented", "flag", "-q"),
            ("undocumented", "flag", "--quiet"), ("undocumented", "config", "cache.ttl"),
            ("undocumented", "route", "api/items"), ("undocumented", "env", "SIGNING_KEY"),
            ("undocumented", "route", "/api/items"), ("undocumented", "config", "Store:Url"),
            ("undocumented", "route", "/health"), ("undocumented", "env", "GO_ENV"), ("undocumented", "flag", "-listen"),
            ("undocumented", "env", "RUST_KEY"), ("undocumented", "export", "public_api")})

    def test_tests_docs_and_changelog_are_not_surface_or_docs(self):
        self.write("tests/test_cli.py", 'os.environ["TEST_ONLY"] = "1"\n')
        self.write("cli.test.js", 'app.get("/only-in-tests", h);\n')
        self.write("server.js", APP + 'app.get("/changelog-only", h);\n')
        self.write("CHANGELOG.md", "Added `/changelog-only`.\n")
        self.assertEqual(self.drift(), {("undocumented", "route", "/changelog-only")})

    def test_docs_folder_and_extra_docs_paths_count(self):
        self.write("server.js", APP + 'app.get("/a", h);\napp.get("/b", h);\n')
        self.write("docs/api/routes.md", "`GET /a`\n")
        self.write("guide/b.md", "`GET /b`\n")
        self.assertEqual(self.drift(), {("undocumented", "route", "/b")})
        self.assertEqual(self.drift("guide"), set())

    def test_examples_in_comments_are_not_surface(self):
        self.write("server.js", APP + '// app.get("/example", h);\n/* process.env.EXAMPLE_ONLY */\n')
        self.write("cli.py", CLI + '# parser.add_argument("--example")\n')
        self.assertEqual(self.drift(), set())

    def test_an_edited_line_keeps_its_surface(self):
        self.write("cli.py", CLI.replace('default="report.txt"', 'default="out.txt"'))
        self.assertEqual(self.drift(), set())

    def test_a_deleted_file_makes_its_documented_surface_stale(self):
        (self.dir / "server.js").unlink()
        self.assertEqual(self.drift(), {("stale", "route", "/users/:id")})


class CliTest(DriftCase):
    def run_cli(self, *args, cwd=None):
        out = io.StringIO()
        with mock.patch("os.getcwd", return_value=str(cwd or self.dir)), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            code = doc_drift.main(list(args))
        return code, out.getvalue()

    def test_exit_codes_and_output(self):
        self.assertEqual(self.run_cli("HEAD"), (0, ""))
        self.write("cli.py", CLI.replace('"--out"', '"--output"'))
        code, out = self.run_cli("HEAD")
        self.assertEqual(code, 1)
        self.assertIn("undocumented flag --output cli.py:6", out)
        self.assertIn("stale flag --out README.md:3", out)
        code, out = self.run_cli("HEAD", "--json")
        self.assertEqual((code, len(json.loads(out))), (1, 2))
        self.assertEqual(self.run_cli("no-such-ref")[0], 2)
        self.assertEqual(self.run_cli("HEAD", "--docs", "missing-dir")[0], 2)
        self.assertEqual(self.run_cli()[0], 2)
        with tempfile.TemporaryDirectory() as plain:
            self.assertEqual(self.run_cli("HEAD", cwd=plain)[0], 2)

    def test_runs_as_a_script_from_a_subdirectory(self):
        self.write("sub/x.txt", "x")
        result = subprocess.run([sys.executable, str(SCRIPT), "HEAD"], cwd=self.dir / "sub", capture_output=True,
                                text=True)
        self.assertEqual((result.returncode, result.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
