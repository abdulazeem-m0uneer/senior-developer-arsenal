"""Hooks for the agents other than the Claude Code plugin: generated configs (build_hooks.py), the config
merge (hooks_merge.py) and the per-agent adapter (hooks/agent_hook.py) run from an installed layout."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import build_hooks  # noqa: E402
import hooks_merge  # noqa: E402

STEPS = build_hooks.load_steps(ROOT)
ADAPTER_DIR = "/opt/a b/arsenal-hooks"


def config(target):
    return json.loads(build_hooks.render_config(target, STEPS))


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                   capture_output=True)


class StepsTest(unittest.TestCase):
    def test_steps_come_from_the_plugin_hook_file_in_order(self):
        self.assertEqual([step["script"] for step in STEPS["SessionStart"]],
                         ["session_core.py", "../skills/lessons-learned/scripts/lessons.py", "guard.py"])
        self.assertEqual(STEPS["SessionStart"][1]["args"], ["active", "--hook"])
        self.assertEqual(STEPS["Stop"], [{"script": "guard.py", "args": ["stop"], "timeout": 15}])

    def test_every_step_script_exists_in_the_repository(self):
        for step in (step for steps in STEPS.values() for step in steps):
            source = step["script"].replace("../skills/", ".agents/skills/") if step["script"].startswith("..") \
                else "hooks/" + step["script"]
            self.assertTrue((ROOT / source).is_file(), source)

    def write_hooks(self, directory, command):
        handler = {"hooks": [{"type": "command", "command": command, "timeout": 5}]}
        (directory / "hooks").mkdir()
        (directory / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"SessionStart": [handler], "Stop": [handler]}}))

    def test_a_command_in_another_form_or_outside_the_installed_paths_fails_the_build(self):
        for command in ('node "${CLAUDE_PLUGIN_ROOT}/hooks/x.js"',
                        'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/x.py" || python "${CLAUDE_PLUGIN_ROOT}/scripts/x.py"'):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp:
                self.write_hooks(Path(tmp), command)
                with self.assertRaises(ValueError):
                    build_hooks.load_steps(Path(tmp))

    def test_an_event_left_with_no_portable_step_fails_the_build(self):
        script = "${CLAUDE_PLUGIN_ROOT}/" + build_hooks.UNPORTED_SCRIPTS[0]
        with tempfile.TemporaryDirectory() as tmp:
            self.write_hooks(Path(tmp), f'python3 "{script}" show || python "{script}" show')
            with self.assertRaises(ValueError):
                build_hooks.load_steps(Path(tmp))


class ConfigShapeTest(unittest.TestCase):
    def command(self, target, event):
        return (f'python3 "{{{{ARSENAL_HOOKS}}}}/agent_hook.py" {target} {event} || '
                f'python "{{{{ARSENAL_HOOKS}}}}/agent_hook.py" {target} {event}')

    def test_codex_uses_the_claude_shape_with_seconds(self):
        self.assertEqual(config("codex"), {"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": self.command("codex", "SessionStart"), "timeout": 30}]}],
            "Stop": [{"hooks": [{"type": "command", "command": self.command("codex", "Stop"), "timeout": 15}]}]}})

    def test_gemini_names_the_after_agent_event_and_counts_milliseconds(self):
        hooks = config("gemini")["hooks"]
        self.assertEqual(set(hooks), {"SessionStart", "AfterAgent"})
        self.assertEqual(hooks["AfterAgent"], [{"hooks": [{"name": "arsenal-Stop", "type": "command",
                                                           "command": self.command("gemini", "Stop"), "timeout": 15000}]}])

    def test_cursor_is_versioned_and_flat(self):
        self.assertEqual(config("cursor"), {"version": 1, "hooks": {
            "sessionStart": [{"command": self.command("cursor", "SessionStart"), "timeout": 30}],
            "stop": [{"command": self.command("cursor", "Stop"), "timeout": 15}]}})

    def test_copilot_has_a_command_per_shell(self):
        hooks = config("copilot")
        self.assertEqual(hooks["version"], 1)
        self.assertEqual(hooks["hooks"]["agentStop"], [{
            "type": "command", "bash": self.command("copilot", "Stop"),
            "powershell": 'python "{{ARSENAL_HOOKS}}/agent_hook.py" copilot Stop', "timeoutSec": 15}])
        self.assertEqual(set(hooks["hooks"]), {"sessionStart", "agentStop"})

    def test_antigravity_groups_the_events_under_one_hook_name(self):
        self.assertEqual(config("antigravity"), {"senior-developer-arsenal": {
            "SessionStart": [{"type": "command", "command": self.command("antigravity", "SessionStart"), "timeout": 30}],
            "Stop": [{"type": "command", "command": self.command("antigravity", "Stop"), "timeout": 15}]}})

    def test_every_generated_handler_is_recognised_as_an_arsenal_handler(self):
        for target in build_hooks.HOOK_TARGETS:
            entry = hooks_merge.substituted(config(target), [("ARSENAL_HOOKS", ADAPTER_DIR)])
            for section in hooks_merge.sections(entry).values():
                for handlers in section.values():
                    self.assertTrue(all(hooks_merge.owned(handler) for handler in handlers), target)

    def test_targets_without_a_documented_command_hook_get_nothing(self):
        self.assertEqual(set(build.TARGETS) - set(build_hooks.HOOK_TARGETS), {"claude", "opencode", "windsurf"})
        for target in ("claude", "opencode", "windsurf"):
            self.assertEqual(build_hooks.manifest_rows(ROOT, target, "global"), [])


class ManifestTest(unittest.TestCase):
    def test_hook_scripts_are_installed_beside_the_skills_of_each_target(self):
        rows = build.manifest_rows(build.load_sources())
        for target in build_hooks.HOOK_TARGETS:
            for scope in ("global", "project"):
                mine = [row for row in rows if row[:2] == (target, scope)]
                hooks = [row for row in mine if row[2] == "hooks"]
                self.assertEqual(len(hooks), 1, (target, scope))
                directory = hooks[0][6]
                skills = {os.path.dirname(row[5]) for row in mine if row[2] == "dir"}
                self.assertEqual(skills, {os.path.dirname(directory) + "/skills"}, (target, scope))
                installed = {row[5] for row in mine if row[2] == "file"}
                for name in ("agent_hook.py", "steps.json", "session_core.py", "core.md", "guard.py",
                             "guard_destructive.py", "guard_limits.py"):
                    self.assertIn(f"{directory}/{name}", installed, (target, scope))
                self.assertEqual(hooks[0][4], f"dist/hooks/{target}.json")

    def test_config_destinations_are_the_documented_files(self):
        destinations = {(row[0], row[1]): row[5] for row in build.manifest_rows(build.load_sources()) if row[2] == "hooks"}
        self.assertEqual(destinations, {
            ("codex", "global"): ".codex/hooks.json", ("codex", "project"): ".codex/hooks.json",
            ("gemini", "global"): ".gemini/settings.json", ("gemini", "project"): ".gemini/settings.json",
            ("cursor", "global"): ".cursor/hooks.json", ("cursor", "project"): ".cursor/hooks.json",
            ("copilot", "global"): ".copilot/hooks/arsenal.json", ("copilot", "project"): ".github/hooks/arsenal.json",
            ("antigravity", "global"): ".gemini/config/hooks.json", ("antigravity", "project"): ".agents/hooks.json"})


class MergeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.file = self.dir / "sub" / "hooks.json"

    def tearDown(self):
        self.tmp.cleanup()

    def merge(self, target, *extra, directory=ADAPTER_DIR):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = hooks_merge.main(["--file", str(self.file), "--entry", str(ROOT / "dist" / "hooks" / f"{target}.json"),
                                     "--set", f"ARSENAL_HOOKS={directory}", *extra])
        return code, out.getvalue() + err.getvalue()

    def given(self, data):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(data if isinstance(data, str) else json.dumps(data))

    def read(self):
        return json.loads(self.file.read_text())

    def backups(self):
        return list(self.file.parent.glob("hooks.json.bak-*"))

    def test_a_missing_file_is_created_with_the_path_substituted(self):
        code, _ = self.merge("cursor")
        self.assertEqual(code, 0)
        self.assertIn(f'"{ADAPTER_DIR}/agent_hook.py" cursor Stop', self.read()["hooks"]["stop"][0]["command"])
        self.assertNotIn("{{", self.file.read_text())
        self.assertEqual(self.backups(), [])

    def test_a_windows_path_survives_as_valid_json(self):
        self.assertEqual(self.merge("copilot", directory="C:\\Users\\a b\\.agents\\arsenal-hooks")[0], 0)
        self.assertIn("C:\\Users\\a b\\.agents\\arsenal-hooks/agent_hook.py",
                      self.read()["hooks"]["sessionStart"][0]["powershell"])

    def test_the_users_hooks_and_other_settings_are_kept_and_backed_up(self):
        mine = {"hooks": [{"type": "command", "command": "./mine.sh"}]}
        self.given({"mcpServers": {"x": {"command": "y"}}, "hooks": {"AfterAgent": [mine], "BeforeTool": [mine]}})
        self.assertEqual(self.merge("gemini")[0], 0)
        data = self.read()
        self.assertEqual(data["mcpServers"], {"x": {"command": "y"}})
        self.assertEqual(data["hooks"]["BeforeTool"], [mine])
        self.assertEqual(data["hooks"]["AfterAgent"][0], mine)
        self.assertEqual(len(data["hooks"]["AfterAgent"]), 2)
        self.assertEqual(len(self.backups()), 1)

    def test_a_second_merge_changes_nothing(self):
        for target in build_hooks.HOOK_TARGETS:
            with self.subTest(target=target):
                self.given({"other": 1})
                self.merge(target)
                before, backups = self.file.read_text(), len(self.backups())
                code, output = self.merge(target)
                self.assertEqual((code, self.file.read_text(), len(self.backups())), (0, before, backups))
                self.assertIn("unchanged", output)

    def test_a_moved_install_replaces_the_old_arsenal_handlers(self):
        self.merge("codex", directory="/old/arsenal-hooks")
        self.merge("codex", directory="/new/arsenal-hooks")
        stop = self.read()["hooks"]["Stop"]
        self.assertEqual(len(stop), 1)
        self.assertIn("/new/arsenal-hooks/agent_hook.py", stop[0]["hooks"][0]["command"])

    def test_an_existing_version_is_not_overwritten(self):
        self.given({"version": 2, "hooks": {}})
        self.merge("cursor")
        self.assertEqual(self.read()["version"], 2)

    def test_remove_restores_the_users_file_exactly(self):
        for target in build_hooks.HOOK_TARGETS:
            with self.subTest(target=target):
                original = {"version": 1, "other": [1], "hooks": {"Stop": [{"command": "./mine.sh"}], "stop": [{"command": "m"}]}}
                self.given(original)
                self.merge(target)
                self.assertNotEqual(self.read(), original)
                self.assertEqual(self.merge(target, "--remove")[0], 0)
                self.assertEqual(self.read(), original)

    def test_remove_deletes_a_file_that_held_only_arsenal_hooks(self):
        for target in build_hooks.HOOK_TARGETS:
            with self.subTest(target=target):
                self.merge(target)
                self.assertEqual(self.merge(target, "--remove")[0], 0)
                self.assertFalse(self.file.exists())

    def test_remove_keeps_a_backup_of_a_file_it_deletes(self):
        self.merge("cursor")
        before = self.file.read_text()
        self.assertEqual(self.merge("cursor", "--remove")[0], 0)
        self.assertFalse(self.file.exists())
        self.assertEqual([Path(path).read_text() for path in self.backups()], [before])

    def test_remove_leaves_a_file_without_arsenal_hooks_alone(self):
        self.given('{"hooks":{"stop":[{"command":"./mine.sh"}]}}')
        code, output = self.merge("cursor", "--remove")
        self.assertEqual((code, self.file.read_text()), (0, '{"hooks":{"stop":[{"command":"./mine.sh"}]}}'))
        self.assertIn("unchanged", output)
        self.assertEqual(self.merge("cursor", "--remove")[0], 0)  # also when the file is missing
        self.file.unlink()
        self.assertEqual(self.merge("cursor", "--remove")[0], 0)
        self.assertFalse(self.file.exists())

    def test_an_unmergeable_file_is_refused_and_left_untouched(self):
        for text in ("{ not json", "[1]", '{"hooks": []}', '{"hooks": {"stop": {"command": "x"}}}'):
            with self.subTest(text=text):
                self.given(text)
                for extra in ((), ("--remove",)) if text != '{"hooks": []}' else ((),):
                    code, output = self.merge("cursor", *extra)
                    self.assertEqual((code, self.file.read_text()), (2, text))
                    self.assertIn("left untouched", output)
                self.assertEqual(self.backups(), [])

    def test_dry_run_writes_nothing(self):
        code, output = self.merge("cursor", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("[dry-run]", output)
        self.assertFalse(self.file.exists())

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_permissions_are_kept(self):
        self.given({})
        self.file.chmod(0o600)
        self.merge("cursor")
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)


class AdapterCase(unittest.TestCase):
    """The layout the installer creates (arsenal-hooks beside skills) and a git repository to work in."""

    link = False

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.hooks, self.repo = base / "agents" / "arsenal-hooks", base / "repo"
        self.hooks.mkdir(parents=True)
        place = os.symlink if self.link else shutil.copy
        for name in [path.name for path in (ROOT / "hooks").glob("*.py")] + ["core.md"]:
            place(ROOT / "hooks" / name, self.hooks / name)
        place(ROOT / build_hooks.STEPS_PATH, self.hooks / "steps.json")
        for skill in ("lessons-learned", "handoff"):
            if self.link:
                (base / "agents" / "skills").mkdir(exist_ok=True)
                os.symlink(ROOT / ".agents" / "skills" / skill, base / "agents" / "skills" / skill)
            else:
                shutil.copytree(ROOT / ".agents" / "skills" / skill, base / "agents" / "skills" / skill,
                                ignore=shutil.ignore_patterns("__pycache__"))
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        (self.repo / "README.md").write_text("x")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "init")
        self.env = {**os.environ, "HANDOFF_SNAPSHOT": str(base / "snap.md"),
                    "LESSONS_GLOBAL_FILE": str(base / "no-global-lessons.md")}
        for name in ("ARSENAL_GUARD", "ARSENAL_RUN_LIMITS", "CLAUDE_PROJECT_DIR", "LESSONS_FILE"):
            self.env.pop(name, None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, target, event, payload, env=None):
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        result = subprocess.run([sys.executable, str(self.hooks / "agent_hook.py"), target, event], input=stdin,
                                capture_output=True, text=True, cwd=self.repo, env={**self.env, **(env or {})})
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        return json.loads(result.stdout) if result.stdout.strip() else None

    def session(self, target):
        """Hook input of each agent, in its documented field names."""
        return {"codex": {"session_id": "s1", "cwd": str(self.repo), "source": "startup"},
                "gemini": {"session_id": "s1", "cwd": str(self.repo), "source": "startup"},
                "cursor": {"conversation_id": "s1", "workspace_roots": [str(self.repo)]},
                "copilot": {"sessionId": "s1", "cwd": str(self.repo), "source": "new"},
                "antigravity": {"conversationId": "s1", "workspacePaths": [str(self.repo)]}}[target]

    def stopping(self, target):
        extra = {"cursor": {"status": "completed", "loop_count": 0}, "antigravity": {"error": "", "fullyIdle": True},
                 "copilot": {"stop_hook_active": False}}.get(target, {"stop_hook_active": False})
        return {**self.session(target), **extra}

    def change_source(self):
        (self.repo / "app.py").write_text("print(1)\n")


class SessionStartTest(AdapterCase):
    CONTEXT = {"codex": lambda out: out["hookSpecificOutput"]["additionalContext"],
               "gemini": lambda out: out["hookSpecificOutput"]["additionalContext"],
               "cursor": lambda out: out["additional_context"],
               "copilot": lambda out: out["additionalContext"],
               "antigravity": lambda out: out["injectSteps"][0]["systemMessage"]["systemMessage"]}

    def test_each_agent_gets_the_core_and_the_lessons_in_its_own_contract(self):
        for target, context in self.CONTEXT.items():
            with self.subTest(target=target):
                out = self.run_hook(target, "SessionStart", self.session(target))
                text = context(out)
                self.assertIn("Arsenal operating core", text)
                self.assertIn("lessons.py", text)
                self.assertLess(text.index("Arsenal operating core"), text.index("lessons.py"))

    def test_claude_shaped_outputs_name_the_event(self):
        out = self.run_hook("codex", "SessionStart", self.session("codex"))
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertEqual(set(out), {"hookSpecificOutput"})

    def test_garbage_or_empty_input_still_gives_the_static_context(self):
        for payload in ("", "{ not json", "[1, 2]"):
            with self.subTest(payload=payload):
                self.assertIn("Arsenal operating core", self.run_hook("cursor", "SessionStart", payload)["additional_context"])

    def test_an_unknown_target_or_event_prints_nothing(self):
        self.assertIsNone(self.run_hook("nope", "SessionStart", self.session("codex")))
        self.assertIsNone(self.run_hook("codex", "Nope", self.session("codex")))
        result = subprocess.run([sys.executable, str(self.hooks / "agent_hook.py")], input="{}", capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_a_missing_step_script_costs_only_that_step(self):
        (self.hooks / "guard.py").unlink()
        shutil.rmtree(self.hooks.parent / "skills")
        self.assertIn("Arsenal operating core", self.run_hook("cursor", "SessionStart", self.session("cursor"))["additional_context"])

    def test_a_missing_steps_file_is_silent(self):
        (self.hooks / "steps.json").unlink()
        self.assertIsNone(self.run_hook("cursor", "SessionStart", self.session("cursor")))


class StopGateTest(AdapterCase):
    BLOCK = {"codex": lambda out: (out["decision"], out["reason"]), "copilot": lambda out: (out["decision"], out["reason"]),
             "gemini": lambda out: (out["decision"], out["reason"]),
             "cursor": lambda out: ("followup", out["followup_message"]),
             "antigravity": lambda out: (out["decision"], out["reason"])}
    VERB = {"codex": "block", "copilot": "block", "gemini": "deny", "cursor": "followup", "antigravity": "continue"}
    IDLE = {"antigravity": {"decision": "allow"}}

    def test_a_source_change_without_a_test_blocks_once_in_each_agents_contract(self):
        for target in self.BLOCK:
            with self.subTest(target=target):
                self.env["HANDOFF_SNAPSHOT"] = str(self.hooks.parent / f"{target}.md")
                self.run_hook(target, "SessionStart", self.session(target))
                self.assertEqual(self.run_hook(target, "Stop", self.stopping(target)), self.IDLE.get(target))
                self.change_source()
                out = self.run_hook(target, "Stop", self.stopping(target))
                verb, reason = self.BLOCK[target](out)
                self.assertEqual(verb, self.VERB[target])
                self.assertIn("app.py", reason)
                self.assertEqual(len(out), 1 if target == "cursor" else 2)
                self.assertEqual(self.run_hook(target, "Stop", self.stopping(target)), self.IDLE.get(target))
                (self.repo / "app.py").unlink()

    def test_the_session_is_keyed_by_the_agents_own_id_field(self):
        del self.env["HANDOFF_SNAPSHOT"]
        self.env["TMPDIR"] = self.env["TEMP"] = self.env["TMP"] = str(self.hooks.parent)
        for target, field in (("cursor", "conversation_id"), ("copilot", "sessionId"), ("antigravity", "conversationId")):
            with self.subTest(target=target):
                first = {**self.session(target), field: f"{target}-one"}
                self.run_hook(target, "SessionStart", first)
                self.change_source()
                other = {**self.stopping(target), field: f"{target}-two"}  # no baseline: fails open
                self.assertEqual(self.run_hook(target, "Stop", other), self.IDLE.get(target))
                self.assertIn("app.py", json.dumps(self.run_hook(target, "Stop", {**self.stopping(target), field: f"{target}-one"})))
                (self.repo / "app.py").unlink()

    def blocked(self, target, **fields):
        self.run_hook(target, "SessionStart", self.session(target))
        self.change_source()
        return self.run_hook(target, "Stop", {**self.stopping(target), **fields})

    def test_cursor_does_not_push_on_after_an_abort_an_error_or_a_follow_up(self):
        for fields in ({"status": "aborted"}, {"status": "error"}, {"loop_count": 1}):
            with self.subTest(fields=fields):
                self.env["HANDOFF_SNAPSHOT"] = str(self.hooks.parent / f"{len(str(fields))}.md")
                self.assertIsNone(self.blocked("cursor", **fields))
                (self.repo / "app.py").unlink()  # else the next case starts with the change already in its baseline

    def test_the_cursor_gate_does_block_a_completed_first_stop(self):
        self.assertIsNotNone(self.blocked("cursor", status="completed", loop_count=0))

    def test_antigravity_lets_a_failed_run_stop_without_an_answer(self):
        self.assertIsNone(self.blocked("antigravity", error="model unavailable"))

    def test_a_continued_turn_is_not_blocked_again(self):
        for target in ("codex", "gemini", "copilot"):
            with self.subTest(target=target):
                self.env["HANDOFF_SNAPSHOT"] = str(self.hooks.parent / f"{target}.md")
                self.assertIsNone(self.blocked(target, stop_hook_active=True))

    def test_the_guard_switch_turns_the_gate_off(self):
        self.env["ARSENAL_GUARD"] = "off"
        self.assertIsNone(self.blocked("codex"))

    def test_the_reason_points_at_the_installed_lessons_script(self):
        self.run_hook("codex", "SessionStart", self.session("codex"))
        state = Path(self.env["HANDOFF_SNAPSHOT"]).with_suffix(".guard.jsonl")
        with open(state, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event": "fail", "command": "pytest", "checks": ["pytest"]}) + "\n")
        reason = self.run_hook("codex", "Stop", self.stopping("codex"))["reason"]
        self.assertIn("lessons.py", reason)
        self.assertNotIn(".agents/.agents", reason.replace("\\", "/"))
        named = next(word.strip('"') for word in reason.split() if word.strip('"').endswith("lessons.py"))
        self.assertTrue(Path(named).is_file(), named)


@unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
class LinkedInstallTest(AdapterCase):
    link = True

    def test_a_linked_install_runs_the_steps_beside_the_link(self):
        self.assertIn("lessons.py", self.run_hook("cursor", "SessionStart", self.session("cursor"))["additional_context"])
        self.change_source()
        self.assertIn("app.py", self.run_hook("cursor", "Stop", self.stopping("cursor"))["followup_message"])


if __name__ == "__main__":
    unittest.main()
