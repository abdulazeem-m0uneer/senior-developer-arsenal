"""timer.py: durable timers (systemd units, launchd plist, pause file, run wrapper). No real systemd is ever called."""
import io
import os
import plistlib
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents" / "skills" / "multi-session-delivery" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import timer  # noqa: E402


def is_zombie(pid):
    try:
        return Path("/proc/%d/stat" % pid).read_text().rsplit(")", 1)[1].split()[0] == "Z"
    except (OSError, IndexError):
        return False

NOW = "2030-01-01T10:00:00+00:00"
STUB = """#!/bin/sh
d="$(dirname "$0")"
b="$(basename "$0")"
k="$b"
case " $* " in *" verify "*) k="$b.verify";; esac
echo "$@" >> "$d/$b.calls"
cat "$d/$k.out" 2>/dev/null
exit "$(cat "$d/$k.rc" 2>/dev/null || echo 0)"
"""


def analyze_out(when="Tue 2030-01-01 12:00:00 UTC"):
    return f"  Original form: x\nNormalized form: x\n    Next elapse: {when}\n       From now: 2h left\n"


def show_out(state="active", nxt="Tue 2030-01-01 12:00:00 UTC"):
    return f"NextElapseUSecRealtime={nxt}\nActiveState={state}\n"


class TimerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bin, self.units, self.state = root / "bin", root / "units", root / "state"
        self.bin.mkdir()
        for name in ("systemd-analyze", "systemctl"):
            stub = self.bin / name
            stub.write_text(STUB)
            stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        self.fake("systemd-analyze", analyze_out())
        self.fake("systemctl", show_out())
        self.addCleanup(time.tzset)  # registered first, so it runs after the environment is restored
        patcher = unittest.mock.patch.dict(
            os.environ, {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "TIMER_NOW": NOW, "TZ": "UTC"}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        time.tzset()

    def set_tz(self, zone):
        patcher = unittest.mock.patch.dict(os.environ, {"TZ": zone})
        patcher.start()
        time.tzset()
        self.addCleanup(time.tzset)
        self.addCleanup(patcher.stop)

    def fake(self, name, out="", rc=0):
        (self.bin / f"{name}.out").write_text(out)
        (self.bin / f"{name}.rc").write_text(str(rc))

    def run_cmd(self, *args):
        out, err = io.StringIO(), io.StringIO()
        code = timer.main([*args], out=lambda s: out.write(s + "\n"), err=lambda s: err.write(s + "\n"))
        return code, out.getvalue(), err.getvalue()

    def make(self, *extra, name="rep"):
        return self.run_cmd(
            "make", name, "--on-calendar", "daily", "--command", "/bin/true", "--timeout", "10m",
            "--dir", str(self.units), "--state-dir", str(self.state), *extra,
        )

    def service(self, name="rep"):
        return (self.units / f"{name}.service").read_text()

    def timer_file(self, name="rep"):
        return (self.units / f"{name}.timer").read_text()


class MakeTests(TimerCase):
    def test_happy_path_writes_bounded_oneshot_and_exact_timer(self):
        code, out, _ = self.make()
        self.assertEqual(code, 0)
        svc, tmr = self.service(), self.timer_file()
        self.assertIn("Type=oneshot", svc)
        self.assertIn("TimeoutStartSec=600s", svc)
        self.assertNotIn("RuntimeMaxSec", svc)
        self.assertIn("ExecStart=/bin/true", svc)
        self.assertIn(f"ConditionPathExists=!{self.state}/rep.paused", svc)
        self.assertIn("OnCalendar=daily", tmr)
        self.assertIn("AccuracySec=1s", tmr)
        self.assertNotIn("Persistent", tmr)
        self.assertIn("systemctl --user daemon-reload && systemctl --user enable --now rep.timer", out)
        self.assertIn("timer.py check rep", out)

    def test_persistent_only_with_flag_and_workdir(self):
        self.make("--persistent", "--workdir", "/srv/w")
        self.assertIn("Persistent=true", self.timer_file())
        self.assertIn("WorkingDirectory=/srv/w", self.service())

    def test_make_never_runs_systemctl(self):
        self.make()
        self.assertFalse((self.bin / "systemctl.calls").exists())

    def test_percent_in_command_is_escaped(self):
        self.run_cmd("make", "p", "--on-calendar", "daily", "--command", "date +%F", "--timeout", "1m",
                     "--dir", str(self.units), "--state-dir", str(self.state))
        self.assertIn("ExecStart=date +%%F", self.service("p"))

    def test_bad_spec_is_refused_and_writes_nothing(self):
        self.fake("systemd-analyze", analyze_out(), rc=1)  # even with a plausible next run on stdout
        code, _, err = self.make()
        self.assertEqual(code, 1)
        self.assertIn("OnCalendar", err)
        self.assertFalse(self.units.exists() and any(self.units.iterdir()))

    def test_spec_with_no_next_run_is_refused(self):
        self.fake("systemd-analyze", "Normalized form: x\n    Next elapse: never\n")
        self.assertEqual(self.make()[0], 1)

    def test_spec_is_validated_with_one_iteration(self):
        self.make()
        first = (self.bin / "systemd-analyze.calls").read_text().splitlines()[0]
        self.assertEqual(first.split(), ["calendar", "--iterations=1", "daily"])

    def test_missing_analyze_is_exit_2_not_a_pass(self):
        with unittest.mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            code, _, err = self.make()
        self.assertEqual(code, 2)
        self.assertIn("systemd-analyze", err)
        self.assertFalse(self.units.exists() and any(self.units.iterdir()))

    def test_utc_line_wins_over_local_zone_name(self):
        self.fake("systemd-analyze", "    Next elapse: Tue 2030-01-01 14:00:00 EET\n       (in UTC): Tue 2030-01-01 12:00:00 UTC\n")
        code, out, _ = self.make("--deadline", "2030-01-01T12:30:00+00:00")
        self.assertEqual(code, 0, out)

    def test_bad_names_are_refused(self):
        for bad in ("../x", "a b", "", "a/b", ".hidden", "x;y"):
            code, _, err = self.make(name=bad)
            self.assertEqual(code, 2, bad)
            self.assertIn("NAME", err)

    def test_option_like_spec_refused(self):
        code, _, _ = self.run_cmd("make", "n", "--on-calendar", "-x", "--command", "/bin/true", "--timeout", "1m",
                                  "--dir", str(self.units), "--state-dir", str(self.state))
        self.assertEqual(code, 2)

    def test_bad_timeout_is_usage_error(self):
        code, _, _ = self.run_cmd("make", "n", "--on-calendar", "daily", "--command", "/bin/true", "--timeout", "0",
                                  "--dir", str(self.units), "--state-dir", str(self.state))
        self.assertEqual(code, 2)

    def test_timeout_is_mandatory(self):
        code, _, _ = self.run_cmd("make", "n", "--on-calendar", "daily", "--command", "/bin/true", "--dir", str(self.units))
        self.assertEqual(code, 2)


class DeadlineTests(TimerCase):
    # the fake next run is 12:00 UTC
    def test_ok_with_room(self):
        self.assertEqual(self.make("--deadline", "2030-01-01T13:00:00+00:00")[0], 0)

    def test_exactly_the_margin_is_ok(self):
        self.assertEqual(self.make("--deadline", "2030-01-01T12:30:00+00:00")[0], 0)

    def test_one_second_inside_the_margin_is_refused(self):
        code, out, err = self.make("--deadline", "2030-01-01T12:29:59+00:00")
        self.assertEqual(code, 1)
        text = out + err
        self.assertIn("2030-01-01", text)
        self.assertIn("gap", text)
        self.assertFalse(self.units.exists() and any(self.units.iterdir()))

    def test_after_deadline_is_refused_as_after(self):
        code, _, err = self.make("--deadline", "2030-01-01T11:00:00+00:00", "--margin", "1s")
        self.assertEqual(code, 1)
        self.assertIn("after the deadline", err)

    def test_custom_margin(self):
        self.assertEqual(self.make("--deadline", "2030-01-01T12:10:00+00:00", "--margin", "10m")[0], 0)
        self.assertEqual(self.make("--deadline", "2030-01-01T12:10:00+00:00", "--margin", "11m")[0], 1)

    def test_bad_deadline_is_usage_error(self):
        self.assertEqual(self.make("--deadline", "tomorrow-ish")[0], 2)


class OverwriteTests(TimerCase):
    def test_different_existing_unit_is_refused_without_force(self):
        self.make()
        (self.units / "rep.timer").write_text("old")
        code, _, err = self.make()
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        self.assertEqual(self.timer_file(), "old")

    def test_force_overwrites(self):
        self.make()
        (self.units / "rep.timer").write_text("old")
        self.assertEqual(self.make("--force")[0], 0)
        self.assertIn("OnCalendar=daily", self.timer_file())

    def test_identical_rerun_is_fine(self):
        self.make()
        self.assertEqual(self.make()[0], 0)


class CheckTests(TimerCase):
    def check(self, *extra):
        return self.run_cmd("check", "rep", *extra)

    def test_ok_prints_next_and_relative_time(self):
        code, out, _ = self.check()
        self.assertEqual(code, 0)
        self.assertIn("rep next 2030-01-01 12:00", out)
        self.assertIn("(in 2h 0m)", out)
        self.assertEqual((self.bin / "systemctl.calls").read_text().split()[:3], ["--user", "show", "rep.timer"])

    def test_inactive_fails(self):
        self.fake("systemctl", show_out(state="inactive"))
        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("not active", err)

    def test_no_next_run_fails(self):
        for empty in ("", "n/a"):
            self.fake("systemctl", show_out(nxt=empty))
            self.assertEqual(self.check()[0], 1, empty)

    def test_margin_against_deadline(self):
        self.assertEqual(self.check("--deadline", "2030-01-01T12:30:00+00:00")[0], 0)
        self.assertEqual(self.check("--deadline", "2030-01-01T12:29:00+00:00")[0], 1)
        self.assertEqual(self.check("--deadline", "2030-01-01T11:00:00+00:00")[0], 1)

    def test_absurd_next_run_value_is_exit_2(self):
        self.fake("systemctl", show_out(nxt="99999999999999999999"))
        code, _, err = self.check()
        self.assertEqual(code, 2)
        self.assertIn("out of range", err)

    def test_systemctl_failure_is_exit_2(self):
        self.fake("systemctl", "", rc=1)
        self.assertEqual(self.check()[0], 2)

    def test_missing_systemctl_is_exit_2(self):
        with unittest.mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            code, _, err = self.check()
        self.assertEqual(code, 2)
        self.assertIn("systemctl", err)

    def test_bad_name(self):
        self.assertEqual(self.run_cmd("check", "../x")[0], 2)


class PauseTests(TimerCase):
    def pause_file(self):
        return self.state / "rep.paused"

    def test_pause_and_resume_are_idempotent_and_touch_no_timer(self):
        for _ in range(2):
            self.assertEqual(self.run_cmd("pause", "rep", "--state-dir", str(self.state))[0], 0)
            self.assertTrue(self.pause_file().exists())
        for _ in range(2):
            self.assertEqual(self.run_cmd("resume", "rep", "--state-dir", str(self.state))[0], 0)
            self.assertFalse(self.pause_file().exists())
        self.assertFalse((self.bin / "systemctl.calls").exists())

    def test_state_dir_defaults_to_xdg(self):
        with unittest.mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.tmp.name}):
            self.run_cmd("pause", "rep")
        self.assertTrue((Path(self.tmp.name) / "timers" / "rep.paused").exists())

    def test_bad_name(self):
        self.assertEqual(self.run_cmd("pause", "a/b", "--state-dir", str(self.state))[0], 2)


