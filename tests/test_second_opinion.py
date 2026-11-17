"""Unit tests for code-review/scripts/second_opinion.py, with stub CLIs on PATH (nothing leaves the machine)."""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "code-review" / "scripts" / "second_opinion.py"
sys.path.insert(0, str(SCRIPT.parent))
import second_opinion  # noqa: E402

STUB = """#!{python}
import os, sys, time
out = os.environ["STUB_OUT"]
open(os.path.join(out, "argv"), "w").write("\\n".join(sys.argv))
open(os.path.join(out, "stdin"), "w").write(sys.stdin.read())
mode = os.environ.get("STUB_MODE", "")
if mode == "sleep":
    time.sleep(10)
if mode == "fail":
    sys.stderr.write("stub broke")
    sys.exit(7)
print("REVIEW from " + os.path.basename(sys.argv[0]))
"""
TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"  # a GitHub token shape, built so no scanner flags this file


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                   capture_output=True)


class SecondOpinionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.repo, self.bin, self.out = base / "repo", base / "bin", base / "out"
        for folder in (self.repo, self.bin, self.out):
            folder.mkdir()
        git(self.repo, "init", "-q")
        (self.repo / "app.py").write_text("x = 1\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "init")
        tools = {os.path.dirname(shutil.which("git"))}
        self.path = os.pathsep.join([str(self.bin), *tools])  # git, and no real codex or gemini

    def tearDown(self):
        self.tmp.cleanup()

    def stub(self, *names):
        for name in names:
            path = self.bin / name
            path.write_text(STUB.format(python=sys.executable))
            path.chmod(0o755)

    def run_cli(self, *args, mode=""):
        env = {**os.environ, "PATH": self.path, "STUB_OUT": str(self.out), "STUB_MODE": mode}
        result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.repo, capture_output=True, text=True,
                                env=env)
        return result.returncode, result.stdout, result.stderr

    def sent(self, name="stdin"):
        path = self.out / name
        return path.read_text() if path.exists() else None


