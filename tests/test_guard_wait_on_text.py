"""Tests for the opt-in wait-on-text lesson guard (hooks/guard_wait_on_text.py, wired in guard_lessons)."""
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
import guard_wait_on_text  # noqa: E402

ENTRY = {"rule": "wait-on-text", "lesson": "L129", "paths": [".agents/bus/inbox-*.md"], "min_version": "1.33.5"}


class WaitCase(unittest.TestCase):
    """A project whose registry names wait-on-text for the inbox files, and a 1.33.5 hook."""

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

    def assertRefused(self, command):
        hit = self.judge(command)
        self.assertIsNotNone(hit, command)
        self.assertEqual((hit.rule, hit.lesson), ("wait-on-text", "L129"), command)
        return hit

    def assertPasses(self, command):
        self.assertIsNone(self.judge(command), command)


class RefusalTests(WaitCase):
    def test_until_loop_on_the_phrase_in_one_inbox(self):
        self.assertRefused('until grep -q "Released:" .agents/bus/inbox-pm.md; do sleep 5; done')

    def test_while_loop_on_the_phrase_in_a_glob_of_inboxes(self):
        self.assertRefused('while ! grep -q "MERGED #741" .agents/bus/inbox-*.md; do sleep 30; done')

    def test_every_reader_program(self):
        for reader in ("grep -q X", "rg -q X", "awk '/X/' ", "sed -n '/X/p'", "tail -n 5", "cat"):
            self.assertRefused(f"while ! {reader} .agents/bus/inbox-pm.md; do sleep 5; done")

    def test_cat_piped_into_grep(self):
        self.assertRefused("until cat .agents/bus/inbox-pm.md | grep -q Released:; do sleep 5; done")

    def test_tail_piped_into_grep(self):
        self.assertRefused("while ! tail -n 20 .agents/bus/inbox-pm.md | grep -q Released:; do sleep 5; done")

    def test_path_suffix_match_on_an_absolute_or_relative_spelling(self):
        for path in ("/work/x/.agents/bus/inbox-pm.md", "./.agents/bus/inbox-pm.md", "$ROOT/.agents/bus/inbox-pm.md"):
            self.assertRefused(f"until grep -q X {path}; do sleep 5; done")

    def test_pattern_without_a_directory_matches_the_basename_anywhere(self):
        self.registry({**ENTRY, "paths": ["inbox-*.md"]})
        self.assertRefused("until grep -q X /any/where/inbox-pm.md; do sleep 5; done")

    def test_pattern_spelled_with_a_leading_dot_slash(self):
        self.registry({**ENTRY, "paths": ["./.agents/bus/inbox-*.md"]})
        self.assertRefused("until grep -q X .agents/bus/inbox-pm.md; do sleep 5; done")

    def test_second_path_of_the_list(self):
        self.registry({**ENTRY, "paths": ["notes.txt", ".agents/bus/inbox-*.md"]})
        self.assertRefused("until grep -q X notes.txt; do sleep 5; done")

    def test_condition_with_another_command_before_the_read(self):
        self.assertRefused("while [ -f lock ] && grep -q X .agents/bus/inbox-pm.md; do sleep 5; done")

    def test_loop_inside_bash_c_and_after_other_commands(self):
        self.assertRefused("echo go; bash -c 'until grep -q X .agents/bus/inbox-pm.md; do sleep 5; done'")

    def test_default_reason_names_the_authoritative_state(self):
        reason = self.assertRefused("until grep -q X .agents/bus/inbox-pm.md; do sleep 5; done").reason
        self.assertIn("authoritative state", reason)
        self.assertIn("gh pr view N --json state", reason)

    def test_entry_reason_replaces_the_default(self):
        self.registry({**ENTRY, "reason": "Wait on the release log."})
        hit = self.assertRefused("until grep -q X .agents/bus/inbox-pm.md; do sleep 5; done")
        self.assertEqual(hit.reason, "Wait on the release log.")


class SubstitutionAndDirectoryTests(WaitCase):
    def test_command_substitution_in_the_condition(self):
        self.assertRefused('until [ "$(grep -c Released: .agents/bus/inbox-pm.md)" -gt 0 ]; do sleep 1; done')
        self.assertRefused('until test -n "`grep Released: .agents/bus/inbox-pm.md`"; do sleep 1; done')

    def test_substitution_that_reads_other_files_passes(self):
        self.assertPasses('until [ "$(grep -c X build.log)" -gt 0 ]; do sleep 1; done')

    def test_wildcard_argument_that_expands_to_the_inboxes(self):
        self.assertRefused("while ! grep -q X .agents/bus/*; do sleep 1; done")
        self.assertPasses("while ! grep -q X other/*; do sleep 1; done")

    def test_recursive_search_of_the_directory(self):
        for search in ("grep -q X -r .agents/bus", "grep -qR X .agents/bus/", "rg X .agents/bus",
                       "grep -q X --include=inbox-pm.md -r .agents/bus", "rg X .agents/bus -g 'inbox-*.md'"):
            self.assertRefused(f"while ! {search}; do sleep 1; done")

    def test_recursive_search_filtered_to_other_files_passes(self):
        self.assertPasses("while ! rg X .agents/bus -g 'outbox-*.md'; do sleep 1; done")
        self.assertPasses("while ! grep -q X --include=*.log -r .agents/bus; do sleep 1; done")

    def test_directory_without_a_recursive_search_passes(self):
        self.assertPasses("while ! grep -q X .agents/bus; do sleep 1; done")

    def test_git_grep(self):
        self.assertRefused("while ! git grep -q X .agents/bus/inbox-pm.md; do sleep 1; done")

    def test_search_pattern_that_spells_an_inbox_path_is_not_a_file(self):
        self.assertPasses("while ! grep -q '.agents/bus/inbox-pm.md' deploy.log; do sleep 1; done")
        self.assertPasses("while ! awk '/inbox-pm.md/' deploy.log; do sleep 1; done")
        self.assertRefused("while ! grep -q -e X .agents/bus/inbox-pm.md; do sleep 1; done")

    def test_relative_name_after_cd_needs_the_basename_glob(self):
        command = "cd .agents/bus && until grep -q X inbox-pm.md; do sleep 1; done"
        self.assertPasses(command)
        self.registry({**ENTRY, "paths": ["inbox-*.md"]})
        self.assertRefused(command)


