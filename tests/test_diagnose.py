"""Unit tests for `usage_stats.py diagnose` (usage-stats/scripts/diagnose.py) and the trigger-phrase helper."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents" / "skills" / "usage-stats" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import diagnose  # noqa: E402
import skill_triggers  # noqa: E402
import usage_stats  # noqa: E402

SESSION = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
CWD = "/work/project"


def line(kind, content, ts, **extra):
    return json.dumps({"type": kind, "sessionId": SESSION, "cwd": CWD, "timestamp": ts,
                       "message": {"role": kind, "content": content}, **extra})


def prompt(text, ts):
    return line("user", text, ts)


def use(tool_id, name, ts, **given):
    return line("assistant", [{"type": "tool_use", "id": tool_id, "name": name, "input": given}], ts)


def result(tool_id, ts, text="", error=False):
    return line("user", [{"type": "tool_result", "tool_use_id": tool_id, "content": text, "is_error": error}], ts)


def say(text, ts):
    return line("assistant", [{"type": "text", "text": text}], ts)


TABLE = {"investigate": ["investigate bug", "find root cause", "/investigate"],
         "ci-wait": ["wait for CI", "/ci-wait"],
         "frontend-architecture-expert": ["React", "/frontend-architecture-expert"],
         "devops-ci": ["GitHub Actions"], "smoke-test": ["smoke test"], "handoff": ["hand off"]}


class Case(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name) / "projects"

    def transcript(self, *lines, name=SESSION):
        path = self.dir / "proj" / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")
        return path

    def kinds(self, *lines, table=TABLE):
        return [(item["kind"], item.get("skill")) for item in
                diagnose.findings(diagnose.read(self.transcript(*lines)), table)]


class TriggerTest(unittest.TestCase):
    def test_triggers_are_read_from_every_skill_description(self):
        table = skill_triggers.triggers(usage_stats.SKILLS)
        self.assertIn("find root cause", table["investigate"])
        self.assertIn("/investigate", table["investigate"])
        self.assertNotIn("use test-strategy", " ".join(table["test-every-change"]))  # "Not for" part left out
        self.assertGreaterEqual(len(table), 55)

    def test_whole_words_any_case_and_bad_skill_files(self):
        self.assertEqual(skill_triggers.matching("Please FIND ROOT  CAUSE now", TABLE), {"investigate": "find root cause"})
        self.assertEqual(skill_triggers.matching("prefind root causes", TABLE), {})
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "broken").mkdir()
            (Path(folder) / "broken" / "SKILL.md").write_bytes(b"\xff\xfe")
            (Path(folder) / "plain").mkdir()
            (Path(folder) / "plain" / "SKILL.md").write_text("---\nname: plain\ndescription: 'no triggers here'\n---\n")
            self.assertEqual(skill_triggers.triggers(folder), {})


class MissedSkillTest(Case):
    def test_a_trigger_phrase_with_no_invocation_is_a_missed_skill(self):
        found = diagnose.findings(diagnose.read(self.transcript(prompt("find root cause of the crash", "2026-11-10T10:00:00Z"))), TABLE)
        self.assertEqual([(item["kind"], item["skill"], item["time"]) for item in found],
                         [("missed-skill", "investigate", "2026-11-10T10:00:00Z")])
        self.assertIn('"find root cause"', found[0]["detail"])
        self.assertIn("/arsenal:investigate", found[0]["fix"])

    def test_an_invocation_anywhere_in_the_session_or_a_subagent_clears_it(self):
        self.assertEqual(self.kinds(prompt("find root cause", "2026-11-10T10:00:00Z"),
                                    use("t1", "Skill", "2026-11-10T10:01:00Z", skill="arsenal:investigate")), [])
        self.assertEqual(self.kinds(prompt("wait for CI please", "2026-11-10T10:00:00Z"),
                                    prompt("<command-name>/arsenal:ci-wait</command-name>", "2026-11-10T10:00:01Z")), [])
        main = self.transcript(prompt("find root cause", "2026-11-10T10:00:00Z"))
        folder = main.with_suffix("") / "subagents"
        folder.mkdir(parents=True)
        (folder / "agent-1.jsonl").write_text(line("assistant", [{"type": "tool_use", "id": "s", "name": "Skill",
                                                                 "input": {"skill": "arsenal:investigate"}}],
                                                   "2026-11-10T10:02:00Z", isSidechain=True) + "\n[1]\nnot json\n")
        self.assertEqual(diagnose.findings(diagnose.read(main), TABLE), [])

    def test_noise_is_not_a_missed_skill(self):
        brief = "find root cause, wait for CI, then a smoke test and hand off"  # four topics: a brief, not one ask
        self.assertEqual(self.kinds(
            prompt(brief, "2026-11-10T10:00:00Z"),
            prompt("we use React here", "2026-11-10T10:01:00Z"),  # one-word stack name
            prompt("<pasted_content id='x'>wait for CI</pasted_content> thanks", "2026-11-10T10:02:00Z"),
            line("user", "find root cause", "2026-11-10T10:03:00Z", isMeta=True),
            result("t9", "2026-11-10T10:04:00Z", text="find root cause in the output")), [])

    def test_each_skill_is_reported_once(self):
        self.assertEqual(self.kinds(prompt("find root cause", "2026-11-10T10:00:00Z"),
                                    prompt("find root cause again", "2026-11-10T10:05:00Z")),
                         [("missed-skill", "investigate")])


class CoreTest(Case):
    def test_source_edit_without_a_test_edit(self):
        self.assertEqual(self.kinds(use("e1", "Edit", "2026-11-10T10:00:00Z", file_path=f"{CWD}/app/service.py")),
                         [("untested-change", None)])
        self.assertEqual(self.kinds(use("e1", "Edit", "2026-11-10T10:00:00Z", file_path=f"{CWD}/app/service.py"),
                                    use("e2", "Write", "2026-11-10T10:01:00Z", file_path=f"{CWD}/tests/test_service.py")),
                         [])

    def test_a_done_claim_needs_a_passing_check_after_the_last_edit(self):
        edits = [use("e1", "Edit", "2026-11-10T10:00:00Z", file_path=f"{CWD}/app/service.py"),
                 use("e2", "Edit", "2026-11-10T10:00:30Z", file_path=f"{CWD}/tests/test_service.py")]
        self.assertEqual(self.kinds(*edits, say("All done, fixed.", "2026-11-10T10:02:00Z")), [("unverified-done", None)])
        passed = [use("b1", "Bash", "2026-11-10T10:01:00Z", command="pytest -q"), result("b1", "2026-11-10T10:01:10Z")]
        self.assertEqual(self.kinds(*edits, *passed, say("All done.", "2026-11-10T10:02:00Z")), [])
        before = [use("b0", "Bash", "2026-11-10T09:00:00Z", command="pytest -q"), result("b0", "2026-11-10T09:00:10Z")]
        self.assertEqual(self.kinds(*before, *edits, say("Done.", "2026-11-10T10:02:00Z")), [("unverified-done", None)])
        self.assertEqual(self.kinds(*edits, say("Next I will refactor the parser.", "2026-11-10T10:02:00Z")), [])

    def test_a_failure_needs_a_later_pass_or_a_lesson(self):
        fail = [use("b1", "Bash", "2026-11-10T10:00:00Z", command="pytest -q"),
                result("b1", "2026-11-10T10:00:05Z", text="1 failed", error=True)]
        self.assertEqual(self.kinds(*fail), [("unlearned-fail", None)])
        green = [use("b2", "Bash", "2026-11-10T10:01:00Z", command="pytest -q"), result("b2", "2026-11-10T10:01:05Z")]
        self.assertEqual(self.kinds(*fail, *green), [])
        lesson = [use("l1", "Bash", "2026-11-10T10:02:00Z",
                      command='python3 .agents/skills/lessons-learned/scripts/lessons.py add --tags ci --mistake m '
                              '--cause c --rule r'),
                  result("l1", "2026-11-10T10:02:01Z", text="added L001")]
        self.assertEqual(self.kinds(*fail, *lesson), [])


class CliTest(Case):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = usage_stats.main(["diagnose", *args])
        return code, out.getvalue(), err.getvalue()

    def test_by_path_session_last_and_json(self):
        path = self.transcript(use("e1", "Edit", "2026-11-10T10:00:00Z", file_path=f"{CWD}/app/service.py"))
        code, out, _ = self.run_cli(str(path))
        self.assertEqual(code, 0)
        self.assertIn(f"## Diagnosis of session {SESSION}", out)
        self.assertIn("2026-11-10T10:00:00Z untested-change", out)
        self.assertNotIn("service.py", out)  # paths are never printed
        self.assertEqual(self.run_cli("--session", SESSION, "--dir", str(self.dir))[0], 0)
        code, out, _ = self.run_cli("--last", "--dir", str(self.dir), "--json")
        self.assertEqual(json.loads(out)["findings"][0]["kind"], "untested-change")

    def test_a_clean_session_and_usage_errors(self):
        path = self.transcript(prompt("hello", "2026-11-10T10:00:00Z"))
        self.assertIn("no missed skill and no operating-core gap", self.run_cli(str(path))[1])
        self.assertEqual(self.run_cli("missing.jsonl")[0], 2)
        self.assertEqual(self.run_cli("--session", "nope", "--dir", str(self.dir))[0], 2)
        self.assertEqual(self.run_cli("--last", "--dir", str(self.dir / "absent"))[0], 2)
        self.assertEqual(self.run_cli("--dir", str(self.dir))[0], 2)  # nothing chosen
        self.assertEqual(self.run_cli("--session", SESSION, "--last")[0], 2)
        empty = Path(tempfile.mkdtemp(dir=self.dir.parent))
        self.assertEqual(self.run_cli("--last", "--dir", str(empty))[0], 2)

    def test_garbage_lines_are_skipped(self):
        path = self.transcript("not json", "[1]", json.dumps({"type": "user", "message": "x"}),
                               prompt("find root cause", "2026-11-10T10:00:00Z"))
        self.assertEqual(self.run_cli(str(path))[0], 0)


if __name__ == "__main__":
    unittest.main()
