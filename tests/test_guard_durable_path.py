"""Tests for the opt-in durable-path lesson guard (hooks/guard_durable_path.py, wired in guard_lessons)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))

import guard_lessons  # noqa: E402

ENTRY = {"rule": "durable-path", "lesson": "G025", "min_version": "1.33.5"}
SCRATCH = "/home/u/.claude/projects/p/abc/scratchpad"


class DurableCase(unittest.TestCase):
    """A project whose registry names durable-path, and a 1.33.5 hook."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.project = self.dir / "project"
        (self.project / ".agents").mkdir(parents=True)
        env = {"LESSONS_GUARDS_GLOBAL_FILE": str(self.dir / "home" / "lesson-guards.json"),
               "LESSONS_GUARD_HITS_FILE": str(self.dir / "home" / "hits.jsonl")}
        for patch in (mock.patch.dict(os.environ, env), mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 33, 5))):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.registry(ENTRY)

    def registry(self, *guards):
        (self.project / ".agents" / "lesson-guards.json").write_text(json.dumps({"guards": list(guards)}),
                                                                     encoding="utf-8")

    def judge(self, command):
        return guard_lessons.judge(command, str(self.project))

    def judge_file(self, tool, **tool_input):
        return guard_lessons.judge_outbound(tool, tool_input, str(self.project))

    def check(self, hit, label):
        self.assertIsNotNone(hit, label)
        self.assertEqual((hit.rule, hit.lesson), ("durable-path", "G025"), label)
        return hit

    def assertRefused(self, command):
        return self.check(self.judge(command), command)

    def assertPasses(self, command):
        self.assertIsNone(self.judge(command), command)

    def assertFileRefused(self, tool, **tool_input):
        return self.check(self.judge_file(tool, **tool_input), tool_input)

    def assertFilePasses(self, tool, **tool_input):
        self.assertIsNone(self.judge_file(tool, **tool_input), tool_input)


class SystemdRunTests(DurableCase):
    def test_every_scheduling_option_with_a_tmp_script(self):
        for option in ("--on-calendar='*-*-* 03:00'", "--on-active=30m", "--on-boot=5min", "--on-startup=1min",
                       "--on-unit-active=1h", "--on-unit-inactive=1h", "--timer-property=AccuracySec=1s"):
            self.assertRefused(f"systemd-run --user {option} /tmp/backup.sh")

    def test_option_value_given_as_the_next_word(self):
        self.assertRefused("systemd-run --user --on-calendar daily /tmp/job.sh")
        self.assertRefused("systemd-run --timer-property AccuracySec=1s /tmp/job.sh")

    def test_interpreter_runs_a_tmp_script(self):
        self.assertRefused("systemd-run --on-boot=5min bash /tmp/x.sh")
        self.assertRefused("systemd-run --on-boot=5min python3 -u /tmp/x.py")
        self.assertRefused("systemd-run --on-boot=5min /usr/bin/env FOO=1 /tmp/x.sh")
        self.assertRefused("systemd-run --on-boot=5min bash -c '/tmp/x.sh --now'")
        self.assertRefused("systemd-run --on-boot=5min bash -lc 'FOO=1 /tmp/x.sh'")
        self.assertPasses("systemd-run --on-boot=5min bash -c '/home/u/x.sh /tmp/data'")

    def test_unit_properties_before_the_command(self):
        self.assertRefused("systemd-run -p MemoryMax=2G -u job --on-calendar=daily /tmp/x.sh")

    def test_session_scratchpad_script(self):
        self.assertRefused(f"systemd-run --user --on-calendar=daily {SCRATCH}/job.sh")

    def test_entry_scratch_globs(self):
        self.registry({**ENTRY, "scratch": ["/var/work/tmp-*/**", "work/scratch/*"]})
        self.assertRefused("systemd-run --on-active=1m /var/work/tmp-1/sub/x.sh")
        self.assertRefused("systemd-run --on-active=1m /srv/work/scratch/x.sh")
        self.assertPasses("systemd-run --on-active=1m /var/work/keep/x.sh")

    def test_space_separated_unit_timer_options(self):
        self.assertRefused("systemd-run --user --on-unit-active 5m /tmp/x.sh")
        self.assertRefused("systemd-run --user --on-unit-inactive 5m bash /tmp/x.sh")

    def test_timer_options_without_a_value(self):
        self.assertRefused("systemd-run --user --on-clock-change /tmp/x.sh")
        self.assertRefused("systemd-run --user --on-timezone-change /tmp/x.sh")

    def test_paths_are_normalised(self):
        self.assertPasses("systemd-run --on-calendar=daily /tmp/../home/me/x")
        self.assertRefused("systemd-run --on-calendar=daily //tmp/x")
        self.assertRefused("systemd-run --on-calendar=daily /home/me/../../tmp/x")

    def test_end_of_options_marker(self):
        self.assertRefused("systemd-run --on-active=1m -- /tmp/x.sh")

    def test_nested_in_a_shell_script_string(self):
        self.assertRefused("bash -c 'systemd-run --on-active=1m /tmp/x.sh'")

    def test_refusal_names_the_path_and_the_fix(self):
        text = self.assertRefused("systemd-run --on-active=1m /tmp/x.sh").reason
        self.assertIn("/tmp/x.sh", text)
        self.assertIn("durable", text)

    def test_entry_reason_replaces_the_text(self):
        self.registry({**ENTRY, "reason": "Keep jobs in the repo."})
        self.assertEqual(self.assertRefused("systemd-run --on-active=1m /tmp/x.sh").reason, "Keep jobs in the repo.")


