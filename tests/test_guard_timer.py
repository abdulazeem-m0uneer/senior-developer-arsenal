"""timer-safety: a timer is never restarted to pause it, its OnCalendar= parses, and a oneshot unit has a start timeout."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))

import guard_lessons  # noqa: E402
import guard_timer  # noqa: E402

SCRIPT = HOOKS / "guard.py"
ENTRY = {"rule": "timer-safety", "lesson": "G051", "min_version": "1.33.0"}
FAKE_ANALYZE = """#!/bin/sh
echo "$@" >> "${0%/*}/calls.log"
rc=0
for value in "$@"; do
  case "$value" in
    slow*) exec /bin/sleep 5 ;;
    bad*) if [ "$LC_ALL" = C ]; then echo "Failed to parse calendar specification '$value': Invalid argument" >&2
          else echo "Kalenderangabe '$value' nicht lesbar" >&2; fi; rc=1 ;;
    quoted*) echo "Failed to parse calendar specification '$value': only quoted" >&2 ;;
  esac
done
exit $rc
"""
GOOD_TIMER = "[Unit]\nDescription=nightly\n\n[Timer]\nOnCalendar=good-daily\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n"
ONESHOT = "[Unit]\nDescription=job\n\n[Service]\nType=oneshot\nExecStart=/usr/bin/true\n"


class TimerCase(unittest.TestCase):
    """A project whose registry names timer-safety, a 1.33.0 hook, and a fake systemd-analyze on PATH."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.project = self.dir / "project"
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        (self.project / ".agents").mkdir(parents=True)
        analyze = self.bin / "systemd-analyze"
        analyze.write_text(FAKE_ANALYZE, encoding="utf-8")
        analyze.chmod(0o755)
        env = {"LESSONS_GUARDS_GLOBAL_FILE": str(self.dir / "home" / "lesson-guards.json"),
               "LESSONS_GUARD_HITS_FILE": str(self.dir / "home" / "hits.jsonl"), "PATH": str(self.bin)}
        for patch in (mock.patch.dict(os.environ, env), mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 33, 0))):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.registry(ENTRY)

    def registry(self, *guards):
        (self.project / ".agents" / "lesson-guards.json").write_text(json.dumps({"guards": list(guards)}),
                                                                     encoding="utf-8")

    def calls(self):
        log = self.bin / "calls.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


