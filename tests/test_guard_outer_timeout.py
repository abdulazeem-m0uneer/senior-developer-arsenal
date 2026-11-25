"""Tests for the opt-in outer-timeout lesson guard (hooks/guard_outer_timeout.py, wired in guard_lessons)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))

import guard_lessons  # noqa: E402
import guard_outer_timeout  # noqa: E402

SCRIPT = HOOKS / "guard.py"
ENTRY = {"rule": "outer-timeout", "lesson": "G013", "programs": ["gate-slot", "lock-run.sh"],
         "min_version": "1.33.0"}


class TimeoutCase(unittest.TestCase):
    """A project whose registry names outer-timeout for two queueing programs, and a 1.33.0 hook."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.project = self.dir / "project"
        (self.project / ".agents").mkdir(parents=True)
        env = {"LESSONS_GUARDS_GLOBAL_FILE": str(self.dir / "home" / "lesson-guards.json"),
               "LESSONS_GUARD_HITS_FILE": str(self.dir / "home" / "hits.jsonl")}
        for patch in (mock.patch.dict(os.environ, env), mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 33, 0))):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.registry(ENTRY)

    def registry(self, *guards):
        (self.project / ".agents" / "lesson-guards.json").write_text(json.dumps({"guards": list(guards)}),
                                                                     encoding="utf-8")

    def judge(self, command):
        return guard_lessons.judge(command, str(self.project))

    def assertRefused(self, command, program="gate-slot"):
        hit = self.judge(command)
        self.assertIsNotNone(hit, command)
        self.assertEqual((hit.rule, hit.lesson), ("outer-timeout", "G013"), command)
        self.assertIn(f"`{program}`", hit.reason, command)
        self.assertIn("put the timeout inside, on the command it runs", hit.reason)

    def assertPasses(self, command):
        self.assertIsNone(self.judge(command), command)


class TimeoutWrapperTests(TimeoutCase):
    def test_timeout_around_the_queueing_program(self):
        self.assertRefused("timeout 600 gate-slot pnpm test")

    def test_timeout_options(self):
        self.assertRefused("timeout -k 5 600 gate-slot pnpm test")
        self.assertRefused("timeout -k5 600 gate-slot x")
        self.assertRefused("timeout --kill-after=5 -s KILL 600 gate-slot x")
        self.assertRefused("timeout --foreground --preserve-status 1h gate-slot x")

    def test_systemd_run_with_runtime_max_sec(self):
        self.assertRefused("systemd-run --user --scope -p RuntimeMaxSec=600 gate-slot x")
        self.assertRefused("systemd-run --user --scope --property=RuntimeMaxSec=1h gate-slot x")
        self.assertRefused("systemd-run --user --scope -p RuntimeMaxSec=600 -- gate-slot x")
        self.assertRefused("systemd-run --user -pRuntimeMaxSec=60 gate-slot x")

    def test_other_wrappers_between(self):
        self.assertRefused("sudo timeout 5 env FOO=1 nice -n 5 gate-slot x")
        self.assertRefused("timeout 5 systemd-run --user --scope -p MemoryMax=2G gate-slot x")
        self.assertRefused("systemd-run --user --scope -p MemoryMax=2G -p RuntimeMaxSec=60 -- "
                           "unshare --user --map-root-user --pid --fork -- env PATH=/usr/bin gate-slot x")
        self.assertRefused("nohup timeout 5 stdbuf -oL gate-slot x")

    def test_options_that_take_a_value(self):
        self.assertRefused("timeout 5 unshare --map-user 1000 gate-slot x")
        self.assertRefused("timeout 5 systemd-run -u job --uid 1000 gate-slot x")
        self.assertRefused("timeout 5 sudo -u root gate-slot x")

    def test_launchers_ssh_and_shell_scripts(self):
        self.assertRefused("timeout 5 sh -c 'gate-slot x'")
        self.assertRefused("timeout 5 bash -lc \"cd /tmp && gate-slot x\"")
        self.assertRefused("timeout 5 npx gate-slot x")
        self.assertRefused("echo a | timeout 5 xargs gate-slot")
        self.assertRefused("ssh host timeout 5 gate-slot x")
        self.assertRefused("ssh host 'timeout 5 gate-slot x'")

    def test_inside_larger_commands(self):
        self.assertRefused("echo hi && timeout 5 gate-slot x")
        self.assertRefused("echo a | timeout 5 gate-slot x | tail -1")
        self.assertRefused("if true; then timeout 5 gate-slot x; fi")
        self.assertRefused("while true; do timeout 5 gate-slot x; done")

    def test_program_by_path_script_and_variable(self):
        self.assertRefused("timeout 5 /opt/bin/gate-slot x")
        self.assertRefused("timeout 5 bash ./scripts/lock-run.sh x", program="lock-run.sh")
        self.assertRefused("timeout 5 ./lock-run.sh x", program="lock-run.sh")
        self.assertRefused("S=gate-slot; timeout 5 $S x")
        self.assertRefused("export S=/bin/gate-slot; timeout 5 ${S} x")

    def test_the_hint_and_the_reason(self):
        hit = self.judge("timeout 5 gate-slot x")
        self.assertIn("the tool's own wait setting", hit.reason)
        self.registry({**ENTRY, "hint": "GATE_MAX_WAIT"})
        self.assertIn("Bound the wait with GATE_MAX_WAIT", self.judge("timeout 5 gate-slot x").reason)
        self.registry({**ENTRY, "reason": "Wait inside."})
        self.assertEqual(self.judge("timeout 5 gate-slot x").reason, "Wait inside.")