class AtTests(DurableCase):
    def test_at_reads_a_tmp_script(self):
        self.assertRefused("at -f /tmp/job.sh now + 1 hour")
        self.assertRefused("echo /tmp/job.sh | at 5pm")
        self.assertRefused('at now + 5 minutes <<< "/tmp/x.sh"')
        self.assertRefused("batch < /tmp/job.sh")
        self.assertRefused("at now + 1 hour <<EOF\n/tmp/job.sh\nEOF")
        self.assertRefused(f"at -f {SCRATCH}/job.sh 17:00")

    def test_at_with_a_durable_script(self):
        self.assertPasses("at -f /home/u/bin/job.sh now + 1 hour")
        self.assertPasses('at now <<< "/home/u/bin/x.sh"')

    def test_at_job_text_runs_a_tmp_script_through_an_interpreter(self):
        self.assertRefused("echo 'bash /tmp/x.sh' | at 5pm")
        self.assertRefused('at 5pm <<< "bash /tmp/x.sh"')
        self.assertRefused("printf 'python3 /tmp/x.py\\n' | at 5pm")
        self.assertRefused("bash -c \"echo 'bash /tmp/x.sh' | at 5pm\"")

    def test_tmp_word_outside_the_job_text_is_not_judged(self):
        self.assertPasses("cp /tmp/x.log ~/ && echo '~/bin/x' | at 5pm")
        self.assertPasses("at -f ~/bin/job.sh now; ls /tmp/a")
        self.assertPasses("echo hi | at now; echo /tmp/x")
        self.assertPasses("echo /tmp/x; echo ~/bin/y | at now")

    def test_at_that_only_lists_or_removes(self):
        self.assertPasses("at -l")
        self.assertPasses("at -r 3 && echo /tmp/x")