class BashTests(TimerCase):
    def judge(self, command):
        return guard_lessons.judge(command, str(self.project))

    def assertRefused(self, command):
        hit = self.judge(command)
        self.assertIsNotNone(hit, command)
        self.assertEqual((hit.lesson, hit.rule), ("G051", "timer-safety"), command)
        return hit

    def assertPasses(self, command):
        self.assertIsNone(self.judge(command), command)

    def test_restarting_a_timer_is_refused_with_the_fix(self):
        hit = self.assertRefused("systemctl --user restart backup.timer")
        self.assertIn("backup.timer", hit.reason)
        self.assertIn("missed run", hit.reason)
        self.assertIn("daemon-reload", hit.reason)
        self.assertIn("disable", hit.reason)
        self.assertIn("list-timers", hit.reason)

    def test_every_restart_verb_and_form_is_refused(self):
        for command in ("systemctl restart backup.timer", "sudo systemctl try-restart backup.timer",
                        "systemctl --user reload-or-restart a.service backup.timer",
                        "systemctl try-reload-or-restart backup.timer", "systemctl force-reload backup.timer",
                        "systemctl -H host --user restart backup.timer", "systemctl --no-block restart backup.timer",
                        "bash -c 'systemctl --user restart backup.timer'", "T=backup.timer; systemctl restart $T",
                        "/usr/bin/systemctl restart 'backup.timer'", "systemctl restart -- backup.timer",
                        "systemctl restart -- -x.timer"):
            self.assertRefused(command)

    def test_a_timer_restart_run_through_ssh_is_refused(self):
        for command in ("ssh host 'sudo systemctl restart backup.timer'",
                        "ssh -p 22 -t host systemctl --user restart backup.timer",
                        "ssh -p22 -i key -- admin@host 'systemctl stop backup.timer; systemctl start backup.timer'",
                        "ssh -J jump host \"bash -c 'systemctl restart backup.timer'\"",
                        "ssh a 'ssh b systemctl restart backup.timer'",
                        "ssh host -p 22 -t 'systemctl restart backup.timer'",
                        "ssh host -- systemctl restart backup.timer"):
            self.assertIn("backup.timer", self.assertRefused(command).reason, command)

    def test_an_ssh_call_that_restarts_no_timer_passes(self):
        for command in ("ssh host 'systemctl --user status backup.timer'", "ssh host", "ssh -F x.timer host uptime",
                        "ssh -l systemctl host restart.timer", "ssh host systemctl restart backup.service",
                        "ssh a 'systemctl stop backup.timer'; ssh b 'systemctl start backup.timer'"):
            self.assertPasses(command)

    def test_a_stop_and_a_start_on_the_same_host_in_two_ssh_calls_is_refused(self):
        for command in ("ssh a 'systemctl --user stop x.timer' && ssh a 'systemctl --user start x.timer'",
                        "ssh a 'systemctl stop x.timer'; ssh a 'systemctl start x.timer'",
                        "ssh a 'systemctl stop x.timer'; ssh a 'ssh b true'; ssh a 'systemctl start x.timer'"):
            self.assertIn("x.timer", self.assertRefused(command).reason, command)

    def test_a_stop_and_a_start_on_different_hosts_or_scopes_pass(self):
        for command in ("ssh a 'systemctl stop x.timer'; ssh b 'systemctl start x.timer'",
                        "ssh a 'systemctl --user stop x.timer'; ssh a 'systemctl start x.timer'",
                        "systemctl stop x.timer; ssh a 'systemctl start x.timer'",
                        "ssh a 'systemctl stop x.timer'; systemctl start x.timer"):
            self.assertPasses(command)

    def test_a_restart_in_a_for_loop_is_refused(self):
        for command in ('for t in a.timer b.timer; do systemctl --user restart "$t"; done',
                        "for t in a.service b.timer; do sudo systemctl restart ${t}; done",
                        "for u in a b; do systemctl restart $u.timer; done",
                        "for t in backup.timer; do systemctl stop $t; systemctl start $t; done"):
            self.assertRefused(command)

    def test_nested_loops_are_read_up_to_the_reading_limit(self):
        values = " ".join(f"v{n}" for n in range(20))
        found = guard_lessons.commands(f"for a in {values}; do for b in {values}; do systemctl restart $a$b; done; done")
        self.assertEqual(len(guard_timer.readings(found[2], {"a": values.split(), "b": values.split()})),
                         guard_timer.MAX_READINGS)

    def test_a_for_loop_over_other_units_passes(self):
        for command in ('for t in a.service b.service; do systemctl --user restart "$t"; done',
                        "for t in a.timer; do systemctl status $t; done",
                        "for t in a.timer; do echo $t; done; systemctl restart b.service"):
            self.assertPasses(command)

    def test_the_alias_verbs_and_a_capsule_value_are_read(self):
        for command in ("systemctl --user condrestart backup.timer", "systemctl reload-or-try-restart backup.timer",
                        "systemctl condreload backup.timer", "systemctl -C cap restart backup.timer",
                        "systemctl --capsule cap --user restart backup.timer",
                        "systemctl --user condstop backup.timer; systemctl --user start backup.timer"):
            self.assertRefused(command)

    def test_a_stop_then_start_of_the_same_timer_in_one_call_is_refused(self):
        for command in ("systemctl --user stop backup.timer; systemctl --user start backup.timer",
                        "systemctl --user stop backup.timer && sleep 1 && systemctl --user start backup.timer",
                        "systemctl stop a.timer backup.timer\nsystemctl start backup.timer",
                        "systemctl --user disable --now backup.timer; systemctl --user enable --now backup.timer",
                        "systemctl --user restart backup.timer; systemctl --user start backup.timer"):
            hit = self.assertRefused(command)
            self.assertIn("backup.timer", hit.reason)

    def test_a_stop_alone_a_start_alone_and_other_units_pass(self):
        for command in ("systemctl --user stop backup.timer", "systemctl --user start backup.timer",
                        "systemctl --user disable --now backup.timer", "systemctl --user enable --now backup.timer",
                        "systemctl --user restart backup.service", "systemctl --user daemon-reload",
                        "systemctl --user stop a.timer; systemctl --user start b.timer",
                        "systemctl --user stop backup.timer; systemctl start backup.timer",
                        "systemctl --user start backup.timer; systemctl --user stop backup.timer",
                        "systemctl --user disable backup.timer; systemctl --user enable backup.timer",
                        "systemctl --user stop backup.timer; systemctl --user enable backup.timer",
                        "systemctl --user disable backup.timer; systemctl --user start backup.timer",
                        "systemctl --user list-timers backup.timer", "systemctl -p restart show backup.timer",
                        "systemctl --user status backup.timer", "systemctl restart"):
            self.assertPasses(command)

    def test_text_that_only_mentions_the_command_passes(self):
        for command in ('echo "systemctl --user restart backup.timer"', "grep -n 'systemctl restart x.timer' notes.md",
                        "git commit -m 'never systemctl restart x.timer'"):
            self.assertPasses(command)

    def test_off_until_a_registry_entry_names_it(self):
        self.registry()
        self.assertPasses("systemctl --user restart backup.timer")


