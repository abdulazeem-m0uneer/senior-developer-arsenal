"""live-script: a script that a process is running right now is never edited in place."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))

import guard_lessons  # noqa: E402
import guard_live_script  # noqa: E402

SCRIPT = HOOKS / "guard.py"
ENTRY = {"rule": "live-script", "lesson": "G010", "min_version": "1.33.0"}
LOOP = "#!/bin/bash\nwhile :; do sleep 0.1; done\n"


class LiveScriptCase(unittest.TestCase):
    """A project whose registry names live-script, a 1.33.0 hook, and a fake /proc folder."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name).resolve()
        self.project = self.dir / "project"
        (self.project / ".agents").mkdir(parents=True)
        self.proc = self.dir / "proc"
        self.proc.mkdir()
        self.target = self.project / "run.sh"
        self.target.write_text(LOOP, encoding="utf-8")
        env = {"LESSONS_GUARDS_GLOBAL_FILE": str(self.dir / "home" / "lesson-guards.json"),
               "LESSONS_GUARD_HITS_FILE": str(self.dir / "home" / "hits.jsonl")}
        for patch in (mock.patch.dict(os.environ, env), mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 33, 0)),
                      mock.patch.object(guard_live_script, "PROC", str(self.proc))):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.registry(ENTRY)

    def registry(self, *guards):
        (self.project / ".agents" / "lesson-guards.json").write_text(json.dumps({"guards": list(guards)}),
                                                                     encoding="utf-8")

    def process(self, pid, *argv, fds=None):
        """A fake /proc/<pid> whose command line is argv and whose open descriptors are fds ({number: path})."""
        folder = self.proc / str(pid)
        (folder / "fd").mkdir(parents=True)
        (folder / "cmdline").write_bytes(b"".join(str(word).encode() + b"\0" for word in argv))
        for number, path in (fds or {}).items():
            (folder / "fd" / str(number)).symlink_to(path)
        return folder

    def shell(self, pid, argv0="bash", fd=255, script=None):
        """A fake shell process reading script (the target by default) on descriptor fd."""
        script = script or self.target
        return self.process(pid, argv0, script, fds={0: "/dev/null", fd: script})

    def judge(self, tool_name="Edit", tool_input=None):
        tool_input = tool_input or {"file_path": str(self.target), "old_string": "sleep", "new_string": "true"}
        return guard_lessons.judge_outbound(tool_name, tool_input, str(self.project))

    def assertRefused(self, tool_name="Edit", tool_input=None, msg=None):
        hit = self.judge(tool_name, tool_input)
        self.assertIsNotNone(hit, msg)
        self.assertEqual((hit.lesson, hit.rule), ("G010", "live-script"), msg)
        return hit

    def assertPasses(self, tool_name="Edit", tool_input=None, msg=None):
        self.assertIsNone(self.judge(tool_name, tool_input), msg)