class PassTests(WaitCase):
    def test_grep_of_the_files_outside_a_loop(self):
        for command in ('grep -q "Released:" .agents/bus/inbox-pm.md', "tail -n 5 .agents/bus/inbox-pm.md",
                        "cat .agents/bus/inbox-pm.md | grep X && echo yes", "echo x; grep X .agents/bus/inbox-*.md"):
            self.assertPasses(command)

    def test_loop_whose_condition_greps_other_files(self):
        self.assertPasses("until grep -q X build.log; do sleep 5; done")
        self.assertPasses("while ! grep -q X .agents/bus/outbox-pm.md; do sleep 5; done")
        self.assertPasses("until grep -q X .agents/bus/inbox-pm.md.bak; do sleep 5; done")

    def test_pattern_with_a_directory_does_not_match_another_directory(self):
        self.assertPasses("until grep -q X other/inbox-pm.md; do sleep 5; done")

    def test_loop_body_that_greps_the_files(self):
        self.assertPasses("while sleep 5; do grep -q X .agents/bus/inbox-pm.md && break; done")
        self.assertPasses("until gh pr view 5 --json state; do grep X .agents/bus/inbox-pm.md; sleep 5; done")

    def test_loop_on_authoritative_state(self):
        self.assertPasses('until [ "$(gh pr view 5 --json state -q .state)" = MERGED ]; do sleep 30; done')

    def test_condition_that_names_the_file_without_reading_it(self):
        self.assertPasses("while [ ! -s .agents/bus/inbox-pm.md ]; do sleep 5; done")
        self.assertPasses("until echo .agents/bus/inbox-pm.md; do sleep 5; done")

    def test_no_paths_judges_nothing(self):
        self.registry({"rule": "wait-on-text", "lesson": "L129", "min_version": "1.33.5"})
        self.assertPasses("until grep -q X .agents/bus/inbox-pm.md; do sleep 5; done")

    def test_off_until_an_entry_names_it(self):
        self.registry()
        self.assertPasses("until grep -q X .agents/bus/inbox-pm.md; do sleep 5; done")

    def test_older_hook_skips_the_entry(self):
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 33, 4)):
            self.assertPasses("until grep -q X .agents/bus/inbox-pm.md; do sleep 5; done")

    def test_disabled_entry(self):
        self.registry({**ENTRY, "enabled": False})
        self.assertPasses("until grep -q X .agents/bus/inbox-pm.md; do sleep 5; done")


class RegistryAndSafetyTests(WaitCase):
    def problems(self, entry):
        self.registry(entry)
        return guard_lessons.registry_problems(str(self.project))

    def test_valid_entry_has_no_problem(self):
        self.assertEqual(self.problems(ENTRY), [])

    def test_bad_paths_are_registry_problems(self):
        for paths in ("inbox-*.md", [], [""], [1], ["a", None]):
            self.assertTrue(self.problems({**ENTRY, "paths": paths}), paths)

    def test_paths_belong_to_the_rule_only(self):
        self.assertTrue(self.problems({"rule": "help-probe", "paths": ["a"], "min_version": "1.33.5"}))

    def test_problem_never_raises(self):
        for command, entry in ((None, ENTRY), (5, ENTRY), ("until grep X a; do :; done", None),
                               ("until grep X a; do :; done", {"paths": 5}), ("until grep X a; do :; done", {}),
                               ("until grep X a; do :; done", {"paths": [None, 3]})):
            self.assertIsNone(guard_wait_on_text.problem(command, entry), (command, entry))

    def test_pre_filter_skips_commands_without_a_loop_before_parsing(self):
        parse = mock.Mock(return_value=[])
        self.assertIsNone(guard_wait_on_text.problem("grep X .agents/bus/inbox-pm.md", ENTRY, parse))
        parse.assert_not_called()

    def test_a_string_of_paths_is_not_read_as_a_list_of_characters(self):
        loop = "until grep -q X a*b; do sleep 5; done"
        self.assertIsNone(guard_wait_on_text.problem(loop, {"paths": "*"}, guard_lessons.commands))
        self.assertIsNotNone(guard_wait_on_text.problem(loop, {"paths": ["*"]}, guard_lessons.commands))

    def test_rule_is_not_active_without_an_entry(self):
        self.registry()
        self.assertNotIn("wait-on-text", [name for name, _, _ in guard_lessons.rules(str(self.project))])

    def test_error_while_judging_passes(self):
        with mock.patch.object(guard_wait_on_text, "reads_in_condition", side_effect=RuntimeError("boom")):
            self.assertIsNone(guard_wait_on_text.problem("until grep X a; do :; done", ENTRY))


if __name__ == "__main__":
    unittest.main()
