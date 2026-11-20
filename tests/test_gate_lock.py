"""gate_lock.py: the kernel lock decides busy, leftover processes ended, git lock report. Temp dirs only."""
import json
import errno
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "quality-gate" / "scripts" / "gate_lock.py"
sys.path.insert(0, str(SCRIPT.parent))

import gate_lock  # noqa: E402

REAL_PID_ALIVE = gate_lock.pid_alive
T0 = "2030-01-01T10:00:00+00:00"
T_PLUS_73 = "2030-01-01T11:13:00+00:00"
PY = sys.executable


def record(pid, started=T0, host=None, cmd="make gate", max_minutes=45):
    return {"pid": pid, "started": started, "host": host or gate_lock.socket.gethostname(),
            "cwd": "/w", "command": cmd, "max_minutes": max_minutes}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.lock = str(self.dir / "gate.lock")
        self.rec = Path(self.lock + ".json")
        env = unittest.mock.patch.dict(os.environ, {"GATE_LOCK_NOW": T0}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        self.dead = 4_000_000_000  # no real pid
        alive = unittest.mock.patch.object(gate_lock, "pid_alive", lambda pid: pid != self.dead)
        alive.start()
        self.addCleanup(alive.stop)
        self.settles = []
        settle = unittest.mock.patch.object(gate_lock, "settle", lambda: self.settles.append(1))
        settle.start()
        self.addCleanup(settle.stop)

    def call(self, *argv):
        out, err = [], []
        rc = gate_lock.main(list(argv), out=out.append, err=err.append)
        return rc, "\n".join(out), "\n".join(err)

    def run_gate(self, *opts, cmd=None):
        return self.call("run", "--lock", self.lock, *opts, "--", *(cmd or [PY, "-c", "pass"]))

    def put(self, rec, held=False):
        """Write the holder record; held=True also takes the kernel lock, as a live gate would."""
        if rec is None:
            self.rec.unlink(missing_ok=True)
        else:
            self.rec.write_text(json.dumps(rec) if isinstance(rec, dict) else rec, encoding="utf-8")
        if held:
            self.holder = open(self.lock, "a+b")
            self.assertTrue(gate_lock._try_lock(self.holder))
            self.addCleanup(self.unhold)

    def unhold(self):
        if getattr(self, "holder", None):
            self.holder.close()
            self.holder = None


class RunTests(Base):
    def test_passes_exit_code_and_removes_record(self):
        self.assertEqual(self.run_gate(cmd=[PY, "-c", "raise SystemExit(0)"])[0], 0)
        self.assertFalse(self.rec.exists())
        self.assertEqual(self.run_gate(cmd=[PY, "-c", "raise SystemExit(7)"])[0], 7)
        self.assertFalse(self.rec.exists())

    def test_record_written_while_running(self):
        probe = f"import json;d=json.load(open({str(self.rec)!r}));print(d['pid']>0,d['max_minutes'],d['command'])"
        out = subprocess.run([PY, str(SCRIPT), "run", "--lock", self.lock, "--max-minutes", "9", "--", PY, "-c", probe],
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(out.split()[:2], ["True", "9"])

    def test_record_removed_when_runner_raises(self):
        with unittest.mock.patch.object(gate_lock.subprocess, "Popen", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.run_gate()
        self.assertFalse(self.rec.exists())

    def test_missing_command_exit_127_and_record_removed(self):
        rc, _, err = self.run_gate(cmd=["no-such-binary-xyz"])
        self.assertEqual(rc, 127)
        self.assertIn("no-such-binary-xyz", err)
        self.assertFalse(self.rec.exists())

    def test_a_command_the_os_cannot_exec_is_exit_126(self):
        script = Path(self.lock).parent / "no-shebang"
        script.write_text("echo hi\n")
        script.chmod(0o755)
        rc, _, err = self.run_gate(cmd=[str(script)])
        self.assertEqual(rc, 126)
        self.assertIn("cannot run", err)
        self.assertFalse(self.rec.exists())

    def test_the_replaced_lock_message_names_the_record_file(self):
        text = gate_lock.replaced_message({"pid": 42, "started": "T", "command": "make gate"}, "/x/gate.lock")
        self.assertIn("/x/gate.lock.json", text)

    def test_no_command_is_usage_error(self):
        self.assertEqual(self.call("run", "--lock", self.lock)[0], 2)

    def test_there_is_no_take_over_option(self):
        with unittest.mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            self.call("run", "--lock", self.lock, "--take-over", "--", "true")

    def test_env_var_sets_default_lock(self):
        path = str(self.dir / "viaenv.lock")
        with unittest.mock.patch.dict(os.environ, {"ARSENAL_GATE_LOCK": path}):
            self.assertEqual(gate_lock.lock_path(None), Path(path))
        self.assertEqual(gate_lock.lock_path("/x/y.lock"), Path("/x/y.lock"))

    def test_default_lock_is_under_cache_dir(self):
        with unittest.mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "/c"}):
            os.environ.pop("ARSENAL_GATE_LOCK", None)
            self.assertEqual(gate_lock.lock_path(None), Path("/c/arsenal/gate.lock"))

    def test_record_of_another_holder_is_left_alone_at_the_end(self):
        newer = json.dumps(record(os.getpid() + 1, cmd="newer"))
        write = f"open({str(self.rec)!r}, 'w').write({newer!r})"
        self.assertEqual(self.run_gate(cmd=[PY, "-c", write])[0], 0)
        self.assertEqual(json.loads(self.rec.read_text())["command"], "newer")

    def test_wait_then_take(self):
        self.put(record(os.getpid(), cmd="g"), held=True)
        ticks = []

        def sleep(seconds):  # the holder finishes while we wait
            ticks.append(seconds)
            self.rec.unlink(missing_ok=True)
            self.unhold()

        with unittest.mock.patch.object(gate_lock.time, "sleep", sleep):
            rc, _, _ = self.run_gate("--wait-minutes", "1")
        self.assertEqual((rc, ticks[0]), (0, 1))

    def test_wait_gives_up_busy(self):
        self.put(record(os.getpid()), held=True)
        clock = iter(range(0, 10_000, 30))

        def sleep(_):
            os.environ["GATE_LOCK_NOW"] = "2030-01-01T10:%02d:00+00:00" % (next(clock) // 30 + 1)

        with unittest.mock.patch.object(gate_lock.time, "sleep", sleep):
            rc, _, err = self.run_gate("--wait-minutes", "2")
        self.assertEqual(rc, 5)
        self.assertIn("busy", err)

    def test_backoff_grows_and_is_capped(self):
        self.assertEqual([gate_lock.backoff(n) for n in (0, 1, 2, 3, 4, 9)], [1, 2, 4, 8, 10, 10])


class BusyTests(Base):
    """The kernel lock alone says busy; the record only says who."""

    def test_busy_exit_5_with_holder_info_and_how_to_stop_it(self):
        self.put(record(os.getpid(), cmd="npm run gate"), held=True)
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 5)
        self.assertIn(f"busy: held by pid {os.getpid()} since {T0} (npm run gate)", err)
        self.assertIn(f"to stop it: kill {os.getpid()}", err)
        self.assertNotIn("over its", err)
        self.assertEqual(json.loads(self.rec.read_text())["pid"], os.getpid())  # record untouched

    def test_over_limit_is_only_a_hint_never_a_reason_to_clear(self):
        os.environ["GATE_LOCK_NOW"] = T_PLUS_73
        self.put(record(os.getpid(), cmd="slow"), held=True)
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 5)
        self.assertIn("running 73 min, over its 45 min limit", err)
        self.assertNotIn("cleared", err)

    def test_dead_pid_but_lock_held_is_busy_and_names_fuser(self):
        self.put(record(self.dead, cmd="make gate"), held=True)
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 5)
        self.assertIn(f"pid {self.dead} is gone, its leftover processes hold the lock", err)
        self.assertIn(f"fuser {self.lock}", err)
        self.assertTrue(self.rec.exists())

    def test_lock_held_without_record(self):
        self.put(None, held=True)
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 5)
        self.assertIn("held by a process that left no record", err)
        self.assertIn(f"`fuser {self.lock}` or `lsof {self.lock}`", err)

    def test_lock_held_with_corrupt_record_is_no_record(self):
        self.put("{nope", held=True)
        self.assertIn("left no record", self.run_gate()[2])
        self.assertTrue(self.rec.exists())

    def test_other_host_record_names_the_host_and_no_pid_advice(self):
        self.put(record(self.dead, host="other-box"), held=True)
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 5)
        self.assertIn("on host other-box", err)
        self.assertNotIn("kill", err)
        self.assertNotIn("fuser", err)


