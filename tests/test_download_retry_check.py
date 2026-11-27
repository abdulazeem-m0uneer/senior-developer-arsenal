"""Tests for devops-ci's download_retry_check.py (curl and wget calls in CI files that have no retry)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "devops-ci" / "scripts" / "download_retry_check.py"


def workflow(*run_lines):
    body = "\n".join("          " + line for line in run_lines)
    return "jobs:\n  build:\n    steps:\n      - name: fetch\n        run: |\n" + body + "\n"


class DownloadRetryCheck(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, rel, text):
        path = self.dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_check(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.dir,
                              capture_output=True, text=True)

    def check_workflow(self, *run_lines):
        path = self.write("wf.yml", workflow(*run_lines))
        return self.run_check(str(path)), path

    def test_curl_download_without_retry_is_reported_with_line(self):
        res, path = self.check_workflow("curl -fsSL https://cdn.example/tool.tgz -o tool.tgz")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertEqual(res.stdout.strip(), f"{path}:6: curl needs --retry N")

    def test_curl_with_retry_passes(self):
        res, _ = self.check_workflow("curl -fsSL --retry 3 https://cdn.example/t -o t")
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_curl_retry_equals_form_passes(self):
        res, _ = self.check_workflow("curl -fsSL --retry=2 https://cdn.example/t -o t")
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_curl_retry_one_or_zero_is_reported(self):
        for n in ("1", "0"):
            with self.subTest(n=n):
                res, _ = self.check_workflow(f"curl -fsSL --retry {n} https://cdn.example/t -o t")
                self.assertEqual(res.returncode, 1, res.stdout)

    def test_retry_all_errors_alone_is_not_a_retry(self):
        res, _ = self.check_workflow("curl -fsSL --retry-all-errors https://cdn.example/t -o t")
        self.assertEqual(res.returncode, 1, res.stdout)

    def test_retry_count_from_variable_passes(self):
        res, _ = self.check_workflow('curl -fsSL --retry "$TRIES" https://cdn.example/t -o t')
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_curl_flags_that_download(self):
        for flags in ("-O", "-o out", "-L", "-fsSLO", "--output out", "--remote-name", "--location"):
            with self.subTest(flags=flags):
                res, _ = self.check_workflow(f"curl {flags} https://cdn.example/t")
                self.assertEqual(res.returncode, 1, res.stdout)

    def test_curl_piped_to_shell_or_tar_is_reported(self):
        for tail in ("| bash", "| sh -s -- -y", "| sudo tar xz", "| tar xz -C /opt"):
            with self.subTest(tail=tail):
                res, _ = self.check_workflow(f"curl -s https://cdn.example/t {tail}")
                self.assertEqual(res.returncode, 1, res.stdout)

    def test_curl_api_call_is_not_a_download(self):
        for line in ("curl -s https://api.example/health", "curl -s https://api.example/x | jq .ok"):
            with self.subTest(line=line):
                res, _ = self.check_workflow(line)
                self.assertEqual(res.returncode, 0, res.stdout)

    def test_a_plain_wget_passes_because_it_tries_20_times(self):
        res, _ = self.check_workflow("wget https://cdn.example/t.tgz")
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_wget_with_one_try_is_reported(self):
        res, path = self.check_workflow("wget -t 1 https://cdn.example/t.tgz")
        self.assertEqual(res.returncode, 1)
        self.assertEqual(res.stdout.strip(), f"{path}:6: wget needs --tries=N")

    def test_wget_tries_forms_pass(self):
        for flags in ("--tries=3", "--tries 3", "-t 3", "-t3"):
            with self.subTest(flags=flags):
                res, _ = self.check_workflow(f"wget {flags} https://cdn.example/t")
                self.assertEqual(res.returncode, 0, res.stdout)

    def test_wget_tries_one_is_reported(self):
        for flags in ("--tries=1", "--tries 1", "-t 1", "-t1", "-qt1"):
            with self.subTest(flags=flags):
                res, _ = self.check_workflow(f"wget {flags} https://cdn.example/t")
                self.assertEqual(res.returncode, 1, res.stdout)

    def test_wget_spider_is_not_a_download(self):
        res, _ = self.check_workflow("wget --spider https://cdn.example/t")
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_installing_wget_is_not_a_download(self):
        res, _ = self.check_workflow("sudo apt-get install -y curl wget")
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_wget_of_a_variable_url_is_reported_with_one_try(self):
        res, _ = self.check_workflow('wget -t 1 "$TOOL_URL"')
        self.assertEqual(res.returncode, 1, res.stdout)

    def test_single_line_run_is_checked(self):
        path = self.write("wf.yml", "steps:\n  - run: curl -fsSLO https://cdn.example/t\n  - run: echo ok\n")
        res = self.run_check(str(path))
        self.assertEqual(res.returncode, 1)
        self.assertEqual(res.stdout.strip(), f"{path}:2: curl needs --retry N")

    def test_curl_outside_a_run_block_is_ignored(self):
        text = ("steps:\n  - name: curl -O https://x/y\n    run: |\n      echo hi\n"
                "    env:\n      HINT: curl -O https://x/y\n")
        res = self.run_check(str(self.write("wf.yml", text)))
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_comment_line_is_ignored(self):
        res, _ = self.check_workflow("# curl -O https://cdn.example/t", "echo done")
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_continuation_lines_are_one_command(self):
        res, path = self.check_workflow("curl -fsSL \\", "  --retry 3 \\", "  -o t https://cdn.example/t")
        self.assertEqual(res.returncode, 0, res.stdout)
        res, path = self.check_workflow("curl -fsSL \\", "  -o t https://cdn.example/t")
        self.assertEqual(res.stdout.strip(), f"{path}:6: curl needs --retry N")

    def test_command_in_retry_loop_counts_as_retried(self):
        loops = (["for i in 1 2 3; do", "  curl -fsSLO https://cdn.example/t && break", "done"],
                 ["until curl -fsSLO https://cdn.example/t; do", "  sleep 2", "done"],
                 ["n=0", "while [ $n -lt 3 ]; do", "  wget -t 1 https://cdn.example/t && break", "  n=$((n+1))", "done"])
        for lines in loops:
            with self.subTest(first=lines[0]):
                res, _ = self.check_workflow(*lines)
                self.assertEqual(res.returncode, 0, res.stdout)

    def test_command_after_loop_is_not_retried(self):
        res, _ = self.check_workflow("for i in 1 2; do", "  echo $i", "done", "curl -fsSLO https://cdn.example/t")
        self.assertEqual(res.returncode, 1, res.stdout)

    def test_two_commands_on_one_line_are_judged_separately(self):
        res, _ = self.check_workflow("curl --retry 3 -fsSLO https://a/t && curl -fsSLO https://b/t")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertEqual(len(res.stdout.strip().splitlines()), 1)

    def test_shell_js_and_python_scripts_are_checked(self):
        sh = self.write("ci/get.sh", "#!/bin/sh\ncurl -fsSLO https://cdn.example/t\n")
        js = self.write("ci/get.mjs", 'execSync("curl -fsSL https://cdn.example/t | bash");\n')
        py = self.write("ci/get.py", 'subprocess.run(["wget", "-t", "1", "https://cdn.example/t"])\n')
        res = self.run_check(str(sh.parent))
        self.assertEqual(res.returncode, 1)
        self.assertEqual(sorted(res.stdout.splitlines()), sorted([
            f"{sh}:2: curl needs --retry N", f"{js}:1: curl needs --retry N", f"{py}:1: wget needs --tries=N"]))

    def test_python_list_form_with_retry_passes(self):
        path = self.write("ci/get.py", 'subprocess.run(["curl", "-fsSLO", "--retry", "3", url])\n')
        self.assertEqual(self.run_check(str(path)).returncode, 0)

    def test_defaults_scan_workflows_and_ci_folders(self):
        self.write(".github/workflows/a.yml", workflow("curl -O https://x/t"))
        self.write("tools/ci/b.sh", "wget -t 1 https://x/t\n")
        self.write("src/app.sh", "curl -O https://x/t\n")
        res = self.run_check()
        self.assertEqual(res.returncode, 1)
        out = res.stdout
        self.assertIn("a.yml:6: curl needs --retry N", out)
        self.assertIn("b.sh:1: wget needs --tries=N", out)
        self.assertNotIn("app.sh", out)

    def test_defaults_with_nothing_to_scan_pass(self):
        res = self.run_check()
        self.assertEqual(res.returncode, 0)

    def test_clean_files_exit_zero_and_print_nothing(self):
        path = self.write("wf.yml", workflow("curl --retry 3 -fsSLO https://x/t", "wget -t 3 https://x/u"))
        res = self.run_check(str(path))
        self.assertEqual((res.returncode, res.stdout), (0, ""))

    def test_missing_path_is_bad_input(self):
        res = self.run_check(str(self.dir / "nope"))
        self.assertEqual(res.returncode, 2)
        self.assertIn("nope", res.stderr)

    def test_non_utf8_file_is_bad_input(self):
        path = self.dir / "bad.sh"
        path.write_bytes(b"curl \xff\xfe -O x\n")
        self.assertEqual(self.run_check(str(path)).returncode, 2)

    def test_other_files_in_a_folder_are_skipped(self):
        self.write("ci/README.md", "curl -O https://x/t\n")
        self.assertEqual(self.run_check(str(self.dir / "ci")).returncode, 0)

    def test_python_for_loop_is_not_a_shell_retry_loop(self):
        path = self.write("ci/get.py", 'for x in range(3):\n    pass\nsubprocess.run(["curl", "-fsSLO", "https://cdn.example/t"])\n')
        res = self.run_check(str(path))
        self.assertEqual(res.stdout.strip(), f"{path}:3: curl needs --retry N")

    def test_loop_over_different_files_is_not_a_retry(self):
        for lines in (["for f in a b c; do", "  curl -fsSLO https://cdn.example/$f", "done"],
                      ["for f in a b; do curl -fsSLO \"https://cdn.example/${f}\"; done"],
                      ["while read u; do", "  curl -O $u", "done < urls"]):
            with self.subTest(first=lines[0]):
                res, _ = self.check_workflow(*lines)
                self.assertEqual(res.returncode, 1, res.stdout)

    def test_one_line_retry_loop_passes(self):
        res, _ = self.check_workflow("for i in 1 2 3; do curl -fsSLO https://cdn.example/t && break; done")
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_wget_as_an_argument_or_text_is_not_a_download(self):
        for line in ("apt-get install -y wget ca-certificates $EXTRA", 'echo "wget $URL"', "which wget $X"):
            with self.subTest(line=line):
                res, _ = self.check_workflow(line)
                self.assertEqual(res.returncode, 0, res.stdout)

    def test_wget_after_wrapper_or_keyword_is_a_download(self):
        for line in ("sudo wget -t 1 https://x/t", "FOO=1 wget -t 1 https://x/t", "if wget -t 1 https://x/t; then echo; fi",
                     "x=$(curl -fsSLO https://x/t)"):
            with self.subTest(line=line):
                res, _ = self.check_workflow(line)
                self.assertEqual(res.returncode, 1, res.stdout)

    def test_output_to_dev_null_is_not_a_download(self):
        for line in ('curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health',
                     "curl -sL --output /dev/null https://x/y"):
            with self.subTest(line=line):
                res, _ = self.check_workflow(line)
                self.assertEqual(res.returncode, 0, res.stdout)

    def test_wget_infinite_tries_passes(self):
        for flags in ("-t 0", "--tries=0", "--tries=inf", "-t inf", "-t 2", "--tries=5"):
            with self.subTest(flags=flags):
                res, _ = self.check_workflow(f"wget {flags} https://cdn.example/t")
                self.assertEqual(res.returncode, 0, res.stdout)

    def test_folder_scan_skips_vendored_folders_and_undecodable_files(self):
        self.write("node_modules/p/i.js", 'execSync("curl -O https://x/t");\n')
        (self.dir / "ci").mkdir()
        (self.dir / "ci" / "bad.sh").write_bytes(b"\xff\xfe\n")
        self.write("ci/ok.sh", "curl -O https://x/t\n")
        res = self.run_check(str(self.dir))
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertEqual(res.stdout.strip(), f"{self.dir / 'ci' / 'ok.sh'}:1: curl needs --retry N")

    def test_multi_line_argv_array_is_one_command(self):
        text = 'execFileSync("curl", [\n  "-fsSLO",\n  "https://x/t",\n]);\n'
        path = self.write("ci/get.js", text)
        self.assertEqual(self.run_check(str(path)).stdout.strip(), f"{path}:1: curl needs --retry N")
        retried = self.write("ci/ok.js", 'execFileSync("curl", [\n  "-fsSLO",\n  "--retry", "3",\n  "https://x/t",\n]);\n')
        self.assertEqual(self.run_check(str(retried)).returncode, 0)


if __name__ == "__main__":
    unittest.main()
