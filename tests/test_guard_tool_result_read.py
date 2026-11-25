"""Tests for the opt-in tool-result-read lesson guard (hooks/guard_tool_result_read.py, wired in guard_lessons)."""
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
import guard_tool_result_read  # noqa: E402

ENTRY = {"rule": "tool-result-read", "lesson": "L113", "min_version": "1.33.5"}
HOME = "/home/u"
PROJECTS = HOME + "/.claude/projects"
PERSISTED = PROJECTS + "/-work-app/8b1f/tool-results/toolu_01.txt"


class ToolResultCase(unittest.TestCase):
    """A project whose registry names tool-result-read, a fake home and a 1.33.5 hook."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.project = self.dir / "project"
        (self.project / ".agents").mkdir(parents=True)
        env = {"LESSONS_GUARDS_GLOBAL_FILE": str(self.dir / "home" / "lesson-guards.json"),
               "LESSONS_GUARD_HITS_FILE": str(self.dir / "home" / "hits.jsonl"), "HOME": HOME}
        for patch in (mock.patch.dict(os.environ, env), mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 33, 5))):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.registry(ENTRY)

    def registry(self, *guards):
        (self.project / ".agents" / "lesson-guards.json").write_text(json.dumps({"guards": list(guards)}),
                                                                     encoding="utf-8")

    def judge(self, tool="Read", **tool_input):
        return guard_lessons.judge_outbound(tool, tool_input, str(self.project))

    def assertRefused(self, path, tool="Read"):
        hit = self.judge(tool, file_path=path)
        self.assertIsNotNone(hit, path)
        self.assertEqual((hit.rule, hit.lesson), ("tool-result-read", "L113"), path)
        return hit

    def assertPasses(self, path, tool="Read"):
        self.assertIsNone(self.judge(tool, file_path=path), path)


class RefuseTests(ToolResultCase):
    def test_persisted_result_under_projects(self):
        self.assertRefused(PERSISTED)

    def test_any_project_and_session(self):
        self.assertRefused(PROJECTS + "/other/zz/tool-results/x.json")

    def test_tilde_path_is_expanded(self):
        self.assertRefused("~/.claude/projects/p/s/tool-results/x.txt")

    def test_dot_dot_is_resolved(self):
        self.assertRefused(PROJECTS + "/p/s/memory/../tool-results/x.txt")

    def test_dot_dot_out_of_the_projects_folder(self):
        self.assertRefused(HOME + "/x/../.claude/projects/p/s/tool-results/x.txt")

    def test_extra_path_glob_with_a_slash_is_a_suffix_match(self):
        self.registry({**ENTRY, "paths": ["cache/persisted-output/*"]})
        self.assertRefused("/var/cache/persisted-output/abc.txt")

    def test_extra_path_glob_without_a_slash_names_the_basename(self):
        self.registry({**ENTRY, "paths": ["persisted-*.txt"]})
        self.assertRefused("/anywhere/persisted-1.txt")

    def test_tilde_and_home_globs_are_expanded(self):
        for pattern in ("~/.cache/a/*", "$HOME/.cache/a/*", "${HOME}/.cache/a/*"):
            self.registry({**ENTRY, "paths": [pattern]})
            self.assertRefused(HOME + "/.cache/a/b.json")

    def test_leading_double_slash(self):
        self.assertRefused("/" + PERSISTED)

    def test_relative_path_is_resolved_against_the_working_directory(self):
        with mock.patch("os.getcwd", return_value=HOME):
            self.assertRefused(".claude/projects/p/s/tool-results/x.txt")

    def test_bounded_read_is_refused_too(self):
        hit = self.judge(file_path=PERSISTED, offset=1, limit=50)
        self.assertEqual(hit.rule, "tool-result-read")

    def test_reason_says_to_narrow_the_source(self):
        reason = self.assertRefused(PERSISTED).reason
        for word in ("filter", "extraction prompt", "smaller query"):
            self.assertIn(word, reason)

    def test_entry_reason_replaces_the_text(self):
        self.registry({**ENTRY, "reason": "use the filter"})
        self.assertEqual(self.assertRefused(PERSISTED).reason, "use the filter")


class PassTests(ToolResultCase):
    def test_other_files_under_projects(self):
        self.assertPasses(PROJECTS + "/-work-app/memory/MEMORY.md")
        self.assertPasses(PROJECTS + "/-work-app/8b1f.jsonl")

    def test_tool_results_outside_projects(self):
        self.assertPasses("/home/u/work/tool-results/x.txt")
        self.assertPasses(HOME + "/.claude/tool-results/x.txt")

    def test_a_file_named_tool_results_is_not_a_directory(self):
        self.assertPasses(PROJECTS + "/p/s/tool-results")

    def test_dot_dot_leaves_the_results_directory(self):
        self.assertPasses(PROJECTS + "/p/s/tool-results/../memory/MEMORY.md")

    def test_similar_directory_names(self):
        self.assertPasses(PROJECTS + "/p/s/tool-results-old/x.txt")
        self.assertPasses(PROJECTS + "/p/s/my-tool-results/x.txt")

    def test_tool_results_is_only_the_session_subfolder(self):
        self.assertPasses(PROJECTS + "/tool-results/notes.md")
        self.assertPasses(PROJECTS + "/x/s/memory/tool-results/n.md")

    def test_other_users_home(self):
        self.assertPasses("/home/v/.claude/projects/p/s/tool-results/x.txt")

    def test_other_tools(self):
        for tool in ("Write", "Edit", "Grep", "Bash"):
            self.assertPasses(PERSISTED, tool)

    def test_extra_globs_do_not_match_other_files(self):
        self.registry({**ENTRY, "paths": ["cache/persisted-output/*"]})
        self.assertPasses("/var/cache/other/abc.txt")

    def test_rule_off_without_an_entry(self):
        self.registry()
        self.assertPasses(PERSISTED)

    def test_min_version_above_the_hook_keeps_it_off(self):
        self.registry({**ENTRY, "min_version": "1.33.6"})
        self.assertPasses(PERSISTED)

    def test_disabled_entry(self):
        self.registry({**ENTRY, "enabled": False})
        self.assertPasses(PERSISTED)


class RegistryAndRobustnessTests(ToolResultCase):
    def problems(self, entry):
        self.registry(entry)
        return guard_lessons.registry_problems(str(self.project))

    def test_valid_entries(self):
        self.assertEqual(self.problems(ENTRY), [])
        self.assertEqual(self.problems({**ENTRY, "paths": ["a/*"]}), [])

    def test_bad_paths(self):
        for paths in ("a", [], [""], [1]):
            self.assertTrue(self.problems({**ENTRY, "paths": paths}), paths)

    def test_never_raises(self):
        for tool_input in (None, 5, {}, {"file_path": None}, {"file_path": 7}, {"file_path": ""},
                           {"file_path": "x\0y"}):
            self.assertIsNone(guard_tool_result_read.problem("Read", tool_input, ENTRY), tool_input)
        self.assertIsNone(guard_tool_result_read.problem(None, {"file_path": PERSISTED}, ENTRY))
        self.assertIsNone(guard_tool_result_read.problem("Read", {"file_path": "/x/y.txt"}, {"paths": 5}))
        self.assertIsNotNone(guard_tool_result_read.problem("Read", {"file_path": PERSISTED}, {"paths": 5}))
        self.assertIsNotNone(guard_tool_result_read.problem("Read", {"file_path": PERSISTED}, None))


if __name__ == "__main__":
    unittest.main()
