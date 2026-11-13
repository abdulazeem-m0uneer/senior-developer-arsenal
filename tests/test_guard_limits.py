import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_guard import GuardCase  # noqa: E402  (a repository, a private state file, run_hook)

SESSION = {"session_id": "s1", "permission_mode": "bypassPermissions"}


class LimitsCase(GuardCase):
    def setUp(self):
        super().setUp()
        self.limits = self.dir / ".claude" / "arsenal-run-limits.json"
        self.env = {"CLAUDE_PROJECT_DIR": str(self.dir), "ARSENAL_RUN_LIMITS": ""}

    def set_limits(self, value):
        self.limits.parent.mkdir(exist_ok=True)
        self.limits.write_text(value if isinstance(value, str) else json.dumps(value))

    def call(self, tool="Read", env=None, **tool_input):
        payload = {**SESSION, "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": str(self.dir)}
        out = self.run_hook("pre", payload, env={**self.env, **(env or {})})
        return json.loads(out)["hookSpecificOutput"] if out else None

    def denied(self, *args, **kwargs):
        out = self.call(*args, **kwargs)
        if out is None:
            return ""
        self.assertEqual((out["hookEventName"], out["permissionDecision"]), ("PreToolUse", "deny"))
        self.assertLess(len(out["permissionDecisionReason"]), 500)
        return out["permissionDecisionReason"]