class PassTests(TimeoutCase):
    def test_timeout_inside_the_queueing_program(self):
        self.assertPasses("gate-slot timeout 600 pnpm test")
        self.assertPasses("gate-slot -- timeout 5 x")
        self.assertPasses("gate-slot sh -c 'timeout 5 x'")
        self.assertPasses("systemd-run --user --scope -p RuntimeMaxSec=60 -- true; gate-slot x")

    def test_no_queueing_program(self):
        self.assertPasses("timeout 5 pnpm test")
        self.assertPasses("timeout 5 echo gate-slot")
        self.assertPasses("timeout 5 sh -c 'echo hi'")
        self.assertPasses("systemd-run --user --scope -p RuntimeMaxSec=60 pnpm test")

    def test_the_two_are_separate_commands(self):
        self.assertPasses("timeout 5 true; gate-slot x")
        self.assertPasses("timeout 5 pnpm test && gate-slot x")
        self.assertPasses("timeout 5 pnpm test | gate-slot x")

    def test_no_timeout_set(self):
        self.assertPasses("timeout 0 gate-slot x")
        self.assertPasses("timeout 0s gate-slot x")
        self.assertPasses("systemd-run --user --scope -p MemoryMax=2G gate-slot x")
        self.assertPasses("systemd-run --user --scope -p RuntimeMaxSec=infinity gate-slot x")
        self.assertPasses("systemd-run --user --scope -p RuntimeMaxSec=0 gate-slot x")
        self.assertPasses("env PATH=/usr/bin nice gate-slot x")
        self.assertPasses("unshare --user --pid -- gate-slot x")

    def test_text_that_only_mentions_the_commands(self):
        self.assertPasses("grep 'timeout 5 gate-slot' notes.md")
        self.assertPasses("echo \"timeout 5 gate-slot x\"")
        self.assertPasses("git commit -m 'drop timeout 5 gate-slot'")

    def test_help_and_version_calls(self):
        self.assertPasses("timeout --help gate-slot")
        self.assertPasses("timeout --version")
        self.assertPasses("timeout --help 5 gate-slot x")

    def test_a_status_call_of_the_queueing_program_passes(self):
        self.assertPasses("timeout 10 gate-slot status")
        self.assertPasses("systemd-run -p RuntimeMaxSec=30 gate-slot status")
        self.assertPasses("timeout 10 bash gate-slot status")
        self.assertPasses("timeout 10 gate-slot -h")

    def test_status_anywhere_but_first_is_still_a_queueing_call(self):
        self.assertRefused("timeout 10 gate-slot x status")
        self.assertRefused("timeout 10 gate-slot statuses")
        self.assertRefused("timeout 10 gate-slot -- status")

    def test_an_inner_timeout_that_never_fires_does_not_clear_an_outer_one(self):
        self.assertRefused("timeout 5 timeout 0 gate-slot x")
        self.assertRefused("systemd-run -p RuntimeMaxSec=60 timeout 0 gate-slot x")
        self.assertRefused("timeout 5 systemd-run -p RuntimeMaxSec=0 gate-slot x")

    def test_a_command_nested_too_deep_to_read_passes(self):
        self.assertPasses("timeout 5 " + "env " * 3000 + "gate-slot x")

    def test_an_empty_or_blank_command(self):
        self.assertPasses("")
        self.assertPasses("   ")
        self.assertPasses("timeout")
        self.assertPasses("timeout 5")


