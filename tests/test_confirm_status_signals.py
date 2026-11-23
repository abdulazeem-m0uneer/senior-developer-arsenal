"""Signal and process-group safety of confirm_status: the kill guard and the SIGTERM races."""
import inspect
import io
import os
import signal
import subprocess
import sys
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_confirm_status import BAD, OK, REF, FakeTime, cs, is_zombie  # noqa: E402

@unittest.skipIf(os.name == "nt", "POSIX process groups")
class KillGroupSafetyTests(unittest.TestCase):
    """killpg(1) is kill(-1): a fake process whose pid reads as 1 once took down a whole desktop session.

    The refusal rules of cs.kill_group are checked with the other helpers in tests/test_kill_safety.py.
    """

    def test_a_mock_pgid_is_refused(self):
        with unittest.mock.patch.object(cs.os, "killpg") as killpg:
            with self.assertRaisesRegex(ValueError, "refusing to signal"):
                cs.kill_group(unittest.mock.MagicMock(), signal.SIGKILL)
        killpg.assert_not_called()

    def fake_process(self):
        """A mock process whose stdout is a private pipe that never becomes readable.

        A bare MagicMock stdout reads as fd 1, so the poll would watch and read the runner's own stdout.
        """
        read_end, write_end = os.pipe()
        self.addCleanup(os.close, write_end)
        fake = unittest.mock.MagicMock()
        fake.returncode = None  # still running, as a live Popen reads
        fake.stdout = os.fdopen(read_end, "rb")
        self.addCleanup(fake.stdout.close)
        return fake

    def test_a_fake_process_reaching_cleanup_is_refused_not_killpg_1(self):
        fake = self.fake_process()
        with unittest.mock.patch.object(cs.subprocess, "Popen", return_value=fake), \
                unittest.mock.patch.object(cs.os, "killpg") as killpg:
            with self.assertRaisesRegex(cs.FetchSetupError, "refusing to signal"):
                cs._run_bounded(["unused"], 1)
        killpg.assert_not_called()
        self.assertTrue(fake.stdout.closed)

    def test_a_refused_cleanup_ends_the_poll_instead_of_retrying(self):
        fake = self.fake_process()
        ft = FakeTime()
        fetch = cs.command_fetcher("prog {ref}", fetch_timeout=1)
        with unittest.mock.patch.object(cs.subprocess, "Popen", return_value=fake) as popen, \
                unittest.mock.patch.object(cs.os, "killpg") as killpg:
            with self.assertRaises(cs.FetchSetupError):
                cs.confirm(fetch, REF, 5000, "SEK", OK, BAD, 600, clock=ft.clock, sleep=ft.sleep)
        self.assertEqual(popen.call_count, 1)
        killpg.assert_not_called()
        self.assertTrue(fake.stdout.closed)