class FileCase(TimerCase):
    def judge(self, tool_name, tool_input):
        return guard_lessons.judge_outbound(tool_name, tool_input, str(self.project))

    def write(self, name, content):
        return self.judge("Write", {"file_path": str(self.project / name), "content": content})


class TimerFileTests(FileCase):
    def test_a_good_calendar_passes_with_one_analyzer_call(self):
        self.assertIsNone(self.write("backup.timer", GOOD_TIMER.replace("OnCalendar=good-daily",
                                                                        "OnCalendar=good-1\nOnCalendar = good-2")))
        self.assertEqual(self.calls(), ["calendar -- good-1 good-2"])

    def test_a_bad_calendar_is_refused_naming_the_value_and_the_check(self):
        hit = self.write("backup.timer", GOOD_TIMER.replace("good-daily", "bad *-*-* 25:00"))
        self.assertEqual((hit.lesson, hit.rule), ("G051", "timer-safety"))
        self.assertIn("OnCalendar=bad *-*-* 25:00", hit.reason)
        self.assertIn("systemd-analyze calendar", hit.reason)
        self.assertIn("list-timers", hit.reason)

    def test_only_timer_section_values_are_judged(self):
        content = ("# OnCalendar=bad-comment\n[Unit]\nOnCalendar=bad-unit\n[Timer]\nOnCalendar=\n"
                   "OnCalendar=good-%i\n; OnCalendar=bad-semicolon\nOnCalendar=good-1\n")
        self.assertIsNone(self.write("backup.timer", content))
        self.assertEqual(self.calls(), ["calendar -- good-1"])

    def test_a_comment_line_never_continues(self):
        hit = self.write("backup.timer", "[Timer]\n# a note ending in a backslash \\\nOnCalendar=bad-after\n")
        self.assertIn("OnCalendar=bad-after", hit.reason)
        hit = self.write("backup.timer", "[Timer]\n; a note \\\nOnCalendar=bad-semicolon\n")
        self.assertIn("OnCalendar=bad-semicolon", hit.reason)

    def test_a_comment_inside_a_continued_line_is_skipped(self):
        content = "[Timer]\nOnCalendar=good-1\\\n# bad note\n  ; bad too \\\n tail\n"
        self.assertIsNone(self.write("backup.timer", content))
        self.assertEqual(self.calls(), ["calendar -- good-1 tail"])

    def test_a_byte_order_mark_before_the_first_section_is_skipped(self):
        hit = self.write("backup.timer", "\ufeff[Timer]\nOnCalendar=bad-bom\n")
        self.assertIn("OnCalendar=bad-bom", hit.reason)

    def test_a_repeated_value_goes_to_the_analyzer_once(self):
        content = "[Timer]\n" + "OnCalendar=good-0\n" * (guard_timer.MAX_VALUES + 1) + "OnCalendar=bad-last\n"
        hit = self.write("backup.timer", content)
        self.assertEqual(self.calls(), ["calendar -- good-0 bad-last"])
        self.assertIn("OnCalendar=bad-last", hit.reason)

    def test_the_analyzer_runs_in_the_c_locale(self):
        with mock.patch.dict(os.environ, {"LC_ALL": "de_DE.UTF-8", "LANG": "de_DE.UTF-8"}):
            hit = self.write("backup.timer", GOOD_TIMER.replace("good-daily", "bad-daily"))
        self.assertIn("OnCalendar=bad-daily", hit.reason)

    def test_an_analyzer_exit_0_passes_even_when_it_quotes_a_failure(self):
        self.assertIsNone(self.write("backup.timer", GOOD_TIMER.replace("good-daily", "quoted-daily")))
        self.assertEqual(self.calls(), ["calendar -- quoted-daily"])

    def test_a_continued_line_is_judged_whole(self):
        hit = self.write("backup.timer", "[Timer]\nOnCalendar=bad-1\\\n tail\n")
        self.assertIn("OnCalendar=bad-1 tail", hit.reason)

    def test_a_missing_analyzer_or_a_timeout_passes(self):
        (self.bin / "systemd-analyze").unlink()
        self.assertIsNone(self.write("backup.timer", GOOD_TIMER.replace("good-daily", "bad")))
        (self.bin / "systemd-analyze").write_text(FAKE_ANALYZE, encoding="utf-8")
        (self.bin / "systemd-analyze").chmod(0o755)
        started = time.monotonic()
        with mock.patch.object(guard_timer, "TIMEOUT_SECONDS", 0.3):
            self.assertIsNone(self.write("backup.timer", GOOD_TIMER.replace("good-daily", "slow")))
        self.assertLess(time.monotonic() - started, 2.0)

    def test_an_analyzer_failure_naming_no_value_passes(self):
        (self.bin / "systemd-analyze").write_text("#!/bin/sh\necho 'Failed to connect' >&2\nexit 1\n",
                                                  encoding="utf-8")
        self.assertIsNone(self.write("backup.timer", GOOD_TIMER))

    def test_the_analyzer_gets_at_most_the_value_limit(self):
        content = "[Timer]\n" + "".join(f"OnCalendar=good-{n}\n" for n in range(guard_timer.MAX_VALUES + 5))
        self.assertIsNone(self.write("backup.timer", content))
        self.assertEqual(len(self.calls()[0].split()) - 2, guard_timer.MAX_VALUES)

    def test_other_files_and_tools_are_not_judged(self):
        bad = GOOD_TIMER.replace("good-daily", "bad")
        self.assertIsNone(self.write("notes.md", bad))
        self.assertIsNone(self.write("backup.timer.bak", bad))
        self.assertIsNone(self.judge("NotebookEdit", {"notebook_path": str(self.project / "a.timer"),
                                                      "new_source": bad}))
        self.assertIsNone(self.judge("Write", {"file_path": None, "content": bad}))
        self.assertIsNone(self.judge("Write", {"file_path": str(self.project / "a.timer"), "content": None}))
        self.assertEqual(self.calls(), [])

    @unittest.skipUnless(shutil.which("systemd-analyze", path="/usr/bin:/bin"), "systemd-analyze is not installed")
    def test_the_real_analyzer_refuses_an_impossible_hour(self):
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}):
            self.assertIsNone(self.write("ok.timer", "[Timer]\nOnCalendar=Mon *-*-* 03:00\nOnCalendar=daily\n"))
            hit = self.write("bad.timer", "[Timer]\nOnCalendar=daily\nOnCalendar=Mon *-*-* 25:00\n")
        self.assertIn("OnCalendar=Mon *-*-* 25:00", hit.reason)
        self.assertNotIn("OnCalendar=daily", hit.reason)