class ReviewedMissTests(TimeoutCase):
    """Behaviours the review found unpinned or missed."""

    def test_long_forms_and_end_of_options(self):
        self.assertRefused("timeout --kill-after 5 600 gate-slot x")
        self.assertRefused("timeout --signal KILL 600 gate-slot x")
        self.assertRefused("timeout -- 600 gate-slot x")
        self.assertRefused("systemd-run --user --property RuntimeMaxSec=60 gate-slot x")

    def test_wrapper_gaps(self):
        self.assertRefused("timeout 5 setsid gate-slot x")
        self.assertRefused("timeout 5 bash -o pipefail ./lock-run.sh x", program="lock-run.sh")
        self.assertRefused("timeout 5 eval gate-slot x")
        self.assertRefused("timeout 5 >out gate-slot x")
        self.assertRefused("timeout 5 2>&1 gate-slot x")
        self.assertRefused("timeout 5 2 >/dev/null gate-slot x")
        self.assertRefused("FOO=1 timeout 5 gate-slot x")
        self.assertRefused("timeout 5 sudo FOO=1 gate-slot x")

    def test_a_variable_set_in_a_shell_script_stays_there(self):
        self.assertPasses("timeout 5 sh -c 'S=gate-slot; true'; timeout 5 $S x")

    def test_wrappers_outside_the_list(self):
        self.assertRefused("timeout 60 taskset -c 0 gate-slot x")
        self.assertRefused("timeout 60 taskset --cpu-list 0 gate-slot x")
        self.assertRefused("timeout 60 taskset 0x3 gate-slot x")
        self.assertRefused("timeout 60 chrt -f 1 gate-slot x")
        self.assertRefused("timeout 60 su -c 'gate-slot x'")
        self.assertRefused("timeout 60 su - root -c 'gate-slot x'")
        self.assertRefused("timeout 60 su --command 'gate-slot x' root")
        self.assertRefused("timeout 60 find . -exec gate-slot {} \\;")
        self.assertRefused("timeout 60 find . -type f -execdir gate-slot {} +")
        self.assertRefused("timeout 60 find . -exec echo {} + -exec gate-slot {} +")
        self.assertRefused("timeout 60 docker exec c gate-slot x")
        self.assertRefused("timeout 60 docker exec -e A=1 -u root c gate-slot x")
        self.assertRefused("timeout 60 exec -a n gate-slot x")

    def test_option_values_of_interpreters_and_time(self):
        self.assertRefused("timeout 60 python3 -W ignore gate-slot")
        self.assertRefused("timeout 60 python3 -X dev gate-slot")
        self.assertRefused("timeout 60 node -r ts-node/register gate-slot")
        self.assertRefused("timeout 60 node --import x gate-slot")
        self.assertRefused("timeout 60 time -f %e gate-slot x")

    def test_split_string_default_expansion_and_runners(self):
        self.assertRefused("timeout 5 env -S 'gate-slot x'")
        self.assertRefused("timeout 5 env --split-string='A=1 gate-slot x'")
        self.assertRefused("timeout 5 env -S'gate-slot x'")
        self.assertRefused("timeout 5 ${GATE:-gate-slot} x")
        self.assertRefused("GATE=gate-slot; timeout 5 ${GATE:-other} x")
        self.assertRefused("timeout 60 deno run gate-slot")
        self.assertRefused("timeout 60 bun run gate-slot")