@unittest.skipIf(os.name == "nt", "POSIX process groups")
class SigtermRaceTests(unittest.TestCase):
    """A SIGTERM landing while the fetch command starts must still kill its group (the exit-143 promise)."""

    SLEEPER = (sys.executable, "-c", "import time; time.sleep(30)")

    def setUp(self):
        self.started = []
        self.real_popen = subprocess.Popen

    def spawn(self, *args, **kwargs):
        proc = self.real_popen(*args, **kwargs)
        self.started.append(proc)
        self.addCleanup(self.reap, proc)
        return proc

    def reap(self, proc):
        if proc.poll() is None:  # only the child this test started, never a mock
            proc.kill()
            proc.wait(timeout=5)

    def assert_child_group_dead(self):
        self.assertEqual(len(self.started), 1)
        proc = self.started[0]
        for _ in range(40):
            if proc.poll() is not None or is_zombie(proc.pid):
                return
            time.sleep(0.05)
        self.fail("the fetch command survived SIGTERM")

    def assert_hold_released(self):
        self.assertFalse(cs._SigtermHold.active)
        self.assertIsNone(cs._SigtermHold.pending)

    def test_sigterm_right_after_popen_returns_kills_the_group(self):
        real_monotonic = time.monotonic

        def monotonic():
            if self.started and not fired:
                fired.append(True)
                raise SystemExit(143)  # what _stop_on_sigterm raises at the next bytecode
            return real_monotonic()

        fired = []
        with unittest.mock.patch.object(cs.subprocess, "Popen", side_effect=self.spawn), \
                unittest.mock.patch.object(cs.time, "monotonic", side_effect=monotonic):
            with self.assertRaises(SystemExit) as caught:
                cs._run_bounded(self.SLEEPER, 5)
        self.assertEqual(caught.exception.code, 143)
        self.assert_child_group_dead()
        self.assert_hold_released()

    def test_sigterm_while_popen_runs_is_held_until_the_kill_is_armed(self):
        def spawn_then_signal(*args, **kwargs):
            proc = self.spawn(*args, **kwargs)
            cs._stop_on_sigterm(signal.SIGTERM, None)  # delivered inside Popen, after the fork
            return proc

        with unittest.mock.patch.object(cs.subprocess, "Popen", side_effect=spawn_then_signal):
            with self.assertRaises(SystemExit) as caught:
                cs._run_bounded(self.SLEEPER, 5)
        self.assertEqual(caught.exception.code, 143)
        self.assert_child_group_dead()
        self.assert_hold_released()

    def test_sigterm_held_while_popen_fails_still_exits_143(self):
        def signal_then_fail(*args, **kwargs):
            cs._stop_on_sigterm(signal.SIGTERM, None)
            raise OSError("no such program")

        with unittest.mock.patch.object(cs.subprocess, "Popen", side_effect=signal_then_fail):
            with self.assertRaises(SystemExit) as caught:
                cs._run_bounded(["unused"], 5)
        self.assertEqual(caught.exception.code, 143)
        self.assert_hold_released()

    def sigterm_at_line(self, text, argv, timeout):
        """Deliver SIGTERM (call the handler) when _run_bounded reaches the line holding text; return the exit."""
        code = cs._run_bounded.__code__
        lines, first = inspect.getsourcelines(cs._run_bounded)
        hits = [first + i for i, line in enumerate(lines) if line.strip() == text]
        self.assertEqual(len(hits), 1, text)

        def local(frame, event, arg):
            if event == "line" and frame.f_lineno == hits[0]:
                cs._stop_on_sigterm(signal.SIGTERM, None)
            return local

        def tracer(frame, event, arg):
            return local if frame.f_code is code else None

        self.addCleanup(sys.settrace, None)
        with unittest.mock.patch.object(cs.subprocess, "Popen", side_effect=self.spawn):
            sys.settrace(tracer)
            try:
                with self.assertRaises(SystemExit) as caught:
                    cs._run_bounded(argv, timeout)
            finally:
                sys.settrace(None)
        self.assert_hold_released()
        self.assertIsNone(cs._SigtermHold.proc)
        return caught.exception.code

    def sigterm_at_cleanup_line(self, text):
        self.assertEqual(self.sigterm_at_line(text, self.SLEEPER, 0.3), 143)  # times out: cleanup must kill
        self.assert_child_group_dead()

    def test_no_fetch_is_left_armed_after_a_run(self):
        with unittest.mock.patch.object(cs.subprocess, "Popen", side_effect=self.spawn):
            cs._run_bounded((sys.executable, "-c", "print(1)"), 5)
            self.assertIsNone(cs._SigtermHold.proc)
            with self.assertRaises(TimeoutError):
                cs._run_bounded(self.SLEEPER, 0.3)
            self.assertIsNone(cs._SigtermHold.proc)

    def test_sigterm_entering_cleanup_before_the_hold_still_kills_the_group(self):
        self.sigterm_at_cleanup_line("if proc is not None:")

    def test_sigterm_before_the_cleanup_hold_is_armed_still_kills_the_group(self):
        self.sigterm_at_cleanup_line("if not clean:")

    def test_sigterm_after_the_fetch_is_reaped_signals_nothing(self):
        with unittest.mock.patch.object(cs.os, "killpg") as killpg:
            code = self.sigterm_at_line("clean = True", (sys.executable, "-c", "print(1)"), 5)
        self.assertEqual(code, 143)
        self.assertIsNotNone(self.started[0].returncode)
        killpg.assert_not_called()  # a reaped pid may already belong to another process

    def test_sigterm_between_the_reap_and_the_returncode_signals_nothing(self):
        def spawn_with_late_returncode(*args, **kwargs):
            proc = self.spawn(*args, **kwargs)
            record_exit = proc._handle_exitstatus

            def handle(sts, *rest):
                cs._stop_on_sigterm(signal.SIGTERM, None)  # waitpid reaped the child; returncode is still None
                record_exit(sts, *rest)

            proc._handle_exitstatus = handle
            return proc

        with unittest.mock.patch.object(cs.subprocess, "Popen", side_effect=spawn_with_late_returncode), \
                unittest.mock.patch.object(cs.os, "killpg") as killpg:
            with self.assertRaises(SystemExit) as caught:
                cs._run_bounded((sys.executable, "-c", "print(1)"), 5)
        self.assertEqual(caught.exception.code, 143)
        killpg.assert_not_called()  # the reaped pid may already belong to another process group
        self.assert_hold_released()
        self.assertIsNone(cs._SigtermHold.proc)

    def test_sigterm_during_the_cleanup_kill_waits_for_the_reap(self):
        def spawn_signalled_in_wait(*args, **kwargs):
            proc = self.spawn(*args, **kwargs)
            real_wait = proc.wait

            def wait(*a, **kw):
                cs._stop_on_sigterm(signal.SIGTERM, None)  # a second SIGTERM, after the cleanup's kill
                return real_wait(*a, **kw)

            proc.wait = wait
            return proc

        with unittest.mock.patch.object(cs.subprocess, "Popen", side_effect=spawn_signalled_in_wait):
            with self.assertRaises(SystemExit) as caught:
                cs._run_bounded(self.SLEEPER, 0.3)
        self.assertEqual(caught.exception.code, 143)
        self.assertEqual(self.started[0].returncode, -signal.SIGKILL)  # killed and reaped, not left a zombie
        self.assert_hold_released()
        self.assertIsNone(cs._SigtermHold.proc)

    def test_a_kill_refused_by_the_os_ends_the_poll_instead_of_retrying(self):
        ft = FakeTime()
        fetch = cs.command_fetcher("prog {ref}", fetch_timeout=1)
        with unittest.mock.patch.object(cs.subprocess, "Popen",
                                        side_effect=lambda *a, **kw: self.spawn(self.SLEEPER, **kw)) as popen, \
                unittest.mock.patch.object(cs.os, "killpg", side_effect=PermissionError(1, "EPERM")):
            with self.assertRaisesRegex(cs.FetchSetupError, "EPERM"):
                cs.confirm(fetch, REF, 5000, "SEK", OK, BAD, 600, clock=ft.clock, sleep=ft.sleep)
        self.assertEqual(popen.call_count, 1)  # a retry would leave one more unkilled fetch command
        self.assertTrue(self.started[0].stdout.closed)

    def test_sigterm_outside_a_fetch_start_exits_at_once(self):
        with self.assertRaises(SystemExit) as caught:
            cs._stop_on_sigterm(signal.SIGTERM, None)
        self.assertEqual(caught.exception.code, 143)
        self.assert_hold_released()

    def sigterm_main_during_a_fetch(self, refusal):
        """Send a real SIGTERM to this thread while main() runs a fetch that every kill refuses; return the exit."""
        fetch_cmd = "%s -c 'import time; time.sleep(30)' {ref}" % sys.executable
        argv = ["--fetch-cmd", fetch_cmd, "--reference", REF, "--amount-minor", "5000", "--currency", "SEK",
                "--success", "paid", "--failure", "failed", "--deadline", "1m"]
        timer = threading.Timer(0.3, signal.pthread_kill, (threading.main_thread().ident, signal.SIGTERM))
        self.addCleanup(timer.cancel)
        with unittest.mock.patch.object(cs.subprocess, "Popen", side_effect=self.spawn), refusal, \
                unittest.mock.patch.object(cs.sys, "stderr", io.StringIO()) as stderr:
            timer.start()
            with self.assertRaises(SystemExit) as caught:
                cs.main(argv)
        self.assertEqual(len(self.started), 1)
        self.assert_hold_released()
        self.assertIsNone(cs._SigtermHold.proc)
        return caught.exception.code, stderr.getvalue()

    def test_sigterm_exits_143_when_the_os_refuses_the_kill(self):
        refusal = unittest.mock.patch.object(cs.os, "killpg", side_effect=PermissionError(1, "EPERM"))
        code, stderr = self.sigterm_main_during_a_fetch(refusal)
        self.assertEqual(code, 143)  # not 2: the SIGTERM must not be lost to the refused kill
        self.assertIn("EPERM", stderr)

    def test_sigterm_exits_143_when_the_guard_refuses_the_kill(self):
        refusal = unittest.mock.patch.object(cs, "_protected_groups", return_value=unittest.mock.MagicMock(
            __contains__=lambda *_: True))
        code, stderr = self.sigterm_main_during_a_fetch(refusal)
        self.assertEqual(code, 143)
        self.assertIn("refusing to signal", stderr)