class LaunchdTests(TimerCase):
    def launchd(self, *extra, name="job"):
        return self.run_cmd("launchd", name, "--command", "echo hi there", "--timeout", "5m",
                            "--dir", str(self.units), "--state-dir", str(self.state), *extra)

    def plist(self, name="job"):
        return plistlib.loads((self.units / f"{name}.plist").read_bytes())

    def test_daily_plist(self):
        code, _, _ = self.launchd("--at", "07:05")
        self.assertEqual(code, 0)
        data = self.plist()
        self.assertEqual(data["Label"], "job")
        self.assertEqual(data["StartCalendarInterval"], {"Hour": 7, "Minute": 5})
        args = data["ProgramArguments"]
        self.assertEqual(args[:2], [sys.executable, str(Path(timer.__file__).resolve())])
        self.assertEqual(args[2:8], ["run", "--name", "job", "--timeout", "5m", "--state-dir"])
        self.assertEqual(args[-4:], ["--", "echo", "hi", "there"])

    def test_weekday_range_and_list_expand(self):
        self.launchd("--at", "09:30", "--weekdays", "1-5")
        self.assertEqual([d["Weekday"] for d in self.plist()["StartCalendarInterval"]], [1, 2, 3, 4, 5])
        self.launchd("--at", "09:30", "--weekdays", "1,3,5", "--force")
        self.assertEqual([d["Weekday"] for d in self.plist()["StartCalendarInterval"]], [1, 3, 5])

    def test_bad_at_and_weekdays_are_refused(self):
        for at in ("25:00", "9", "09:60", "*:30", "every day", "09:5"):
            self.assertEqual(self.launchd("--at", at)[0], 2, at)
        for wd in ("8", "5-1", "a", "1,,3", ""):
            self.assertEqual(self.launchd("--at", "09:00", "--weekdays", wd)[0], 2, wd)

    def test_overwrite_refused_without_force(self):
        self.launchd("--at", "09:00")
        self.assertEqual(self.launchd("--at", "10:00")[0], 1)
        self.assertEqual(self.plist()["StartCalendarInterval"]["Hour"], 9)


