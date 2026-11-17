"""Unit tests for scripts/doctor.py (`arsenal doctor`), against a fake home directory."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "doctor.py"
sys.path.insert(0, str(SCRIPT.parent))
import doctor  # noqa: E402

CACHE = Path(".claude") / "plugins" / "cache" / "senior-developer-arsenal" / "arsenal"


def manifest_paths(target, scope="global"):
    return [(row[2], row[5]) for row in doctor.manifest_rows(scope) if row[0] == target]


def own_paths(target, scope="global"):
    users = {}
    for row in doctor.manifest_rows(scope):
        users.setdefault(row[5], set()).add(row[0])
    return [(kind, dest) for kind, dest in manifest_paths(target, scope) if users[dest] == {target}]


class DoctorCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.home, self.project = base / "home", base / "project"
        self.home.mkdir()
        self.project.mkdir()
        patch = mock.patch.dict(os.environ, {"LESSONS_GLOBAL_FILE": str(self.home / ".agents" / "lessons.md")})
        patch.start()
        self.addCleanup(patch.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def write_json(self, relative, data):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data))

    def place(self, paths, base=None):
        for kind, dest in paths:
            path = (base or self.home) / dest
            if kind == "dir":
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x")

    def install_plugin(self, version="1.0.0", enabled=True, stale=()):
        cache = self.home / CACHE
        cache.mkdir(parents=True)
        (cache / version).symlink_to(ROOT, target_is_directory=True)  # a real plugin tree with that version name
        for name in stale:
            (cache / name).mkdir()
        self.write_json(".claude/plugins/installed_plugins.json", {"version": 2, "plugins": {doctor.PLUGIN: [
            {"scope": "user", "installPath": str(cache / version), "version": version}]}})
        self.write_json(".claude/settings.json", {"enabledPlugins": {doctor.PLUGIN: enabled}})

    def rows(self, project=None):
        report = doctor.diagnose(self.home, project)
        return report, {(level, text.split(":")[0]): (text, repair) for level, text, repair in report.rows}

    def find(self, report, level, needle):
        return [(text, repair) for row_level, text, repair in report.rows if row_level == level and needle in text]


class FreshHomeTest(DoctorCase):
    def test_nothing_installed_is_warnings_only(self):
        report, _ = self.rows()
        self.assertFalse(report.failed(), report.render())
        self.assertTrue(self.find(report, "warn", "Claude Code plugin not installed"))
        self.assertTrue(self.find(report, "warn", "no installer target found globally"))
        self.assertTrue(self.find(report, "ok", "this checkout's hooks.json parses"))
        self.assertTrue(self.find(report, "warn", "codegraph MCP server not configured"))

    def test_python_too_old_fails(self):
        report = doctor.Report()
        with mock.patch.object(doctor.sys, "version_info", (3, 8, 10)):
            doctor.check_python(report)
        self.assertTrue(report.failed())


class PluginTest(DoctorCase):
    def test_installed_old_disabled_with_stale_versions(self):
        self.install_plugin("1.0.0", enabled=False, stale=("0.9.0", "0.8.1"))
        report, _ = self.rows()
        self.assertTrue(self.find(report, "warn", "installed but disabled"))
        self.assertTrue(self.find(report, "warn", "Claude Code plugin 1.0.0 is older than this checkout"))
        stale = self.find(report, "warn", "older plugin versions no install uses: 0.8.1, 0.9.0 (not deleted)")
        self.assertTrue(stale)
        self.assertIn("rm -r", stale[0][1])
        self.assertTrue((self.home / CACHE / "0.9.0").is_dir())  # reported, never deleted
        self.assertTrue(self.find(report, "ok", "plugin 1.0.0 hooks.json parses"))

    def test_current_plugin_is_ok(self):
        self.install_plugin((ROOT / "VERSION").read_text().strip())
        report, _ = self.rows()
        self.assertTrue(self.find(report, "ok", "Claude Code plugin"))

    def test_broken_hooks_json_and_broken_registry_fail(self):
        cache = self.home / CACHE / "1.0.0" / "hooks"
        cache.mkdir(parents=True)
        (cache / "hooks.json").write_text("{not json")
        self.write_json(".claude/plugins/installed_plugins.json", {"plugins": {doctor.PLUGIN: [
            {"scope": "user", "installPath": str(cache.parent)}]}})
        report, _ = self.rows()
        self.assertTrue(self.find(report, "fail", "plugin 1.0.0 hooks.json does not parse"))
        self.write_json(".claude/plugins/installed_plugins.json", "{oops")
        report, _ = self.rows()
        self.assertTrue(self.find(report, "fail", "Claude Code settings do not parse"))

    def test_a_missing_hook_script_fails(self):
        plugin = self.home / CACHE / "1.0.0"
        (plugin / "hooks").mkdir(parents=True)
        (plugin / "hooks" / "hooks.json").write_text((ROOT / "hooks" / "hooks.json").read_text())
        self.write_json(".claude/plugins/installed_plugins.json", {"plugins": {doctor.PLUGIN: [
            {"scope": "user", "installPath": str(plugin)}]}})
        report, _ = self.rows()
        failed = self.find(report, "fail", "plugin 1.0.0 hook scripts broken")
        self.assertTrue(failed)
        self.assertIn("hooks/guard.py (missing)", failed[0][0])


class TargetTest(DoctorCase):
    def test_a_partial_install_fails_with_the_installer_command(self):
        self.place(own_paths("codex")[:1])
        report, _ = self.rows()
        failed = self.find(report, "fail", "codex installed globally but")
        self.assertTrue(failed, report.render())
        self.assertEqual(failed[0][1], "./install.sh --global --target codex")
        self.assertEqual(report.missing, {("global", None): {"codex"}})

    def test_shared_paths_alone_do_not_make_a_target_installed(self):
        users = {}
        for row in doctor.manifest_rows("global"):
            users.setdefault(row[5], set()).add(row[0])
        shared = [(row[2], row[5]) for row in doctor.manifest_rows("global") if len(users[row[5]]) > 1][:3]
        self.place(shared)
        report, _ = self.rows()
        self.assertFalse(report.failed(), report.render())

    def test_a_complete_install_is_ok_and_project_scope_is_read_from_project(self):
        self.place(manifest_paths("codex"))
        self.place(own_paths("cursor", "project")[:1], base=self.project)
        report, _ = self.rows(self.project)
        self.assertTrue(self.find(report, "ok", "codex installed globally"))
        failed = self.find(report, "fail", f"cursor installed in {self.project}")
        self.assertTrue(failed, report.render())
        self.assertIn(f"./install.sh --project {self.project} --target cursor", failed[0][1])


class LedgerAndMcpTest(DoctorCase):
    def test_a_damaged_ledger_fails_with_the_check_command(self):
        ledger = self.home / ".agents" / "lessons.md"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("# Lessons Learned\n\n## Active\nthis is not a lesson line\n")
        report, _ = self.rows()
        failed = self.find(report, "fail", "global lessons ledger")
        self.assertTrue(failed)
        self.assertIn("check", failed[0][1])
        ledger.write_bytes(b"# Lessons Learned\n\n## Active\n\xff\xfe\n")
        self.assertTrue(self.find(self.rows()[0], "fail", "is not UTF-8"))

    def test_mcp_servers_configured_by_file_or_plugin(self):
        self.write_json(".claude.json", {"mcpServers": {"codegraph": {}}, "projects": {}})
        self.write_json(".claude/settings.json", {"enabledPlugins": {doctor.MCP_PLUGINS["hindsight"]: True}})
        report, _ = self.rows()
        self.assertTrue(self.find(report, "ok", "codegraph MCP server configured"))
        self.assertTrue(self.find(report, "ok", "hindsight MCP server configured"))


class CliTest(DoctorCase):
    def run_cli(self, *args, env=None):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.project, capture_output=True, text=True,
                                env={**os.environ, "HOME": str(self.home), **(env or {})})
        return result.returncode, result.stdout, result.stderr

    def test_exit_codes_and_fix_reruns_the_installer_for_missing_targets_only(self):
        self.assertEqual(self.run_cli()[0], 0)
        self.assertEqual(self.run_cli("--project", str(self.project / "nope"))[0], 2)
        self.place(own_paths("codex")[:1])
        code, out, _ = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("repair: ./install.sh --global --target codex", out)
        listing = self.home / "to-create.txt"
        listing.write_text("".join(f"{kind} {self.home / dest}\n" for kind, dest in manifest_paths("codex")))
        stub = self.home / "installer.sh"
        stub.write_text('echo "$@" > "$HOME/installer-args"\n'
                        'while read -r kind path; do\n'
                        '  if [ "$kind" = dir ]; then mkdir -p "$path"; else mkdir -p "$(dirname "$path")"; : > "$path"; fi\n'
                        'done < "$HOME/to-create.txt"\n')
        code, out, _ = self.run_cli("--fix", env={"ARSENAL_DOCTOR_INSTALLER": str(stub)})
        self.assertEqual(code, 0, out)
        self.assertEqual((self.home / "installer-args").read_text().strip(), "--global --target codex")
        self.assertIn("after fix:", out)
        self.assertIn("[ok] codex installed globally", out)

    def test_fix_with_nothing_to_repair_runs_no_installer(self):
        stub = self.home / "installer.sh"
        stub.write_text('touch "$HOME/ran"\n')
        code, out, _ = self.run_cli("--fix", env={"ARSENAL_DOCTOR_INSTALLER": str(stub)})
        self.assertEqual(code, 0)
        self.assertIn("nothing the installer can repair", out)
        self.assertFalse((self.home / "ran").exists())

    def test_the_arsenal_cli_dispatches_doctor(self):
        result = subprocess.run(["bash", str(ROOT / "scripts" / "arsenal"), "doctor"], cwd=self.project,
                                capture_output=True, text=True, env={**os.environ, "HOME": str(self.home)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok,", result.stdout)


if __name__ == "__main__":
    unittest.main()
