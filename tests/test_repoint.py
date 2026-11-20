"""Unit tests for scripts/repoint.py (`arsenal repoint`) and its doctor / guard_registry adjustments, against a fake
home directory; the real ~/.claude is never touched."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "lessons-learned" / "scripts"))
import doctor  # noqa: E402
import guard_registry  # noqa: E402
import repoint  # noqa: E402

CACHE = Path(".claude/plugins/cache/senior-developer-arsenal/arsenal")


def hooks(*scripts):
    return {"hooks": {"PreToolUse": [{"hooks": [
        {"type": "command", "command": f'python3 "${{CLAUDE_PLUGIN_ROOT}}/hooks/{name}" --x'} for name in scripts]}]}}


class RepointCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(os.path.realpath(self.tmp.name))
        self.cache = self.home / CACHE
        self.cache.mkdir(parents=True)
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("ARSENAL_CACHE", None)
        os.environ.pop("ARSENAL_INSTALLED_PLUGINS", None)
        self.lines = []

    def version(self, name, scripts=("guard.py",)):
        folder = self.cache / name
        (folder / "hooks").mkdir(parents=True)
        (folder / "hooks" / "hooks.json").write_text(json.dumps(hooks(*scripts)))
        for script in scripts:
            (folder / "hooks" / script).write_text(f"# {name}\n")
        return folder

    def install(self, *names):
        path = self.home / ".claude/plugins/installed_plugins.json"
        entries = [{"scope": "user", "installPath": str(self.cache / name)} for name in names]
        path.write_text(json.dumps({"version": 2, "plugins": {doctor.PLUGIN: entries}}))

    def run_repoint(self, **kwargs):
        self.lines = []
        return repoint.run(self.home, out=self.lines.append, **kwargs)

    def text(self):
        return "\n".join(self.lines)

    def backups(self, name):
        return sorted(p.name for p in self.cache.glob(f".{name}.repointed-*"))


class RepointTests(RepointCase):
    def test_older_versions_become_relative_links_to_the_target_with_a_backup(self):
        self.version("1.0.0")
        self.version("1.1.0")
        self.version("1.2.0")
        self.install("1.2.0")
        self.assertEqual(self.run_repoint(), 0)
        for old in ("1.0.0", "1.1.0"):
            self.assertTrue((self.cache / old).is_symlink())
            self.assertEqual(os.readlink(self.cache / old), "1.2.0")
            self.assertEqual((self.cache / old / "hooks" / "guard.py").read_text(), "# 1.2.0\n")
            self.assertEqual(len(self.backups(old)), 1)
            self.assertEqual((self.cache / self.backups(old)[0] / "hooks" / "guard.py").read_text(), f"# {old}\n")
        self.assertFalse((self.cache / "1.2.0").is_symlink())
        self.assertIn("1.0.0: repointed to 1.2.0", self.text())
        self.assertEqual([p.name for p in self.cache.iterdir() if p.name.startswith(".") and "link" in p.name], [])

    def test_limits_are_printed_every_run(self):
        self.version("1.2.0")
        self.install("1.2.0")
        self.assertEqual(self.run_repoint(), 0)
        self.assertIn("nothing to do", self.text())
        self.assertIn("new skill is not listed until restart", self.text())
        self.assertIn("next hook call runs the new code", self.text())

    def test_target_is_the_newest_referenced_not_the_newest_cached(self):
        self.version("1.0.0")
        self.version("1.1.0")
        self.version("1.3.0")  # cached, no install references it
        self.install("1.1.0")
        self.assertEqual(self.run_repoint(), 0)
        self.assertEqual(os.readlink(self.cache / "1.0.0"), "1.1.0")
        self.assertFalse((self.cache / "1.3.0").is_symlink())
        self.assertEqual(self.backups("1.3.0"), [])

    def test_a_referenced_version_missing_from_the_cache_is_not_a_target(self):
        self.version("1.0.0")
        self.install("1.0.0", "1.5.0")
        self.assertEqual(self.run_repoint(), 0)
        self.assertEqual(self.backups("1.0.0"), [])

    def test_version_with_a_script_the_target_lacks_is_skipped_by_name(self):
        self.version("1.0.0", scripts=("guard.py", "old_only.py"))
        self.version("1.1.0", scripts=("guard.py",))
        self.version("1.2.0")
        self.install("1.2.0")
        self.assertEqual(self.run_repoint(), 1)
        self.assertFalse((self.cache / "1.0.0").is_symlink())
        self.assertIn("1.0.0: skipped: its hooks run hooks/old_only.py, missing in 1.2.0", self.text())
        self.assertTrue((self.cache / "1.1.0").is_symlink())  # the others are still done

    def test_unreadable_hooks_json_skips(self):
        folder = self.version("1.0.0")
        (folder / "hooks" / "hooks.json").write_text("{bad")
        self.version("1.2.0")
        self.install("1.2.0")
        self.assertEqual(self.run_repoint(), 1)
        self.assertIn("1.0.0: skipped: cannot read", self.text())
        self.assertFalse((self.cache / "1.0.0").is_symlink())

    def test_already_pointing_is_reported_and_unchanged(self):
        self.version("1.0.0")
        self.version("1.2.0")
        self.install("1.2.0")
        self.run_repoint()
        self.assertEqual(self.run_repoint(), 0)
        self.assertIn("1.0.0: already points to 1.2.0", self.text())
        self.assertEqual(len(self.backups("1.0.0")), 1)

    def test_a_link_to_an_older_target_is_repointed_atomically(self):
        self.version("1.0.0")
        self.version("1.1.0")
        self.version("1.2.0")
        self.install("1.1.0")
        self.run_repoint()
        self.assertEqual(os.readlink(self.cache / "1.0.0"), "1.1.0")
        self.install("1.1.0", "1.2.0")
        self.assertEqual(self.run_repoint(), 0)
        self.assertEqual(os.readlink(self.cache / "1.0.0"), "1.2.0")
        self.assertEqual(os.readlink(self.cache / "1.1.0"), "1.2.0")
        self.assertIn("1.0.0: repointed to 1.2.0 (was 1.1.0)", self.text())

    def test_a_link_outside_the_cache_versions_is_skipped(self):
        self.version("1.2.0")
        os.symlink(self.home, self.cache / "1.0.0", target_is_directory=True)
        self.install("1.2.0")
        self.assertEqual(self.run_repoint(), 1)
        self.assertIn("1.0.0: skipped: symlink to", self.text())

    def test_dry_run_changes_nothing(self):
        self.version("1.0.0")
        self.version("1.2.0")
        self.install("1.2.0")
        before = sorted(p.name for p in self.cache.iterdir())
        self.assertEqual(self.run_repoint(dry_run=True), 0)
        self.assertEqual(sorted(p.name for p in self.cache.iterdir()), before)
        self.assertFalse((self.cache / "1.0.0").is_symlink())
        self.assertIn("1.0.0: would repoint to 1.2.0", self.text())

    def test_undo_restores_the_newest_backup_and_leaves_other_links(self):
        self.version("1.0.0")
        self.version("1.2.0")
        self.install("1.2.0")
        self.run_repoint()
        os.symlink("1.2.0", self.cache / "0.9.0", target_is_directory=True)  # no backup beside it
        self.assertEqual(self.run_repoint(undo=True, dry_run=True), 0)
        self.assertTrue((self.cache / "1.0.0").is_symlink())
        self.assertIn("1.0.0: would restore", self.text())
        self.assertEqual(self.run_repoint(undo=True), 0)
        self.assertFalse((self.cache / "1.0.0").is_symlink())
        self.assertEqual((self.cache / "1.0.0" / "hooks" / "guard.py").read_text(), "# 1.0.0\n")
        self.assertEqual(self.backups("1.0.0"), [])
        self.assertIn("1.0.0: restored", self.text())
        self.assertTrue((self.cache / "0.9.0").is_symlink())
        self.assertIn("0.9.0: left: symlink without a backup", self.text())

    def test_undo_picks_the_newest_of_two_backups(self):
        self.version("1.0.0")
        self.version("1.2.0")
        self.install("1.2.0")
        older = self.cache / ".1.0.0.repointed-20200101T000000000000Z"
        (self.cache / "1.0.0").rename(older)
        (older / "marker").write_text("old")
        newer = self.version("1.0.0")
        (newer / "marker").write_text("new")
        newer.rename(self.cache / ".1.0.0.repointed-20210101T000000000000Z")
        os.symlink("1.2.0", self.cache / "1.0.0", target_is_directory=True)
        self.assertEqual(self.run_repoint(undo=True), 0)
        self.assertEqual((self.cache / "1.0.0" / "marker").read_text(), "new")
        self.assertEqual(self.backups("1.0.0"), [".1.0.0.repointed-20200101T000000000000Z"])

    def test_no_installed_version_exits_2(self):
        self.version("1.0.0")
        self.assertEqual(self.run_repoint(), 2)
        self.install("2.0.0")  # referenced but not cached
        self.assertEqual(self.run_repoint(), 2)
        self.assertIn("no version referenced", self.text())
        self.assertFalse((self.cache / "1.0.0").is_symlink())

    def test_unparsable_installed_file_exits_2(self):
        (self.home / ".claude/plugins/installed_plugins.json").write_text("{bad")
        self.assertEqual(self.run_repoint(), 2)

    def test_env_overrides_are_honoured(self):
        other = self.home / "elsewhere"
        (other / "1.0.0" / "hooks").mkdir(parents=True)
        (other / "1.0.0" / "hooks" / "hooks.json").write_text(json.dumps(hooks()))
        (other / "1.1.0" / "hooks").mkdir(parents=True)
        (other / "1.1.0" / "hooks" / "hooks.json").write_text(json.dumps(hooks()))
        listing = self.home / "list.json"
        listing.write_text(json.dumps({"plugins": {doctor.PLUGIN: [{"installPath": "/x/1.1.0"}]}}))
        os.environ.update(ARSENAL_CACHE=str(other), ARSENAL_INSTALLED_PLUGINS=str(listing))
        self.assertEqual(self.run_repoint(), 0)
        self.assertEqual(os.readlink(other / "1.0.0"), "1.1.0")


class RollbackTests(RepointCase):
    def setUp(self):
        super().setUp()
        self.version("1.0.0")
        self.version("1.2.0")
        self.install("1.2.0")

    def assert_untouched(self):
        self.assertFalse((self.cache / "1.0.0").is_symlink())
        self.assertEqual((self.cache / "1.0.0" / "hooks" / "guard.py").read_text(), "# 1.0.0\n")
        self.assertEqual(sorted(p.name for p in self.cache.iterdir()), ["1.0.0", "1.2.0"])

    def test_symlink_failure_changes_nothing(self):
        with mock.patch("repoint.os.symlink", side_effect=OSError("privilege not held")):
            self.assertEqual(self.run_repoint(), 1)
        self.assert_untouched()
        self.assertIn("1.0.0: failed: cannot create a symlink (privilege not held); nothing changed", self.text())

    def test_replace_failure_rolls_the_folder_back(self):
        with mock.patch("repoint.os.replace", side_effect=OSError("boom")):
            self.assertEqual(self.run_repoint(), 1)
        self.assert_untouched()
        self.assertIn("1.0.0: failed: boom; rolled back", self.text())

    def test_rename_failure_changes_nothing(self):
        with mock.patch("repoint.os.rename", side_effect=OSError("busy")):
            self.assertEqual(self.run_repoint(), 1)
        self.assert_untouched()
        self.assertIn("1.0.0: failed: busy; folder unchanged", self.text())

    def test_failed_rollback_says_how_to_restore(self):
        with mock.patch("repoint.os.replace", side_effect=OSError("boom")), \
                mock.patch("repoint.os.rename", side_effect=[None, OSError("denied")]):
            self.assertEqual(self.run_repoint(), 1)
        self.assertIn("ROLLBACK FAILED (denied): restore by hand with mv", self.text())

    def test_failed_link_replace_keeps_the_old_link(self):
        self.version("1.1.0")
        self.install("1.1.0")
        self.run_repoint()
        self.install("1.1.0", "1.2.0")
        with mock.patch("repoint.os.replace", side_effect=OSError("boom")):
            self.assertEqual(self.run_repoint(), 1)
        self.assertEqual(os.readlink(self.cache / "1.0.0"), "1.1.0")
        self.assertIn("link unchanged", self.text())
        self.assertEqual([p.name for p in self.cache.glob(".*link-*")], [])

    def test_undo_rename_failure_recreates_the_link(self):
        self.run_repoint()
        with mock.patch("repoint.os.rename", side_effect=OSError("busy")):
            self.assertEqual(self.run_repoint(undo=True), 1)
        self.assertEqual(os.readlink(self.cache / "1.0.0"), "1.2.0")
        self.assertIn("1.0.0: failed: busy; link unchanged", self.text())


class InterruptTests(RepointCase):
    def setUp(self):
        super().setUp()
        self.version("1.0.0")
        self.version("1.2.0")
        self.install("1.2.0")

    def names(self):
        return sorted(p.name for p in self.cache.iterdir())

    def test_interrupt_between_the_rename_and_the_replace_restores_the_folder(self):
        with mock.patch("repoint.os.replace", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_repoint()
        self.assertEqual(self.names(), ["1.0.0", "1.2.0"])
        self.assertFalse((self.cache / "1.0.0").is_symlink())

    def test_interrupt_during_undo_recreates_the_link(self):
        self.run_repoint()
        with mock.patch("repoint.os.rename", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_repoint(undo=True)
        self.assertEqual(os.readlink(self.cache / "1.0.0"), "1.2.0")

    def crash_gap(self):
        """The state a kill leaves between the rename and the replace."""
        backup = self.cache / ".1.0.0.repointed-20200101T000000000000Z"
        (self.cache / "1.0.0").rename(backup)
        os.symlink("1.2.0", self.cache / ".1.0.0.link-20200101T000000000000Z", target_is_directory=True)

    def test_a_rerun_recovers_a_version_a_kill_left_missing_then_repoints_it(self):
        self.crash_gap()
        self.assertEqual(self.run_repoint(), 0)
        self.assertIn("1.0.0: recovered from .1.0.0.repointed-20200101T000000000000Z", self.text())
        self.assertEqual(os.readlink(self.cache / "1.0.0"), "1.2.0")
        self.assertEqual([p for p in self.names() if ".link-" in p], [])

    def test_dry_run_reports_the_recovery_and_changes_nothing(self):
        self.crash_gap()
        before = self.names()
        self.assertEqual(self.run_repoint(dry_run=True), 0)
        self.assertIn("1.0.0: would recover from", self.text())
        self.assertEqual(self.names(), before)

    def test_undo_recovers_a_gap_left_by_an_interrupted_undo(self):
        self.run_repoint()
        (self.cache / "1.0.0").unlink()  # undo's gap: link gone, backup not yet renamed
        self.assertEqual(self.run_repoint(undo=True), 0)
        self.assertIn("1.0.0: recovered from", self.text())
        self.assertFalse((self.cache / "1.0.0").is_symlink())
        self.assertEqual((self.cache / "1.0.0" / "hooks" / "guard.py").read_text(), "# 1.0.0\n")

    def test_a_stray_temp_link_is_removed_when_the_version_is_present(self):
        os.symlink("1.2.0", self.cache / ".1.0.0.link-20200101T000000000000Z", target_is_directory=True)
        self.assertEqual(self.run_repoint(dry_run=True), 0)
        self.assertIn("1.0.0: would remove stray link .1.0.0.link-20200101T000000000000Z", self.text())
        self.assertEqual(self.run_repoint(), 0)
        self.assertIn("1.0.0: removed stray link", self.text())
        self.assertEqual([p for p in self.names() if ".link-" in p], [])

    def test_a_missing_version_without_a_backup_is_reported_as_a_failure(self):
        os.symlink("1.2.0", self.cache / ".1.0.0.link-20200101T000000000000Z", target_is_directory=True)
        (self.cache / "1.0.0").rename(self.home / "moved")
        self.assertEqual(self.run_repoint(), 1)
        self.assertIn("1.0.0: missing and no backup beside it", self.text())


class CompatibilityTests(RepointCase):
    def commands(self, name, *commands):
        folder = self.cache / name
        (folder / "hooks").mkdir(parents=True, exist_ok=True)
        config = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": c} for c in commands]}]}}
        (folder / "hooks" / "hooks.json").write_text(json.dumps(config))
        return folder

    def test_bare_and_quoted_variable_forms_are_both_checked(self):
        for command in ('python3 $CLAUDE_PLUGIN_ROOT/hooks/old_only.py', 'python3 "$CLAUDE_PLUGIN_ROOT/hooks/old_only.py"',
                        "python3 '${CLAUDE_PLUGIN_ROOT}/hooks/old_only.py'"):
            with self.subTest(command=command):
                self.commands("1.0.0", command)
                self.version("1.2.0")
                self.install("1.2.0")
                self.assertEqual(self.run_repoint(), 1)
                self.assertIn("1.0.0: skipped: its hooks run hooks/old_only.py, missing in 1.2.0", self.text())
                self.assertFalse((self.cache / "1.0.0").is_symlink())
                import shutil
                shutil.rmtree(self.cache / "1.0.0")
                shutil.rmtree(self.cache / "1.2.0")

    def test_a_command_with_the_variable_but_no_parsable_path_cannot_be_verified(self):
        self.commands("1.0.0", 'sh -c "cd ${CLAUDE_PLUGIN_ROOT} && run"')
        self.version("1.2.0")
        self.install("1.2.0")
        self.assertEqual(self.run_repoint(), 1)
        self.assertIn("1.0.0: skipped: cannot verify its hooks: a command uses CLAUDE_PLUGIN_ROOT in a form", self.text())
        self.assertFalse((self.cache / "1.0.0").is_symlink())

    def test_a_skill_missing_in_the_target_skips_the_version(self):
        self.version("1.0.0")
        (self.cache / "1.0.0" / ".agents" / "skills" / "kept").mkdir(parents=True)
        (self.cache / "1.0.0" / ".agents" / "skills" / "dropped").mkdir()
        self.version("1.2.0")
        (self.cache / "1.2.0" / ".agents" / "skills" / "kept").mkdir(parents=True)
        self.install("1.2.0")
        self.assertEqual(self.run_repoint(), 1)
        self.assertIn("1.0.0: skipped: its skills or agents missing in 1.2.0: skill dropped", self.text())
        self.assertFalse((self.cache / "1.0.0").is_symlink())

    def test_an_agent_missing_in_the_target_skips_the_version(self):
        self.version("1.0.0")
        (self.cache / "1.0.0" / "agents").mkdir()
        (self.cache / "1.0.0" / "agents" / "reviewer.md").write_text("x")
        self.version("1.2.0")
        self.install("1.2.0")
        self.assertEqual(self.run_repoint(), 1)
        self.assertIn("missing in 1.2.0: agent reviewer", self.text())

    def test_skill_directories_come_from_plugin_json(self):
        self.version("1.0.0")
        (self.cache / "1.0.0" / ".claude-plugin").mkdir()
        (self.cache / "1.0.0" / ".claude-plugin" / "plugin.json").write_text(json.dumps({"skills": ["./custom/"]}))
        (self.cache / "1.0.0" / "custom" / "only-old").mkdir(parents=True)
        self.version("1.2.0")
        self.install("1.2.0")
        self.assertEqual(self.run_repoint(), 1)
        self.assertIn("skill only-old", self.text())

    def test_a_wrong_type_in_plugin_json_falls_back_to_the_default_paths(self):
        for value in (None, 5, {"a": 1}):
            with self.subTest(value=value):
                root = self.cache / "odd"
                (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
                (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"skills": value}))
                self.assertEqual(repoint.listed(root, "skills", "./.agents/skills/"), ["./.agents/skills/"])

    def test_extra_skills_in_the_target_are_fine(self):
        self.version("1.0.0")
        self.version("1.2.0")
        (self.cache / "1.2.0" / ".agents" / "skills" / "new").mkdir(parents=True)
        (self.cache / "1.2.0" / "agents").mkdir()
        (self.cache / "1.2.0" / "agents" / "new.md").write_text("x")
        self.install("1.2.0")
        self.assertEqual(self.run_repoint(), 0)
        self.assertTrue((self.cache / "1.0.0").is_symlink())

    def test_hook_arguments_are_not_verified_and_the_limit_says_so(self):
        self.version("1.2.0")
        self.install("1.2.0")
        self.run_repoint()
        self.assertIn("hook command-line arguments are not verified", self.text())
        self.assertIn("hook command-line arguments are not verified", (ROOT / "README.md").read_text())


class AdjacentToolTests(RepointCase):
    def test_doctor_treats_a_link_to_the_version_in_use_as_fine(self):
        self.version("1.0.0")
        self.version("1.2.0")
        self.install("1.2.0")
        (self.home / ".claude/settings.json").write_text("{}")
        self.run_repoint()
        report = doctor.diagnose(self.home, None)
        self.assertFalse([row for row in report.rows if "older plugin versions" in row[1]], report.rows)

    def test_doctor_still_reports_a_real_stale_version_and_names_repoint(self):
        self.version("1.0.0")
        self.version("1.2.0")
        self.install("1.2.0")
        (self.home / ".claude/settings.json").write_text("{}")
        rows = [row for row in doctor.diagnose(self.home, None).rows if "older plugin versions" in row[1]]
        self.assertEqual(len(rows), 1)
        self.assertIn("1.0.0", rows[0][1])
        self.assertIn("arsenal repoint", rows[0][2])

    def test_doctor_ignores_repoint_backups(self):
        self.version("1.0.0")
        self.version("1.2.0")
        self.install("1.2.0")
        (self.home / ".claude/settings.json").write_text("{}")
        self.run_repoint()
        self.assertEqual([r for r in doctor.diagnose(self.home, None).rows if "older plugin" in r[1]], [])

    def test_guard_registry_lists_a_linked_version_once_as_the_target_only(self):
        for name in ("1.0.0", "1.2.0"):
            folder = self.version(name)
            (folder / "hooks" / "guard_lessons.py").write_text("")
        self.install("1.2.0")
        self.assertEqual([v for v, _ in guard_registry.installed_versions(self.cache)], ["1.0.0", "1.2.0"])
        self.run_repoint()
        self.assertEqual([v for v, _ in guard_registry.installed_versions(self.cache)], ["1.2.0"])


if __name__ == "__main__":
    unittest.main()