class RunTests(TimerCase):
    def alarm(self, seconds):
        def fail(*_):
            raise AssertionError(f"hung for {seconds}s")
        old = signal.signal(signal.SIGALRM, fail)
        self.addCleanup(signal.signal, signal.SIGALRM, old)
        self.addCleanup(signal.alarm, 0)
        signal.alarm(seconds)

    @staticmethod
    def kill_recorded(pidfile):
        try:
            os.kill(int(pidfile.read_text()), signal.SIGKILL)
        except (OSError, ValueError):
            pass

    def run_wrapper(self, *argv, timeout="30s", grace="0.3"):
        return self.run_cmd("run", "--name", "rep", "--timeout", timeout, "--state-dir", str(self.state),
                            "--grace", grace, "--", *argv)

    def test_paused_skips_with_exit_0(self):
        self.run_cmd("pause", "rep", "--state-dir", str(self.state))
        marker = Path(self.tmp.name) / "ran"
        code, out, _ = self.run_wrapper("touch", str(marker))
        self.assertEqual((code, "paused" in out, marker.exists()), (0, True, False))

    def test_exit_code_is_propagated(self):
        self.assertEqual(self.run_wrapper("sh", "-c", "exit 7")[0], 7)
        self.assertEqual(self.run_wrapper("true")[0], 0)

    def test_timeout_kills_group_and_exits_124(self):
        leader, grandchild = Path(self.tmp.name) / "leader.pid", Path(self.tmp.name) / "grandchild.pid"
        script = f"echo $$ > {leader}; sleep 30 & echo $! > {grandchild}; wait"
        for pidfile in (leader, grandchild):
            self.addCleanup(self.kill_recorded, pidfile)
        self.alarm(30)
        started = time.monotonic()
        code, _, err = self.run_wrapper("sh", "-c", script, timeout="3s")  # room to write both pid files first
        self.assertEqual(code, 124)
        self.assertLess(time.monotonic() - started, 15)
        for pidfile in (leader, grandchild):
            self.assert_gone(int(pidfile.read_text()))

    def test_sigterm_ignoring_child_gets_sigkill(self):
        pidfile = Path(self.tmp.name) / "stubborn.pid"
        script = f"trap '' TERM; echo $$ > {pidfile}; while true; do sleep 0.1; done"
        self.addCleanup(self.kill_recorded, pidfile)
        self.alarm(20)  # a regression that never sends SIGKILL must fail, not hang
        code, _, _ = self.run_wrapper("sh", "-c", script, timeout="3s", grace="0.3")
        signal.alarm(0)
        self.assertEqual(code, 124)
        self.assert_gone(int(pidfile.read_text()))

    def test_sighup_to_wrapper_takes_the_child_down(self):
        proc, child = self.spawn_wrapper()
        proc.send_signal(signal.SIGHUP)
        self.assertEqual(proc.wait(timeout=10), 129)
        self.assert_gone(child)

    def test_a_signal_the_caller_ignored_stays_ignored(self):
        for sig in (signal.SIGHUP, signal.SIGINT):  # as under nohup
            proc, child = self.spawn_wrapper(ignored=(sig,))
            proc.send_signal(sig)
            with self.assertRaises(subprocess.TimeoutExpired):
                proc.wait(timeout=1.0)
            self.assertIsNone(os.kill(child, 0))
            proc.send_signal(signal.SIGTERM)  # still handled
            self.assertEqual(proc.wait(timeout=10), 128 + signal.SIGTERM)
            self.assert_gone(child)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores file modes")
    def test_unreadable_pause_file_is_exit_2_with_a_message(self):
        self.state.mkdir()
        (self.state / "rep.paused").touch()
        self.state.chmod(0)
        self.addCleanup(self.state.chmod, 0o755)
        code, _, err = self.run_wrapper("true")
        self.assertEqual(code, 2)
        self.assertIn("cannot read pause file", err)

    def test_grandchild_left_behind_by_a_normal_exit_is_killed(self):
        pidfile = Path(self.tmp.name) / "gc.pid"
        self.addCleanup(self.kill_recorded, pidfile)
        code, _, _ = self.run_wrapper("sh", "-c", f"sleep 30 & echo $! > {pidfile}")
        self.assertEqual(code, 0)
        self.assert_gone(int(pidfile.read_text()))

    def test_bad_grace_is_exit_2(self):
        for grace in ("-1", "nan", "inf"):
            self.assertEqual(self.run_wrapper("true", grace=grace)[0], 2, grace)

    def test_not_executable_is_126_and_missing_is_127(self):
        plain = Path(self.tmp.name) / "plain"
        plain.write_text("x")
        self.assertEqual(self.run_wrapper(str(plain))[0], 126)
        code, _, err = self.run_wrapper("/nonexistent/cmd")
        self.assertEqual(code, 127)
        self.assertIn("/nonexistent/cmd", err)

    def spawn_wrapper(self, ignored=()):
        pidfile = Path(self.tmp.name) / "w.pid"
        pidfile.unlink(missing_ok=True)  # a second spawn in one test must not read the first child's pid
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPTS / "timer.py"), "run", "--name", "rep", "--timeout", "30s", "--state-dir",
             str(self.state), "--grace", "0.3", "--", "sh", "-c", f"echo $$ > {pidfile}; exec sleep 30"],
            stderr=subprocess.PIPE, text=True,
            preexec_fn=lambda: [signal.signal(sig, signal.SIG_IGN) for sig in ignored])
        self.addCleanup(proc.kill)
        self.addCleanup(self.kill_recorded, pidfile)
        for _ in range(600):  # 30 s: a loaded machine starts a python wrapper slowly
            if proc.poll() is not None:
                self.fail(f"wrapper exited early rc={proc.returncode}: {proc.stderr.read()}")
            if pidfile.exists() and pidfile.read_text().strip():
                return proc, int(pidfile.read_text())
            time.sleep(0.05)
        self.fail("child never started")

    def assert_gone(self, pid):
        for _ in range(40):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            if is_zombie(pid):  # dead, waiting for a reaper (in a PID namespace the runner is init)
                return
            time.sleep(0.05)
        self.fail(f"child {pid} still alive")

    def test_sigterm_to_wrapper_takes_the_child_down(self):
        proc, child = self.spawn_wrapper()
        proc.send_signal(signal.SIGTERM)
        self.assertEqual(proc.wait(timeout=10), 128 + signal.SIGTERM)
        self.assert_gone(child)

    def test_sigint_to_wrapper_has_no_traceback(self):
        proc, child = self.spawn_wrapper()
        proc.send_signal(signal.SIGINT)
        self.assertEqual(proc.wait(timeout=10), 128 + signal.SIGINT)
        self.assertNotIn("Traceback", proc.stderr.read())
        self.assert_gone(child)

    def test_no_command_is_usage_error(self):
        self.assertEqual(self.run_cmd("run", "--name", "rep", "--timeout", "1m", "--state-dir", str(self.state))[0], 2)