class ServiceFileTests(FileCase):
    def test_a_oneshot_without_a_start_timeout_is_refused_with_the_fix(self):
        hit = self.write("job.service", ONESHOT)
        self.assertEqual(hit.rule, "timer-safety")
        self.assertIn("Type=oneshot", hit.reason)
        self.assertIn("TimeoutStartSec=", hit.reason)
        self.assertIn("RuntimeMaxSec", hit.reason)

    def test_runtime_max_or_an_unbounded_timeout_does_not_bound_it(self):
        for extra in ("RuntimeMaxSec=10min", "TimeoutStartSec=infinity", "TimeoutStartSec=0",
                      "TimeoutStartSec=0s", "TimeoutStartSec=", "TimeoutStartSec=5min\nTimeoutSec=infinity",
                      "TimeoutStopSec=5min"):
            self.assertIsNotNone(self.write("job.service", ONESHOT + extra + "\n"), extra)

    def test_a_start_timeout_or_another_type_passes(self):
        for content in (ONESHOT + "TimeoutStartSec=15min\n", ONESHOT + "TimeoutSec=90\n",
                        ONESHOT + "TimeoutSec=infinity\nTimeoutStartSec=2h\n",
                        ONESHOT.replace("oneshot", "simple"), ONESHOT + "Type=exec\n",
                        "[Unit]\nType=oneshot\n[Service]\nExecStart=/usr/bin/true\n"):
            self.assertIsNone(self.write("job.service", content), content)
        self.assertIsNone(self.write("job@.service", ONESHOT + "TimeoutStartSec=1min\n"))
        self.assertIsNotNone(self.write("job@.service", ONESHOT))

    def test_a_byte_order_mark_before_the_first_section_is_skipped(self):
        self.assertIsNotNone(self.write("job.service", "\ufeff" + ONESHOT.split("\n\n", 1)[1]))

    def test_a_drop_in_folder_may_hold_the_timeout(self):
        (self.project / "job.service.d").mkdir()
        self.assertIsNone(self.write("job.service", ONESHOT))