class RunningScriptTests(LiveScriptCase):
    def test_an_edit_of_a_script_bash_is_running_is_refused_with_the_fix(self):
        self.shell(4321)
        reason = self.assertRefused().reason
        self.assertIn(str(self.target), reason)
        self.assertIn("4321", reason)
        self.assertIn(f"{self.target}.next", reason)
        self.assertIn("mv", reason)
        self.assertIn("a shell reads its script", reason)

    def test_write_and_multi_edit_are_refused_too(self):
        self.shell(10)
        self.assertRefused("Write", {"file_path": str(self.target), "content": "echo hi\n"})
        self.assertRefused("MultiEdit", {"file_path": str(self.target),
                                         "edits": [{"old_string": "sleep", "new_string": "true"}]})

    def test_every_shell_and_a_shell_path_count(self):
        for argv0 in ("bash", "sh", "zsh", "dash", "ksh", "mksh", "/usr/bin/bash", "/bin/sh"):
            with self.subTest(argv0=argv0):
                folder = self.shell(10, argv0=argv0, fd=10)
                try:
                    self.assertRefused(msg=argv0)
                finally:
                    shutil.rmtree(folder)

    def test_compiled_interpreters_and_other_programs_pass(self):
        # python, node, perl and ruby compile the whole file at start: changing it in place breaks no run
        for pid, argv0 in enumerate(("python3", "python3.12", "node", "nodejs", "perl", "ruby", "vim", "less",
                                     "tail", "bashful", "-bash"), 10):
            self.process(pid, argv0, self.target, fds={255: self.target})
        self.assertPasses()

    def test_a_shell_matches_on_the_open_script_not_its_command_line(self):
        self.process(10, "bash", "run.sh", "--flag")  # names the script but holds it on no descriptor
        self.process(11, "bash", "-c", "x", fds={3: self.target})  # a redirection below 10
        self.process(12, "bash", fds={0: self.target})  # bash < run.sh: stdin
        self.process(14, "bash", self.target, fds={3: self.target})  # its own redirection, not the script it reads
        self.assertPasses()
        self.process(13, "bash", "-x", "elsewhere/run.sh", fds={10: self.target})
        self.assertRefused()

    def test_a_file_a_shell_holds_but_does_not_run_passes(self):
        # exec {lk}>lock.txt lands on 10 and up, and so does the stdout bash saves during `{ ...; } > summary.txt`
        self.process(10, "bash", self.dir / "locker.sh", fds={10: self.target})
        self.process(11, "bash", "-c", "x", "run.sh", fds={10: self.target})  # -c: no script file
        self.process(12, "bash", "-s", "run.sh", fds={10: self.target})  # -s: the script is stdin
        self.assertPasses()

    def test_the_script_operand_follows_the_shells_options(self):
        for pid, argv in enumerate((("-o", "pipefail", self.target), ("--rcfile", "x", self.target),
                                    ("-O", "extglob", "--", self.target), ("-ex", self.target),
                                    ("-eo", "pipefail", self.target), ("-euo", "pipefail", self.target),
                                    ("-eO", "extglob", self.target), ("+eo", "pipefail", self.target)), 10):
            with self.subTest(argv=argv):
                folder = self.process(pid, "bash", *argv, fds={255: self.target})
                try:
                    self.assertRefused(msg=argv)
                finally:
                    shutil.rmtree(folder)
        self.process(20, "bash", "--rcfile", self.target, fds={255: self.target})  # an option's value
        self.process(21, "bash", "-euo", self.target, fds={255: self.target})  # a clustered option's value
        self.assertPasses()

    def test_a_shell_is_known_by_its_executable_or_a_versioned_name(self):
        for pid, (argv0, exe) in enumerate((("worker", "/usr/bin/bash"), ("bash-5.2", None), ("bash5", None),
                                            ("-bash", "/bin/zsh")), 10):
            with self.subTest(argv0=argv0):
                folder = self.process(pid, argv0, self.target, fds={255: self.target})
                if exe:
                    (folder / "exe").symlink_to(exe)
                try:
                    self.assertRefused(msg=argv0)
                finally:
                    shutil.rmtree(folder)
        folder = self.process(10, "worker", self.target, fds={255: self.target})
        (folder / "exe").symlink_to("/usr/bin/python3")
        self.assertPasses()

    def test_a_replaced_script_passes(self):
        old = self.dir / "old.sh"  # the inode the shell still holds after `mv run.sh.next run.sh`
        old.write_text(LOOP, encoding="utf-8")
        self.shell(10, script=old)
        self.assertPasses()

    def test_symlinks_and_hard_links_resolve(self):
        link = self.dir / "link.sh"
        link.symlink_to(self.target)
        hard = self.dir / "hard.sh"
        os.link(self.target, hard)
        self.shell(10, script=link)
        self.assertRefused()
        self.assertRefused("Edit", {"file_path": str(link), "old_string": "sleep", "new_string": "true"})
        self.assertRefused("Edit", {"file_path": str(hard), "old_string": "sleep", "new_string": "true"})

    def test_the_same_inode_on_another_device_passes(self):
        self.shell(10)
        real_stat, fd_folder = os.stat, str(self.proc / "10" / "fd")

        def stat(path, *args, **kwargs):
            found = real_stat(path, *args, **kwargs)
            if str(path).startswith(fd_folder):
                return os.stat_result((*found[:2], found.st_dev + 1, *found[3:]))
            return found

        with mock.patch.object(guard_live_script.os, "stat", stat):
            self.assertPasses()

    def test_a_descriptor_closed_mid_scan_skips_only_that_descriptor(self):
        self.process(10, "bash", self.target, fds={10: self.target, 255: self.target})
        real_stat, fd_folder, failed = os.stat, str(self.proc / "10" / "fd"), []

        def stat(path, *args, **kwargs):  # whichever descriptor is listed first closes before its stat
            if str(path).startswith(fd_folder) and not failed:
                failed.append(path)
                raise FileNotFoundError(path)
            return real_stat(path, *args, **kwargs)

        with mock.patch.object(guard_live_script.os, "stat", stat):
            self.assertRefused()
        self.assertEqual(len(failed), 1)

    def test_a_relative_file_path_is_read_from_the_hook_folder(self):
        self.shell(10)
        self.assertRefused("Edit", {"file_path": "run.sh", "old_string": "sleep", "new_string": "true"})