class CrontabTests(DurableCase):
    def test_crontab_line_appended_through_echo(self):
        self.assertRefused('(crontab -l; echo "0 3 * * * /tmp/x.sh") | crontab -')
        self.assertRefused("(crontab -l 2>/dev/null; echo '*/5 * * * * /tmp/run.sh >/dev/null') | crontab -")

    def test_crontab_special_schedule_printf_and_heredoc(self):
        self.assertRefused('(crontab -l; printf "@reboot /tmp/x.sh\\n") | crontab -')
        self.assertRefused("crontab - <<EOF\n0 3 * * * /tmp/x.sh\nEOF")

    def test_crontab_line_with_an_interpreter_and_scratchpad(self):
        self.assertRefused(f'(crontab -l; echo "0 3 * * * bash {SCRATCH}/x.sh") | crontab -')

    def test_durable_crontab_line(self):
        self.assertPasses('(crontab -l; echo "0 3 * * * /home/u/bin/x.sh") | crontab -')

    def test_tmp_path_only_as_an_argument(self):
        self.assertPasses('(crontab -l; echo "0 3 * * * /usr/bin/backup /tmp/data") | crontab -')

    def test_only_the_text_piped_into_crontab_is_judged(self):
        self.assertPasses("echo '0 3 * * * ~/bin/x' | crontab -; echo 'see 0 3 * * * /tmp/x'")
        self.assertPasses("echo 'see 0 3 * * * /tmp/x'; echo '0 3 * * * ~/bin/x' | crontab -")
        self.assertRefused("echo 'see' ; (crontab -l; echo '0 3 * * * /tmp/x') | crontab -")
        self.assertRefused("crontab - <<< '0 3 * * * /tmp/x'")

    def test_text_piped_into_a_subshell_and_printf_line_breaks(self):
        self.assertRefused("echo '0 3 * * * /tmp/x' | (crontab -)")
        self.assertPasses("echo '0 3 * * * /tmp/x'; (crontab -)")
        self.assertRefused("printf '0 3 * * * ~/bin/a\\n0 3 * * * /tmp/x\\n' | crontab -")

    def test_every_command_of_a_crontab_line_and_day_names(self):
        self.assertRefused("(crontab -l; echo '0 3 * * * cd ~ && /tmp/x') | crontab -")
        self.assertRefused("(crontab -l; echo '0 3 * * mon-fri /tmp/x') | crontab -")
        self.assertRefused("(crontab -l; echo '0 3 * * * bash -c \"/tmp/x\"') | crontab -")

    def test_crontab_listing_and_unrelated_echo(self):
        self.assertPasses("crontab -l")
        self.assertPasses('crontab -l | grep x; echo "0 3 * * * /tmp/x.sh"')
        self.assertPasses('echo "0 3 * * * /tmp/x.sh"')


class RunNowTests(DurableCase):
    def test_running_a_tmp_script_now(self):
        self.assertPasses("bash /tmp/x.sh")
        self.assertPasses("/tmp/x.sh")
        self.assertPasses("systemd-run --scope -q -p MemoryMax=2G /tmp/x")
        self.assertPasses("systemd-run --user --scope -p MemoryMax=2G -- bash /tmp/x.sh")
        self.assertPasses("systemd-run --on-active=1m /bin/echo /tmp/x")

    def test_scheduling_a_durable_script(self):
        self.assertPasses("systemd-run --user --on-calendar=daily /usr/local/bin/x.sh")
        self.assertPasses("systemd-run --user --on-calendar=daily bash /home/u/bin/x.sh")
        self.assertPasses("systemd-run --on-active=1m -p WorkingDirectory=/tmp /home/u/bin/x.sh")

    def test_unrelated_commands(self):
        for command in ("ls /tmp", "cat /tmp/at.txt", "echo at /tmp/x", "git status", ""):
            self.assertPasses(command)


