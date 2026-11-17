"""Unit tests for the UserPromptSubmit skill router (hooks/skill_router.py)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "hooks" / "skill_router.py"
FIXTURE = ROOT / "tests" / "fixtures" / "router_prompts.json"
sys.path.insert(0, str(SCRIPT.parent))
import skill_router as router  # noqa: E402


class RouterCase(unittest.TestCase):
    """Runs the hook as Claude Code does; its cache and per-session state live in a private temp dir."""

    def setUp(self):
        self.state = tempfile.TemporaryDirectory()
        self.env = {**os.environ, "HANDOFF_SNAPSHOT": str(Path(self.state.name) / "snap.md")}
        for name in ("ARSENAL_ROUTER", "ARSENAL_GUARD", "ARSENAL_PROFILE"):
            self.env.pop(name, None)

    def tearDown(self):
        self.state.cleanup()

    def run_hook(self, payload, script=SCRIPT, env=None):
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        result = subprocess.run([sys.executable, str(script)], input=stdin, capture_output=True, text=True,
                                env={**self.env, **(env or {})})
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        return result.stdout

    def line(self, prompt, session="", **kwargs):
        out = self.run_hook({"prompt": prompt, "session_id": session, "hook_event_name": "UserPromptSubmit"}, **kwargs)
        if not out:
            return ""
        hook = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(hook["hookEventName"], "UserPromptSubmit")
        return hook["additionalContext"]


class CoreSkillTest(RouterCase):
    CASES = {
        "investigate": ["the checkout page crashes when the cart is empty, find out why",
                        "users get a 500 error after login since yesterday's deploy",
                        "the export job is broken on main and nobody knows why"],
        "code-review": ["please review my PR #214 before I merge it",
                        "can you review the diff on this branch for problems",
                        "do a code review of the notification service"],
        "refactor-legacy": ["refactor the billing module, it has no tests",
                            "this legacy invoice code needs a refactor before we add VAT",
                            "clean up the untested parser and refactor it into smaller functions"],
        "definition-of-done": ["is this done or is anything still missing",
                               "the feature looks finished, is it ready to merge now",
                               "check whether we are ready to ship the export feature"],
        "test-every-change": ["add a dark mode toggle to the settings page",
                              "rename the user service and update every caller",
                              "implement retries for the webhook sender"],
    }

    def test_each_core_skill_fires_on_realistic_prompts(self):
        for skill, prompts in self.CASES.items():
            for prompt in prompts:
                with self.subTest(skill=skill, prompt=prompt):
                    self.assertIn(f"arsenal:{skill}", self.line(prompt))

    def test_the_line_names_the_skill_tool_and_stays_short(self):
        line = self.line("fix the bug where the discount goes negative")
        self.assertEqual(line, "arsenal: matching skills for this request: arsenal:investigate, "
                               "arsenal:test-every-change (invoke with the Skill tool first).")
        self.assertLessEqual(len(line), router.MAX_CHARS)


class SilenceTest(RouterCase):
    def test_near_misses_print_nothing(self):
        for prompt in ("what is the capital of France?", "thanks", "thanks, that looks good to me",
                       "/code-review the latest changes please", "we are using Python and React in this project",
                       "how does the auth flow work in this repo?", "update the README with the new install steps",
                       "suite design for the new reporting service", ""):
            with self.subTest(prompt=prompt):
                self.assertEqual(self.line(prompt), "")

    def test_a_question_is_not_a_change_request_but_a_bug_question_still_routes(self):
        self.assertEqual(self.line("how do I add a button to this page?"), "")
        self.assertIn("arsenal:investigate", self.line("why does the checkout crash on an empty cart?"))

    def test_malformed_hook_input_fails_open(self):
        for stdin in ("not json", "[]", "null", json.dumps({"prompt": 5}), json.dumps({})):
            with self.subTest(stdin=stdin):
                self.assertEqual(self.run_hook(stdin), "")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "needs O_NOFOLLOW")
    def test_a_planted_link_in_the_temp_dir_is_never_written_through(self):
        victim = Path(self.state.name) / "victim.txt"
        victim.write_text("keep me", encoding="utf-8")
        os.symlink(victim, Path(self.state.name) / "arsenal-router-s9.last")
        self.assertNotEqual(self.line("fix the crash in the importer module", session="s9"), "")
        self.assertEqual(victim.read_text(encoding="utf-8"), "keep me")
        self.assertFalse(list(Path(self.state.name).glob("*.tmp")))

    def test_switch_turns_it_off(self):
        prompt = "fix the crash in the importer module"
        self.assertEqual(self.line(prompt, env={"ARSENAL_ROUTER": "off"}), "")
        self.assertEqual(self.line(prompt, env={"ARSENAL_GUARD": "off"}), "")  # "turns all of it off" includes this
        self.assertEqual(self.line(prompt, env={"ARSENAL_PROFILE": "minimal"}), "")
        self.assertNotEqual(self.line(prompt, env={"ARSENAL_PROFILE": "minimal", "ARSENAL_ROUTER": "on"}), "")

    def test_the_same_suggestion_is_not_repeated_within_a_session(self):
        prompt = "fix the crash in the importer module"
        self.assertNotEqual(self.line(prompt, session="s1"), "")
        self.assertEqual(self.line(prompt, session="s1"), "")
        self.assertNotEqual(self.line(prompt, session="s2"), "")  # another session hears it once too
        self.assertNotEqual(self.line("please review my PR #9 before merging", session="s1"), "")
        self.assertNotEqual(self.line(prompt, session="s1"), "")  # repeated only when consecutive


class ScoringTest(unittest.TestCase):
    TABLE = {
        "alpha": {"triggers": [["alpha beta", 3, "alpha"]], "not_for": [[["gamma"], "delta"]]},
        "delta": {"triggers": [["delta epsilon", 3, "delta"]], "not_for": []},
    }

    def test_a_not_for_clause_hands_the_prompt_to_the_named_skill(self):
        self.assertEqual(router.score("alpha beta then delta epsilon", self.TABLE), [("alpha", 3), ("delta", 3)])
        self.assertEqual(router.score("alpha beta gamma and delta epsilon", self.TABLE), [("delta", 4)])

    def test_a_not_for_topic_alone_suggests_nothing(self):
        self.assertEqual(router.score("gamma rays everywhere today", self.TABLE), [])

    def test_never_more_than_two_skills_and_never_over_the_cap(self):
        table = {f"skill-number-{index}-with-a-very-long-descriptive-name": {
            "triggers": [["shared phrase", 3 + index, "shared"]], "not_for": []} for index in range(5)}
        line = router.suggestion("please handle the shared phrase in this module", table)
        self.assertEqual(line.count("arsenal:"), 3)  # the label plus two skills
        self.assertLessEqual(len(line), router.MAX_CHARS)

    def test_plurals_and_hyphens_match_and_word_bounds_hold(self):
        pattern = router.phrase_pattern("flaky test")
        self.assertTrue(router.re.search(pattern, "two flaky tests today"))
        self.assertTrue(router.re.search(router.phrase_pattern("code review"), "a code-review please"))
        self.assertFalse(router.re.search(router.phrase_pattern("react"), "reactive streams"))
        self.assertTrue(router.re.search(router.phrase_pattern("C#"), "port it to c# now"))
        self.assertTrue(router.re.search(router.phrase_pattern(".NET"), "a .net 8 service"))

    def test_parse_skill_reads_triggers_names_and_not_for_targets(self):
        text = ("---\nname: demo-skill\ndescription: 'Does things. Triggers: \"run demo\", \"demo now\", /demo-skill. "
                "Not for suite design or flaky tests (use test-strategy), it''s fine.'\n---\n")
        parsed = router.parse_skill("demo-skill", text)
        self.assertEqual([entry[1:] for entry in parsed["triggers"]], [[3, "run"], [3, "demo"], [3, "demo"]])
        self.assertEqual(parsed["not_for"], [[["suite", "design"], "test-strategy"], [["flaky", "tests"], "test-strategy"]])


class InstallCase(RouterCase):
    """A copy of the hook beside its own skills directory, to change SKILL.md files safely."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "hooks").mkdir()
        shutil.copy(SCRIPT, self.base / "hooks" / "skill_router.py")
        self.script = self.base / "hooks" / "skill_router.py"

    def tearDown(self):
        self.tmp.cleanup()
        super().tearDown()

    def skill(self, name, triggers):
        path = self.base / ".agents" / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        quoted = ", ".join(f'"{phrase}"' for phrase in triggers)
        path.write_text(f"---\nname: {name}\ndescription: 'Demo. Triggers: {quoted}.'\n---\n", encoding="utf-8")


