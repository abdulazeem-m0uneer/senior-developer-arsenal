"""Output safety of confirm_status: a lost stdout or stderr never changes the documented exit code."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_confirm_status import REF, SCRIPT, cs, reply  # noqa: E402


class Unwritable(io.StringIO):
    def write(self, text):
        raise OSError(5, "Input/output error")


def args(deadline="0", reference=REF):
    return ["--fetch-cmd", "unused {ref}", "--reference=" + reference, "--amount-minor", "5000",
            "--currency", "SEK", "--success", "paid", "--failure", "failed", "--deadline", deadline]


def fetching(result):
    def factory(cmd, fetch_timeout, remaining):
        def fetch(ref):
            if isinstance(result, Exception):
                raise result
            return result
        return fetch
    return factory


class UnwritableStderrTests(unittest.TestCase):
    """An OSError from the 'error:' print once escaped main, and Python's exit 1 reads as "failed"."""

    def run_main(self, stderr, argv, factory):
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()) as out:
            code = cs.main(argv, fetch_factory=factory)
        self.assertEqual(out.getvalue(), "")
        return code

    def test_a_usage_error_exits_2_with_stderr_broken_or_closed(self):
        for stderr in (Unwritable(), None):
            with self.subTest(stderr=type(stderr).__name__):
                self.assertEqual(self.run_main(stderr, args(reference="-x"), fetching(reply("paid"))), cs.EXIT_USAGE)

    def test_a_setup_error_exits_2_with_stderr_broken(self):
        code = self.run_main(Unwritable(), args(), fetching(cs.FetchSetupError("cannot run the fetch command")))
        self.assertEqual(code, cs.EXIT_USAGE)

    def test_an_internal_error_exits_5_with_stderr_broken_or_closed(self):
        for stderr in (Unwritable(), None):
            with self.subTest(stderr=type(stderr).__name__):
                self.assertEqual(self.run_main(stderr, args(), fetching(TypeError("bug"))), cs.EXIT_INTERNAL)

    def test_sigterm_still_exits_143_when_the_refusal_cannot_be_printed(self):
        refused = unittest.mock.Mock(returncode=None, pid=1)  # pid 1 is refused before any killpg
        with unittest.mock.patch.object(cs._SigtermHold, "proc", refused), \
                unittest.mock.patch.object(cs.os, "killpg") as killpg, \
                contextlib.redirect_stderr(Unwritable()):
            with self.assertRaises(SystemExit) as stop:
                cs._stop_on_sigterm(15, None)
        self.assertEqual(stop.exception.code, 143)
        killpg.assert_not_called()


class ClosedStdoutTests(unittest.TestCase):
    """With fd 1 closed at start, sys.stdout is None and print() once dropped the result line silently."""

    def test_no_stdout_exits_5_and_puts_the_result_line_on_stderr(self):
        for status, line_outcome in (("paid", "paid"), ("failed", "failed"), ("pending", "pending-reconcile")):
            with self.subTest(status=status):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(None):
                    code = cs.main(args(), fetching(reply(status)))
                self.assertEqual(code, cs.EXIT_INTERNAL)
                self.assertIn("stdout is closed", err.getvalue())
                self.assertIn('"outcome": "%s"' % line_outcome, err.getvalue())

    def test_no_stdout_and_no_stderr_still_exits_5(self):
        with contextlib.redirect_stderr(None), contextlib.redirect_stdout(None):
            self.assertEqual(cs.main(args(), fetching(reply("paid"))), cs.EXIT_INTERNAL)


class ExitFlushTests(unittest.TestCase):
    """A stdout whose flush fails at exit turns any exit code into 120, which the contract does not list."""

    def test_a_failing_final_flush_exits_hard_with_the_intended_code(self):
        class Stuck(io.StringIO):
            def flush(self):
                raise OSError(28, "No space left on device")

        for stream in (Stuck(), io.StringIO()):
            for code in (cs.EXIT_PAID, cs.EXIT_INTERNAL):
                with self.subTest(stream=type(stream).__name__, code=code):
                    hard_exit = unittest.mock.Mock(side_effect=SystemExit("hard"))
                    with contextlib.redirect_stdout(stream), self.assertRaises(SystemExit) as stop:
                        cs.exit_with(code, hard_exit=hard_exit)
                    if isinstance(stream, Stuck):
                        hard_exit.assert_called_once_with(code)
                    else:
                        hard_exit.assert_not_called()
                        self.assertEqual(stop.exception.code, code)

    def test_no_stdout_at_exit_is_a_plain_exit(self):
        hard_exit = unittest.mock.Mock()
        with contextlib.redirect_stdout(None), self.assertRaises(SystemExit) as stop:
            cs.exit_with(cs.EXIT_INTERNAL, hard_exit=hard_exit)
        self.assertEqual(stop.exception.code, cs.EXIT_INTERNAL)
        hard_exit.assert_not_called()


class CliOutputTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        fetch = self.dir / "fetch.py"
        fetch.write_text("import sys\nsys.stdout.write(%r)\n" % json.dumps(reply("pending")), encoding="utf-8")
        self.argv = [str(SCRIPT), "--fetch-cmd", "%s %s {ref}" % (sys.executable, fetch), "--reference", REF,
                     "--amount-minor", "5000", "--currency", "SEK", "--success", "paid", "--failure", "failed",
                     "--deadline", "0"]

    def run_wrapped(self, prelude, stdout):
        code = prelude + "import runpy, sys\nsys.argv = %r\nrunpy.run_path(sys.argv[0], run_name='__main__')\n" % (
            self.argv,)
        return subprocess.run([sys.executable, "-c", code], stdout=stdout, stderr=subprocess.PIPE, text=True,
                              cwd=self.dir, timeout=60)

    @unittest.skipUnless(os.path.exists("/dev/full"), "needs /dev/full")
    def test_a_full_stdout_without_dev_null_exits_5_not_120(self):
        no_devnull = (
            "import os\n"
            "real_open = os.open\n"
            "def failing_open(path, flags, *rest, **kw):\n"
            "    if path == os.devnull and flags == os.O_WRONLY:\n"
            "        raise OSError(24, 'Too many open files')\n"
            "    return real_open(path, flags, *rest, **kw)\n"
            "os.open = failing_open\n")
        with open("/dev/full", "w") as full:
            proc = self.run_wrapped(no_devnull, full)
        self.assertEqual(proc.returncode, cs.EXIT_INTERNAL, proc.stderr)
        self.assertIn("cannot write the result", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_started_with_fd_1_closed_exits_5_and_reports_on_stderr(self):
        close_fd_1 = "import os\nos.close(1)\nos.execv(%r, [%r] + %r)\n" % (sys.executable, sys.executable, self.argv)
        proc = subprocess.run([sys.executable, "-c", close_fd_1], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                              text=True, cwd=self.dir, timeout=60)
        self.assertEqual(proc.returncode, cs.EXIT_INTERNAL, proc.stderr)
        self.assertIn("stdout is closed", proc.stderr)
        self.assertIn('"outcome": "pending-reconcile"', proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