class ScanLimitTests(LiveScriptCase):
    def test_only_this_users_processes_are_read(self):
        self.shell(10)
        with mock.patch.object(guard_live_script.os, "getuid", return_value=os.getuid() + 1):
            self.assertPasses()

    def test_the_hook_process_itself_is_not_counted(self):
        self.shell(os.getpid())
        self.assertPasses()

    def test_the_highest_pids_are_read_up_to_the_limit(self):
        self.shell(5)
        self.process(70, "vim")
        self.process(800, "vim")
        with mock.patch.object(guard_live_script, "MAX_PIDS", 2):
            self.assertPasses()
            self.shell(900)
            self.assertRefused()

    def test_other_users_processes_do_not_use_up_the_limit(self):
        self.shell(5)
        for pid in (70, 800, 900):
            self.process(pid, "vim")
        real_stat, foreign = os.stat, {str(self.proc / pid) for pid in ("70", "800", "900")}

        def stat(path, *args, **kwargs):
            found = real_stat(path, *args, **kwargs)
            if str(path) in foreign:
                return os.stat_result((*found[:4], found.st_uid + 1, *found[5:]))
            return found

        with mock.patch.object(guard_live_script, "MAX_PIDS", 1), mock.patch.object(guard_live_script.os, "stat", stat):
            self.assertRefused()

    def test_the_limits_are_2000_pids_and_150_ms(self):
        self.assertEqual(guard_live_script.MAX_PIDS, 2000)
        self.assertEqual(guard_live_script.BUDGET_SECONDS, 0.15)

    def test_a_scan_past_its_time_budget_passes(self):
        self.shell(5)
        self.process(9, "vim")
        calls = []

        def clock():  # the scan starts at 0 s; every later reading is 1 s on, past the budget
            calls.append(None)
            return 0.0 if len(calls) == 1 else 1.0

        with mock.patch.object(guard_live_script, "monotonic", side_effect=clock):
            self.assertPasses()

    def test_a_scan_that_blocks_passes_within_its_budget(self):
        self.shell(5)
        release = threading.Event()
        self.addCleanup(release.set)
        with mock.patch.object(guard_live_script, "scan_pids", side_effect=lambda *_: release.wait(5) and 5):
            started = time.monotonic()
            self.assertPasses()
            self.assertLess(time.monotonic() - started, 1.0)

    def test_a_blocked_scan_never_holds_the_hook_process_open(self):
        code = ("import sys, threading; sys.path.insert(0, sys.argv[1]); import guard_live_script as g; "
                "g.scan_pids = lambda *_: threading.Event().wait(); print(g.running_pid((1, 1), 'x.sh'))")
        result = subprocess.run([sys.executable, "-c", code, str(HOOKS)], capture_output=True, text=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout), (0, "None\n"), result.stderr)

    def test_a_shell_without_a_script_does_not_end_the_scan(self):
        self.process(31, "bash")  # an interactive shell, read first (highest pids)
        self.process(30, "bash", "-c", "sleep 9")
        self.shell(5)
        self.assertRefused()

    def test_a_vanished_or_empty_process_is_skipped(self):
        (self.proc / "99").mkdir()  # exited between the listing and the read: no cmdline
        self.process(98, "")
        (self.proc / "97").mkdir()
        (self.proc / "97" / "cmdline").write_bytes(b"")  # a kernel thread
        (self.proc / "95").mkdir()
        (self.proc / "95" / "cmdline").write_bytes(b"bash\0")  # exited before its fd folder was listed
        self.process(94, "bash", fds={10: self.dir / "gone"})  # a descriptor closed before its stat
        (self.proc / "self").mkdir()
        self.shell(10)
        self.assertRefused()