class DurationTests(unittest.TestCase):
    def test_valid(self):
        for text, seconds in (("90s", 90), ("30m", 1800), ("2h", 7200), ("1h30m", 5400), ("1h1m1s", 3661)):
            self.assertEqual(timer.parse_duration(text), seconds, text)

    def test_cap_is_366_days(self):
        self.assertEqual(timer.parse_duration("8784h"), 366 * 86400)
        with self.assertRaises(ValueError):
            timer.parse_duration("8785h")

    def test_invalid(self):
        for text in ("0", "0s", "0m0s", "-5m", "", "abc", "5", "1.5h", "30m1h", "1 h", "m"):
            with self.assertRaises(ValueError, msg=text):
                timer.parse_duration(text)


class InjectionTests(TimerCase):
    def refused_2(self, *extra, name="rep"):
        code, _, err = self.make(*extra, name=name)
        self.assertEqual(code, 2, extra)
        self.assertFalse(self.units.exists() and any(self.units.iterdir()))
        return err

    def test_trailing_backslash_is_refused_everywhere(self):
        self.refused_2("--workdir", "/srv/w\\")
        self.refused_2("--state-dir", str(self.state) + "\\")
        code, _, _ = self.run_cmd("make", "n", "--on-calendar", "daily", "--command", "/bin/true \\", "--timeout", "1m",
                                  "--dir", str(self.units), "--state-dir", str(self.state))
        self.assertEqual(code, 2)
        code, _, _ = self.run_cmd("make", "n", "--on-calendar", "daily\\", "--command", "/bin/true", "--timeout", "1m",
                                  "--dir", str(self.units), "--state-dir", str(self.state))
        self.assertEqual(code, 2)

    def test_newlines_and_carriage_returns_are_refused_everywhere(self):
        for bad in ("a\nb", "a\rb"):
            self.refused_2("--workdir", f"/srv/{bad}")
            self.refused_2("--state-dir", f"/s/{bad}")
            for flag in ("--command", "--on-calendar"):
                args = {"--on-calendar": "daily", "--command": "/bin/true", "--timeout": "1m"}
                args[flag] = bad
                code, _, _ = self.run_cmd("make", "n", *[x for kv in args.items() for x in kv],
                                          "--dir", str(self.units), "--state-dir", str(self.state))
                self.assertEqual(code, 2, (flag, bad))
        self.refused_2(name="rep\n")

    def test_relative_state_dir_becomes_absolute(self):
        cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, cwd)
        self.run_cmd("make", "rep", "--on-calendar", "daily", "--command", "/bin/true", "--timeout", "1m",
                     "--dir", str(self.units), "--state-dir", "rel")
        self.assertIn(f"ConditionPathExists=!{Path(self.tmp.name).resolve()}/rel/rep.paused", self.service())
        self.run_cmd("pause", "rep", "--state-dir", "rel")
        self.assertTrue((Path(self.tmp.name) / "rel" / "rep.paused").exists())

    def test_percent_in_state_dir_and_workdir_is_escaped(self):
        self.run_cmd("make", "rep", "--on-calendar", "daily", "--command", "/bin/true", "--timeout", "1m",
                     "--dir", str(self.units), "--state-dir", "/s/50%x", "--workdir", "/w/%h")
        self.assertIn("ConditionPathExists=!/s/50%%x/rep.paused", self.service())
        self.assertIn("WorkingDirectory=/w/%%h", self.service())

    def test_dollar_in_command_is_escaped(self):
        self.run_cmd("make", "p", "--on-calendar", "daily", "--command", "echo $HOME", "--timeout", "1m",
                     "--dir", str(self.units), "--state-dir", str(self.state))
        self.assertIn("ExecStart=echo $$HOME", self.service("p"))

    def test_empty_command_is_refused(self):
        for blank in ("", "   "):
            code, _, _ = self.run_cmd("make", "n", "--on-calendar", "daily", "--command", blank, "--timeout", "1m",
                                      "--dir", str(self.units), "--state-dir", str(self.state))
            self.assertEqual(code, 2, repr(blank))
        self.assertFalse(self.units.exists() and any(self.units.iterdir()))