class StaleTests(Base):
    """Kernel lock free: take it, replace any leftover record with one line."""

    def test_dead_pid_cleared_with_message(self):
        self.put(record(self.dead, cmd="make gate"))
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 0)
        self.assertIn(f"cleared stale gate lock: pid {self.dead} (dead) started {T0}: make gate", err)

    def test_live_pid_with_free_lock_is_a_reused_pid(self):
        self.put(record(os.getpid(), cmd="make gate"))
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 0)
        self.assertIn(f"cleared stale gate lock: pid {os.getpid()} (reused) started {T0}: make gate", err)

    def test_age_does_not_matter_when_the_lock_is_free(self):
        os.environ["GATE_LOCK_NOW"] = T_PLUS_73
        self.put(record(os.getpid()))
        self.assertEqual(self.run_gate()[0], 0)

    def test_corrupt_record_cleared_with_message(self):
        for text in ("{not json", "[]", json.dumps({"pid": "x"}), ""):
            with self.subTest(text=text):
                self.put(text)
                rc, _, err = self.run_gate()
                self.assertEqual(rc, 0)
                self.assertIn("cleared stale gate lock: unreadable holder record", err)
                self.assertFalse(self.rec.exists())

    def test_string_pid_in_an_otherwise_full_record_is_corrupt(self):
        self.put({**record(1), "pid": "123"})
        self.assertIn("unreadable holder record", self.run_gate()[2])

    def test_bad_start_time_is_corrupt(self):
        self.put(record(os.getpid(), started="yesterday"))
        self.assertIn("unreadable holder record", self.run_gate()[2])

    def test_no_message_when_there_is_no_record(self):
        self.assertEqual(self.run_gate()[2], "")