class PassTests(LiveScriptCase):
    def test_no_proc_folder_passes_without_a_scan(self):
        self.shell(10)
        with mock.patch.object(guard_live_script, "PROC", str(self.dir / "missing")), \
                mock.patch.object(guard_live_script, "running_pid") as scan:
            self.assertPasses()
        scan.assert_not_called()

    def test_a_new_file_other_tools_and_bad_input_pass(self):
        self.shell(10)
        self.assertPasses("Write", {"file_path": str(self.project / "new.sh"), "content": "x"})
        self.assertPasses("Read", {"file_path": str(self.target)})
        self.assertPasses("NotebookEdit", {"notebook_path": str(self.target)})
        self.assertPasses("Edit", {"file_path": 7})
        self.assertPasses("Edit", {"file_path": ""})
        self.assertIsNone(guard_live_script.file_problem("Edit", "not a dict", str(self.project)))

    def test_a_folder_or_fifo_is_never_scanned(self):
        fifo = self.project / "pipe.sh"
        os.mkfifo(fifo)
        self.shell(10, script=fifo)
        self.shell(11, script=self.project)
        with mock.patch.object(guard_live_script, "running_pid", return_value=10) as scan:
            self.assertPasses("Write", {"file_path": str(fifo), "content": "x"})
            self.assertPasses("Edit", {"file_path": str(self.project)})
        scan.assert_not_called()

    def test_an_error_in_the_rule_passes(self):
        self.shell(10)
        with mock.patch.object(guard_live_script, "holds", side_effect=RuntimeError("boom")), \
                mock.patch.object(threading, "excepthook") as unhandled:
            self.assertPasses()
        unhandled.assert_not_called()  # caught in the scan thread: no traceback reaches the hook's stderr
        with mock.patch.object(guard_live_script.os, "scandir", side_effect=PermissionError("no")):
            self.assertPasses()

    def test_a_bash_command_is_not_judged(self):
        self.shell(10)
        self.assertIsNone(guard_lessons.judge(f"sed -i s/a/b/ {self.target}", str(self.project)))


class RegistryTests(LiveScriptCase):
    def test_off_until_a_registry_entry_names_it(self):
        self.shell(10)
        self.registry()
        self.assertPasses()

    def test_enabled_false_and_a_reason_of_its_own(self):
        self.shell(10)
        self.registry({**ENTRY, "enabled": False})
        self.assertPasses()
        self.registry({**ENTRY, "reason": "Stage it first."})
        self.assertEqual(self.judge().reason, "Stage it first.")

    def test_min_version_1_33_0_skips_on_older_hooks(self):
        self.shell(10)
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 32, 0)):
            self.assertPasses()
            self.assertEqual(guard_lessons.registry_problems(str(self.project)), [])
        self.assertRefused()

    def test_bad_registry_values_are_skipped(self):
        self.shell(10)
        for bad in ({"programs": ["send.sh"]}, {"shell": "bash"}, {"lesson": "nope"}):
            self.registry({**ENTRY, **bad})
            self.assertPasses(msg=bad)
            self.assertTrue(guard_lessons.registry_problems(str(self.project)), bad)