class ReviewedFalseRefusalTests(TimeoutCase):
    """Commands that name the queueing program but never queue."""

    def test_lookups_and_help(self):
        self.assertPasses("timeout 60 command -v gate-slot")
        self.assertPasses("timeout 60 command -V gate-slot")
        self.assertPasses("timeout 60 gate-slot --version")
        self.assertPasses("timeout 60 bash ./lock-run.sh --version")
        entry = {"programs": ["gate-slot"]}  # --help itself is the help-probe rule's, so judge this rule alone
        self.assertIsNone(guard_outer_timeout.problem("timeout 60 gate-slot --help", entry))

    def test_interpreter_flags_that_run_no_script(self):
        for command in ("bash -n gate-slot", "sh -n gate-slot", "ruby -c gate-slot", "perl -c gate-slot",
                        "node --check gate-slot", "python3 -m gate-slot", "bash -s gate-slot",
                        "python3 -c gate-slot", "node -e gate-slot"):
            self.assertPasses("timeout 60 " + command)

    def test_a_timeout_that_never_fires(self):
        for duration in ("0", ".0", "0x0", "0.0s", "inf", "infinity"):
            self.assertPasses(f"timeout {duration} gate-slot x")

    def test_a_script_name_is_not_a_run_argument(self):
        self.assertPasses("timeout 5 pnpm run build gate-slot")
        self.assertPasses("timeout 60 find . -name gate-slot")
        self.assertPasses("timeout 60 docker exec c echo gate-slot")


class SecondReviewTests(TimeoutCase):
    def test_more_wrappers_are_walked(self):
        self.assertRefused("timeout 60 watch -n5 gate-slot x")
        self.assertRefused("timeout 60 watch --interval 5 gate-slot x")
        self.assertRefused("timeout 60 runuser -u bob -- gate-slot x")
        self.assertRefused("timeout 60 runuser --user bob gate-slot x")
        self.assertRefused("timeout 60 sudo -r role gate-slot x")
        self.assertRefused("timeout 60 sudo -t type gate-slot x")
        self.assertRefused("timeout 5 bash -c -- 'gate-slot x'")

    def test_only_exec_runs_a_command_in_a_container(self):
        for sub in ("run img gate-slot", "ps", "cp gate-slot c:/x"):
            self.assertPasses(f"timeout 5 docker {sub}")
            self.assertPasses(f"timeout 5 podman {sub}")
        self.assertRefused("timeout 5 docker exec c gate-slot x")

    def test_unshare_p_is_not_a_property_option(self):
        self.assertRefused("timeout 5 unshare -p gate-slot x")

    def test_only_runtime_max_sec_bounds_a_unit(self):
        self.assertPasses("systemd-run -p RuntimeRandomizedExtraSec=5 gate-slot x")
        self.assertPasses("systemd-run -p RuntimeMaxSecX=5 gate-slot x")

    def test_the_last_bound_and_a_known_duration_win(self):
        self.assertPasses("systemd-run -p RuntimeMaxSec=60 -p RuntimeMaxSec=0 gate-slot x")
        self.assertRefused("systemd-run -p RuntimeMaxSec=0 -p RuntimeMaxSec=60 gate-slot x")
        self.assertPasses("T=0; timeout $T gate-slot x")
        self.assertRefused("T=5; timeout $T gate-slot x")

    def test_short_help_runs_nothing(self):
        self.assertPasses("timeout 5 gate-slot -h")


