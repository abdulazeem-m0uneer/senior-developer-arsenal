"""Process-group kill helpers never signal beyond the child's own group.

killpg(1, sig) is kill(-1, sig): every process the user may signal. A mutation run once reached such a
call and took down a whole desktop session, so the helpers refuse pgid <= 1, non-integers, our own group
and our parent's. The refusal tests patch os.killpg and send no signal; the namespace test sends a real
kill(-1) only inside a fresh PID and user namespace and is skipped where those are unavailable.
"""
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "multi-session-delivery" / "scripts"))
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "quality-gate" / "scripts"))
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "payments-integrity" / "scripts"))

import confirm_status  # noqa: E402
import gate_lock  # noqa: E402
import timer  # noqa: E402

HELPERS = (("timer.kill_group", timer, timer.kill_group), ("gate_lock.killpg", gate_lock, gate_lock.killpg),
           ("confirm_status.kill_group", confirm_status, confirm_status.kill_group))


@unittest.skipIf(os.name == "nt", "POSIX process groups")
class RefusalTests(unittest.TestCase):
    def forbidden(self):
        values = [1, 0, -1, -4242, True, False, "4242", 4242.0, None, os.getpgrp()]
        try:
            values.append(os.getpgid(os.getppid()))
        except OSError:
            pass
        return values

    def test_each_helper_refuses_groups_beyond_the_child(self):
        for label, module, helper in HELPERS:
            for pgid in self.forbidden():
                with self.subTest(helper=label, pgid=pgid), \
                        unittest.mock.patch.object(module.os, "killpg") as killpg:
                    with self.assertRaisesRegex(ValueError, "refusing to signal process group"):
                        helper(pgid, signal.SIGKILL)
                    killpg.assert_not_called()

    def test_each_helper_signals_a_child_group(self):
        for label, module, helper in HELPERS:
            with self.subTest(helper=label), unittest.mock.patch.object(module.os, "killpg") as killpg:
                helper(424242, signal.SIGTERM)
                killpg.assert_called_once_with(424242, signal.SIGTERM)

    def test_own_and_parent_groups_are_refused_even_above_1(self):
        # In a PID namespace our real groups read as 0, which pgid <= 1 already refuses; fixed values do not.
        for label, module, helper in HELPERS:
            with self.subTest(helper=label), unittest.mock.patch.object(module.os, "killpg") as killpg, \
                    unittest.mock.patch.object(module.os, "getpgrp", return_value=5000), \
                    unittest.mock.patch.object(module.os, "getpgid", return_value=6000):
                for pgid in (5000, 6000):
                    with self.assertRaisesRegex(ValueError, "refusing to signal process group"):
                        helper(pgid, signal.SIGKILL)
                killpg.assert_not_called()
                helper(7000, signal.SIGKILL)
                killpg.assert_called_once_with(7000, signal.SIGKILL)

    def test_parent_lookup_failure_still_protects_our_own_group(self):
        for label, module, helper in HELPERS:
            with self.subTest(helper=label), unittest.mock.patch.object(module.os, "killpg") as killpg, \
                    unittest.mock.patch.object(module.os, "getpgrp", return_value=5000), \
                    unittest.mock.patch.object(module.os, "getpgid", side_effect=ProcessLookupError):
                with self.assertRaisesRegex(ValueError, "refusing to signal process group"):
                    helper(5000, signal.SIGKILL)
                killpg.assert_not_called()


def namespace_available():
    if os.name == "nt" or not shutil.which("unshare"):
        return False
    try:
        done = subprocess.run(["unshare", "--user", "--map-root-user", "--pid", "--fork", "--mount-proc", "true"],
                              capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


@unittest.skipUnless(namespace_available(), "needs unprivileged PID and user namespaces")
class NamespaceTests(unittest.TestCase):
    """The unguarded call kills everything it can reach; inside the namespace that is only the namespace."""

    def run_inside(self, body):
        script = textwrap.dedent("""
            import os, signal, subprocess, sys, time
            sys.path.insert(0, %r)
            inner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            time.sleep(0.2)
        """ % str(ROOT / ".agents" / "skills" / "multi-session-delivery" / "scripts")) + textwrap.dedent(body)
        return subprocess.run(["unshare", "--user", "--map-root-user", "--pid", "--fork", "--mount-proc",
                               sys.executable, "-c", script], capture_output=True, text=True, timeout=60)

    def test_unguarded_kill_minus_one_dies_inside_the_namespace_only(self):
        outside = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(outside.wait)
        self.addCleanup(outside.kill)
        done = self.run_inside("""
            os.killpg(1, signal.SIGKILL)  # the mutant: the guard removed, pgid 1 reached
            time.sleep(0.2)
            print("inner", inner.poll())
        """)
        self.assertIn("inner -9", done.stdout, done.stderr)
        self.assertIsNone(outside.poll(), "a process outside the namespace was signalled")

    def test_guarded_helper_refuses_inside_the_namespace_too(self):
        done = self.run_inside("""
            import timer
            try:
                timer.kill_group(1, signal.SIGKILL)
            except ValueError as exc:
                print("refused", exc)
            print("inner", inner.poll())
            inner.kill()
        """)
        self.assertIn("refused refusing to signal process group 1", done.stdout, done.stderr)
        self.assertIn("inner None", done.stdout)


if __name__ == "__main__":
    unittest.main()
