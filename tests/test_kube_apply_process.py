"""kube_apply_check.py: every kubectl call ends by its timeout, even when a child of kubectl holds its pipes."""
import os
import sys
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_kube_apply_check import KubeTestCase, kube_apply_check  # noqa: E402


def process_gone(pid):
    """True once `pid` has exited (a zombie counts as gone); needs /proc."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return True
    return state == "Z"


@unittest.skipIf(os.name == "nt", "POSIX process groups and pipes")
class ProcessBoundTests(KubeTestCase):
    """A child of kubectl (an exec credential plugin, say) inherits its pipes and may outlive it."""

    def fake(self, body):
        script = self.kubectl.dir / "kubectl"
        script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        return self.kubectl.dir / "child.pid"

    def assert_child_stopped(self, pid_file):
        if not Path("/proc/self/stat").exists():
            self.skipTest("needs /proc to see the child")
        pid = int(pid_file.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 3
        while not process_gone(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(process_gone(pid), f"child {pid} of kubectl still runs")

    def test_a_child_holding_the_pipes_cannot_stretch_a_timed_out_call(self):
        pid_file = self.fake('sleep 10 &\necho $! > "$(dirname "$0")/child.pid"\nsleep 10')
        started = time.monotonic()
        code, _, err = self.check("--kubectl-timeout", "1", "--overall-timeout", "1")
        self.assertEqual(code, 4, err)
        self.assertLess(time.monotonic() - started, 4)
        self.assert_child_stopped(pid_file)

    def test_a_child_left_holding_the_pipes_after_kubectl_exits_does_not_stall_the_call(self):
        pid_file = self.fake('sleep 10 &\necho $! > "$(dirname "$0")/child.pid"\nprintf out')
        started = time.monotonic()
        self.assertEqual(kube_apply_check.kubectl(["get", "x"], 20), "out")
        self.assertLess(time.monotonic() - started, kube_apply_check.EXIT_GRACE + 2)
        self.assert_child_stopped(pid_file)

    def test_kubectl_that_exits_without_reading_a_large_stdin_returns_its_output(self):
        self.fake("printf out")
        self.assertEqual(kube_apply_check.kubectl(["get", "x"], 20, b"x" * (4 * 1024 * 1024)), "out")

    def test_kubectl_that_closes_its_output_but_keeps_running_times_out(self):
        self.fake("exec >&- 2>&-\nsleep 10")
        started = time.monotonic()
        with self.assertRaises(kube_apply_check.TimedOut):
            kube_apply_check.kubectl(["get", "x"], 1)
        self.assertLess(time.monotonic() - started, 4)

    def test_a_missing_group_kill_helper_refuses_to_run_kubectl(self):
        self.fake("printf out")
        with unittest.mock.patch.object(kube_apply_check, "killpg", None):
            with self.assertRaisesRegex(kube_apply_check.Failure, "gate_lock.py"):
                kube_apply_check.kubectl(["get", "x"], 5)



if __name__ == "__main__":
    unittest.main()