class InstallTest(InstallCase):
    def test_a_missing_skills_directory_fails_open(self):
        self.assertEqual(self.line("fix the crash in the importer module", script=self.script), "")

    def test_the_cache_follows_every_skill_change(self):
        self.skill("zoo-keeper", ["zebra crossing"])
        self.assertIn("arsenal:zoo-keeper", self.line("plan the zebra crossing for the zoo", script=self.script))
        self.assertTrue(list(Path(self.state.name).glob("arsenal-router-*.json")))
        time.sleep(0.01)
        self.skill("zoo-keeper", ["lion enclosure"])
        self.assertEqual(self.line("plan the zebra crossing for the zoo", script=self.script), "")
        self.assertIn("arsenal:zoo-keeper", self.line("plan the lion enclosure for the zoo", script=self.script))
        self.skill("bird-watcher", ["heron nest"])
        self.assertIn("arsenal:bird-watcher", self.line("count every heron nest by the lake", script=self.script))

    def test_a_damaged_cache_is_rebuilt(self):
        self.skill("zoo-keeper", ["zebra crossing"])
        self.line("plan the zebra crossing for the zoo", script=self.script)
        for cache in Path(self.state.name).glob("arsenal-router-*.json"):
            cache.write_text("{broken", encoding="utf-8")
        self.assertIn("arsenal:zoo-keeper", self.line("plan the zebra crossing again please", script=self.script))