class UnitFileTests(DurableCase):
    def test_service_exec_start_under_tmp(self):
        for line in ("ExecStart=/tmp/x.sh", "ExecStart=-/tmp/x.sh", "ExecStart=/usr/bin/bash /tmp/x.sh",
                     "ExecStartPre=/tmp/prep.sh", f"ExecStart={SCRATCH}/x.sh --flag"):
            self.assertFileRefused("Write", file_path="/home/u/.config/systemd/user/job.service",
                                   content=f"[Service]\n{line}\n")

    def test_service_with_durable_paths(self):
        self.assertFilePasses("Write", file_path="/etc/systemd/system/job.service",
                              content="[Service]\nExecStart=/usr/bin/bash /home/u/bin/x.sh /tmp/data\n")

    def test_service_scratch_glob(self):
        self.registry({**ENTRY, "scratch": ["/var/work/tmp-*/**"]})
        self.assertFileRefused("Write", file_path="/etc/systemd/system/job.service",
                               content="[Service]\nExecStart=/var/work/tmp-9/x.sh\n")

    def test_edit_that_leaves_a_tmp_exec_start(self):
        path = self.dir / "job.service"
        path.write_text("[Service]\nExecStart=/usr/bin/x\n", encoding="utf-8")
        self.assertFileRefused("Edit", file_path=str(path), old_string="/usr/bin/x", new_string="/tmp/x.sh")
        self.assertFilePasses("Edit", file_path=str(path), old_string="/usr/bin/x", new_string="/usr/bin/y")

    def test_multi_edit(self):
        path = self.dir / "job.service"
        path.write_text("[Service]\nExecStart=/usr/bin/x\n", encoding="utf-8")
        self.assertFileRefused("MultiEdit", file_path=str(path),
                               edits=[{"old_string": "/usr/bin/x", "new_string": "/tmp/x.sh"}])

    def test_service_drop_in_and_continuation_lines(self):
        self.assertFileRefused("Write", file_path="/etc/systemd/system/x.service.d/override.conf",
                               content="[Service]\nExecStart=\nExecStart=/tmp/x.sh\n")
        self.assertFileRefused("Write", file_path="/x/job.service",
                               content="[Service]\nExecStart=/usr/bin/env \\\n  /tmp/y\n")
        self.assertFilePasses("Write", file_path="/etc/systemd/system/x.service.d/override.conf",
                              content="[Service]\nEnvironment=A=/tmp/x\n")
        self.assertFilePasses("Write", file_path="/x/other.d/override.conf", content="ExecStart=/tmp/x.sh\n")

    def test_documents_named_crontab_are_not_crontabs(self):
        self.assertFilePasses("Write", file_path="docs/crontab-guide.md", content="0 3 * * * /tmp/x\n")
        self.assertFilePasses("Write", file_path="docs/crontab.txt", content="0 3 * * * /tmp/x\n")

    def test_timer_unit_and_other_files_are_not_judged(self):
        self.assertFilePasses("Write", file_path="/x/job.timer", content="[Timer]\nOnCalendar=daily\n")
        self.assertFilePasses("Write", file_path="/x/notes.txt", content="ExecStart=/tmp/x.sh\n")
        self.assertFilePasses("Read", file_path="/x/job.service")

    def test_unreadable_edit_passes(self):
        self.assertFilePasses("Edit", file_path=str(self.dir / "missing.service"), old_string="a", new_string="/tmp/x")


class CronAndAtFileTests(DurableCase):
    def test_comments_in_unit_and_cron_files_are_not_commands(self):
        self.assertFilePasses("Write", file_path="/x/job.service", content="[Service]\n# ExecStart=/tmp/x.sh\n")
        self.assertFilePasses("Write", file_path="/x/crontab", content="#0 3 * * * /tmp/x.sh\n")
        self.assertFilePasses("Write", file_path="/var/spool/cron/atjobs/a1", content="# /tmp/x.sh\n")

    def test_crontab_files(self):
        self.assertFileRefused("Write", file_path="/home/u/crontab", content="MAILTO=\n0 3 * * * /tmp/x.sh\n")
        self.assertFileRefused("Write", file_path="/var/spool/cron/crontabs/u", content="@daily /tmp/x.sh\n")
        self.assertFileRefused("Write", file_path="/x/mine.crontab", content="*/5 * * * * bash /tmp/x.sh\n")

    def test_system_crontab_has_a_user_field(self):
        self.assertFileRefused("Write", file_path="/etc/cron.d/job", content="0 3 * * * root /tmp/x.sh\n")
        self.assertFileRefused("Write", file_path="/etc/crontab", content="0 3 * * * root bash /tmp/x.sh\n")
        self.assertFilePasses("Write", file_path="/etc/cron.d/job", content="0 3 * * * root /usr/local/bin/x.sh\n")

    def test_crontab_with_durable_paths_and_comments(self):
        self.assertFilePasses("Write", file_path="/home/u/crontab",
                              content="# 0 3 * * * /tmp/old.sh\n0 3 * * * /home/u/bin/x.sh /tmp/data\n")

    def test_crontab_file_with_day_names(self):
        self.assertFileRefused("Write", file_path="/home/u/crontab", content="0 3 * * mon-fri /tmp/x\n")
        self.assertFileRefused("Write", file_path="/home/u/crontab", content="0 3 * jan,feb sun /tmp/x\n")

    def test_at_job_files(self):
        self.assertFileRefused("Write", file_path="/var/spool/cron/atjobs/a0001",
                               content="#!/bin/sh\ncd /home/u\nexport A=1\n/tmp/job.sh\n")
        self.assertFilePasses("Write", file_path="/var/spool/cron/atjobs/a0001",
                              content="#!/bin/sh\ncd /tmp\n/home/u/bin/job.sh\n")


