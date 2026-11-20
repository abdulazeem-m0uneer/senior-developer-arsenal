"""lessons.py commands that turn repeats into guards: unguarded, hits, the promotion threshold, promote --keep-rule,
and the lesson-guard registry check."""
import json
import os
import re
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lessons import LedgerCase, lessons, promotion  # noqa: E402

import guard_hits  # noqa: E402  (on sys.path through test_lessons)


class GuardLedgerCase(LedgerCase):
    def setUp(self):
        super().setUp()
        self.hits_file = self.dir / "hits.jsonl"
        patch = mock.patch.dict(os.environ, {"LESSONS_GUARD_HITS_FILE": str(self.hits_file)})
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("LESSONS_PROMOTE_AT", None)

    def lesson(self, mistake, rule, hits=1, extra=()):
        lesson_id = re.search(r"added ([LG]\d{3,})", self.add(mistake, rule=rule, extra=extra)[1]).group(1)
        for _ in range(hits - 1):
            self.run_cli("bump", lesson_id)
        return lesson_id


class UnguardedTests(GuardLedgerCase):
    def setUp(self):
        super().setUp()
        self.once = self.lesson("Alpha happened once", "alpha rule unique")
        self.twice = self.lesson("Bravo happened twice", "bravo rule unique", hits=2)
        self.four = self.lesson("Charlie happened four times", "charlie rule unique", hits=4)
        self.guard = self.dir / "guard.py"
        self.guard.write_text("", encoding="utf-8")

    def listed(self, *argv):
        code, out, err = self.run_cli("unguarded", *argv)
        self.assertEqual(code, 0, err)
        return [line.split()[0] for line in out.splitlines()[:-1]], out.splitlines()[-1]

    def test_lists_repeats_without_a_guard_most_hits_first(self):
        ids, summary = self.listed("--min", "2")
        self.assertEqual(ids, [self.four, self.twice])
        self.assertEqual(summary, "2 lessons seen 2+ times without a guard")
        self.assertEqual(self.listed()[0], [self.four])  # default threshold 3

    def test_guarded_lessons_drop_out_and_archived_ones_stay(self):
        self.run_cli("promote", self.four, "--guard", str(self.guard))
        self.run_cli("archive", self.twice)
        _, out, _ = self.run_cli("unguarded", "--min", "2")
        self.assertNotIn(self.four, out)
        self.assertIn(f"{self.twice} hits:2 [archive]", out)

    def test_global_and_named_ledgers_are_included_once(self):
        self.lesson("Delta global mistake", "delta rule unique", hits=2, extra=("--global",))
        other = self.dir / "other.md"
        self.run_cli("--file", str(other), "add", "--mistake", "Echo other mistake", "--cause", "c", "--rule",
                     "echo rule unique")  # parsed last: --file given twice, the later wins
        self.run_cli("--file", str(other), "bump", "L001")
        _, out, _ = self.run_cli("unguarded", "--min", "2", str(other), self.file)
        self.assertIn("G001 hits:2 [active]", out)
        self.assertIn(f"L001 hits:2 [active] {other}", out)
        self.assertEqual(out.count("bravo rule unique"), 1)
        self.assertTrue(out.endswith("4 lessons seen 2+ times without a guard\n"))

    def test_globalized_lessons_are_counted_in_the_global_ledger_only(self):
        self.run_cli("globalize", self.four)
        _, out, _ = self.run_cli("unguarded")
        self.assertEqual(out.count("charlie rule unique"), 1)
        self.assertIn("G001 hits:4", out)

    def test_a_missing_named_ledger_and_a_bad_threshold_are_usage_errors(self):
        code, _, err = self.run_cli("unguarded", str(self.dir / "nope.md"))
        self.assertEqual(code, 2)
        self.assertIn("no ledger at", err)
        for bad in ("0", "-2"):
            self.assertEqual(self.run_cli("unguarded", "--min", bad)[0], 2, bad)

    def test_an_empty_ledger_lists_nothing(self):
        self.file = str(self.dir / "empty.md")
        self.assertEqual(self.listed("--min", "1"), ([], "0 lessons seen 1+ times without a guard"))