class RangeTests(TimerCase):
    def test_huge_margin_is_exit_2(self):
        self.assertEqual(self.make("--deadline", "2030-01-01T13:00:00+00:00", "--margin", "99999999999h")[0], 2)
        self.assertEqual(self.run_cmd("check", "rep", "--margin", "99999999999h")[0], 2)

    def test_year_9999_deadline_is_exit_2_not_a_traceback(self):
        self.set_tz("UTC-3")
        code, _, err = self.make("--deadline", "9999-12-31T23:59:59+00:00")
        self.assertEqual(code, 2)
        self.assertIn("deadline", err)

    def test_naive_clock_is_treated_as_local(self):
        self.set_tz("UTC-3")  # 10:00 local is 07:00 UTC, so the 12:00 UTC run is 5h away (2h if read as UTC)
        with unittest.mock.patch.dict(os.environ, {"TIMER_NOW": "2030-01-01T10:00:00"}):
            code, out, _ = self.run_cmd("check", "rep")
        self.assertEqual(code, 0)
        self.assertIn("(in 5h 0m)", out)

    def test_garbage_clock_is_exit_2(self):
        with unittest.mock.patch.dict(os.environ, {"TIMER_NOW": "soon"}):
            self.assertEqual(self.run_cmd("check", "rep")[0], 2)


class WriteTests(TimerCase):
    def test_directory_at_unit_path_is_exit_2(self):
        (self.units / "rep.timer").mkdir(parents=True)
        code, _, err = self.make()
        self.assertEqual(code, 2)
        self.assertIn("not a file", err)
        self.assertFalse((self.units / "rep.service").exists())

    def test_symlink_at_unit_path_is_refused_and_target_untouched(self):
        self.units.mkdir()
        target = Path(self.tmp.name) / "elsewhere"
        target.write_text("keep")
        (self.units / "rep.service").symlink_to(target)
        code, _, err = self.make("--force")
        self.assertEqual(code, 1)
        self.assertIn("symlink", err)
        self.assertEqual(target.read_text(), "keep")
        self.assertFalse((self.units / "rep.timer").exists())

    def test_failure_on_second_file_leaves_no_half_pair(self):
        real = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError("disk full")
            return real(src, dst)

        with unittest.mock.patch("timer.os.replace", flaky):
            code, _, err = self.make()
        self.assertEqual(code, 2)
        self.assertIn("disk full", err)
        self.assertEqual(sorted(p.name for p in self.units.iterdir()), [])

    def test_failure_restores_the_previous_pair(self):
        self.make()
        old = (self.service(), self.timer_file())
        real = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError("disk full")
            return real(src, dst)

        with unittest.mock.patch("timer.os.replace", flaky):
            code, _, _ = self.make("--force", "--persistent")
        self.assertEqual((code, (self.service(), self.timer_file())), (2, old))

    def test_no_temp_files_remain(self):
        self.make()
        self.assertEqual(sorted(p.name for p in self.units.iterdir()), ["rep.service", "rep.timer"])