class EntryTests(TimeoutCase):
    def test_off_until_a_registry_entry_names_it(self):
        self.registry()
        self.assertPasses("timeout 5 gate-slot x")

    def test_without_programs_nothing_is_judged(self):
        self.registry({"rule": "outer-timeout", "lesson": "G013", "min_version": "1.33.0"})
        self.assertPasses("timeout 5 gate-slot x")
        self.assertEqual(guard_lessons.registry_problems(str(self.project)), [])

    def test_a_program_written_as_a_path_matches_its_basename(self):
        self.registry({**ENTRY, "programs": ["bin/gate-slot"]})
        self.assertRefused("timeout 5 gate-slot x")

    def test_enabled_false(self):
        self.registry({**ENTRY, "enabled": False})
        self.assertPasses("timeout 5 gate-slot x")

    def test_min_version_1_33_0_skips_on_older_hooks(self):
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 32, 0)):
            self.assertPasses("timeout 5 gate-slot x")
            self.assertEqual(guard_lessons.registry_problems(str(self.project)), [])
        self.assertIsNotNone(self.judge("timeout 5 gate-slot x"))

    def test_bad_registry_values_are_skipped(self):
        for bad in ({"hint": ""}, {"hint": 3}, {"hint": "a\nb"}, {"hint": "a\rb"}, {"hint": "x" * 201}, {"programs": []},
                    {"programs": "gate-slot"}, {"confirm": ["--yes"]}):
            self.registry({**ENTRY, **bad})
            self.assertPasses("timeout 5 gate-slot x")
            self.assertTrue(guard_lessons.registry_problems(str(self.project)), bad)

    def test_hint_is_for_this_rule_only(self):
        self.registry({"rule": "help-probe", "hint": "x"}, ENTRY)
        problems = guard_lessons.registry_problems(str(self.project))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("hint", problems[0])
        self.assertIsNotNone(self.judge("timeout 5 gate-slot x"))

    def test_an_error_in_the_rule_passes(self):
        with mock.patch.object(guard_outer_timeout, "walk", side_effect=RuntimeError("boom")):
            self.assertPasses("timeout 5 gate-slot x")


class ModuleTests(unittest.TestCase):
    def test_problem(self):
        entry = {"programs": ["x"]}
        self.assertIn("`x`", guard_outer_timeout.problem("timeout 5 x", entry))
        self.assertIsNone(guard_outer_timeout.problem("timeout 5 x", {}))
        self.assertIsNone(guard_outer_timeout.problem("x timeout 5 y", entry))

    def test_bad_input_passes(self):
        self.assertIsNone(guard_outer_timeout.problem(None, {"programs": ["x"]}))
        self.assertIsNone(guard_outer_timeout.problem("timeout 5 x", {"programs": None}))
        self.assertIsNone(guard_outer_timeout.problem("timeout 5 x", {"programs": [3]}))

    def test_valid_hint(self):
        self.assertTrue(guard_outer_timeout.valid_hint("the --wait option"))
        for bad in ("", "  ", None, 3, "a\nb", "a\rb", "x" * 201):
            self.assertFalse(guard_outer_timeout.valid_hint(bad), bad)


class HookTests(TimeoutCase):
    """guard.py pre denies a timeout around the queueing program."""

    def pre(self, command):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command},
                   "cwd": str(self.project), "permission_mode": "default"}
        base = {k: v for k, v in os.environ.items()
                if k not in ("ARSENAL_GUARD", "ARSENAL_LESSON_GUARDS", "ARSENAL_GUARD_DESTRUCTIVE",
                             "ARSENAL_RUN_LIMITS", "CLAUDE_PROJECT_DIR", "ARSENAL_PROFILE", "ARSENAL_GUARD_SCOPE")}
        result = subprocess.run([sys.executable, str(SCRIPT), "pre"], cwd=self.project, input=json.dumps(payload),
                                capture_output=True, text=True, env=base)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None

    def test_the_hook_denies_the_outer_timeout_and_passes_the_inner_one(self):
        self.registry({k: v for k, v in ENTRY.items() if k != "min_version"})  # the hook may be older than 1.33.0
        out = self.pre("timeout 600 gate-slot pnpm test")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("G013 (outer-timeout)", out["permissionDecisionReason"])
        self.assertIsNone(self.pre("gate-slot timeout 600 pnpm test"))


if __name__ == "__main__":
    unittest.main()