class RealProcessTests(LiveScriptCase):
    """The real /proc: a bash loop started here, then the hook through guard.py pre."""

    def setUp(self):
        super().setUp()
        if not os.path.isdir("/proc/self"):
            self.skipTest("no /proc on this system")
        real_proc = mock.patch.object(guard_live_script, "PROC", "/proc")
        real_proc.start()
        self.addCleanup(real_proc.stop)
        self.child = self.start(self.target, self.dir)

    def start(self, script, cwd):
        """A bash child running script from cwd, once it holds the script open."""
        child = subprocess.Popen(["bash", str(script)], cwd=cwd)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        found, deadline = os.stat(cwd / script), time.monotonic() + 5
        # bash opens the script on a low descriptor, then moves it to 255 and closes the first one
        while not guard_live_script.holds(child.pid, (found.st_dev, found.st_ino)):
            self.assertLess(time.monotonic(), deadline, "the child never opened the script")
            time.sleep(0.01)
        return child

    def pre(self, tool_name, tool_input):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input,
                   "cwd": str(self.project), "permission_mode": "default"}
        base = {k: v for k, v in os.environ.items()
                if k not in ("ARSENAL_GUARD", "ARSENAL_LESSON_GUARDS", "ARSENAL_GUARD_DESTRUCTIVE",
                             "ARSENAL_RUN_LIMITS", "CLAUDE_PROJECT_DIR", "ARSENAL_PROFILE", "ARSENAL_GUARD_SCOPE")}
        result = subprocess.run([sys.executable, str(SCRIPT), "pre"], cwd=self.project, input=json.dumps(payload),
                                capture_output=True, text=True, env=base)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None

    def test_a_running_script_is_refused_until_its_process_ends(self):
        self.assertIn(str(self.child.pid), self.assertRefused().reason)
        self.child.kill()
        self.child.wait()
        self.assertPasses()

    def test_a_script_replaced_by_mv_can_be_edited_at_once(self):
        shutil.copy(self.target, f"{self.target}.next")
        os.replace(f"{self.target}.next", self.target)  # the staged copy the refusal asks for
        self.assertPasses()

    def test_a_script_that_ran_cd_is_matched_on_the_file_it_runs(self):
        first, second = self.dir / "a", self.dir / "b"
        first.mkdir()
        second.mkdir()
        (first / "run.sh").write_text(f"cd {second}\nwhile :; do sleep 0.1; done\n", encoding="utf-8")
        (second / "run.sh").write_text(LOOP, encoding="utf-8")
        child = self.start(Path("run.sh"), first)
        deadline = time.monotonic() + 5
        while os.readlink(f"/proc/{child.pid}/cwd") != str(second):
            self.assertLess(time.monotonic(), deadline, "the child never ran cd")
            time.sleep(0.01)
        self.assertPasses("Edit", {"file_path": str(second / "run.sh"), "old_string": "s", "new_string": "t"})
        hit = self.assertRefused("Edit", {"file_path": str(first / "run.sh"), "old_string": "s", "new_string": "t"})
        self.assertIn(str(child.pid), hit.reason)

    def test_a_lock_file_the_running_script_holds_can_be_edited(self):
        lock, script = self.dir / "lock.txt", self.dir / "locker.sh"
        lock.write_text("", encoding="utf-8")
        script.write_text(f"exec {{lk}}>>{lock}\nwhile :; do sleep 0.1; done\n", encoding="utf-8")
        child = self.start(script, self.dir)
        found, deadline = os.stat(lock), time.monotonic() + 5
        while not guard_live_script.holds(child.pid, (found.st_dev, found.st_ino)):
            self.assertLess(time.monotonic(), deadline, "the child never opened the lock file")
            time.sleep(0.01)
        self.assertPasses("Edit", {"file_path": str(lock), "old_string": "", "new_string": "x"})
        self.assertIn(str(child.pid), self.assertRefused("Edit", {"file_path": str(script), "old_string": "s",
                                                                  "new_string": "t"}).reason)

    def test_the_hook_denies_an_edit_of_a_running_script(self):
        self.registry({"rule": "live-script", "lesson": "G010"})  # the installed hook may be older than 1.33.0
        edit = {"file_path": str(self.target), "old_string": "sleep", "new_string": "true"}
        out = self.pre("Edit", edit)
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("G010 (live-script)", out["permissionDecisionReason"])
        self.child.kill()
        self.child.wait()
        self.assertIsNone(self.pre("Edit", edit))


if __name__ == "__main__":
    unittest.main()