class ThresholdTests(GuardLedgerCase):
    def setUp(self):
        super().setUp()
        self.twice = self.lesson("Bravo happened twice", "bravo rule unique", hits=2)

    def test_check_min_and_the_environment_set_the_candidate_threshold(self):
        self.assertNotIn("candidate", self.run_cli("check")[1])
        self.assertIn(f"candidate {self.twice} hits:2", self.run_cli("check", "--min", "2")[1])
        with mock.patch.dict(os.environ, {"LESSONS_PROMOTE_AT": "2"}):
            self.assertIn(f"candidate {self.twice} hits:2", self.run_cli("check")[1])
            self.assertIn(f"{self.twice} hits:2", self.run_cli("unguarded")[1])
            self.assertNotIn("candidate", self.run_cli("check", "--min", "3")[1])  # the option wins

    def test_the_bump_hint_follows_the_threshold(self):
        third = self.lesson("Golf ball lost in the pond", "carry spare golf balls always")
        with mock.patch.dict(os.environ, {"LESSONS_PROMOTE_AT": "2"}):
            self.assertIn(f"PROMOTE {third}", self.run_cli("bump", third)[1])

    def test_an_unusable_environment_value_refuses_and_writes_nothing(self):
        before = Path(self.file).read_text(encoding="utf-8")
        for bad in ("two", "0", "-1"):
            with mock.patch.dict(os.environ, {"LESSONS_PROMOTE_AT": bad}):
                code, _, err = self.run_cli("bump", self.twice)
            self.assertEqual(code, 2, bad)
            self.assertIn("LESSONS_PROMOTE_AT", err)
        self.assertEqual(Path(self.file).read_text(encoding="utf-8"), before)


class KeepRuleTests(GuardLedgerCase):
    def setUp(self):
        super().setUp()
        self.add("Pasted a password into a chat line", rule="Name the secret file, never its value")
        self.guard = self.dir / "chat-guard.mjs"
        self.guard.write_text("", encoding="utf-8")
        self.rules = Path(self.file).parent / "rules" / promotion.RULE_FILE

    def test_a_partial_guard_also_writes_the_rule(self):
        code, out, _ = self.run_cli("promote", "L001", "--guard", str(self.guard), "--keep-rule")
        self.assertEqual(code, 0)
        self.assertIn("keeps the part of the rule", out)
        self.assertIn("- Name the secret file, never its value Check:", self.rules.read_text(encoding="utf-8"))
        promoted = f"| Promoted: {self.guard.as_posix()} + rule {self.rules.as_posix()}"
        self.assertIn(promoted, Path(self.file).read_text(encoding="utf-8"))
        self.assertNotIn("L001", self.run_cli("unguarded", "--min", "1")[1])
        self.assertEqual(self.run_cli("check")[0], 0)

    def test_keep_rule_needs_a_guard(self):
        code, _, err = self.run_cli("promote", "L001", "--keep-rule")
        self.assertEqual(code, 2)
        self.assertIn("--keep-rule goes with --guard", err)
        self.assertFalse(self.rules.exists())

    def test_a_missing_guard_writes_no_rule(self):
        code, _, _ = self.run_cli("promote", "L001", "--guard", str(self.dir / "nope.mjs"), "--keep-rule")
        self.assertEqual(code, 2)
        self.assertFalse(self.rules.exists())

    def test_a_full_guard_writes_no_rule(self):
        self.assertEqual(self.run_cli("promote", "L001", "--guard", str(self.guard))[0], 0)
        self.assertFalse(self.rules.exists())


class HitsCommandTests(GuardLedgerCase):
    def test_counts_per_lesson_in_the_window(self):
        guard_hits.append("G027", "hook-bypass", "/w")
        guard_hits.append("G027", "hook-bypass", "/w")
        guard_hits.append(None, "help-probe", "/w")
        guard_hits.append("G002", "pgrep-wait-loop", "/w", now=1)  # long ago
        code, out, _ = self.run_cli("hits", "--since", "24h")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[:2], ["G027 (hook-bypass) x2", "- (help-probe) x1"])
        self.assertIn("3 guard refusals in the last 24h", out)
        self.assertNotIn("G002", out)

    def test_no_log_and_damaged_lines(self):
        self.assertIn("0 guard refusals in the last 24h", self.run_cli("hits")[1])
        self.hits_file.write_text("garbage\n", encoding="utf-8")
        self.assertIn("1 damaged lines skipped", self.run_cli("hits")[1])

    def test_a_bad_window_is_a_usage_error(self):
        code, _, err = self.run_cli("hits", "--since", "yesterday")
        self.assertEqual(code, 2)
        self.assertIn("not a positive number", err)