class RegistryAndSafetyTests(DurableCase):
    def problems(self, entry):
        self.registry(entry)
        return guard_lessons.registry_problems(str(self.project))

    def test_valid_entry_has_no_problem(self):
        self.assertEqual(self.problems(ENTRY), [])
        self.assertEqual(self.problems({**ENTRY, "scratch": ["/var/work/tmp-*/**"]}), [])

    def test_bad_scratch_is_a_registry_problem(self):
        for scratch in ("/var/tmp", [], [""], [1], ["a", None], ["x"] * 51):
            self.assertTrue(self.problems({**ENTRY, "scratch": scratch}), scratch)

    def test_scratch_belongs_to_the_rule_only(self):
        self.assertTrue(self.problems({"rule": "help-probe", "scratch": ["a"], "min_version": "1.33.5"}))

    def test_off_until_an_entry_names_it(self):
        self.registry()
        self.assertPasses("systemd-run --on-active=1m /tmp/x.sh")
        self.assertFilePasses("Write", file_path="/x/job.service", content="[Service]\nExecStart=/tmp/x\n")

    def test_older_hook_skips_the_entry(self):
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 33, 4)):
            self.assertPasses("systemd-run --on-active=1m /tmp/x.sh")

    def test_disabled_entry(self):
        self.registry({**ENTRY, "enabled": False})
        self.assertPasses("systemd-run --on-active=1m /tmp/x.sh")

    def test_never_raises(self):
        import guard_durable_path
        for command, entry in ((None, ENTRY), (5, ENTRY), ("systemd-run --on-active=1m /tmp/x", None),
                               ("systemd-run --on-active=1m /tmp/x", "durable-path")):
            self.assertIsNone(guard_durable_path.problem(command, entry, guard_lessons.commands), (command, entry))
        bad_globs = guard_durable_path.problem("systemd-run --on-active=1m /tmp/x", {"scratch": [None, 3]},
                                               guard_lessons.commands)
        self.assertIn("/tmp/x", bad_globs)  # unusable globs are ignored, /tmp still counts
        for tool, tool_input in (("Write", None), ("Write", {"file_path": 5, "content": 3}),
                                 ("Edit", {"file_path": "/x/a.service"}), ("MultiEdit", {"file_path": "/x/a.service",
                                                                                      "edits": 3})):
            self.assertIsNone(guard_durable_path.file_problem(tool, tool_input, ENTRY), (tool, tool_input))

    def test_pre_filter_skips_commands_without_a_scheduler_before_parsing(self):
        import guard_durable_path
        parse = mock.Mock(return_value=[])
        self.assertIsNone(guard_durable_path.problem("bash /tmp/x.sh && ls /tmp", ENTRY, parse))
        parse.assert_not_called()

    def test_a_parser_that_raises_passes(self):
        import guard_durable_path
        self.assertIsNone(guard_durable_path.problem("systemd-run --on-active=1m /tmp/x", ENTRY,
                                                     mock.Mock(side_effect=RuntimeError)))


if __name__ == "__main__":
    unittest.main()