class RunLimitTest(LimitsCase):
    def test_without_a_limits_file_nothing_is_counted_or_enforced(self):
        for _ in range(3):
            self.assertIsNone(self.call("Bash", command="ls"))
        self.assertFalse(self.state.exists())

    def test_tool_call_limit_denies_every_tool_and_names_the_handoff(self):
        self.set_limits({"max_tool_calls": 2})
        self.assertIsNone(self.call("Bash", command="ls"))
        self.assertIsNone(self.call("Edit", file_path="src/app.py"))
        for tool, tool_input in (("Bash", {"command": "ls"}), ("Read", {"file_path": "a.py"}), ("Agent", {"prompt": "go on"}),
                                 ("Write", {"file_path": "src/app.py"}), ("Edit", {"file_path": str(self.limits)})):
            reason = self.denied(tool, **tool_input)
            self.assertIn("2 of 2 tool calls used", reason, tool)
            self.assertIn(str(self.limits), reason)
            self.assertIn("handoff", reason)
        self.assertEqual(self.state.read_text().count('"call"'), 2)  # denied calls are not counted

    def test_the_report_can_still_be_written_after_the_limit(self):
        self.set_limits({"max_tool_calls": 1})
        self.call()
        self.assertIsNone(self.call("Write", file_path="docs/HANDOFF.md"))
        self.assertIsNone(self.call("Edit", file_path=str(self.dir / "report.MD")))
        self.assertTrue(self.denied("Write", file_path="notes.md.py"))
        self.assertTrue(self.denied("Write", file_path=None))
        self.assertTrue(self.denied("Bash", command="cat > HANDOFF.md"))

    def test_an_existing_report_can_be_read_before_it_is_edited(self):
        # Claude Code refuses to Edit or overwrite a file that was not read first, so Read must pass too
        self.set_limits({"max_tool_calls": 1})
        self.call()
        self.assertIsNone(self.call("Read", file_path="docs/HANDOFF.md"))
        self.assertTrue(self.denied("Read", file_path="src/app.py"))

    def test_the_damaged_limits_file_can_be_read_to_repair_it(self):
        self.set_limits("{")
        self.assertIsNone(self.call("Read", file_path=str(self.limits)))
        self.assertTrue(self.denied("Read", file_path="other.json"))

    def test_limit_boundaries_are_exact(self):
        guard_limits = sys.modules["guard_limits"]
        reached = guard_limits.reached
        self.assertEqual(reached({"max_minutes": 30}, 0, 1000, 1000 + 1800 - 1), "")
        self.assertNotEqual(reached({"max_minutes": 30}, 0, 1000, 1000 + 1800), "")
        self.assertNotEqual(reached({"max_minutes": 30}, 0, 1000, 1000 + 1800 + 1), "")
        self.assertEqual(reached({"deadline": 5000}, 0, None, 4999), "")
        self.assertNotEqual(reached({"deadline": 5000}, 0, None, 5000), "")
        self.assertEqual(reached({"max_tool_calls": 3}, 2, None, 0), "")
        self.assertNotEqual(reached({"max_tool_calls": 3}, 3, None, 0), "")

    def test_the_limit_applies_when_a_human_is_present_too(self):
        self.set_limits({"max_tool_calls": 1})
        self.call()
        payload = {"session_id": "s1", "permission_mode": "default", "tool_name": "Bash", "tool_input": {"command": "ls"}}
        out = json.loads(self.run_hook("pre", payload, env=self.env))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_minutes_are_counted_from_the_first_call_of_the_session(self):
        self.set_limits({"max_minutes": 30})
        self.assertIsNone(self.call())
        self.assertIsNone(self.call())
        self.state.write_text(json.dumps({"event": "call", "time": int(time.time()) - 31 * 60}) + "\n")
        self.assertIn("30 minutes used", self.denied())
        self.set_limits({"max_minutes": 0.5})
        self.state.write_text(json.dumps({"event": "call", "time": int(time.time()) - 20}) + "\n")
        self.assertIsNone(self.call())

    def test_deadline_is_absolute_and_needs_no_session_state(self):
        self.set_limits({"deadline": "2020-01-01T00:00:00Z"})
        self.assertIn("deadline has passed", self.denied())
        payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}}  # no session id: nothing can be counted
        env = {**self.env, "HANDOFF_SNAPSHOT": ""}
        self.assertIn("deadline has passed", self.run_hook("pre", payload, env=env))
        self.set_limits({"deadline": "2999-01-01T00:00:00+02:00", "max_tool_calls": 1})
        self.assertEqual(self.run_hook("pre", payload, env=env), "")
        self.assertEqual(self.run_hook("pre", payload, env=env), "")  # uncounted, so the call limit cannot bite
        self.assertIsNone(self.call())

    def test_a_damaged_limits_file_stops_work_until_it_is_repaired(self):
        damaged = ["", "{not json", "[1]", '"text"', '{"max_tool_call": 5}', '{"max_tool_calls": 0}',
                   '{"max_tool_calls": -3}', '{"max_tool_calls": "5"}', '{"max_tool_calls": true}', '{"max_minutes": null}',
                   '{"deadline": "tomorrow"}', '{"deadline": "2999-01-01T00:00:00"}', '{"deadline": 5}', "\xff\xfe"]
        for text in damaged:
            self.set_limits(text)
            reason = self.denied("Bash", command="ls")
            self.assertIn("the limits file", reason, text)
            self.assertNotIn("tool calls used", reason)
        self.assertIsNone(self.call("Write", file_path=str(self.limits)))  # the repair itself
        self.assertIsNone(self.call("Edit", file_path="HANDOFF.md"))
        self.assertTrue(self.denied("Write", file_path="other.json"))
        self.set_limits({})  # valid and empty: no limit
        self.assertIsNone(self.call("Bash", command="ls"))

    def test_where_the_file_is_looked_for(self):
        self.set_limits({"deadline": "2020-01-01T00:00:00Z"})
        deep = self.dir / "a" / "b"
        deep.mkdir(parents=True)
        payload = {**SESSION, "tool_name": "Read", "tool_input": {}, "cwd": str(deep)}
        no_project = {"CLAUDE_PROJECT_DIR": "", "ARSENAL_RUN_LIMITS": ""}
        self.assertIn("deny", self.run_hook("pre", payload, env=no_project))  # upward from the working directory
        elsewhere = {**payload, "cwd": self.outside.name}
        self.assertEqual(self.run_hook("pre", elsewhere, cwd=self.outside.name, env=no_project), "")
        self.assertIn("deny", self.run_hook("pre", elsewhere, cwd=self.outside.name, env=self.env))  # the project wins
        other = Path(self.outside.name) / "limits.json"
        other.write_text("{}")
        self.assertIsNone(self.call(env={"ARSENAL_RUN_LIMITS": str(other)}))  # an explicit path replaces the search
        self.assertIsNone(self.call(env={"ARSENAL_RUN_LIMITS": str(other) + ".missing"}))

    def test_opt_out_and_a_destructive_command_under_a_limit(self):
        self.set_limits({"max_tool_calls": 1})
        self.call()
        self.assertIsNone(self.call(env={"ARSENAL_GUARD": "off"}))
        self.assertTrue(self.denied(env={"ARSENAL_GUARD_DESTRUCTIVE": "allow"}))  # that switch is not for limits
        self.set_limits({"max_tool_calls": 50})
        self.assertIn("git stash", self.denied("Bash", command="git reset --hard"))

    def test_stop_gate_is_silent_once_the_limit_is_reached(self):
        self.start()
        self.write("src/app.py")
        self.bash("pytest -q", failed=True)
        self.set_limits({"max_tool_calls": 1})
        self.call()
        self.assertEqual(self.stop(env=self.env), "")
        self.set_limits("{broken")
        self.assertEqual(self.stop(env=self.env), "")
        self.limits.unlink()  # the operator lifts the limit: the gates are back
        self.assertIn("src/app.py", self.stop(env=self.env))

    def test_stop_gate_still_blocks_inside_the_limits(self):
        self.start()
        self.write("src/app.py")
        self.set_limits({"max_tool_calls": 5, "deadline": "2999-01-01T00:00:00Z"})
        self.call()
        self.assertIn("src/app.py", self.stop(env=self.env))

    def test_a_resumed_session_keeps_its_count_and_start_time(self):
        self.set_limits({"max_tool_calls": 3})
        self.start()
        self.call()
        self.call()
        first = json.loads(self.state.read_text().splitlines()[1])["time"]
        self.start("resume")  # rewrites the baseline
        events = [json.loads(line) for line in self.state.read_text().splitlines()]
        self.assertEqual([event["event"] for event in events], ["baseline", "run"])
        self.assertEqual((events[1]["calls"], events[1]["time"]), (2, first))
        self.assertIsNone(self.call())
        self.assertIn("3 of 3 tool calls used", self.denied())

    def test_damaged_counter_lines_are_ignored(self):
        self.set_limits({"max_tool_calls": 2, "max_minutes": 10})
        self.state.write_text('{"event": "call", "time": "soon"}\n{"event": "run", "calls": "many", "time": null}\nnot json\n')
        self.assertIn("2 of 2 tool calls used", self.denied())  # each damaged line still counts as one call


if __name__ == "__main__":
    unittest.main()
