"""Tests for the subagent cost guard (hooks/guard_models.py) and its wiring in guard.py pre."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hooks"))
import guard_models  # noqa: E402

DEFINITIONS = {"subagents": [
    {"name": "explorer", "recommended_model": "fast"},
    {"name": "builder", "recommended_model": "balanced"},
    {"name": "auditor", "recommended_model": "pro"},
    {"name": "generalist", "recommended_model": "inherit"},
]}


class ModelCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(os.path.realpath(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def definitions(self, content):
        path = self.root / ".agents" / "subagents" / "subagent-definitions.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content))

    def agent_file(self, name, model):
        path = self.root / "agents" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'---\nname: "{name}"\ndescription: "x"\nmodel: {model}\n---\n\nBody with model: opus\n')

    def judge(self, subagent, model):
        return guard_models.refusal({"subagent_type": subagent, "model": model, "prompt": "x"}, str(self.root))


class TierMatrixTest(ModelCase):
    def test_each_tier_by_each_requested_model(self):
        self.definitions(DEFINITIONS)
        allowed = {"explorer": {"haiku"}, "builder": {"haiku", "sonnet"},
                   "auditor": {"haiku", "sonnet", "opus", "fable"}, "generalist": {"haiku", "sonnet", "opus", "fable"}}
        for name, models in allowed.items():
            for model in ("haiku", "sonnet", "opus", "fable"):
                with self.subTest(subagent=name, model=model):
                    reason = self.judge(f"arsenal:{name}", model)
                    self.assertEqual(reason == "", model in models, reason)

    def test_the_reason_names_the_subagent_its_model_and_both_ways_out(self):
        self.definitions(DEFINITIONS)
        reason = self.judge("arsenal:builder", "opus")
        for part in ("arsenal:builder", "built to run on sonnet", '"opus"', "without the model parameter",
                     "ARSENAL_SUBAGENT_MODEL=any"):
            self.assertIn(part, reason)

    def test_absent_unknown_or_cased_models(self):
        self.definitions(DEFINITIONS)
        self.assertEqual(self.judge("arsenal:explorer", None), "")
        self.assertEqual(self.judge("arsenal:explorer", ""), "")
        self.assertEqual(self.judge("arsenal:explorer", "gpt-5"), "")
        self.assertTrue(self.judge("arsenal:explorer", " Opus "))

    def test_other_subagents_and_odd_names_are_not_judged(self):
        self.definitions(DEFINITIONS)
        for subagent in ("builder", "general-purpose", "other:builder", "arsenal:", "arsenal:../builder",
                         "arsenal:Builder", None, 3):
            with self.subTest(subagent=subagent):
                self.assertEqual(guard_models.refusal({"subagent_type": subagent, "model": "opus"}, str(self.root)), "")
        self.assertEqual(guard_models.refusal("not a dict", str(self.root)), "")
        self.assertEqual(self.judge("arsenal:not-listed", "opus"), "")


class FallbackTest(ModelCase):
    def test_without_definitions_the_generated_agent_file_decides(self):
        self.agent_file("builder", "sonnet")
        self.agent_file("explorer", "haiku")
        self.agent_file("generalist", "inherit")
        self.assertTrue(self.judge("arsenal:builder", "opus"))
        self.assertEqual(self.judge("arsenal:builder", "sonnet"), "")
        self.assertTrue(self.judge("arsenal:explorer", "sonnet"))
        self.assertEqual(self.judge("arsenal:generalist", "fable"), "")

    def test_malformed_definitions_fall_back_to_the_agent_file_then_allow(self):
        for content in ("{not json", json.dumps([1, 2]), json.dumps({"subagents": "x"}),
                        json.dumps({"subagents": [{"name": "builder", "recommended_model": 3}]})):
            with self.subTest(content=content):
                self.definitions(content)
                self.assertEqual(self.judge("arsenal:builder", "opus"), "")  # neither source says: allowed
                self.agent_file("builder", "sonnet")
                self.assertTrue(self.judge("arsenal:builder", "opus"))
                (self.root / "agents" / "builder.md").unlink()

    def test_nothing_installed_allows(self):
        self.assertEqual(self.judge("arsenal:builder", "opus"), "")

    def test_the_shipped_definitions_cap_the_builders_the_measurement_named(self):
        reason = guard_models.refusal({"subagent_type": "arsenal:node-specialist", "model": "opus"}, str(ROOT))
        self.assertIn("built to run on sonnet", reason)
        self.assertEqual(guard_models.refusal({"subagent_type": "arsenal:code-explorer", "model": "haiku"}, str(ROOT)), "")


class PreHookTest(ModelCase):
    def setUp(self):
        super().setUp()
        self.hooks = self.root / "plugin" / "hooks"
        shutil.copytree(ROOT / "hooks", self.hooks, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / ".agents" / "skills" / "handoff", self.root / "plugin" / ".agents" / "skills" / "handoff",
                        ignore=shutil.ignore_patterns("__pycache__"))
        path = self.root / "plugin" / ".agents" / "subagents" / "subagent-definitions.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(DEFINITIONS))

    def pre(self, tool_input, tool="Agent", mode="bypassPermissions", **env):
        environment = {k: v for k, v in os.environ.items() if not k.startswith("ARSENAL_")}
        environment.update(HANDOFF_SNAPSHOT=str(self.root / "snap.md"), **env)
        payload = {"tool_name": tool, "tool_input": tool_input, "cwd": str(self.root), "permission_mode": mode}
        out = subprocess.run([sys.executable, str(self.hooks / "guard.py"), "pre"], input=json.dumps(payload),
                             cwd=self.root, capture_output=True, text=True, env=environment)
        self.assertEqual((out.returncode, out.stderr), (0, ""))
        return json.loads(out.stdout)["hookSpecificOutput"] if out.stdout.strip() else None

    def test_the_hook_denies_an_upgrade_and_allows_the_default(self):
        decision = self.pre({"subagent_type": "arsenal:builder", "model": "opus", "prompt": "x"})
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("subagent cost guard", decision["permissionDecisionReason"])
        self.assertIsNone(self.pre({"subagent_type": "arsenal:builder", "prompt": "x"}))
        self.assertEqual(self.pre({"subagent_type": "arsenal:builder", "model": "fable"}, tool="Task")["permissionDecision"],
                         "deny")

    def test_an_attended_session_is_asked_and_an_unattended_one_is_denied(self):
        call = {"subagent_type": "arsenal:builder", "model": "opus"}
        for mode, expected in (("default", "ask"), ("acceptEdits", "ask"), ("plan", "ask"),
                               ("bypassPermissions", "deny"), ("dontAsk", "deny"), ("auto", "deny")):
            with self.subTest(mode=mode):
                self.assertEqual(self.pre(call, mode=mode)["permissionDecision"], expected)

    def test_switches_allow_the_override_and_minimal_keeps_the_guard(self):
        call = {"subagent_type": "arsenal:builder", "model": "opus"}
        self.assertIsNone(self.pre(call, ARSENAL_SUBAGENT_MODEL="any"))
        self.assertIsNone(self.pre(call, ARSENAL_GUARD="off"))
        self.assertEqual(self.pre(call, ARSENAL_PROFILE="minimal")["permissionDecision"], "deny")
        self.assertIsNone(self.pre(call, ARSENAL_PROFILE="minimal", ARSENAL_SUBAGENT_MODEL="any"))

    def test_a_missing_helper_allows(self):
        (self.hooks / "guard_models.py").unlink()
        self.assertIsNone(self.pre({"subagent_type": "arsenal:builder", "model": "opus"}))


if __name__ == "__main__":
    unittest.main()