class FailureTests(Base):
    def test_unopenable_lock_is_exit_2_with_message(self):
        blocker = self.dir / "file"
        blocker.write_text("")
        rc, _, err = self.call("run", "--lock", str(blocker / "sub" / "g.lock"), "--", PY, "-c", "pass")
        self.assertEqual(rc, 2)
        self.assertIn("cannot open or lock", err)

    def test_os_error_while_locking_is_exit_2_not_busy(self):
        with unittest.mock.patch.object(gate_lock.fcntl, "flock", side_effect=OSError(errno.EIO, "io")):
            rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("cannot open or lock", err)

    def test_contended_errno_is_busy_not_error(self):
        for code in (errno.EAGAIN, errno.EACCES):
            with self.subTest(code=code):
                with unittest.mock.patch.object(gate_lock.fcntl, "flock", side_effect=OSError(code, "held")):
                    self.assertEqual(self.run_gate()[0], 5)

    def test_record_write_failure_is_exit_2_and_frees_the_lock(self):
        with unittest.mock.patch.object(gate_lock, "_write_record", side_effect=OSError(errno.ENOSPC, "full")):
            self.assertEqual(self.run_gate()[0], 2)
        self.assertTrue(gate_lock.lock_is_free(Path(self.lock)))

    def test_release_failure_keeps_the_command_exit_code(self):
        with unittest.mock.patch.object(gate_lock.Path, "unlink", side_effect=OSError("denied")):
            rc, _, err = self.run_gate(cmd=[PY, "-c", "raise SystemExit(3)"])
        self.assertEqual(rc, 3)
        self.assertIn("could not remove the holder record: denied", err)

    def test_group_cleanup_failure_keeps_the_command_exit_code(self):
        with unittest.mock.patch.object(gate_lock, "group_count", side_effect=RuntimeError("ps broke")):
            rc, _, err = self.run_gate(cmd=[PY, "-c", "raise SystemExit(4)"])
        self.assertEqual(rc, 4)
        self.assertIn("could not end the gate's leftover processes: ps broke", err)
        self.assertFalse(self.rec.exists())