class OutputTests(TimerCase):
    def test_make_prints_state_dir_and_state_dir_flag_on_follow_up_lines(self):
        _, out, _ = self.make()
        self.assertIn(str(self.state), out)
        self.assertIn(f"--state-dir {self.state}", out)
        self.assertIn(f"pause rep --state-dir {self.state}", out)
        self.assertIn(f"check rep --state-dir {self.state}", out)

    def test_weekdays_seven_is_sunday_and_duplicates_collapse(self):
        self.run_cmd("launchd", "job", "--command", "/bin/true", "--timeout", "5m", "--dir", str(self.units),
                     "--state-dir", str(self.state), "--at", "09:00", "--weekdays", "7,0,1-2,2")
        data = plistlib.loads((self.units / "job.plist").read_bytes())
        self.assertEqual([d["Weekday"] for d in data["StartCalendarInterval"]], [0, 1, 2])

    def test_launchd_state_dir_is_absolute(self):
        cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, cwd)
        self.run_cmd("launchd", "job", "--command", "/bin/true", "--timeout", "5m", "--dir", str(self.units),
                     "--state-dir", "rel", "--at", "09:00")
        args = plistlib.loads((self.units / "job.plist").read_bytes())["ProgramArguments"]
        self.assertEqual(args[args.index("--state-dir") + 1], str(Path(self.tmp.name).resolve() / "rel"))


class VerifyTests(TimerCase):
    BAD = "Unit rep.service has a bad unit file setting.\n"

    def test_unit_pair_is_verified_with_systemd_analyze(self):
        self.make()
        verify = [line for line in (self.bin / "systemd-analyze.calls").read_text().splitlines() if "verify" in line]
        self.assertEqual(len(verify), 1)
        words = verify[0].split()
        self.assertEqual(words[:2], ["--user", "verify"])
        self.assertTrue(words[2].endswith("rep.service") and words[3].endswith("rep.timer"))

    def test_each_refusal_phrase_refuses_and_writes_nothing(self):
        for text in ("rep.service: Unit configuration has fatal error, unit will not be started.\n",
                     "rep.service: Service has no ExecStart=, ExecStop=, or SuccessAction=. Refusing.\n",
                     self.BAD):
            self.fake("systemd-analyze.verify", text, rc=1)
            code, _, err = self.make()
            self.assertEqual(code, 1, text)
            self.assertIn("rep.service", err)
            self.assertFalse(self.units.exists() and any(self.units.iterdir()))

    def test_warnings_about_other_units_are_ignored(self):
        self.fake("systemd-analyze.verify",
                  "/usr/lib/x/other.service:23: Unknown key 'StandardError' in section [Install], ignoring.\n"
                  "Unit other.service has a bad unit file setting.\n", rc=1)
        self.assertEqual(self.make()[0], 0)

    def test_relative_workdir_is_refused_up_front(self):
        code, _, err = self.make("--workdir", "rel/dir")
        self.assertEqual(code, 2)
        self.assertIn("absolute", err)
        self.assertEqual(self.make("--workdir", "/abs/dir")[0], 0)

    def test_bare_command_name_is_kept(self):
        self.assertEqual(self.run_cmd("make", "b", "--on-calendar", "daily", "--command", "echo hi", "--timeout", "1m",
                                      "--dir", str(self.units), "--state-dir", str(self.state))[0], 0)
        self.assertIn("ExecStart=echo hi", self.service("b"))


class CommandPortabilityTests(TimerCase):
    def make_cmd(self, command):
        return self.run_cmd("make", "n", "--on-calendar", "daily", "--command", command, "--timeout", "1m",
                            "--dir", str(self.units), "--state-dir", str(self.state))

    def launchd_cmd(self, command):
        return self.run_cmd("launchd", "n", "--at", "09:00", "--command", command, "--timeout", "1m",
                            "--dir", str(self.units), "--state-dir", str(self.state))

    def test_lone_semicolon_word_is_refused_on_both_backends(self):
        for command in ("/bin/a ; /bin/b", ";", "/bin/a ;"):
            self.assertEqual(self.make_cmd(command)[0], 2, command)
            self.assertEqual(self.launchd_cmd(command)[0], 2, command)
        self.assertEqual(self.make_cmd("/bin/echo a;b")[0], 0)

    def test_any_backslash_is_refused_on_both_backends(self):
        for command in ("/bin/echo \\x41", "/bin/echo a\\nb", "/bin/echo \\"):
            self.assertEqual(self.make_cmd(command)[0], 2, command)
            self.assertEqual(self.launchd_cmd(command)[0], 2, command)

    def test_non_utf8_arguments_are_exit_2(self):
        bad = "\udcff"
        base = ["make", "n", "--on-calendar", "daily", "--command", "/bin/true", "--timeout", "1m",
                "--dir", str(self.units), "--state-dir", str(self.state)]
        for flag, value in (("--command", f"/bin/echo {bad}"), ("--workdir", f"/w/{bad}"), ("--dir", f"{self.units}/{bad}"),
                            ("--state-dir", f"/s/{bad}")):
            argv = list(base)
            if flag in argv:
                argv[argv.index(flag) + 1] = value
            else:
                argv += [flag, value]
            self.assertEqual(self.run_cmd(*argv)[0], 2, flag)
        code, _, _ = self.run_cmd("launchd", "n", "--at", "09:00", "--command", "/bin/true", "--timeout", "1m",
                                  "--dir", f"{self.units}/{bad}", "--state-dir", str(self.state))
        self.assertEqual(code, 2)

    def test_header_lists_every_option(self):
        usage = timer.__doc__.split("usage:")[1].split("Exit:")[0]
        lines = {chunk.split()[0]: chunk for chunk in usage.split("timer.py ")[1:]}
        for option in ("--state-dir", "--margin"):
            self.assertIn(option, lines["check"])
        for option in ("--state-dir", "--python", "--force"):
            self.assertIn(option, lines["launchd"])
        self.assertIn("--python", lines["make"])
        self.assertIn("without a shell", timer.__doc__)


