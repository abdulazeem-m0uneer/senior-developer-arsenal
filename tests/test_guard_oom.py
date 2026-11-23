"""oom-first: a command that exited 134 or 137 may not run again before the kernel log was read."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "hooks")]
from test_guard import GuardCase  # noqa: E402
import guard_lessons  # noqa: E402
import guard_oom  # noqa: E402

LESSONS = ROOT / ".agents" / "skills" / "lessons-learned" / "scripts" / "lessons.py"
KLOG = "journalctl -k --since '-15 min' | grep -i -E 'oom|killed process'"
BIG = "node build/big.js"


class OomCase(GuardCase):
    def setUp(self):
        super().setUp()
        self.registry = Path(self.outside.name) / "no-global-lesson-guards.json"
        self.registry.write_text(json.dumps({"guards": [{"rule": "oom-first", "lesson": "G040"}]}))

    def pre(self, command, **kwargs):
        out = self.run_hook("pre", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                    "tool_input": {"command": command}}, **kwargs)
        return json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"] if out else ""

    def killed(self, command, code=137, **extra):
        self.bash(command, failed=True, error=f"Exit code {code}\nKilled", is_interrupt=False, **extra)

    def cause(self, note="node: timeout"):
        self.bash(f'python3 {LESSONS} cause "{note}"')


class ArmedTest(OomCase):
    def test_the_same_command_after_137_or_134_is_refused_with_the_steps(self):
        for code in (137, 134):
            self.state.unlink(missing_ok=True)
            self.killed(BIG, code)
            reason = self.pre(BIG)
            self.assertIn("G040 (oom-first)", reason)
            self.assertIn(f"{BIG} exited 134/137", reason)
            self.assertIn("journalctl -k --since '-15 min'", reason)
            self.assertNotIn("timeout limit", reason)

    def test_the_same_command_with_other_whitespace_is_refused(self):
        self.killed(BIG)
        self.assertIn("oom-first", self.pre("node   build/big.js "))

    def test_a_command_sharing_a_check_key_is_refused(self):
        self.killed("cd web && npx eslint src")
        self.assertIn("oom-first", self.pre("npx eslint . --cache"))

    def test_a_different_command_passes(self):
        self.killed(BIG)
        self.assertIn("oom-first", self.pre(BIG))
        for command in ("node build/other.js", "ls -la", "git status", "pytest -q", f'echo "{BIG}"'):
            self.assertEqual(self.pre(command), "", command)

    def test_other_exit_codes_do_not_arm_it(self):
        for code in (1, 2, 13, 1370, 143):
            self.killed(BIG, code)
        self.assertEqual(self.pre(BIG), "")
        self.killed(BIG)
        self.assertIn("oom-first", self.pre(BIG))

    def test_an_interrupted_call_does_not_arm_it(self):
        self.bash(BIG, failed=True, error="Exit code 137", is_interrupt=True)
        self.assertEqual(self.pre(BIG), "")
        self.bash(BIG, failed=True, error="Exit code 137", is_interrupt=False)
        self.assertIn("oom-first", self.pre(BIG))

    def test_nothing_is_refused_without_the_registry_entry(self):
        self.registry.unlink()
        self.killed(BIG)
        self.assertEqual(self.pre(BIG), "")

    def test_the_same_command_behind_other_wrappers_is_refused(self):
        wrapped = ("systemd-run --user --scope -q -p MemoryMax={}G -- unshare --user --map-root-user -- "
                   "env PATH=/usr/bin:/bin python3 -m unittest tests.test_x")
        for failed, again in ((wrapped.format(2), wrapped.format(4)),
                              ("pnpm lint", "systemd-run --user --scope -q -p MemoryMax=4G -- pnpm lint"),
                              ("systemd-run --user --scope -q -- pnpm lint", "pnpm lint"),
                              ("systemd-run --user --scope -- npx eslint src", "npx eslint . --cache"),
                              ("systemd-run --user --scope -p MemoryMax=2G " + BIG, "sudo env A=1 " + BIG),
                              ("unshare --propagation private -m -- pnpm test", "pnpm test"),
                              ("systemd-run --user --scope --on-active 5 pnpm build", "pnpm build"),
                              ("unshare --setgroups deny --map-user 0 --map-group 0 -U pnpm test", "pnpm test"),
                              ("/usr/bin/timeout -k 5 60 " + BIG, BIG), ("/usr/bin/time -v " + BIG, BIG)):
            self.state.unlink(missing_ok=True)
            self.killed(failed)
            self.assertIn("oom-first", self.pre(again), again)
            self.assertEqual(self.pre("systemd-run --user --scope -q -- ls"), "")

    def test_a_help_or_version_call_of_the_check_passes(self):
        self.killed("pnpm lint")
        for command in ("pnpm lint --help", "pnpm lint --version"):
            self.assertEqual(self.pre(command), "", command)
        self.assertIn("oom-first", self.pre("pnpm lint --fix"))

    def test_a_multi_line_command_run_again_is_refused(self):
        command = "cd /srv/app\nnode --max-old-space-size=512 scripts/import.js"
        self.killed(command)
        for again in (command, "cd /srv/app && node --max-old-space-size=512 scripts/import.js"):
            self.assertIn("oom-first", self.pre(again), again)
        self.assertEqual(self.pre("cd /srv/app\nnode scripts/other.js"), "")

    def test_a_here_document_run_again_is_refused_and_another_body_passes(self):
        script = "python3 - <<'EOF'\nimport numpy as np\nx = np.zeros((10**6, 10**4))\nEOF"
        self.killed(script)
        self.assertIn("oom-first", self.pre(script))
        self.assertEqual(self.pre(script.replace("10**4", "10")), "")

    def test_the_same_command_with_a_trivial_step_or_through_a_shell_is_refused(self):
        self.killed(BIG)
        for again in (f"{BIG} && echo ok", f"echo start; {BIG}", f"bash -c '{BIG}'", f"sh -c \"{BIG}; true\""):
            self.assertIn("oom-first", self.pre(again), again)
        self.assertEqual(self.pre("echo ok"), "")

    def test_the_newest_matching_failure_is_named(self):
        self.killed("pnpm lint")
        self.killed("pnpm lint --fix")
        self.assertIn("pnpm lint --fix exited 134/137", self.pre("pnpm lint"))

    def errors(self):
        return [event for event in map(json.loads, self.state.read_text().splitlines()) if event["event"] == "error"]

    def test_a_recorded_failure_keeps_its_digest_and_timeout_and_never_the_body(self):
        self.killed("timeout 9 python3 - <<'EOF'\nsecret_body = 1\nEOF")
        self.killed("pnpm lint", 1)
        killed, other = self.errors()
        self.assertEqual((killed["timed"], len(killed["same"])), (True, 16))
        self.assertNotIn("secret_body", killed["same"])
        self.assertNotIn("same", other)

    def test_one_kernel_log_read_clears_every_armed_failure(self):
        self.killed(BIG)
        self.killed("pnpm lint", 134)
        self.killed(BIG)
        self.bash("journalctl -k -n 50")
        for command in (BIG, "pnpm lint"):
            self.assertEqual(self.pre(command), "", command)

    def test_an_unreadable_state_file_fails_open(self):
        self.state.mkdir()
        self.assertEqual(self.pre(BIG), "")
        self.state.rmdir()
        self.state.write_text('not json\n{"event": "error", "error": 137}\n[1]\n{"event": "error", "command": 5, '
                              '"error": "Exit code 137", "checks": "eslint"}\n')
        self.assertEqual(self.pre(BIG), "")


class KernelLogTest(OomCase):
    def test_reading_the_kernel_log_clears_it(self):
        for reader in ("journalctl -k --since '-15 min'", "sudo journalctl --dmesg -b", "journalctl -t kernel",
                       "journalctl --identifier=kernel -n 50", "journalctl --user -u app | grep -i OOM",
                       "journalctl -b -g oom", "dmesg -T", "timeout 5 dmesg",
                       "cat /sys/fs/cgroup/user.slice/memory.events",
                       "grep oom_kill /sys/fs/cgroup/app.scope/memory.events.local",
                       "systemctl --user status app.service", KLOG,
                       "journalctl -kb | tail -50", "journalctl -kn 50", "journalctl -xk --no-pager",
                       "journalctl -xtkernel", "journalctl -b -g 'Out of memory'",
                       "journalctl --since '-15 min' | grep -i 'killed process'",
                       "journalctl -b | grep -iE 'out of memory'", "journalctl -b | rg -i oom",
                       "journalctl _TRANSPORT=kernel --since -1h", "journalctl SYSLOG_IDENTIFIER=kernel",
                       "tail memory.events", "grep -m 1 oom_kill memory.events", "dmesg -c",
                       "journalctl -b > /tmp/j.log; grep -i oom /tmp/j.log"):
            self.state.unlink(missing_ok=True)
            self.killed(BIG)
            self.assertIn("oom-first", self.pre(BIG))
            self.bash(reader)
            self.assertEqual(self.pre(BIG), "", reader)

    def test_a_grep_of_the_kernel_log_that_matched_nothing_clears_it(self):
        self.killed(BIG)
        self.assertIn("oom-first", self.pre(BIG))
        self.bash(KLOG, failed=True, error="Exit code 1")
        self.assertEqual(self.pre(BIG), "")

    def test_a_grep_of_a_saved_kernel_log_that_matched_nothing_clears_it(self):
        for command in ("journalctl -k --since '-15 min' > /tmp/k.log 2>&1; grep -ciE 'oom|killed process' /tmp/k.log",
                        "journalctl -k | grep oom && echo found", "dmesg >> k.log\ngrep -i oom k.log"):
            self.state.unlink(missing_ok=True)
            self.killed(BIG)
            self.bash(command, failed=True, error="Exit code 1")
            self.assertEqual(self.pre(BIG), "", command)

    def test_a_failing_grep_that_did_not_read_a_saved_kernel_log_does_not_clear_it(self):
        self.killed(BIG)
        for command in ("journalctl -k > /tmp/k.log; grep -i oom /tmp/other.log",
                        "journalctl -k | grep oom && pnpm lint",
                        "pnpm lint && journalctl -k > k.log; grep oom k.log"):
            self.bash(command, failed=True, error="Exit code 1")
            self.assertIn("oom-first", self.pre(BIG), command)

    def test_failing_kernel_log_reads_do_not_clear_it(self):
        self.killed(BIG)
        self.bash("journalctl -k", failed=True, error="Exit code 1")
        for code in (2, 10, 100, 127):
            self.bash(KLOG, failed=True, error=f"Exit code {code}")
        self.bash("dmesg", failed=True, error="Exit code 1")
        self.bash("systemctl --user status gone.service", failed=True, error="Exit code 4\nUnit gone.service could "
                                                                              "not be found.")
        self.assertIn("oom-first", self.pre(BIG))

    def test_a_read_the_kernel_refused_does_not_clear_it(self):
        denied = "dmesg: read kernel buffer failed: Operation not permitted"
        self.killed(BIG)
        self.bash("dmesg | tail -50", tool_response={"stdout": "", "stderr": denied})
        self.bash("dmesg || true", tool_response={"stdout": denied})
        self.bash("dmesg | grep -i oom", failed=True, error=f"Exit code 1\n{denied}")
        self.bash("journalctl -k", tool_response={"stdout": "No journal files were opened due to insufficient "
                                                            "permissions."})
        self.assertIn("oom-first", self.pre(BIG))
        self.bash("dmesg | tail -50", tool_response={"stdout": "[1.0] Out of memory: Killed process 42 (node)"})
        self.assertEqual(self.pre(BIG), "")

    def test_a_status_of_a_unit_the_oom_killer_stopped_clears_it(self):
        self.killed(BIG)
        self.bash("systemctl --user status app.service", failed=True,
                  error="Exit code 3\n× app.service\n     Active: failed (Result: oom-kill)")
        self.assertEqual(self.pre(BIG), "")

    def test_a_grep_that_exits_1_counts_only_when_it_read_the_log(self):
        self.killed(BIG)
        for command in ("pnpm lint && journalctl -k | grep oom", "journalctl -k; grep oom notes.txt"):
            self.bash(command, failed=True, error="Exit code 1")
            self.assertIn("oom-first", self.pre(BIG), command)
        for command in ("cd /tmp; journalctl -k | grep oom", "pnpm lint || journalctl -k | grep oom",
                        "grep 'oom_kill [1-9]' /sys/fs/cgroup/app.scope/memory.events"):
            self.state.unlink(missing_ok=True)
            self.killed(BIG)
            self.bash(command, failed=True, error="Exit code 1")
            self.assertEqual(self.pre(BIG), "", command)

    def test_other_commands_do_not_clear_it(self):
        self.killed(BIG)
        for command in ("journalctl --user -u app", "echo dmesg", "grep -i oom notes.txt", "cat memory.txt",
                        "systemctl --user restart app", 'git commit -m "journalctl -k"', "journalctl -uk",
                        "journalctl -b | grep -i memory", "journalctl -t app", "journalctl -t kernel-foo",
                        "journalctl --identifier=kernelx", "journalctl SYSLOG_IDENTIFIER=kernelx",
                        "journalctl _TRANSPORT=journal", "journalctl -b -g x", "journalctl -k --help",
                        "dmesg --help", "dmesg --version", "dmesg -C", "dmesg --clear", "dmesg -h",
                        "rg memory.events docs/", "grep -rn x src/memory.events", "cat memory.events.txt",
                        "cat /sys/fs/cgroup/x/memory.events.bak", "echo /sys/fs/cgroup/x/memory.events",
                        "rm -f /sys/fs/cgroup/x/memory.events", "journalctl -b > j.log; grep -i memory j.log"):
            self.bash(command)
        self.assertIn("oom-first", self.pre(BIG))

    def test_a_kernel_log_read_before_the_failure_does_not_count(self):
        self.bash("journalctl -k")
        self.killed(BIG)
        self.assertIn("oom-first", self.pre(BIG))

    def test_a_new_failure_after_the_read_arms_it_again(self):
        self.killed(BIG)
        self.bash("dmesg")
        self.killed(BIG)
        self.assertIn("oom-first", self.pre(BIG))


class TimeoutTest(OomCase):
    def test_a_command_under_timeout_is_cleared_by_a_cause_note_and_says_so(self):
        for command in ("timeout -s KILL 60 node build/big.js", "timeout -k 5 600 pytest -q",
                        "cd web && env CI=1 timeout --signal=KILL 30s npm test",
                        "systemd-run --user --scope -q -p MemoryMax=2G -- timeout -k 5 600 node build/big.js",
                        "systemd-run --user --scope timeout 60 node build/big.js",
                        "systemd-run --user --scope -q -- unshare --user --map-root-user -- timeout 9 python3 x.py"):
            self.state.unlink(missing_ok=True)
            self.killed(command)
            reason = self.pre(command)
            self.assertIn("oom-first", reason, command)
            self.assertIn('or, if it ran out its timeout limit, confirm that with python3 ', reason)
            self.assertIn(f'{LESSONS} cause "<command>: timeout"', reason)
            self.cause()
            self.assertEqual(self.pre(command), "", command)

    def test_a_cause_note_does_not_clear_a_command_not_under_timeout(self):
        command = "systemd-run --user --scope -q -p MemoryMax=2G -- env PATH=/usr/bin python3 -m unittest tests.a"
        self.killed(command)
        self.cause("unittest: timeout")
        reason = self.pre(command)
        self.assertIn("oom-first", reason)
        self.assertNotIn("timeout limit", reason)
        self.bash("journalctl -k -n 20")
        self.assertEqual(self.pre(command), "")

    def test_a_timeout_written_as_a_path_is_cleared_by_a_cause_note(self):
        self.killed("/usr/bin/timeout -k 5 60 " + BIG)
        self.assertIn("timeout limit", self.pre(BIG))
        self.cause()
        self.assertEqual(self.pre(BIG), "")

    def test_a_cause_note_before_the_failure_does_not_count(self):
        self.cause()
        self.killed("timeout 60 node build/big.js")
        self.assertIn("oom-first", self.pre("timeout 60 node build/big.js"))


class RegistryTest(unittest.TestCase):
    STATE = {"keys": set(), "events": [{"event": "error", "command": BIG, "error": "Exit code 137", "checks": []}]}

    def judge(self, folder, version):
        with mock.patch.object(guard_lessons, "HOOK_VERSION", version), \
                mock.patch.dict("os.environ", {"LESSONS_GUARDS_GLOBAL_FILE": str(Path(folder) / "g.json"),
                                               "CLAUDE_PROJECT_DIR": folder}):
            return guard_lessons.judge(BIG, folder, session=lambda: self.STATE)

    def test_min_version_1_30_0_is_skipped_by_older_hooks(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / ".agents").mkdir()
            (Path(folder) / ".agents" / "lesson-guards.json").write_text(json.dumps(
                {"guards": [{"rule": "oom-first", "lesson": "G040", "min_version": "1.30.0"}]}))
            self.assertIsNone(self.judge(folder, (1, 29, 1)))
            self.assertEqual(guard_lessons.registry_problems(folder), [])
            self.assertEqual(self.judge(folder, (1, 30, 0)).rule, "oom-first")

    def test_only_the_newest_armed_failures_are_judged(self):
        events = [{"event": "error", "command": f"node job{n}.js", "error": "Exit code 137", "checks": []}
                  for n in range(guard_oom.MAX_ARMED + 1)]
        self.assertIsNone(guard_oom.armed("node job0.js", {"events": events}))
        self.assertEqual(guard_oom.armed("node job1.js", {"events": events}), ("node job1.js", False))

    def test_a_broken_session_state_passes(self):
        for state in ({}, {"events": None}, {"events": [None, {"event": "error", "error": None}]}, None):
            self.assertIsNone(guard_oom.armed(BIG, state), state)



class KernelLogCostTest(unittest.TestCase):
    """reads_kernel_log runs after every Bash call, rule on or off: its cost must not grow with the square of a long
    pipeline, and a call that names no reader is not parsed at all."""
    def test_a_long_pipeline_is_judged_in_linear_time(self):
        import time
        many_greps = "a;" * 10000  # about 20 KB, the most the tracker keeps
        with_reader = "journalctl -b" + " |a" * 9990
        started = time.monotonic()
        self.assertFalse(guard_oom.reads_kernel_log(many_greps))
        self.assertFalse(guard_oom.reads_kernel_log(with_reader))  # no grep for oom: not a kernel-log read
        self.assertTrue(guard_oom.reads_kernel_log(with_reader + " | grep -i oom"))
        self.assertLess(time.monotonic() - started, 1.0)

    def test_a_call_naming_no_reader_is_not_parsed(self):
        with mock.patch.object(guard_oom, "pipelines", wraps=guard_oom.pipelines) as parse:
            self.assertFalse(guard_oom.reads_kernel_log("pnpm test 2>&1 | tail -30"))
            self.assertFalse(guard_oom.reads_kernel_log("grep -c oom notes.md", "Exit code 1"))
            self.assertEqual(parse.call_count, 0)
            self.assertTrue(guard_oom.reads_kernel_log("dmesg -T"))
            self.assertEqual(parse.call_count, 1)


if __name__ == "__main__":
    unittest.main()