class SendTest(SecondOpinionCase):
    def test_auto_prefers_codex_in_a_read_only_sandbox_with_the_diff_on_stdin(self):
        self.stub("codex", "gemini")
        (self.repo / "app.py").write_text("x = 2\n")
        code, out, _ = self.run_cli("--diff", "HEAD")
        self.assertEqual(code, 0)
        self.assertIn("REVIEW from codex", out)
        argv = self.sent("argv").split("\n")
        self.assertEqual(argv[1:], ["exec", "--sandbox", "read-only", "--skip-git-repo-check", "--color", "never", "-"])
        self.assertIn("+x = 2", self.sent())
        self.assertIn("Read-only", self.sent())

    def test_gemini_runs_without_yolo_and_auto_falls_back_to_it(self):
        self.stub("gemini")
        (self.repo / "app.py").write_text("x = 2\n")
        code, out, _ = self.run_cli("--diff", "HEAD")
        self.assertEqual(code, 0)
        self.assertIn("REVIEW from gemini", out)
        argv = self.sent("argv")
        self.assertIn("-p", argv.split("\n"))
        self.assertNotIn("yolo", argv)

    def test_a_plan_is_reviewed(self):
        self.stub("codex")
        (self.repo / "plan.md").write_text("# Plan\n1. Drop the users table\n")
        code, _, _ = self.run_cli("--plan", "plan.md")
        self.assertEqual(code, 0)
        self.assertIn("Drop the users table", self.sent())
        self.assertIn("engineering plan", self.sent())

    def test_dry_run_prints_the_prompt_and_sends_nothing(self):
        self.stub("codex")
        (self.repo / "app.py").write_text("x = 2\n")
        code, out, _ = self.run_cli("--diff", "HEAD", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("+x = 2", out)
        self.assertIsNone(self.sent())


class SafetyTest(SecondOpinionCase):
    def test_credentials_are_redacted_before_sending(self):
        self.stub("codex")
        (self.repo / "app.py").write_text(f"x = 2\nTOKEN = '{TOKEN}'\n")
        code, _, _ = self.run_cli("--diff", "HEAD")
        self.assertEqual(code, 0)
        sent = self.sent()
        self.assertNotIn(TOKEN, sent)
        self.assertIn("+[redacted: ", sent)
        self.assertIn("+x = 2", sent)

    def test_secret_files_are_left_out_and_named(self):
        self.stub("codex")
        (self.repo / ".env").write_text("DB_PASSWORD=hunter2hunter2\n")
        (self.repo / "keys.yaml").write_text("a: b\n")
        (self.repo / "keyboard.py").write_text("layout = 1\n")
        git(self.repo, "add", "-A")
        code, _, err = self.run_cli("--diff", "HEAD")
        self.assertEqual(code, 0)
        sent = self.sent()
        self.assertNotIn("hunter2", sent)
        self.assertNotIn("keys.yaml", sent)
        self.assertIn("keyboard.py", sent)
        self.assertIn("left out .env", err)
        self.assertIn("left out keys.yaml", err)

    def test_a_secret_looking_plan_is_refused(self):
        self.stub("codex")
        (self.repo / ".env").write_text("A=b\n")
        code, _, err = self.run_cli("--plan", ".env")
        self.assertEqual(code, 2)
        self.assertIn("looks like a secrets file", err)
        self.assertIsNone(self.sent())

    def test_without_a_cli_nothing_is_sent(self):
        (self.repo / "app.py").write_text("x = 2\n")
        code, _, err = self.run_cli("--diff", "HEAD")
        self.assertEqual(code, 3)
        self.assertIn("nothing was sent", err)
        self.stub("gemini")
        self.assertEqual(self.run_cli("--diff", "HEAD", "--cli", "codex")[0], 3)  # the one asked for is missing

    def test_oversized_material_is_refused_not_truncated(self):
        self.stub("codex")
        (self.repo / "app.py").write_text("x = 2\n" * 200)
        code, _, err = self.run_cli("--diff", "HEAD", "--max-bytes", "500")
        self.assertEqual(code, 4)
        self.assertIn("over --max-bytes 500", err)
        self.assertIsNone(self.sent())

    def test_a_huge_line_is_refused_or_replaced_fast_and_never_scanned(self):
        self.stub("codex")
        (self.repo / "app.py").write_text("a." * 120_000 + "\n")  # 240 KB on one line: quadratic for the check
        started = time.monotonic()
        code, _, _ = self.run_cli("--diff", "HEAD")
        self.assertEqual(code, 4)
        self.assertLess(time.monotonic() - started, 5)
        (self.repo / "app.py").write_text("x = 3\n" + "a." * 5000 + "\n")
        started = time.monotonic()
        code, _, _ = self.run_cli("--diff", "HEAD")
        self.assertEqual(code, 0)
        self.assertLess(time.monotonic() - started, 5)
        self.assertIn("[redacted: a line over 2000 characters]", self.sent())
        self.assertNotIn("a." * 1000, self.sent())

    def test_a_ref_that_looks_like_an_option_is_refused(self):
        self.stub("codex")
        for ref in ("--output=" + str(self.out / "planted"), "-p", ""):
            with self.subTest(ref=ref):
                code, _, err = self.run_cli(f"--diff={ref}")
                self.assertEqual(code, 2)
                self.assertFalse((self.out / "planted").exists())
                self.assertIsNone(self.sent())

    def test_a_cli_that_hangs_or_fails_is_exit_5(self):
        self.stub("codex")
        (self.repo / "app.py").write_text("x = 2\n")
        code, _, err = self.run_cli("--diff", "HEAD", "--timeout", "1", mode="sleep")
        self.assertEqual(code, 5)
        self.assertIn("did not answer within 1 s", err)
        code, _, err = self.run_cli("--diff", "HEAD", mode="fail")
        self.assertEqual(code, 5)
        self.assertIn("exited 7", err)


class InputTest(SecondOpinionCase):
    def test_empty_diff_bad_ref_missing_plan_and_bad_options(self):
        self.stub("codex")
        self.assertEqual(self.run_cli("--diff", "HEAD")[0], 2)  # nothing to review
        self.assertEqual(self.run_cli("--diff", "no-such-ref")[0], 2)
        self.assertEqual(self.run_cli("--plan", "missing.md")[0], 2)
        self.assertEqual(self.run_cli()[0], 2)  # argparse: one of --diff or --plan
        self.assertEqual(self.run_cli("--diff", "HEAD", "--plan", "x")[0], 2)
        self.assertEqual(self.run_cli("--diff", "HEAD", "--timeout", "0")[0], 2)
        self.assertIsNone(self.sent())

    def test_missing_secret_check_fails_closed(self):
        original = second_opinion.secret_check
        second_opinion.secret_check = lambda: None
        try:
            self.assertEqual(second_opinion.main(["--diff", "HEAD", "--dry-run"]), 2)
        finally:
            second_opinion.secret_check = original

    def test_secret_file_names(self):
        for path in (".env", "a/.env.prod", "id_rsa", "x/server.pem", "tls.key", "dir/keys.yaml", "service-key.json",
                     "api_key.txt", "secrets.json", "aws-credentials"):
            self.assertTrue(second_opinion.looks_secret(path), path)
        for path in ("keyboard.ts", "monkey.py", "src/env.ts", "donkey/app.py", "secretary.py", "turkey.json"):
            self.assertFalse(second_opinion.looks_secret(path), path)


if __name__ == "__main__":
    unittest.main()