OLD_HOOK = '''import json


class RegistryError(ValueError):
    pass


def read_registry(path):
    """An old hook: any rule it does not know makes it refuse the whole file."""
    data = json.load(open(path))
    for index, entry in enumerate(data["guards"]):
        if entry.get("rule") not in ("hook-bypass", "help-probe"):
            raise RegistryError(f"{path} entry {index + 1}: rule must be one of ['help-probe', 'hook-bypass']")
    return data["guards"]
'''


class RegistryCheckTests(GuardLedgerCase):
    """`lessons.py guards` and the session-start note: every installed hook version is asked about the registry."""

    def setUp(self):
        super().setUp()
        self.project = self.dir / "project"
        (self.project / ".agents").mkdir(parents=True)
        self.registry = self.dir / "home" / "lesson-guards.json"
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        self.cache = self.dir / "cache"
        self.installed = self.dir / "installed_plugins.json"  # missing until a test writes it: every version counts
        patch = mock.patch.dict(os.environ, {"LESSONS_GUARDS_GLOBAL_FILE": str(self.registry),
                                             "ARSENAL_CACHE": str(self.cache),
                                             "ARSENAL_INSTALLED_PLUGINS": str(self.installed),
                                             "CLAUDE_PROJECT_DIR": str(self.project)})
        patch.start()
        self.addCleanup(patch.stop)
        cwd = os.getcwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, cwd)

    def write_registry(self, guards):
        self.registry.write_text(json.dumps({"guards": guards}), encoding="utf-8")

    def install(self, version, source=OLD_HOOK):
        hooks = self.cache / version / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "guard_lessons.py").write_text(source, encoding="utf-8")

    def test_no_registry(self):
        code, out, _ = self.run_cli("guards")
        self.assertEqual(code, 0)
        self.assertIn("no lesson-guard registry", out)

    def test_an_entry_an_older_installed_hook_refuses_is_reported(self):
        self.install("1.6.1")
        self.install("1.10.0")  # sorted as a version, after 1.6.1
        (self.cache / "notes").mkdir()  # not a version folder: ignored
        self.write_registry([{"rule": "hook-bypass", "lesson": "G027"},
                             {"rule": "rerun-after-red", "lesson": "L083"}])
        code, out, _ = self.run_cli("guards")
        self.assertEqual(code, 1)
        lines = out.splitlines()
        self.assertIn("this hook: ok", lines)
        self.assertEqual([line.split(":")[0] for line in lines if line.startswith("installed")],
                         ["installed 1.6.1", "installed 1.10.0"])
        self.assertIn("installed 1.6.1: 1 problem(s), REFUSES every Bash command", lines)
        self.assertIn("installed 1.10.0: 1 problem(s), REFUSES every Bash command", lines)
        self.assertIn("min_version", lines[-1])

    def test_min_version_does_not_help_a_hook_that_predates_it_and_says_so(self):
        self.install("1.6.1")
        self.write_registry([{"rule": "rerun-after-red", "min_version": "1.7.0"}])
        code, out, _ = self.run_cli("guards")
        self.assertEqual(code, 1)  # the old hook still reads the rule: the report says which version
        self.assertIn("installed 1.6.1: 1 problem(s)", out)

    def test_this_hooks_problems_and_a_version_that_cannot_be_checked(self):
        self.install("1.5.0", "this is not python\n")
        self.write_registry([{"rule": "no-such-rule"}])
        code, out, _ = self.run_cli("guards")
        self.assertEqual(code, 1)
        self.assertIn("this hook: 1 problem(s)", out)
        self.assertIn("rule must be one of", out)
        self.assertIn("installed 1.5.0: 1 problem(s)", out)
        self.assertIn("installed 1.5.0: 1 problem(s)", out)
        self.assertIn("could not load this version's guard: NameError", out)  # valid syntax, nothing defined

    def test_a_bad_workday_exceptions_file_is_reported_not_refused(self):
        (self.project / ".agents" / "workdays.txt").write_text("2026-11-20 approved-by A: ok\nnonsense\n",
                                                               encoding="utf-8")
        (self.project / ".agents" / "lesson-guards.json").write_text(json.dumps({"guards": [
            {"rule": "calendar", "workweek": "Sun-Thu", "exceptions": "workdays.txt"}]}), encoding="utf-8")
        code, out, _ = self.run_cli("guards")
        self.assertEqual(code, 1)
        self.assertIn("this hook: 1 problem(s)", out)
        self.assertIn("workdays.txt line 2: expected `YYYY-MM-DD approved-by <who>: <reason>`", out)
        context = self.hook_context(json.dumps({"cwd": str(self.project)}))
        self.assertIn("Lesson-guard registry: 1 entry skipped (not applied)", context)

    def test_all_clear(self):
        self.install("1.6.1")
        self.write_registry([{"rule": "hook-bypass", "lesson": "G027"}])
        code, out, _ = self.run_cli("guards")
        self.assertEqual(code, 0)
        self.assertIn("installed 1.6.1: ok", out)

    def test_the_session_start_header_counts_skipped_entries(self):
        os.chdir(self.dir)  # the session's directory comes from the hook input, not this process
        stdin = json.dumps({"cwd": str(self.project)})
        self.assertNotIn("Lesson-guard registry", self.hook_context(stdin))
        self.assertEqual(lessons.registry_note(), "")
        self.write_registry([{"rule": "no-such-rule"}, {"rule": "hook-bypass", "enabled": "no"}])
        context = self.hook_context(stdin)
        self.assertIn("Lesson-guard registry: 2 entries skipped (not applied)", context)
        self.assertIn(" guards` and fix them.", context)
        with mock.patch("guard_registry.current_problems", side_effect=RuntimeError("boom")):
            self.assertNotIn("Lesson-guard registry", self.hook_context(stdin))  # never breaks the session start

    def test_versions_that_hang_crash_or_print_nonsense_are_reported(self):
        self.install("1.6.0", "import time\ntime.sleep(30)\n")
        self.install("1.6.1", "def read_registry(path):\n    raise TypeError('old bug')\nclass RegistryError(ValueError):\n    pass\n")
        self.install("1.6.2", "import sys\nprint('not json')\nsys.exit(0)\n")
        self.write_registry([{"rule": "hook-bypass"}])
        with mock.patch("guard_registry.CHECK_SECONDS", 2):
            code, out, _ = self.run_cli("guards")
        self.assertEqual(code, 1)
        self.assertIn("could not check: no answer within 2s", out)
        self.assertIn("installed 1.6.1: 1 problem(s), runs NO lesson guard (fails open)", out)  # its hook swallows it
        self.assertIn("TypeError: old bug", out)
        self.assertIn("installed 1.6.2: 1 problem(s)", out)
        self.assertNotIn("time.sleep", out)  # never the probe source

    def test_every_registry_is_checked_by_every_version(self):
        self.install("1.6.1")
        self.write_registry([{"rule": "hook-bypass"}])
        (self.project / ".agents" / "lesson-guards.json").write_text(
            json.dumps({"guards": [{"rule": "rerun-after-red"}]}), encoding="utf-8")
        code, out, _ = self.run_cli("guards")
        self.assertEqual(code, 1)
        self.assertIn(str(self.registry), out.splitlines()[0])
        self.assertIn(str(self.project / ".agents" / "lesson-guards.json"), out)
        self.assertIn("installed 1.6.1: 1 problem(s), REFUSES", out)

    def test_a_project_registry_is_found_from_the_session_folder(self):
        (self.project / ".agents" / "lesson-guards.json").write_text(
            json.dumps({"guards": [{"rule": "no-such-rule"}]}), encoding="utf-8")
        (self.project / "src").mkdir()
        os.chdir(self.project / "src")
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": ""}):
            code, out, _ = self.run_cli("guards")
        self.assertEqual(code, 1)
        self.assertIn(str(self.project / ".agents" / "lesson-guards.json"), out)

    def reference(self, *versions):
        entries = [{"scope": "user", "installPath": str(self.cache / version), "version": version} for version in versions]
        self.installed.write_text(json.dumps({"version": 2, "plugins": {"arsenal@senior-developer-arsenal": entries}}),
                                  encoding="utf-8")

    def test_only_referenced_versions_decide_and_the_rest_warn(self):
        self.install("1.6.1")
        self.install("1.10.0", "class RegistryError(ValueError):\n    pass\ndef read_registry(path):\n    return [], []\n")
        self.reference("1.10.0")
        self.write_registry([{"rule": "rerun-after-red", "lesson": "L083"}])
        code, out, _ = self.run_cli("guards")
        self.assertEqual(code, 0)
        self.assertIn("cached 1.6.1 (no install references it): 1 problem(s), REFUSES every Bash command", out)
        self.assertIn("installed 1.10.0: ok", out)
        self.assertIn("warning: only cached versions no install references have problems", out)
        self.assertEqual(self.run_cli("guards", "--strict")[0], 1)
        self.reference("1.6.1", "1.10.0")
        code, out, _ = self.run_cli("guards")
        self.assertEqual(code, 1)
        self.assertNotIn("warning: only cached", out)  # a referenced version fails: no misleading warning
        self.write_registry([{"rule": "hook-bypass"}])
        self.assertNotIn("warning", self.run_cli("guards")[1])  # nothing wrong: no warning at all

    def test_an_unreadable_install_list_counts_every_version(self):
        self.install("1.6.1")
        self.write_registry([{"rule": "rerun-after-red"}])
        for text in ("{broken", '{"plugins": []}', '{"plugins": {"arsenal@senior-developer-arsenal": "x"}}'):
            self.installed.write_text(text, encoding="utf-8")
            code, out, _ = self.run_cli("guards")
            self.assertEqual(code, 1, text)
            self.assertIn("installed 1.6.1", out, text)
        self.installed.unlink()
        code, out, _ = self.run_cli("guards")
        self.assertIn("note: installed_plugins.json not readable", out)

    def test_a_candidate_file_is_judged_before_it_is_in_place(self):
        self.install("1.6.1")
        self.reference("1.6.1")
        self.write_registry([{"rule": "hook-bypass"}])
        candidate = self.dir / "candidate.json"
        candidate.write_text(json.dumps({"guards": [{"rule": "hook-bypass"}, {"rule": "pipe-exit", "lesson": "G004",
                                                                              "min_version": "1.11.0"}]}))
        code, out, _ = self.run_cli("guards", "--registry", str(candidate))
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith(f"candidate registries: {candidate}"), out)
        self.assertIn("installed 1.6.1: 1 problem(s), REFUSES", out)
        self.assertEqual(self.run_cli("guards")[0], 0)  # the file in place is untouched and still fine
        code, _, err = self.run_cli("guards", "--registry", str(self.dir / "nope.json"))
        self.assertEqual((code, "no registry file" in err), (2, True))
        code, out, _ = self.run_cli("guards", "--registry", str(candidate), "--registry", str(candidate))
        self.assertEqual(out.count("entry 2:"), 1)  # the same file named twice is read once
        second = self.dir / "second.json"
        second.write_text(json.dumps({"guards": [{"rule": "hook-bypass"}]}))
        code, out, _ = self.run_cli("guards", "--registry", str(second), "--registry", str(candidate))
        self.assertEqual(code, 1)
        self.assertIn(str(second), out.splitlines()[0])

    def test_a_version_before_the_lesson_guards_is_not_asked(self):
        (self.cache / "1.1.0" / "hooks").mkdir(parents=True)  # no guard_lessons.py: it never reads the registry
        self.reference("1.1.0")
        self.write_registry([{"rule": "pipe-exit", "min_version": "1.11.0"}])
        code, out, _ = self.run_cli("guards")
        self.assertEqual(code, 0)
        self.assertNotIn("1.1.0", out)

