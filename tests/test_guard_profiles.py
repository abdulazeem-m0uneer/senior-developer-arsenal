"""ARSENAL_PROFILE=minimal|standard|strict sets the guard's per-check switches; an explicit switch always wins."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_guard import GuardCase, guard  # noqa: E402  (the module discovery already loaded: no second copy)

DESTRUCTIVE = "git reset --hard"
LESSON = "while pgrep -f vitest; do sleep 1; done"


class SettingTest(unittest.TestCase):
    def setting(self, name, **env):
        clean = {k: v for k, v in os.environ.items() if not k.startswith("ARSENAL_")}
        with mock.patch.dict(os.environ, {**clean, **env}, clear=True):
            return guard.setting(name)

    def test_profile_by_switch_matrix(self):
        switches = ("ARSENAL_GUARD_STOP", "ARSENAL_GUARD_DEADCODE", "ARSENAL_LESSON_GUARDS", "ARSENAL_SUBAGENT_MODEL",
                    "ARSENAL_GUARD_DESTRUCTIVE", "ARSENAL_GUARD_SCOPE", "ARSENAL_GUARD")
        expected = {
            "minimal": {"ARSENAL_GUARD_STOP": "off", "ARSENAL_GUARD_DEADCODE": "off", "ARSENAL_LESSON_GUARDS": "off"},
            "standard": {}, "": {}, "bogus": {},
            "strict": {"ARSENAL_GUARD_DESTRUCTIVE": "deny"},
        }
        for profile, values in expected.items():
            for name in switches:
                with self.subTest(profile=profile, switch=name):
                    self.assertEqual(self.setting(name, ARSENAL_PROFILE=profile), values.get(name, ""))

    def test_an_explicit_switch_wins_over_every_profile(self):
        for profile in ("minimal", "standard", "strict"):
            with self.subTest(profile=profile):
                self.assertEqual(self.setting("ARSENAL_GUARD_STOP", ARSENAL_PROFILE=profile, ARSENAL_GUARD_STOP="on"), "on")
                self.assertEqual(self.setting("ARSENAL_GUARD_DESTRUCTIVE", ARSENAL_PROFILE=profile,
                                              ARSENAL_GUARD_DESTRUCTIVE="ask"), "ask")

    def test_profile_names_and_values_ignore_case_and_spaces(self):
        self.assertEqual(self.setting("ARSENAL_GUARD_DESTRUCTIVE", ARSENAL_PROFILE=" Strict "), "deny")
        self.assertEqual(self.setting("ARSENAL_GUARD_STOP", ARSENAL_PROFILE="minimal", ARSENAL_GUARD_STOP=" "), "off")


class ProfileHookTest(GuardCase):
    def decision(self, command, mode="default", **env):
        payload = {"tool_name": "Bash", "tool_input": {"command": command}, "permission_mode": mode}
        out = self.run_hook("pre", payload, env=env)
        return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else None

    def untested_change_blocks(self, **env):
        self.start()
        self.write("src/app.py")
        return "no test change" in self.stop(env=env)

    def test_standard_and_unset_keep_todays_behaviour(self):
        for env in ({}, {"ARSENAL_PROFILE": "standard"}, {"ARSENAL_PROFILE": "unknown"}):
            with self.subTest(env=env):
                self.assertEqual(self.decision(DESTRUCTIVE, **env), "ask")
                self.assertEqual(self.decision(DESTRUCTIVE, "bypassPermissions", **env), "deny")
                self.assertEqual(self.decision(LESSON, **env), "deny")

    def test_minimal_keeps_only_the_destructive_gate(self):
        self.assertEqual(self.decision(DESTRUCTIVE, ARSENAL_PROFILE="minimal"), "ask")
        self.assertIsNone(self.decision(LESSON, ARSENAL_PROFILE="minimal"))
        self.assertFalse(self.untested_change_blocks(ARSENAL_PROFILE="minimal"))

    def test_minimal_with_an_explicit_stop_switch_still_gates_the_stop(self):
        self.assertTrue(self.untested_change_blocks(ARSENAL_PROFILE="minimal", ARSENAL_GUARD_STOP="on"))

    def test_the_stop_switch_alone_turns_off_the_stop_gate(self):
        self.assertFalse(self.untested_change_blocks(ARSENAL_GUARD_STOP="off"))

    def test_strict_denies_a_destructive_command_in_every_mode(self):
        for mode in ("default", "acceptEdits", "plan", "bypassPermissions"):
            with self.subTest(mode=mode):
                self.assertEqual(self.decision(DESTRUCTIVE, mode, ARSENAL_PROFILE="strict"), "deny")
        self.assertEqual(self.decision(DESTRUCTIVE, ARSENAL_PROFILE="strict", ARSENAL_GUARD_DESTRUCTIVE="ask"), "ask")
        self.assertIsNone(self.decision(DESTRUCTIVE, ARSENAL_PROFILE="strict", ARSENAL_GUARD_DESTRUCTIVE="allow"))

    def test_the_master_switch_still_turns_everything_off(self):
        for profile in ("minimal", "standard", "strict"):
            self.assertIsNone(self.decision(DESTRUCTIVE, ARSENAL_PROFILE=profile, ARSENAL_GUARD="off"))


if __name__ == "__main__":
    unittest.main()