class DstTests(TimerCase):
    def check_at(self, stamp, deadline):
        self.set_tz("America/New_York")
        self.fake("systemctl", show_out(nxt=stamp))
        with unittest.mock.patch.dict(os.environ, {"TIMER_NOW": "2027-11-07T00:00:00-04:00"}):
            return self.run_cmd("check", "rep", "--deadline", deadline, "--margin", "1s")[0]

    def test_second_one_thirty_in_the_fall_back_hour_is_est(self):
        # 01:30 EST is 06:30 UTC, after a deadline of 06:15 UTC; read as EDT (05:30 UTC) it would pass
        self.assertEqual(self.check_at("Sun 2027-11-07 01:30:00 EST", "2027-11-07T01:15:00-05:00"), 1)

    def test_first_one_thirty_is_edt(self):
        self.assertEqual(self.check_at("Sun 2027-11-07 01:30:00 EDT", "2027-11-07T01:45:00-04:00"), 0)


class StateAndPythonTests(TimerCase):
    def test_default_state_dir_is_under_home_local_state(self):
        env = {"HOME": self.tmp.name}
        with unittest.mock.patch.dict(os.environ, env):
            os.environ.pop("XDG_STATE_HOME", None)
            self.run_cmd("pause", "rep")
        self.assertTrue((Path(self.tmp.name) / ".local" / "state" / "timers" / "rep.paused").exists())

    def run_launchd(self, *extra):
        return self.run_cmd("launchd", "job", "--at", "09:00", "--command", "/bin/true", "--timeout", "1m",
                            "--dir", str(self.units), "--state-dir", str(self.state), *extra)

    def in_venv(self):
        return unittest.mock.patch.multiple(sys, prefix="/venv", base_prefix="/usr")

    def test_venv_interpreter_warns_and_explicit_python_does_not(self):
        with self.in_venv():
            code, _, err = self.run_launchd()
            self.assertEqual(code, 0)
            self.assertIn("virtualenv", err)
            code, _, err = self.run_launchd("--python", "/usr/bin/python3", "--force")
        self.assertEqual(code, 0)
        self.assertNotIn("virtualenv", err)
        args = plistlib.loads((self.units / "job.plist").read_bytes())["ProgramArguments"]
        self.assertEqual(args[0], "/usr/bin/python3")

    def test_system_interpreter_does_not_warn(self):
        with unittest.mock.patch.multiple(sys, prefix="/usr", base_prefix="/usr"):
            self.assertNotIn("virtualenv", self.run_launchd()[2])

    def test_relative_python_is_exit_2(self):
        self.assertEqual(self.run_launchd("--python", "python3")[0], 2)

    def test_make_prints_the_chosen_python(self):
        _, out, _ = self.make("--python", "/opt/py/bin/python")
        self.assertIn("/opt/py/bin/python", out)

    def test_make_warns_about_a_venv_interpreter(self):
        with self.in_venv():
            self.assertIn("virtualenv", self.make()[2])


class ControlCharTests(TimerCase):
    BAD = ("a\x01b", "a\x7fb", "a\tb", "a\x1fb")

    def make_with(self, **overrides):
        opts = {"--command": "/bin/true", "--workdir": "/w", "--python": "/p/python", "--state-dir": str(self.state)}
        opts.update(overrides)
        argv = ["make", "n", "--on-calendar", "daily", "--timeout", "1m", "--dir", str(self.units)]
        return self.run_cmd(*argv, *[word for item in opts.items() for word in item])

    def launchd_with(self, **overrides):
        opts = {"--command": "/bin/true", "--python": "/p/python", "--state-dir": str(self.state)}
        opts.update(overrides)
        argv = ["launchd", "n", "--at", "09:00", "--timeout", "1m", "--dir", str(self.units)]
        return self.run_cmd(*argv, *[word for item in opts.items() for word in item])

    def test_control_characters_are_refused_in_every_unit_and_plist_string(self):
        for bad in self.BAD:
            for flag in ("--command", "--workdir", "--python", "--state-dir"):
                self.assertEqual(self.make_with(**{flag: f"/x/{bad}"})[0], 2, ("make", flag, bad))
            for flag in ("--command", "--python", "--state-dir"):
                self.assertEqual(self.launchd_with(**{flag: f"/x/{bad}"})[0], 2, ("launchd", flag, bad))
        self.assertEqual(self.make_with()[0], 0)


class RollbackTests(TimerCase):
    def test_failed_rollback_names_the_inconsistent_paths(self):
        self.make()
        real, calls = os.replace, []

        def flaky(src, dst):
            calls.append(dst)
            if len(calls) >= 2:  # the second write fails, and so does restoring the first
                raise OSError("disk full")
            return real(src, dst)

        with unittest.mock.patch("timer.os.replace", flaky):
            code, _, err = self.make("--force", "--persistent")
        self.assertEqual(code, 2)
        self.assertIn("rollback failed for", err)
        self.assertIn("rep.service", err)
        self.assertIn("half written", err)

    def test_one_failed_rollback_step_does_not_stop_the_rest(self):
        paths = [Path(self.tmp.name) / name for name in ("a", "b", "c")]
        for path in paths:
            path.write_bytes(b"old")
        real, calls = os.replace, []

        def flaky(src, dst):
            calls.append(dst)
            if len(calls) in (3, 4):  # c fails to write; restoring a fails too
                raise OSError("boom")
            return real(src, dst)

        with unittest.mock.patch("timer.os.replace", flaky):
            with self.assertRaises(timer.UsageError) as caught:
                timer.write_files({path: b"new" for path in paths}, True)
        self.assertEqual(paths[1].read_bytes(), b"old")  # b was still restored
        self.assertIn(str(paths[0]), str(caught.exception))
        self.assertNotIn(str(paths[1]), str(caught.exception))