class ReapGraceTests(unittest.TestCase):
    """A fetch that closes stdout right at its time limit still gets MIN_FETCH_TIMEOUT_S to exit."""

    def test_eof_at_the_time_limit_is_reaped_within_the_grace(self):
        read_end, write_end = os.pipe()
        os.close(write_end)  # stdout reads EOF at once
        fake = unittest.mock.MagicMock()
        fake.pid = "not-a-pid"  # any kill attempt is refused by the guard, never sent
        fake.returncode = None
        fake.stdout = os.fdopen(read_end, "rb")
        self.addCleanup(fake.stdout.close)
        clock = FakeTime()
        polls = []

        def poll():
            polls.append(clock.now)
            if len(polls) == 3:  # exits two polls (0.02s) after EOF, inside the 0.1s grace
                fake.returncode = 0
            return fake.returncode

        fake.poll.side_effect = poll
        real_read = os.read

        def read_at_the_limit(fd, size):
            data = real_read(fd, size)
            if not data:
                clock.now += 5  # EOF arrives just as the 5s fetch time runs out
            return data

        with unittest.mock.patch.object(cs.subprocess, "Popen", return_value=fake), \
                unittest.mock.patch.object(cs.time, "monotonic", side_effect=clock.clock), \
                unittest.mock.patch.object(cs.time, "sleep", side_effect=clock.sleep), \
                unittest.mock.patch.object(cs.os, "read", side_effect=read_at_the_limit), \
                unittest.mock.patch.object(cs.os, "killpg") as killpg:
            self.assertEqual(cs._run_bounded(["unused"], 5), (0, b""))
        self.assertEqual(len(polls), 3)
        killpg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