class RetryTests(Base):
    """A brief competing probe (status, a racing run) must not look like a holder."""

    def flaky(self, answers):
        real, seen = gate_lock._try_lock, iter(answers)

        def fake(handle):
            answer = next(seen)
            return real(handle) if answer is None else answer

        return unittest.mock.patch.object(gate_lock, "_try_lock", fake)

    def test_run_retries_a_failed_lock_before_reporting_busy(self):
        with self.flaky([False, False, None]):
            self.assertEqual(self.run_gate()[0], 0)
        self.assertEqual(len(self.settles), 2)

    def test_run_is_busy_after_three_retries(self):
        with self.flaky([False] * 4):
            rc, _, err = self.run_gate()
        self.assertEqual((rc, len(self.settles)), (5, 3))
        self.assertIn("left no record", err)

    def test_status_retries_before_saying_held(self):
        Path(self.lock).write_text("")
        with self.flaky([False, None]):
            self.assertEqual(self.call("status", "--lock", self.lock)[1], "free")
        self.assertEqual(len(self.settles), 1)
        with self.flaky([False] * 4):
            self.assertTrue(self.call("status", "--lock", self.lock)[1].startswith("held, no record"))
        self.assertEqual(len(self.settles), 4)


class ReplacedLockFileTests(Base):
    """rm of the lock file during a run must not let a second gate in."""

    def inode(self):
        st = os.stat(self.lock)
        return [st.st_dev, st.st_ino]

    def test_deleted_lock_file_with_a_live_holder_is_busy_not_cleared(self):
        self.put({**record(os.getpid() + 1, cmd="live"), "lock_inode": [1, 1]}, held=True)
        os.unlink(self.lock)
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 5)
        self.assertIn(f"lock file was replaced while pid {os.getpid() + 1} runs", err)
        self.assertIn(f"kill {os.getpid() + 1}", err)
        self.assertNotIn("cleared", err)
        self.assertEqual(json.loads(self.rec.read_text())["command"], "live")

    def test_replaced_lock_file_with_a_dead_holder_is_cleared(self):
        self.put({**record(self.dead), "lock_inode": [1, 1]})
        self.assertIn("(dead)", self.run_gate()[2])

    def test_same_inode_and_live_pid_is_still_a_reused_pid(self):
        Path(self.lock).write_text("")
        self.put({**record(os.getpid() + 1), "lock_inode": self.inode()})
        self.assertIn("(reused)", self.run_gate()[2])

    def test_own_pid_with_another_inode_is_not_a_replaced_lock(self):
        self.put({**record(os.getpid()), "lock_inode": [1, 1]})
        self.assertIn("(reused)", self.run_gate()[2])

    def test_same_inode_number_on_another_device_is_a_different_file(self):
        handle = unittest.mock.Mock()
        same = lambda dev: unittest.mock.Mock(st_ino=5, st_dev=dev)
        with unittest.mock.patch.object(gate_lock.os, "fstat", return_value=same(1)), \
                unittest.mock.patch.object(gate_lock.os, "stat", return_value=same(2)):
            self.assertFalse(gate_lock.same_inode(handle, "x"))
        with unittest.mock.patch.object(gate_lock.os, "fstat", return_value=same(1)), \
                unittest.mock.patch.object(gate_lock.os, "stat", return_value=same(1)):
            self.assertTrue(gate_lock.same_inode(handle, "x"))

    def test_record_without_inode_keeps_the_old_rules(self):
        self.put(record(os.getpid() + 1))
        self.assertIn("(reused)", self.run_gate()[2])

    def test_record_carries_the_lock_inode(self):
        probe = f"import json;print(json.load(open({str(self.rec)!r}))['lock_inode'])"
        done = subprocess.run([PY, str(SCRIPT), "run", "--lock", self.lock, "--", PY, "-c", probe],
                              capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(done.stdout), self.inode())

    def test_file_removed_between_open_and_lock_is_retried(self):
        real, calls = gate_lock._try_lock, []

        def fake(handle):
            calls.append(1)
            if len(calls) == 1:
                os.unlink(self.lock)
            return real(handle)

        with unittest.mock.patch.object(gate_lock, "_try_lock", fake):
            self.assertEqual(self.run_gate()[0], 0)
        self.assertEqual(len(calls), 2)

    def test_file_that_keeps_vanishing_is_exit_2(self):
        real = gate_lock._try_lock

        def fake(handle):
            os.unlink(self.lock)
            return real(handle)

        with unittest.mock.patch.object(gate_lock, "_try_lock", fake):
            rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("keeps being replaced", err)


class GroupCountTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.bin = Path(tmp.name)
        patched = unittest.mock.patch.dict(os.environ, {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"})
        patched.start()
        self.addCleanup(patched.stop)

    def fake_ps(self, body):
        ps = self.bin / "ps"
        ps.write_text("#!/bin/sh\n" + body)
        ps.chmod(0o755)

    @unittest.skipIf(os.name == "nt", "posix ps")
    def test_failing_ps_falls_back_to_the_group_probe(self):
        self.fake_ps("exit 1\n")
        self.assertEqual(gate_lock.group_count(os.getpgid(0)), 1)

    @unittest.skipIf(os.name == "nt", "posix ps")
    def test_unparsable_ps_output_falls_back_to_the_group_probe(self):
        self.fake_ps("echo garbage\n")
        self.assertEqual(gate_lock.group_count(os.getpgid(0)), 1)

    @unittest.skipIf(os.name == "nt", "posix ps")
    def test_ps_with_output_but_a_failure_code_is_not_trusted(self):
        self.fake_ps(f"echo '0 S'; exit 1\n")
        self.assertEqual(gate_lock.group_count(os.getpgid(0)), 1)

    @unittest.skipIf(os.name == "nt", "posix ps")
    def test_fallback_probe_says_zero_for_a_missing_group(self):
        self.fake_ps("exit 1\n")
        self.assertEqual(gate_lock.group_count(4_000_000), 0)

    @unittest.skipIf(os.name == "nt", "posix ps")
    def test_working_ps_counts_live_members_and_skips_zombies(self):
        self.fake_ps("printf '77 S\\n77 Z\\n77 R+\\n88 S\\n'\n")
        self.assertEqual(gate_lock.group_count(77), 2)
        self.assertEqual(gate_lock.group_count(99), 0)


class UnitTests(Base):
    def test_release_closes_the_lock_file_even_when_the_record_cannot_be_read(self):
        handle = unittest.mock.Mock()
        with unittest.mock.patch.object(gate_lock, "read_record", side_effect=OSError("x")):
            gate_lock.release(self.lock, handle, lambda _: None)
        handle.close.assert_called_once_with()

    @unittest.skipIf(os.name == "nt", "process groups are POSIX")
    def test_end_group_stops_after_sigterm_when_the_group_is_gone(self):
        counts = iter([1, 0, 0, 0])
        with unittest.mock.patch.object(gate_lock, "group_count", lambda _: next(counts)), \
                unittest.mock.patch.object(gate_lock.os, "killpg") as killpg:
            gate_lock.end_group(4242, 5, lambda _: None)
        killpg.assert_called_once_with(4242, signal.SIGTERM)

    @unittest.skipIf(os.name == "nt", "signals are POSIX")
    def test_signal_before_the_command_started_exits_128_plus_signal(self):
        handle = unittest.mock.Mock()
        handle.fileno.return_value = 0
        with unittest.mock.patch.object(gate_lock.subprocess, "Popen",
                                        side_effect=lambda *a, **k: os.kill(os.getpid(), signal.SIGTERM)):
            with self.assertRaises(SystemExit) as caught:
                gate_lock.run_command(["x"], handle, 1, lambda _: None)
        self.assertEqual(caught.exception.code, 128 + signal.SIGTERM)


class StatusTests(Base):
    def test_free_even_with_a_leftover_record(self):
        self.assertEqual(self.call("status", "--lock", self.lock)[1], "free")
        self.put(record(self.dead))
        self.assertEqual(self.call("status", "--lock", self.lock)[1], "free")

    def test_held(self):
        os.environ["GATE_LOCK_NOW"] = "2030-01-01T10:12:00+00:00"
        self.put(record(os.getpid(), cmd="make gate"), held=True)
        self.assertEqual(self.call("status", "--lock", self.lock)[1], f"held (pid {os.getpid()}, 12 min, make gate)")

    def test_held_over_limit(self):
        os.environ["GATE_LOCK_NOW"] = T_PLUS_73
        self.put(record(os.getpid(), cmd="g"), held=True)
        self.assertEqual(self.call("status", "--lock", self.lock)[1],
                         f"held (pid {os.getpid()}, 73 min, g), running 73 min, over its 45 min limit")

    def test_held_no_record(self):
        self.put(None, held=True)
        out = self.call("status", "--lock", self.lock)[1]
        self.assertTrue(out.startswith("held, no record ("))
        self.assertIn("fuser", out)

    def test_json(self):
        self.assertEqual(json.loads(self.call("status", "--lock", self.lock, "--json")[1]), {"state": "free"})
        self.put(record(os.getpid(), cmd="g"), held=True)
        data = json.loads(self.call("status", "--lock", self.lock, "--json")[1])
        self.assertEqual((data["state"], data["pid"], data["age_minutes"], data["command"], data["over_limit"]),
                         ("held", os.getpid(), 0, "g", False))
        self.assertTrue(data["pid_alive"])
        os.environ["GATE_LOCK_NOW"] = T_PLUS_73
        data = json.loads(self.call("status", "--lock", self.lock, "--json")[1])
        self.assertEqual((data["age_minutes"], data["over_limit"]), (73, True))
        os.environ["GATE_LOCK_NOW"] = T0
        self.unhold()
        self.put(None, held=True)
        self.assertEqual(json.loads(self.call("status", "--lock", self.lock, "--json")[1]),
                         {"state": "held", "record": False})


class PidAliveTests(unittest.TestCase):
    def test_own_pid_alive_and_nonpositive_never(self):
        self.assertTrue(REAL_PID_ALIVE(os.getpid()))
        self.assertFalse(REAL_PID_ALIVE(0))
        self.assertFalse(REAL_PID_ALIVE(-5))

    @unittest.skipIf(os.name == "nt", "posix os.kill semantics")
    def test_permission_error_means_alive_and_lookup_error_dead(self):
        with unittest.mock.patch.object(gate_lock.os, "kill", side_effect=PermissionError):
            self.assertTrue(REAL_PID_ALIVE(77))
        with unittest.mock.patch.object(gate_lock.os, "kill", side_effect=ProcessLookupError):
            self.assertFalse(REAL_PID_ALIVE(77))

    def test_exited_child_is_dead(self):
        child = subprocess.Popen([PY, "-c", "pass"])
        child.wait()
        self.assertFalse(REAL_PID_ALIVE(child.pid))


class GitLockTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / "r"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i")
        env = unittest.mock.patch.dict(os.environ, {"GATE_LOCK_NOW": ""}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("GATE_LOCK_NOW")

    def git(self, *args, cwd=None):
        subprocess.run(["git", *args], cwd=cwd or self.repo, check=True, capture_output=True)

    def age(self, path, minutes):
        old = time.time() - minutes * 60
        os.utime(path, (old, old))

    def call(self, *argv):
        out, err = [], []
        rc = gate_lock.main(["git-lock", *argv], out=out.append, err=err.append)
        return rc, "\n".join(out)

    def test_none_found(self):
        self.assertEqual(self.call("--repo", str(self.repo)), (0, "no stale git locks"))

    def test_old_index_lock_found_with_rm_command(self):
        lock = self.repo / ".git" / "index.lock"
        lock.write_text("")
        self.age(lock, 30)
        rc, out = self.call("--repo", str(self.repo))
        self.assertEqual(rc, 1)
        self.assertIn(f"rm -f {lock}", out)
        self.assertIn("30 min", out)
        self.assertTrue(lock.exists())  # never deleted by the tool

    def test_young_lock_ignored_and_limit_respected(self):
        lock = self.repo / ".git" / "index.lock"
        lock.write_text("")
        self.age(lock, 3)
        self.assertEqual(self.call("--repo", str(self.repo))[0], 0)
        self.assertEqual(self.call("--repo", str(self.repo), "--older-than-minutes", "2")[0], 1)

    def test_ref_lock_found(self):
        ref = self.repo / ".git" / "refs" / "heads" / "x.lock"
        ref.write_text("")
        self.age(ref, 20)
        rc, out = self.call("--repo", str(self.repo))
        self.assertEqual(rc, 1)
        self.assertIn(str(ref), out)

    def test_worktree_git_dir(self):
        wt = self.repo.parent / "wt"
        self.git("worktree", "add", "-q", str(wt), "-b", "b")
        wt_git = Path(subprocess.run(["git", "rev-parse", "--absolute-git-dir"], cwd=wt, capture_output=True,
                                     text=True, check=True).stdout.strip())
        own, shared = wt_git / "index.lock", self.repo / ".git" / "refs" / "heads" / "y.lock"
        own.write_text("")
        shared.write_text("")
        self.age(own, 25)
        self.age(shared, 25)
        rc, out = self.call("--repo", str(wt))
        self.assertEqual(rc, 1)
        self.assertIn(str(own), out)
        self.assertIn(str(shared), out)

    def test_worktree_lock_found_from_the_main_checkout(self):
        wt = self.repo.parent / "wt2"
        self.git("worktree", "add", "-q", str(wt), "-b", "b2")
        own = next((self.repo / ".git" / "worktrees").iterdir()) / "index.lock"
        own.write_text("")
        self.age(own, 25)
        rc, out = self.call("--repo", str(self.repo))
        self.assertEqual(rc, 1)
        self.assertIn(str(own), out)

    def test_not_a_repo_is_usage_error(self):
        out, err = [], []
        with tempfile.TemporaryDirectory() as plain:
            rc = gate_lock.main(["git-lock", "--repo", plain], out=out.append, err=err.append)
        self.assertEqual(rc, 2)


@unittest.skipIf(os.name == "nt", "process groups and signals are POSIX")
class GroupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.lock, self.gc = os.path.join(self.dir, "g.lock"), os.path.join(self.dir, "gc")
        self.env = {k: v for k, v in os.environ.items() if k != "GATE_LOCK_NOW"}
        self.addCleanup(self.reap)

    def reap(self):
        if os.path.exists(self.gc):
            try:
                os.kill(int(Path(self.gc).read_text()), 9)
            except (ProcessLookupError, ValueError):
                pass

    def wrapper(self, script, *extra):
        return subprocess.Popen([PY, str(SCRIPT), "run", "--lock", self.lock, *extra, "--", "sh", "-c", script],
                                env=self.env, stderr=subprocess.PIPE, text=True)

    def started(self):
        deadline = time.time() + 20
        while time.time() < deadline and not (os.path.exists(self.gc) and Path(self.gc).read_text().strip()):
            time.sleep(0.05)
        return int(Path(self.gc).read_text())

    def gone(self, pid, seconds=10):
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
            except FileNotFoundError:
                return True
            if state == "Z":
                return True
            time.sleep(0.05)
        return False

    def again(self, *extra):
        return subprocess.run([PY, str(SCRIPT), "run", "--lock", self.lock, *extra, "--", PY, "-c", "pass"],
                              env=self.env, capture_output=True, text=True)

    def test_leftover_background_process_is_stopped_when_the_command_ends(self):
        done = self.wrapper(f"sleep 30 & echo $! > {self.gc}", "--grace-seconds", "5")
        _, err = done.communicate(timeout=30)
        self.assertEqual(done.returncode, 0)
        self.assertIn("stopped 1 leftover gate process", err)
        self.assertTrue(self.gone(int(Path(self.gc).read_text())))
        self.assertEqual(self.again().returncode, 0)

    def test_leftover_that_ignores_sigterm_is_killed_after_the_grace(self):
        script = f"(trap '' TERM; exec sleep 30) & echo $! > {self.gc}"
        started = time.time()
        done = self.wrapper(script, "--grace-seconds", "1")
        _, err = done.communicate(timeout=30)
        self.assertEqual(done.returncode, 0)
        self.assertIn("stopped 1 leftover gate process", err)
        self.assertGreaterEqual(time.time() - started, 1)
        self.assertTrue(self.gone(int(Path(self.gc).read_text())))
        self.assertEqual(self.again().returncode, 0)

    def test_leftover_is_stopped_even_when_ps_is_unusable(self):
        fake = Path(self.dir) / "bin"
        fake.mkdir()
        (fake / "ps").write_text("#!/bin/sh\nexit 1\n")
        (fake / "ps").chmod(0o755)
        self.env["PATH"] = f"{fake}{os.pathsep}{self.env['PATH']}"
        done = self.wrapper(f"sleep 30 & echo $! > {self.gc}", "--grace-seconds", "5")
        _, err = done.communicate(timeout=30)
        self.assertEqual(done.returncode, 0)
        self.assertIn("stopped 1 leftover gate process", err)
        self.assertTrue(self.gone(int(Path(self.gc).read_text())))

    def test_removing_the_lock_file_during_a_run_does_not_let_a_second_gate_in(self):
        wrapper = self.wrapper(f"sleep 30 & echo $! > {self.gc}; wait")
        self.started()
        os.unlink(self.lock)
        busy = self.again()
        self.assertEqual(busy.returncode, 5, busy.stderr)
        self.assertIn(f"lock file was replaced while pid {wrapper.pid} runs", busy.stderr)
        wrapper.send_signal(signal.SIGTERM)
        wrapper.wait(timeout=20)
        wrapper.stderr.close()
        self.assertEqual(self.again().returncode, 0)

    def test_clean_command_prints_nothing(self):
        done = self.wrapper("true")
        self.assertEqual((done.communicate(timeout=30)[1], done.returncode), ("", 0))

    def test_sigterm_stops_the_whole_group_and_frees_the_lock(self):
        wrapper = self.wrapper(f"sleep 30 & echo $! > {self.gc}; wait")
        grandchild = self.started()
        wrapper.send_signal(signal.SIGTERM)
        self.assertEqual(wrapper.wait(timeout=20), 128 + signal.SIGTERM)
        wrapper.stderr.close()
        self.assertTrue(self.gone(grandchild), "grandchild still running")
        self.assertFalse(os.path.exists(self.lock + ".json"))
        self.assertEqual(self.again().returncode, 0)

    def test_sigterm_ignored_by_the_gate_escalates_to_sigkill(self):
        wrapper = self.wrapper(f"trap '' TERM; sleep 30 & echo $! > {self.gc}; wait", "--grace-seconds", "1")
        grandchild = self.started()
        wrapper.send_signal(signal.SIGTERM)
        self.assertEqual(wrapper.wait(timeout=20), 128 + signal.SIGKILL)
        wrapper.stderr.close()
        self.assertTrue(self.gone(grandchild))
        self.assertEqual(self.again().returncode, 0)

    def test_sigkill_of_the_wrapper_keeps_the_lock_while_a_descendant_lives(self):
        wrapper = self.wrapper(f"sleep 30 & echo $! > {self.gc}; wait")
        grandchild = self.started()
        wrapper.kill()
        wrapper.wait(timeout=20)
        wrapper.stderr.close()
        busy = self.again()
        self.assertEqual(busy.returncode, 5, busy.stderr)
        self.assertIn(f"held by pid {wrapper.pid}", busy.stderr)
        self.assertIn("is gone, its leftover processes hold the lock", busy.stderr)
        self.assertNotIn("cleared", busy.stderr)
        os.kill(grandchild, signal.SIGKILL)
        self.assertTrue(self.gone(grandchild))
        deadline, freed = time.time() + 10, None
        while time.time() < deadline:  # the sh that waited for it must end too
            freed = self.again()
            if freed.returncode == 0:
                break
            time.sleep(0.1)
        self.assertEqual(freed.returncode, 0, freed.stderr)
        self.assertIn(f"cleared stale gate lock: pid {wrapper.pid} (dead)", freed.stderr)

    def test_signal_killed_command_returns_128_plus_signal(self):
        done = subprocess.run([PY, str(SCRIPT), "run", "--lock", self.lock, "--", "sh", "-c", "kill -9 $$"],
                              env=self.env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 137)
        self.assertEqual(self.again().returncode, 0)


class ContentionTests(unittest.TestCase):
    def test_second_run_waits_for_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock, log = os.path.join(tmp, "g.lock"), os.path.join(tmp, "log")
            step = lambda name, sleep: f"import time;open({log!r},'a').write('{name}-start\\n');time.sleep({sleep});open({log!r},'a').write('{name}-end\\n')"
            env = {k: v for k, v in os.environ.items() if k != "GATE_LOCK_NOW"}
            first = subprocess.Popen([PY, str(SCRIPT), "run", "--lock", lock, "--", PY, "-c", step("A", 2)], env=env)
            try:
                deadline = time.time() + 20
                while not os.path.exists(lock + ".json") and time.time() < deadline:
                    time.sleep(0.05)
                busy = subprocess.run([PY, str(SCRIPT), "run", "--lock", lock, "--", PY, "-c", "pass"], env=env,
                                      capture_output=True, text=True)
                self.assertEqual(busy.returncode, 5)
                self.assertIn(f"held by pid {first.pid}", busy.stderr)
                second = subprocess.run([PY, str(SCRIPT), "run", "--lock", lock, "--wait-minutes", "1", "--", PY, "-c",
                                         step("B", 0)], env=env, capture_output=True, text=True)
                self.assertEqual(second.returncode, 0, second.stderr)
            finally:
                first.wait(timeout=30)
            self.assertEqual(Path(log).read_text().split(), ["A-start", "A-end", "B-start", "B-end"])
            self.assertFalse(os.path.exists(lock + ".json"))


if __name__ == "__main__":
    unittest.main()