class ShellQuotingTests(TimerCase):
    @staticmethod
    def words(out, key):
        line = next(line for line in out.splitlines() if line.startswith(f"{key}:"))
        return shlex.split(line.split(":", 1)[1])

    def test_printed_lines_survive_a_path_with_a_space(self):
        spaced = Path(self.tmp.name) / "my state"
        _, out, _ = self.run_cmd("make", "rep", "--on-calendar", "daily", "--command", "/bin/true", "--timeout", "1m",
                                 "--dir", str(self.units), "--state-dir", str(spaced), "--python", "/opt/my py/bin/python")
        for key in ("check", "pause"):
            words = self.words(out, key)
            self.assertEqual(words[0], "/opt/my py/bin/python", key)
            self.assertEqual(words[words.index(key) + 1], "rep")
            self.assertEqual(words[words.index("--state-dir") + 1], str(spaced))

    def test_launchctl_line_is_quoted(self):
        spaced = Path(self.tmp.name) / "my agents"
        _, out, _ = self.run_cmd("launchd", "job", "--at", "09:00", "--command", "/bin/true", "--timeout", "1m",
                                 "--dir", str(spaced), "--state-dir", str(self.state))
        self.assertEqual(self.words(out, "enable"), ["launchctl", "load", str(spaced / "job.plist")])


class PausedCheckTests(TimerCase):
    def test_check_reports_a_paused_routine_and_fails(self):
        self.run_cmd("pause", "rep", "--state-dir", str(self.state))
        code, _, err = self.run_cmd("check", "rep", "--state-dir", str(self.state))
        self.assertEqual(code, 1)
        self.assertIn(f"rep paused (pause file {self.state}/rep.paused)", err)

    def test_check_passes_again_after_resume(self):
        self.run_cmd("pause", "rep", "--state-dir", str(self.state))
        self.run_cmd("resume", "rep", "--state-dir", str(self.state))
        self.assertEqual(self.run_cmd("check", "rep", "--state-dir", str(self.state))[0], 0)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores file modes")
    def test_unreadable_state_dir_is_exit_2_for_check(self):
        self.state.mkdir()
        self.state.chmod(0)
        self.addCleanup(self.state.chmod, 0o755)
        code, _, err = self.run_cmd("check", "rep", "--state-dir", str(self.state))
        self.assertEqual(code, 2)
        self.assertIn("cannot read pause file", err)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores file modes")
    def test_unreadable_state_dir_is_exit_2_for_pause_and_resume(self):
        self.state.mkdir()
        self.state.chmod(0)
        self.addCleanup(self.state.chmod, 0o755)
        for verb in ("pause", "resume"):
            code, _, err = self.run_cmd(verb, "rep", "--state-dir", str(self.state))
            self.assertEqual(code, 2, verb)
            self.assertTrue(err)


class NameShapeTests(TimerCase):
    def test_unit_suffix_and_length(self):
        for bad in ("a.service", "x.timer", "a" * 201):
            self.assertEqual(self.run_cmd("pause", bad, "--state-dir", str(self.state))[0], 2, bad[:20])
        for good in ("a" * 200, "service", "a.services", "timer.x"):
            self.assertEqual(self.run_cmd("pause", good, "--state-dir", str(self.state))[0], 0, good[:20])


    def test_trailing_at_or_dot_is_refused(self):
        for bad in ("a@", "a.", "a..", "x@."):
            self.assertEqual(self.run_cmd("pause", bad, "--state-dir", str(self.state))[0], 2, bad)
        for good in ("a", "a.b", "a@b", "a-1", "a_"):
            self.assertEqual(self.run_cmd("pause", good, "--state-dir", str(self.state))[0], 0, good)


class PastDeadlineTests(TimerCase):
    def test_check_refuses_a_deadline_already_in_the_past(self):
        self.fake("systemctl", show_out(nxt="Mon 2029-12-31 10:00:00 UTC"))
        code, _, err = self.run_cmd("check", "rep", "--deadline", "2029-12-31T12:00:00+00:00", "--margin", "1s")
        self.assertEqual(code, 1)
        self.assertIn("already", err)


class NeverATracebackTests(TimerCase):
    def test_unwritable_dir_is_exit_2(self):
        blocker = Path(self.tmp.name) / "file"
        blocker.write_text("x")
        code, _, err = self.run_cmd("make", "n", "--on-calendar", "daily", "--command", "/bin/true", "--timeout", "1m",
                                    "--dir", str(blocker / "sub"), "--state-dir", str(self.state))
        self.assertEqual(code, 2)
        self.assertTrue(err)

    def test_unexecutable_tool_is_exit_2_not_a_traceback(self):
        blocked = Path(self.tmp.name) / "blocked"
        blocked.mkdir()
        (blocked / "systemd-analyze").write_text("not executable")
        with unittest.mock.patch.dict(os.environ, {"PATH": str(blocked)}):
            code, _, err = self.make()
        self.assertEqual(code, 2)
        self.assertTrue(err)

    def test_no_subcommand_is_usage_error(self):
        self.assertEqual(self.run_cmd()[0], 2)


if __name__ == "__main__":
    unittest.main()