class EscalationTests(GuardLedgerCase):
    """Repeats with no guard are named at every session start and in the retro until guarded or exempted."""

    def header(self):
        return self.hook_context(stdin=json.dumps({"cwd": str(self.dir)}))

    def note(self):
        lines = [line for line in self.header().splitlines() if line.startswith("Repeats without a guard")]
        return lines[0] if lines else ""

    def test_no_note_without_repeats(self):
        self.lesson("Alpha happened once", "alpha rule unique")
        self.lesson("Bravo happened twice", "bravo rule unique", hits=2)
        self.assertEqual(self.note(), "")

    def test_the_note_names_repeats_most_hits_first_archive_and_global_included(self):
        four = self.lesson("Pushed a branch over a teammate", "fetch before any push", hits=4)
        three = self.lesson("Dropped a column on staging", "dry run each migration", hits=3)
        self.run_cli("archive", three)
        self.lesson("Quoted the heredoc wrong", "quote heredoc markers", hits=5, extra=("--global",))
        note = self.note()
        self.assertTrue(note.startswith("Repeats without a guard (3): G001 x5, " + four + " x4, " + three + " x3."),
                        note)
        self.assertIn("promote ID --guard PATH", note)
        self.assertIn("exempt ID --reason", note)

    def test_a_lesson_in_both_ledgers_is_counted_once(self):
        self.lesson("Pushed a branch over a teammate", "fetch before any push", hits=3)
        self.lesson("Pushed a branch over a teammate", "fetch before any push", hits=4, extra=("--global",))
        self.assertTrue(self.note().startswith("Repeats without a guard (1): L001 x3."), self.note())

    def test_the_note_room_is_taken_from_the_lessons_budget(self):
        for n in range(lessons.ACTIVE_CAP):  # long rules fill the header to its cap
            self.lesson(f"Mistake{n} unique{n} words{n}", f"rule{n} " + "padding text " * 12 + f"end{n}", hits=3)
        header = self.header()
        self.assertIn("Repeats without a guard (15):", header)
        self.assertLessEqual(len(header), lessons.HOOK_MAX)

    def test_notes_come_after_the_lessons_escalation_first(self):
        self.lesson("Pushed a branch over a teammate", "fetch before any push", hits=3)
        with mock.patch.object(lessons, "registry_note", return_value="Lesson-guard registry: 1 entry skipped."):
            lines = self.header().splitlines()
        self.assertEqual([line.split(" ")[0] for line in lines[-2:]], ["Repeats", "Lesson-guard"])

    def test_an_exemption_lapses_when_the_lesson_recurs(self):
        lesson_id = self.lesson("Dropped a column on staging", "dry run each migration", hits=3)
        self.run_cli("exempt", lesson_id, "--reason", "judgement call")
        self.assertEqual(self.note(), "")
        self.run_cli("bump", lesson_id)
        self.assertIn(f"{lesson_id} x4", self.note())
        self.assertIn(f"{lesson_id} hits:4", self.run_cli("unguarded")[1])
        self.assertIn(f"candidate {lesson_id} hits:4: recurred after its exemption", self.run_cli("check")[1])
        self.run_cli("exempt", lesson_id, "--reason", "still a judgement call")  # granted again at 4
        self.assertEqual(self.note(), "")
        self.assertIn("exempt@4: still a judgement call", Path(self.file).read_text())

    def test_exempt_takes_global_and_a_guard_path_cannot_look_like_an_exemption(self):
        self.lesson("Quoted the heredoc wrong", "quote heredoc markers", hits=3, extra=("--global",))
        self.assertEqual(self.run_cli("exempt", "G001", "--global", "--reason", "habit")[0], 0)
        lesson_id = self.lesson("Dropped a column on staging", "dry run each migration", hits=3)
        odd = self.dir / "exempt@3: trick"
        odd.write_text("", encoding="utf-8")
        cwd = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, cwd)
        code, _, err = self.run_cli("promote", lesson_id, "--guard", odd.name)
        self.assertEqual((code, "reads as an exemption mark" in err), (2, True))

    def test_many_repeats_are_counted_beyond_five(self):
        for n in range(7):
            self.lesson(f"Mistake{n} unique{n} words{n}", f"rule{n} distinct{n} text{n}", hits=3 + n)
        note = self.note()
        self.assertIn("Repeats without a guard (7):", note)
        self.assertIn("and 2 more (`unguarded`)", note)
        self.assertLessEqual(len(self.header()), lessons.HOOK_MAX)  # the note's room is taken from the lessons

    def test_the_threshold_follows_the_setting(self):
        self.lesson("Bravo happened twice", "bravo rule unique", hits=2)
        with mock.patch.dict(os.environ, {"LESSONS_PROMOTE_AT": "2"}):
            self.assertIn("Repeats without a guard (1)", self.note())
        with mock.patch.dict(os.environ, {"LESSONS_PROMOTE_AT": "nonsense"}):
            self.assertEqual(self.note(), "")  # never breaks the session start

    def test_a_guard_or_an_exemption_ends_the_flag(self):
        guarded = self.lesson("Pushed a branch over a teammate", "fetch before any push", hits=4)
        exempted = self.lesson("Dropped a column on staging", "dry run each migration", hits=3)
        guard = self.dir / "guard.py"
        guard.write_text("", encoding="utf-8")
        self.run_cli("promote", guarded, "--guard", str(guard))
        code, out, _ = self.run_cli("exempt", exempted, "--reason", "judgement call: no command shows it")
        self.assertEqual(code, 0)
        self.assertIn(f"exempted {exempted}", out)
        self.assertEqual(self.note(), "")
        self.assertIn(f"- {exempted}", self.run_cli("active")[1])  # still in Active: the rule applies
        self.assertIn("| Promoted: exempt@3: judgement call: no command shows it", Path(self.file).read_text())
        self.assertNotIn(f"candidate {exempted}", self.run_cli("check")[1])

    def test_exempt_needs_a_reason_and_never_hides_a_guard_or_a_secret(self):
        lesson_id = self.lesson("Dropped a column on staging", "dry run each migration", hits=3)
        for argv, fault in ((("exempt", lesson_id), "--reason is required"),
                            (("exempt", lesson_id, "--reason", "  "), "--reason is required"),
                            (("exempt", lesson_id, "--reason", "token=" + "a1B2c3D4" * 3), "looks like a secret"),
                            (("exempt", "L999", "--reason", "x"), "no lesson")):
            code, _, err = self.run_cli(*argv)
            self.assertEqual(code, 2, argv)
            self.assertIn(fault, err, argv)
        guard = self.dir / "guard.py"
        guard.write_text("", encoding="utf-8")
        self.run_cli("promote", lesson_id, "--guard", str(guard))
        code, _, err = self.run_cli("exempt", lesson_id, "--reason", "x")
        self.assertEqual((code, "already has a guard" in err), (2, True))

    def test_an_exemption_can_be_reworded_and_a_recurrence_is_reported(self):
        lesson_id = self.lesson("Dropped a column on staging", "dry run each migration", hits=3)
        self.run_cli("exempt", lesson_id, "--reason", "first reason")
        self.assertEqual(self.run_cli("exempt", lesson_id, "--reason", "better reason")[0], 0)
        self.assertIn("exempt@3: better reason", Path(self.file).read_text())
        _, out, _ = self.run_cli("bump", lesson_id)
        self.assertIn(f"EXEMPT {lesson_id} recurred (exempt@3: better reason)", out)

    def test_global_lessons_are_exempted_in_the_global_ledger(self):
        self.lesson("Quoted the heredoc wrong", "quote heredoc markers", hits=3, extra=("--global",))
        self.assertEqual(self.run_cli("exempt", "G001", "--reason", "habit with no command")[0], 0)
        self.assertIn("exempt@3: habit with no command", self.shared.read_text())

    def test_the_retro_lists_every_repeat_without_a_guard(self):
        self.lesson("Pushed a branch over a teammate", "fetch before any push", hits=4)
        exempted = self.lesson("Dropped a column on staging", "dry run each migration", hits=3)
        self.run_cli("exempt", exempted, "--reason", "judgement call")
        _, out, _ = self.run_cli("retro", "--days", "7")
        section = out.split("### Repeats without a guard")[1].split("### Top 3 actions")[0]
        self.assertIn("fetch before any push", section)
        self.assertNotIn("dry run each migration", section.split("exempted on purpose")[0])
        self.assertIn(f"1 exempted on purpose: {exempted}", section)
        self.assertNotIn("is enforced by exempt", out)