class EditTests(FileCase):
    def setUp(self):
        super().setUp()
        self.unit = self.project / "job.service"
        self.unit.write_text(ONESHOT + "TimeoutStartSec=15min\n", encoding="utf-8")

    def edit(self, old, new, **extra):
        return self.judge("Edit", {"file_path": str(self.unit), "old_string": old, "new_string": new, **extra})

    def test_the_edited_file_is_judged(self):
        self.assertIsNotNone(self.edit("TimeoutStartSec=15min\n", ""))
        self.assertIsNone(self.edit("ExecStart=/usr/bin/true", "ExecStart=/usr/bin/false"))

    def test_replace_all_and_multi_edit(self):
        self.unit.write_text(ONESHOT.replace("true", "true\nTimeoutStartSec=1") + "TimeoutStartSec=1\n",
                             encoding="utf-8")
        self.assertIsNone(self.edit("TimeoutStartSec=1\n", "TimeoutStartSec=2\n"))
        self.assertIsNotNone(self.edit("TimeoutStartSec=1\n", "", replace_all=True))
        edits = [{"old_string": "Type=oneshot", "new_string": "Type=simple"},
                 {"old_string": "Type=simple", "new_string": "Type=oneshot"},
                 {"old_string": "TimeoutStartSec=1\n", "new_string": "", "replace_all": True}]
        self.assertIsNotNone(self.judge("MultiEdit", {"file_path": str(self.unit), "edits": edits}))
        self.assertIsNone(self.judge("MultiEdit", {"file_path": str(self.unit), "edits": edits[:2]}))

    def test_an_edit_on_a_timer_judges_the_resulting_values(self):
        timer = self.project / "backup.timer"
        timer.write_text(GOOD_TIMER, encoding="utf-8")
        hit = self.judge("Edit", {"file_path": str(timer), "old_string": "good-daily", "new_string": "bad-daily"})
        self.assertIn("OnCalendar=bad-daily", hit.reason)

    def test_an_edit_the_tool_itself_would_refuse_passes(self):
        self.assertIsNone(self.edit("not in the file", ""))
        self.unit.unlink()
        self.assertIsNone(self.edit("TimeoutStartSec=15min\n", ONESHOT))
        self.assertIsNotNone(self.edit("", ONESHOT))  # an empty old_string on a missing file creates it
        self.unit.mkdir()
        self.assertIsNone(self.edit("x", "y"))
        self.unit.rmdir()
        os.mkfifo(self.unit)  # opening it would wait for a writer
        started = time.monotonic()
        self.assertIsNone(self.edit("x", "y"))
        self.assertLess(time.monotonic() - started, 1.0)
        for broken in ({"edits": None}, {"edits": [None]}, {"edits": [{"old_string": 1, "new_string": "x"}]}):
            self.assertIsNone(self.judge("MultiEdit", {"file_path": str(self.unit), **broken}), broken)

    def test_an_empty_old_string_on_an_existing_file_passes(self):
        self.unit.write_text(ONESHOT, encoding="utf-8")  # the tool refuses it: the file exists
        self.assertIsNone(self.edit("", "# header\n"))

    def test_a_file_that_is_not_regular_is_not_read(self):
        self.unit.unlink()
        self.unit.symlink_to("/dev/zero")  # reads as endless NULs and reports size 0
        self.assertIsNone(self.edit("\0", ONESHOT))

    def test_a_large_file_is_not_read(self):
        self.unit.write_text(ONESHOT + "#" * guard_timer.MAX_FILE_BYTES + "\n", encoding="utf-8")
        self.assertIsNone(self.edit("ExecStart=/usr/bin/true", "ExecStart=/usr/bin/false"))