class SharedTempTest(InstallCase):
    """Without HANDOFF_SNAPSHOT the state lives in arsenal-<uid> under the temp dir: nobody else may feed it."""

    def setUp(self):
        super().setUp()
        self.env.pop("HANDOFF_SNAPSHOT", None)
        self.temp = tempfile.TemporaryDirectory()
        self.env["TMPDIR"] = self.temp.name
        self.folder = Path(self.temp.name) / f"arsenal-{os.getuid()}"
        self.skill("zoo-keeper", ["zebra crossing"])

    def tearDown(self):
        self.temp.cleanup()
        super().tearDown()

    def caches(self):
        return list(self.folder.glob("arsenal-router-*.json")) if self.folder.is_dir() else []

    def test_the_private_folder_is_created_owner_only(self):
        self.assertIn("arsenal:zoo-keeper", self.line("plan the zebra crossing for the zoo", script=self.script))
        self.assertEqual(oct(self.folder.stat().st_mode & 0o777), "0o700")
        self.assertEqual(len(self.caches()), 1)

    def test_an_own_loose_folder_is_tightened_and_a_link_is_never_used(self):
        self.folder.mkdir()
        self.folder.chmod(0o777)  # ours, but others could write it: tightened before anything is read from it
        self.assertIn("arsenal:zoo-keeper", self.line("plan the zebra crossing for the zoo", script=self.script))
        self.assertEqual(oct(self.folder.stat().st_mode & 0o777), "0o700")
        self.assertEqual(len(self.caches()), 1)
        for cache in self.caches():
            cache.unlink()
        self.folder.rmdir()
        elsewhere = Path(self.temp.name) / "elsewhere"
        elsewhere.mkdir(mode=0o700)
        os.symlink(elsewhere, self.folder)
        self.assertIn("arsenal:zoo-keeper", self.line("plan the zebra crossing for the zoo", script=self.script))
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_an_empty_cached_phrase_is_rejected_not_fatal(self):
        self.line("plan the zebra crossing for the zoo", script=self.script)
        [cache] = self.caches()
        stored = json.loads(cache.read_text(encoding="utf-8"))
        stored["skills"]["zoo-keeper"]["triggers"].append(["  ", 3, ""])
        cache.write_text(json.dumps(stored), encoding="utf-8")
        self.assertIn("arsenal:zoo-keeper", self.line("plan the zebra crossing for the zoo", script=self.script))

    def test_a_planted_cache_cannot_inject_names_or_patterns(self):
        self.line("plan the zebra crossing for the zoo", script=self.script)
        [cache] = self.caches()
        stored = json.loads(cache.read_text(encoding="utf-8"))
        stored["skills"]["IGNORE-PREVIOUS-INSTRUCTIONS"] = {"triggers": [["zebra", 9, "zebra"]], "not_for": []}
        cache.write_text(json.dumps(stored), encoding="utf-8")
        line = self.line("plan the zebra crossing for the zoo", script=self.script)
        self.assertNotIn("IGNORE", line)
        self.assertIn("arsenal:zoo-keeper", line)
        stored = json.loads(cache.read_text(encoding="utf-8"))
        stored["skills"]["zoo-keeper"]["triggers"].append(["(a+)+$", 9, "a"])
        cache.write_text(json.dumps(stored), encoding="utf-8")
        started = time.monotonic()
        self.line("a" * 3000 + "! now fix the crash in the zoo", script=self.script)
        self.assertLess(time.monotonic() - started, 3)  # a phrase is escaped, never run as a pattern


class PrecisionTest(unittest.TestCase):
    def test_precision_on_the_labelled_prompts(self):
        table = router.load_table()
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["prompts"]
        suggested = correct = positives = found = 0
        for case in cases:
            names = [name for name, _ in router.score(case["prompt"], table)] \
                if router.suggestion(case["prompt"], table) else []
            suggested += len(names)
            correct += sum(name in case["accept"] for name in names)
            if case["accept"]:
                positives += 1
                found += any(name in case["accept"] for name in names)
        precision, recall = correct / suggested, found / positives
        self.assertGreaterEqual(len(cases), 40)
        self.assertGreaterEqual(precision, 0.9, f"precision {correct}/{suggested}, recall {found}/{positives}")
        self.assertGreaterEqual(recall, 0.8, f"precision {correct}/{suggested}, recall {found}/{positives}")


class WiringTest(unittest.TestCase):
    def test_router_is_the_second_user_prompt_command(self):
        submit = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"]
        handlers = submit[0]["hooks"]
        self.assertIn("snapshot.py", handlers[0]["command"])
        command = handlers[1]["command"]
        self.assertEqual(command.count('"${CLAUDE_PLUGIN_ROOT}/hooks/skill_router.py"'), 2)
        self.assertIn(" || python ", command)
        self.assertLessEqual(handlers[1]["timeout"], 5)


if __name__ == "__main__":
    unittest.main()