class FailOpenTests(TimerCase):
    def test_an_error_in_the_rule_passes(self):
        with mock.patch.object(guard_timer, "units", side_effect=RuntimeError("boom")):
            self.assertIsNone(guard_lessons.judge("systemctl restart a.timer", str(self.project)))
        with mock.patch.object(guard_timer, "sections", side_effect=RuntimeError("boom")):
            self.assertIsNone(guard_lessons.judge_outbound(
                "Write", {"file_path": str(self.project / "job.service"), "content": ONESHOT}, str(self.project)))


class RegistryTests(TimerCase):
    def test_enabled_false_and_a_reason_of_its_own(self):
        self.registry({**ENTRY, "enabled": False})
        self.assertIsNone(guard_lessons.judge("systemctl restart a.timer", str(self.project)))
        self.registry({**ENTRY, "reason": "Edit the unit instead."})
        self.assertEqual(guard_lessons.judge("systemctl restart a.timer", str(self.project)).reason,
                         "Edit the unit instead.")
        write = {"file_path": str(self.project / "job.service"), "content": ONESHOT}
        self.assertEqual(guard_lessons.judge_outbound("Write", write, str(self.project)).reason,
                         "Edit the unit instead.")

    def test_min_version_1_33_0_skips_on_older_hooks(self):
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 32, 0)):
            self.assertIsNone(guard_lessons.judge("systemctl restart a.timer", str(self.project)))
            self.assertEqual(guard_lessons.registry_problems(str(self.project)), [])
        self.assertIsNotNone(guard_lessons.judge("systemctl restart a.timer", str(self.project)))

    def test_bad_registry_values_are_skipped(self):
        for bad in ({"programs": ["send.sh"]}, {"shell": "bash"}, {"lesson": "nope"}):
            self.registry({**ENTRY, **bad})
            self.assertIsNone(guard_lessons.judge("systemctl restart a.timer", str(self.project)), bad)
            self.assertTrue(guard_lessons.registry_problems(str(self.project)), bad)


class HookTests(TimerCase):
    """guard.py pre denies a Bash call and a Write under the rule."""

    def pre(self, tool_name, tool_input):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input,
                   "cwd": str(self.project), "permission_mode": "default"}
        base = {k: v for k, v in os.environ.items()
                if k not in ("ARSENAL_GUARD", "ARSENAL_LESSON_GUARDS", "ARSENAL_GUARD_DESTRUCTIVE",
                             "ARSENAL_RUN_LIMITS", "CLAUDE_PROJECT_DIR", "ARSENAL_PROFILE", "ARSENAL_GUARD_SCOPE")}
        base["PATH"] = f"{self.bin}:/usr/bin:/bin"
        result = subprocess.run([sys.executable, str(SCRIPT), "pre"], cwd=self.project, input=json.dumps(payload),
                                capture_output=True, text=True, env=base)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None

    def test_the_hook_denies_a_timer_restart_and_a_bad_unit_file(self):
        self.registry({"rule": "timer-safety", "lesson": "G051"})  # the installed hook may be older than 1.33.0
        out = self.pre("Bash", {"command": "systemctl --user restart backup.timer"})
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("G051 (timer-safety)", out["permissionDecisionReason"])
        out = self.pre("Write", {"file_path": str(self.project / "job.service"), "content": ONESHOT})
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIsNone(self.pre("Write", {"file_path": str(self.project / "job.service"),
                                             "content": ONESHOT + "TimeoutStartSec=5min\n"}))


if __name__ == "__main__":
    unittest.main()
