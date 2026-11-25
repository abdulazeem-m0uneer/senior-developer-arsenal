"""Tests for the opt-in dry-run-chain lesson guard (hooks/guard_dry_run_chain.py, wired in guard_lessons)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))

import guard_dry_run_chain  # noqa: E402
import guard_lessons  # noqa: E402

SCRIPT = HOOKS / "guard.py"
ENTRY = {"rule": "dry-run-chain", "lesson": "G007", "programs": ["merge-green", "deploy.sh", "merge.py"],
         "min_version": "1.33.0"}


class ChainCase(unittest.TestCase):
    """A project whose registry names dry-run-chain for three programs, and a 1.33.0 hook."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.project = self.dir / "project"
        (self.project / ".agents").mkdir(parents=True)
        env = {"LESSONS_GUARDS_GLOBAL_FILE": str(self.dir / "home" / "lesson-guards.json"),
               "LESSONS_GUARD_HITS_FILE": str(self.dir / "home" / "hits.jsonl")}
        for patch in (mock.patch.dict(os.environ, env), mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 33, 0))):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.registry(ENTRY)

    def registry(self, *guards):
        (self.project / ".agents" / "lesson-guards.json").write_text(json.dumps({"guards": list(guards)}),
                                                                     encoding="utf-8")

    def judge(self, command):
        return guard_lessons.judge(command, str(self.project))

    def assertRefused(self, command, program="merge-green", flag=None):
        hit = self.judge(command)
        self.assertIsNotNone(hit, command)
        self.assertEqual((hit.rule, hit.lesson), ("dry-run-chain", "G007"), command)
        self.assertIn(f"`{program}`", hit.reason, command)
        if flag:
            self.assertIn(f"({flag})", hit.reason, command)
        self.assertIn("Run the dry run alone, read its line, then the real run as a separate call.", hit.reason)

    def assertPasses(self, command):
        self.assertIsNone(self.judge(command), command)


class RefusedTests(ChainCase):
    def test_a_run_without_a_confirm_flag_then_one_with_it(self):
        self.assertRefused("merge-green 12; merge-green 12 --yes", flag="--yes")
        self.assertRefused("merge-green 12 && merge-green 12 --apply", flag="--apply")
        self.assertRefused("merge-green 12 || merge-green 12 --confirm", flag="--confirm")
        self.assertRefused("merge-green 12\nmerge-green 12 --yes")
        self.assertRefused("merge-green 12 | tee out.log; merge-green 12 --yes")

    def test_an_explicit_dry_run_flag_then_a_confirm_flag(self):
        for dry in ("--dry-run", "-n", "--check", "-vn", "--dry-run=1"):
            self.assertRefused(f"merge-green 12 {dry} && merge-green 12 --yes")

    def test_a_dry_flag_wins_over_a_confirm_flag_on_the_same_run(self):
        self.assertRefused("merge-green --yes --dry-run 12; merge-green --yes 12")

    def test_a_confirm_flag_with_a_value(self):
        self.assertRefused("merge-green 12; merge-green 12 --confirm=yes", flag="--confirm")

    def test_programs_match_by_path_basename(self):
        self.assertRefused("./scripts/merge-green 12; /usr/local/bin/merge-green 12 --yes")
        self.assertRefused("bash ./ops/deploy.sh -n && bash ./ops/deploy.sh --force", program="deploy.sh",
                           flag="--force")
        self.assertRefused("python3 tools/merge.py 7; python3 -u tools/merge.py 7 --yes", program="merge.py")
        self.assertRefused("./deploy.sh --check; sh deploy.sh --apply", program="deploy.sh")

    def test_through_wrappers_sh_c_eval_and_variables(self):
        self.assertRefused("timeout 60 merge-green 12; sudo merge-green 12 --yes")
        self.assertRefused("env CI=1 merge-green 12 && nice merge-green 12 --yes")
        self.assertRefused("sh -c 'merge-green 12; merge-green 12 --yes'")
        self.assertRefused("merge-green 12; bash -c \"merge-green 12 --yes\"")
        self.assertRefused("eval 'merge-green 12 && merge-green 12 --yes'")
        self.assertRefused("M=./bin/merge-green; $M 12; ${M} 12 --yes")

    def test_a_dry_run_after_an_earlier_real_run_still_counts(self):
        self.assertRefused("merge-green 1 --yes; merge-green 2; merge-green 2 --yes")


class PassTests(ChainCase):
    def test_one_run_alone(self):
        for command in ("merge-green 12 --yes", "merge-green 12 --dry-run", "merge-green 12",
                        "merge-green 12 --dry-run > out.log 2>&1; echo rc=$?"):
            self.assertPasses(command)

    def test_the_real_run_first_or_two_dry_runs(self):
        self.assertPasses("merge-green 12 --yes; merge-green 13 --dry-run")
        self.assertPasses("merge-green 12; merge-green 12 -n; merge-green 12 --check")
        self.assertPasses("merge-green --yes -n 12; merge-green --yes --dry-run 12")

    def test_other_programs(self):
        self.assertPasses("other 12; merge-green 12 --yes")
        self.assertPasses("merge-green 12; other 12 --yes")
        self.assertPasses("gh pr merge 1; gh pr merge 1 --yes")
        self.assertPasses("deploy 1; deploy 1 --force")  # deploy.sh is named, deploy is not
        self.assertPasses("merge-green.sh 1; merge-green.sh 1 --yes")  # names match exactly, suffix included

    def test_a_confirm_word_that_is_not_the_flag(self):
        for real in ("merge-green 12 --yesterday", "merge-green 12 yes", "merge-green 12 -- --yes",
                     "merge-green 12 --force-with-lease", "merge-green 12 -yes"):
            self.assertPasses(f"merge-green 12; {real}")

    def test_text_that_only_mentions_the_commands(self):
        for command in ('echo "merge-green 12; merge-green 12 --yes"',
                        "git commit -m 'merge-green 12 --dry-run then merge-green 12 --yes'",
                        "grep -n 'merge-green --yes' notes.md; merge-green 12 --yes",
                        "cat <<'EOF'\nmerge-green 12\nmerge-green 12 --yes\nEOF"):
            self.assertPasses(command)

    def test_an_empty_or_blank_command(self):
        self.assertPasses("")
        self.assertPasses("   ")


class RealRunLooksDryTests(ChainCase):
    """Words that look like a dry-run flag but are not one: a real run must not be taken for a dry run."""

    def test_a_count_after_n_and_longer_single_dash_words_are_not_dry(self):
        for real in ("--yes -n 5", "--yes -name x", "--yes -vn 5"):
            self.assertPasses(f"merge-green {real}; merge-green --yes")

    def test_a_numeric_n_on_the_real_run_does_not_hide_it(self):
        self.assertRefused("merge-green --dry-run && merge-green --apply --pr 3 -n 5", flag="--apply")

    def test_a_dry_flag_set_to_false_is_a_real_run(self):
        self.assertRefused("merge-green --dry-run=true; merge-green --dry-run=false --yes", flag="--yes")
        self.assertPasses("merge-green --yes --dry-run=false; merge-green --yes")
        self.assertRefused("merge-green 1 --check=1; merge-green 1 --yes")

    def test_every_false_value_makes_a_dry_flag_a_real_run(self):
        for value in guard_dry_run_chain.FALSE_VALUES:
            for flag in ("--dry-run", "--check"):
                with self.subTest(flag=flag, value=value):
                    self.assertPasses(f"merge-green {flag}={value} --yes; merge-green --yes")
                    self.assertPasses(f"merge-green {flag}={value.upper()} --yes; merge-green --yes")
        self.assertRefused("merge-green --dry-run=1 --yes; merge-green --yes", flag="--yes")

    def test_a_confirm_flag_set_to_a_false_value_is_not_a_real_run(self):
        for flag in ("--apply=false", "--confirm=no", "--apply=0", "--force=off", "--yes=FALSE"):
            with self.subTest(flag=flag):
                self.assertPasses(f"merge-green 1 --dry-run; merge-green 1 {flag}")
        self.assertRefused("merge-green 1 --dry-run; merge-green 1 --apply=true", flag="--apply")
        self.assertRefused("merge-green 1 --dry-run; merge-green 1 --apply=0 --yes", flag="--yes")
        self.assertRefused("merge-green 1 --apply=false; merge-green 1 --yes", flag="--yes")

    def test_a_cluster_with_n_is_dry(self):
        self.assertRefused("merge-green -yn 12; merge-green 12 --yes")


class WrapperTests(ChainCase):
    def test_the_real_run_behind_a_launcher(self):
        for real in ("pnpm exec merge-green --yes", "npx merge-green --yes", "npx -y merge-green --yes",
                     "ssh -p 22 host merge-green --yes", "echo 12 | xargs -n 1 merge-green --yes",
                     "xargs merge-green --yes", "pnpm dlx merge-green --yes"):
            self.assertRefused(f"merge-green --dry-run; {real}")

    def test_the_dry_run_behind_a_launcher(self):
        self.assertRefused("pnpm exec merge-green --dry-run && pnpm exec merge-green --yes")
        self.assertRefused("npx merge-green --dry-run && npx merge-green --yes")

    def test_other_launcher_uses_pass(self):
        self.assertPasses("merge-green --dry-run; pnpm install; npx other --yes")
        self.assertPasses("merge-green --dry-run; ssh host")
        self.assertPasses("merge-green --dry-run; pnpm exec")


class FalseRefusalTests(ChainCase):
    def test_a_status_or_help_call_before_the_real_run(self):
        for info in ("status", "--help", "-h", "--list", "list", "--version"):
            self.assertPasses(f"merge-green {info}; merge-green --yes 4")

    def test_a_dry_run_and_a_real_run_on_different_subjects(self):
        self.assertPasses("merge-green --dry-run 1; merge-green --yes 2")
        self.assertRefused("merge-green --dry-run 1 2; merge-green --yes 2")
        self.assertRefused("merge-green --dry-run; merge-green --yes 2")
        self.assertRefused("merge-green --dry-run 1; merge-green --yes")


class ReviewTests(ChainCase):
    """Findings of the G007 review: alternatives, read-only words, ssh, launchers, subjects, lone -n."""

    def test_alternative_branches_are_not_a_chain(self):
        self.assertPasses('if [ "$1" = dry ]; then merge-green 12 --dry-run; else merge-green 12 --yes; fi')
        self.assertPasses("if [ x ]; then merge-green 12 --dry-run; elif [ y ]; then merge-green 12 --yes; fi")
        self.assertPasses("case $1 in d) merge-green 12 --dry-run;; r) merge-green 12 --yes;; esac")

    def test_a_run_before_or_after_a_branch_still_chains(self):
        self.assertRefused("merge-green 12 --dry-run; if [ x ]; then merge-green 12 --yes; fi")
        self.assertRefused("if [ x ]; then merge-green 12 --dry-run; else echo no; fi; merge-green 12 --yes")
        self.assertRefused("if [ x ]; then merge-green 12 --dry-run; merge-green 12 --yes; fi")
        self.assertRefused("case $1 in d) merge-green 12 --dry-run; merge-green 12 --yes;; esac")
        self.assertRefused("merge-green 12 --dry-run; case $1 in r) merge-green 12 --yes;; esac")

    def test_separate_constructs_and_a_run_after_a_finished_one_still_chain(self):
        self.assertRefused("if [ a ]; then merge-green 12 --dry-run; fi; if [ b ]; then merge-green 12 --yes; fi")
        self.assertRefused("case $1 in d) merge-green 12 --dry-run;; esac; merge-green 12 --yes")
        self.assertRefused("if [ a ]; then merge-green 12 --dry-run; fi; merge-green 12 --yes")

    def test_a_check_flag_beats_a_confirm_flag_on_the_same_run(self):
        self.assertRefused("merge-green --check --yes 12; merge-green --yes 12")

    def test_npm_needs_run_or_exec_to_launch_a_program(self):
        self.assertPasses("npm merge-green --dry-run; npm merge-green --yes")

    def test_waiting_viewing_and_watching_are_read_only(self):
        for word in ("wait", "view", "watch", "get", "describe", "logs", "info"):
            self.assertPasses(f"merge-green {word} 12; merge-green 12 --yes")

    def test_the_remote_command_of_ssh_is_parsed(self):
        self.assertRefused("ssh h 'merge-green 12 --dry-run && merge-green 12 --yes'")
        self.assertRefused("ssh -p 22 h \"merge-green 12; merge-green 12 --yes\"")
        self.assertRefused("merge-green 12 --dry-run; ssh h merge-green 12 --yes")
        self.assertRefused("ssh h 'merge-green 12 --dry-run'; ssh h 'merge-green 12 --yes'")
        self.assertPasses("ssh h 'merge-green 12 --dry-run'")

    def test_script_launchers_and_sourcing(self):
        self.assertRefused("pnpm merge-green --dry-run && pnpm merge-green --yes")
        self.assertRefused("pnpm run merge-green --dry-run && pnpm run merge-green --yes")
        self.assertRefused("npm run merge-green -- --dry-run && npm run merge-green -- --yes")
        self.assertRefused("yarn merge-green 1 --dry-run; yarn run merge-green 1 --yes")
        self.assertRefused(". ./deploy.sh prod --dry-run; . ./deploy.sh prod --yes", program="deploy.sh")
        self.assertRefused("source deploy.sh prod --dry-run; source deploy.sh prod --yes", program="deploy.sh")
        self.assertPasses("pnpm install --dry-run; pnpm install --yes")

    def test_options_before_the_launcher_mode_word(self):
        self.assertRefused("pnpm --dir x exec merge-green --dry-run; pnpm --dir x exec merge-green --yes")
        self.assertRefused("pnpm --filter x exec merge-green --dry-run; pnpm --filter x exec merge-green --yes")
        self.assertRefused("npm --prefix x exec merge-green --dry-run; npm --prefix x exec merge-green --yes")

    def test_a_variable_operand_may_be_the_same_subject(self):
        self.assertRefused("merge-green $A --dry-run && merge-green $B --yes")
        self.assertRefused("merge-green 1 --dry-run; merge-green $X --yes")
        self.assertRefused("merge-green $(echo 1) --dry-run; merge-green 1 --yes")
        self.assertRefused("A=1; merge-green $A --dry-run; merge-green 1 --yes")
        self.assertPasses("A=1; B=2; merge-green $A --dry-run; merge-green $B --yes")

    def test_targets_given_as_options_are_subjects(self):
        self.assertPasses("merge-green --pr=1 --dry-run; merge-green --pr=2 --yes")
        self.assertRefused("merge-green --pr=1 --dry-run; merge-green --pr=1 --yes")
        self.assertPasses("merge-green --pr 1 --dry-run; merge-green --pr 2 --yes")
        self.assertRefused("merge-green --pr=1 --dry-run=true; merge-green --pr=1 --yes=true")

    def test_a_lone_n_does_not_hide_a_real_run_that_carries_a_confirm_flag(self):
        self.assertRefused("deploy.sh prod; deploy.sh -n prod --yes", program="deploy.sh", flag="--yes")
        self.assertPasses("deploy.sh -n prod --yes; deploy.sh prod --yes")
        self.assertPasses("deploy.sh -n prod --yes; deploy.sh -n prod --yes")
        self.assertPasses("merge-green --yes -n 12; merge-green --yes 12")
        self.assertRefused("merge-green --yes --dry-run -n 12; merge-green --yes 12")

    def test_words_after_double_dash_are_operands_not_dry_flags(self):
        self.assertPasses("merge-green --yes -- --dry-run 1; merge-green --yes 1")

    def test_a_status_call_on_the_same_operand_is_not_a_dry_run(self):
        for info in ("status", "list", "help", "show", "version"):
            self.assertPasses(f"merge-green {info} 4; merge-green --yes 4")


class EntryTests(ChainCase):
    def test_a_program_written_as_a_path_matches_its_basename(self):
        self.registry({**ENTRY, "programs": ["bin/merge-green"]})
        self.assertRefused("merge-green 12; merge-green 12 --yes")

    def test_off_by_default_without_an_entry(self):
        self.registry({"rule": "help-probe"})
        self.assertNotIn("dry-run-chain", [name for name, _, _ in guard_lessons.rules(str(self.project))])

    def test_off_until_a_registry_entry_names_it(self):
        self.registry()
        self.assertPasses("merge-green 12; merge-green 12 --yes")

    def test_without_programs_nothing_is_judged(self):
        self.registry({"rule": "dry-run-chain", "lesson": "G007", "min_version": "1.33.0"})
        self.assertPasses("merge-green 12; merge-green 12 --yes")
        self.assertEqual(guard_lessons.registry_problems(str(self.project)), [])

    def test_the_default_confirm_flags_include_force(self):
        self.assertRefused("merge-green 12; merge-green 12 --force", flag="--force")

    def test_confirm_replaces_the_defaults(self):
        self.registry({**ENTRY, "confirm": ["--go", "-y"]})
        self.assertRefused("merge-green 12; merge-green 12 --go", flag="--go")
        self.assertRefused("merge-green 12 -n; merge-green 12 -vy", flag="-y")
        self.assertPasses("merge-green 12; merge-green 12 --yes")
        self.assertPasses("merge-green 12; merge-green 12 --force")

    def test_enabled_false_and_a_reason_of_its_own(self):
        self.registry({**ENTRY, "enabled": False})
        self.assertPasses("merge-green 12; merge-green 12 --yes")
        self.registry({**ENTRY, "reason": "Two calls, please."})
        self.assertEqual(self.judge("merge-green 12; merge-green 12 --yes").reason, "Two calls, please.")

    def test_min_version_1_33_0_skips_on_older_hooks(self):
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 32, 0)):
            self.assertPasses("merge-green 12; merge-green 12 --yes")
            self.assertEqual(guard_lessons.registry_problems(str(self.project)), [])
        self.assertIsNotNone(self.judge("merge-green 12; merge-green 12 --yes"))

    def test_bad_registry_values_are_skipped(self):
        for bad in ({"confirm": []}, {"confirm": "--yes"}, {"confirm": ["yes"]}, {"confirm": ["--"]},
                    {"confirm": ["-n"]}, {"confirm": ["--dry-run"]}, {"confirm": ["--yes", 3]}, {"programs": []},
                    {"programs": "merge-green"}, {"shell": "bash"}, {"lesson": "nope"}):
            self.registry({**ENTRY, **bad})
            self.assertPasses("merge-green 12; merge-green 12 --yes")
            self.assertTrue(guard_lessons.registry_problems(str(self.project)), bad)

    def test_confirm_is_for_this_rule_only(self):
        self.registry({"rule": "help-probe", "confirm": ["--yes"]}, ENTRY)
        problems = guard_lessons.registry_problems(str(self.project))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("confirm", problems[0])
        self.assertIsNotNone(self.judge("merge-green 12; merge-green 12 --yes"))

    def test_an_error_in_the_rule_passes(self):
        with mock.patch.object(guard_dry_run_chain, "is_dry", side_effect=RuntimeError("boom")):
            self.assertPasses("merge-green 12; merge-green 12 --yes")


class ModuleTests(unittest.TestCase):
    def test_problem_on_runs(self):
        entry = {"programs": ["x"]}
        self.assertIsNone(guard_dry_run_chain.problem([], entry))
        self.assertIsNone(guard_dry_run_chain.problem([("", [])], entry))
        self.assertIn("`x`", guard_dry_run_chain.problem([("x", ["-n"]), ("x", ["--yes"])], entry))
        self.assertIsNone(guard_dry_run_chain.problem([("x", ["-n"]), ("x", ["--yes"])], {}))

    def test_bad_input_passes(self):
        self.assertIsNone(guard_dry_run_chain.problem(None, {"programs": ["x"]}))
        self.assertIsNone(guard_dry_run_chain.problem([("x", None), ("x", ["--yes"])], {"programs": ["x"]}))

    def test_valid_confirm(self):
        self.assertTrue(guard_dry_run_chain.valid_confirm(["--yes", "-y"]))
        for bad in ([], None, "--yes", ["yes"], ["-"], ["--"], ["-n"], ["--check"], [""], [1], [" --yes"], ["--yes "]):
            self.assertFalse(guard_dry_run_chain.valid_confirm(bad), bad)


class HookTests(ChainCase):
    """guard.py pre denies the chained command under the rule."""

    def pre(self, command):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command},
                   "cwd": str(self.project), "permission_mode": "default"}
        base = {k: v for k, v in os.environ.items()
                if k not in ("ARSENAL_GUARD", "ARSENAL_LESSON_GUARDS", "ARSENAL_GUARD_DESTRUCTIVE",
                             "ARSENAL_RUN_LIMITS", "CLAUDE_PROJECT_DIR", "ARSENAL_PROFILE", "ARSENAL_GUARD_SCOPE")}
        result = subprocess.run([sys.executable, str(SCRIPT), "pre"], cwd=self.project, input=json.dumps(payload),
                                capture_output=True, text=True, env=base)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None

    def test_the_hook_denies_the_chain_and_passes_the_dry_run_alone(self):
        self.registry({k: v for k, v in ENTRY.items() if k != "min_version"})  # the hook may be older than 1.33.0
        out = self.pre("merge-green 12 --dry-run && merge-green 12 --yes")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("G007 (dry-run-chain)", out["permissionDecisionReason"])
        self.assertIsNone(self.pre("merge-green 12 --dry-run"))


if __name__ == "__main__":
    unittest.main()


class SubjectTests(ChainCase):
    """What a run works on: an option's separate value (--env prod) is not a target."""

    def test_runs_that_differ_only_in_an_operand_pass_whatever_the_options(self):
        self.assertPasses("merge-green 12 --env prod --dry-run; merge-green 13 --env prod --yes")
        self.assertPasses("merge-green --env prod 12 --dry-run; merge-green --env prod 13 --yes")
        self.assertPasses("merge-green 12 --env prod --dry-run; merge-green 13 --env stage --yes")
        self.assertPasses("merge-green --pr 1 --dry-run; merge-green --pr 2 --yes")
        self.assertPasses("merge-green --verbose 12 --dry-run; merge-green --verbose 13 --yes")

    def test_runs_on_the_same_operand_are_refused_whatever_the_options(self):
        self.assertRefused("merge-green 12 --env prod --dry-run; merge-green 12 --env prod --yes", flag="--yes")
        self.assertRefused("merge-green 12 --env prod --dry-run; merge-green 12 --env stage --yes", flag="--yes")
        self.assertRefused("merge-green --env prod 12 --dry-run; merge-green 12 --yes --env prod", flag="--yes")
        self.assertRefused("merge-green --pr 1 --dry-run; merge-green --pr 1 --yes", flag="--yes")
        self.assertRefused("merge-green --dry-run; merge-green --env prod --yes", flag="--yes")


class ConstructTests(ChainCase):
    """Alternatives of an if or case never run together, behind any word that may lead a command."""

    def test_commands_after_leading_words_in_other_alternatives_pass(self):
        for command in ("while true; do if x; then merge-green --dry-run; else merge-green --yes; fi; done",
                        "until x; do if x; then merge-green --dry-run; else merge-green --yes; fi; done",
                        "! if x; then merge-green --dry-run; else merge-green --yes; fi",
                        "{ if x; then merge-green --dry-run; else merge-green --yes; fi; }",
                        "if x; then { merge-green --dry-run; }; else { merge-green --yes; }; fi",
                        "if x; then while merge-green --dry-run; do :; done; else merge-green --yes; fi",
                        "if x; then until merge-green --dry-run; do :; done; else ! merge-green --yes; fi",
                        "case $x in a) { merge-green --dry-run; };; b) ! merge-green --yes;; esac",
                        "case $x in a) merge-green --dry-run;; b) merge-green --yes;; esac"):
            self.assertPasses(command)

    def test_the_same_alternative_or_separate_constructs_are_refused(self):
        for command in ("if x; then merge-green --dry-run; merge-green --yes; fi",
                        "if x; then merge-green --dry-run; fi; if y; then merge-green --yes; fi",
                        "if x; then { merge-green --dry-run; merge-green --yes; }; fi",
                        "case $x in a) merge-green --dry-run; merge-green --yes;; esac"):
            self.assertRefused(command)

    def test_alternatives_inside_a_shell_script_string(self):
        for command in ("sh -c 'if x; then merge-green --dry-run; else merge-green --yes; fi'",
                        "bash -c 'case $x in a) merge-green --dry-run;; b) merge-green --yes;; esac'",
                        "ssh host 'if x; then merge-green --dry-run; else merge-green --yes; fi'",
                        "eval 'if x; then merge-green --dry-run; else merge-green --yes; fi'"):
            self.assertPasses(command)
        for command in ("sh -c 'if x; then merge-green --dry-run; merge-green --yes; fi'",
                        "merge-green --dry-run; sh -c 'if x; then merge-green --yes; else :; fi'",
                        "sh -c 'if x; then merge-green --dry-run; else :; fi'; merge-green --yes"):
            self.assertRefused(command)


class GatedOnCapturedOutputTests(ChainCase):
    """The dry run's output is captured and the real run sits only in a branch that tests it."""

    def test_an_if_on_the_captured_output(self):
        for command in ('d=$(merge-green 1); if [[ $d == "would merge"* ]]; then merge-green 1 --yes; fi',
                        'd=$(merge-green 1); if [ "$d" = "would merge 1" ]; then merge-green 1 --yes; fi',
                        'd=$(merge-green 1); if [[ ${d} == "would merge"* ]]; then merge-green 1 --yes; fi',
                        'd=$(merge-green 1); if test "$d" = ok; then merge-green 1 --yes; fi',
                        'o=$(merge-green 1 2>&1 | tail -1); if echo "$o" | grep -q "^would merge"; then '
                        "merge-green 1 --yes; fi",
                        'd=$(merge-green 1); if [[ $x == a ]]; then echo a; elif [[ $d == "would merge"* ]]; then '
                        "merge-green 1 --yes; fi"):
            self.assertPasses(command)

    def test_a_case_arm_on_the_captured_output(self):
        for command in ('d=$(merge-green 1 2>&1 | tail -1); case $d in "would merge"*) merge-green 1 --yes;; esac',
                        'd=$(merge-green 1); case "$d" in ok|"would merge"*) merge-green 1 --yes;; *) sleep 1;; esac',
                        'd=$(merge-green 1)\ncase $d in\n  "would merge"*) merge-green 1 --yes;;\n  *) sleep 1;;\nesac'):
            self.assertPasses(command)

    def test_a_grep_on_the_captured_output_joined_by_and(self):
        self.assertPasses('o=$(merge-green 1 2>&1 | tail -3); echo "$o" | grep -q "^would merge" && '
                          "merge-green 1 --yes")
        self.assertPasses('o=$(merge-green 1); [[ $o == "would merge"* ]] && merge-green 1 --yes')

    def test_inside_a_loop_or_a_shell_string(self):
        for command in ('for i in 1 2 3; do d=$(merge-green 1 2>&1 | tail -1); case $d in "would merge"*) '
                        "merge-green 1 --yes; break ;; *) sleep 5 ;; esac; done",
                        'while true; do d=$(merge-green 1); if [[ $d == "would merge"* ]]; then merge-green 1 --yes; '
                        "break; fi; sleep 5; done",
                        'until false; do d=$(merge-green 1 | tail -1); case $d in "would merge"*) merge-green 1 '
                        "--yes; break;; esac; done",
                        "sh -c 'd=$(merge-green 1); if [[ $d == x ]]; then merge-green 1 --yes; fi'"):
            self.assertPasses(command)

    def test_the_real_run_outside_the_gated_branch_is_refused(self):
        self.assertRefused("d=$(merge-green 1); merge-green 1 --yes", flag="--yes")
        self.assertRefused('d=$(merge-green 1); if [[ $d == x ]]; then echo ok; fi; merge-green 1 --yes')
        self.assertRefused('d=$(merge-green 1); case $d in x*) :;; esac; merge-green 1 --yes')
        self.assertRefused('for i in 1 2; do d=$(merge-green 1); done; merge-green 1 --yes')

    def test_a_branch_that_tests_another_variable_is_refused(self):
        self.assertRefused('d=$(merge-green 1); e=x; if [[ $e == x ]]; then merge-green 1 --yes; fi')
        self.assertRefused('d=$(merge-green 1); case $e in x*) merge-green 1 --yes;; esac')
        self.assertRefused('o=$(merge-green 1); echo "$e" | grep -q x && merge-green 1 --yes')

    def test_the_else_or_default_arm_is_refused(self):
        self.assertRefused('d=$(merge-green 1); if [[ $d == "would merge"* ]]; then :; else merge-green 1 --yes; fi')
        self.assertRefused('d=$(merge-green 1); case $d in "would merge"*) :;; *) merge-green 1 --yes;; esac')
        self.assertRefused('d=$(merge-green 1)\ncase $d in\n  "would merge"*) :;;\n  *) merge-green 1 --yes;;\nesac')

    def test_a_shell_string_inside_the_gated_branch_is_gated(self):
        self.assertPasses("d=$(merge-green 1); if [[ $d == x ]]; then sh -c 'merge-green 1 --yes'; fi")

    def test_a_chain_broken_by_semicolon_or_or_or_not_a_test_is_refused(self):
        self.assertRefused('o=$(merge-green 1); echo "$o" | grep -q x || merge-green 1 --yes')
        self.assertRefused('o=$(merge-green 1); echo "$o" | grep -q x; merge-green 1 --yes')
        self.assertRefused('o=$(merge-green 1); echo "$o" && merge-green 1 --yes')

    def test_a_dry_run_that_is_not_captured_still_chains(self):
        self.assertRefused('merge-green 1; if [[ $d == x ]]; then merge-green 1 --yes; fi')
        self.assertRefused('d=$(echo hi); merge-green 1; if [[ $d == x ]]; then merge-green 1 --yes; fi')
        self.assertRefused('d=$(merge-green 1); merge-green 1; if [[ $d == x ]]; then merge-green 1 --yes; fi')

    def test_the_lesson_mistake_stays_refused(self):
        self.assertRefused("merge-green 1 2>&1 | tail -1 && merge-green 1 --yes")


class PipefailTests(ChainCase):
    """set -o pipefail makes `dry | tail && real` act on the dry run's own status."""

    def test_pipefail_then_a_piped_dry_run_and_the_real_run_joined_by_and(self):
        for setting in ("set -o pipefail", "set -eo pipefail", "set -euo pipefail", "set -o errexit -o pipefail"):
            with self.subTest(setting=setting):
                self.assertPasses(f"{setting}; merge-green 1 | tail -1 && merge-green 1 --yes")
        self.assertPasses("set -o pipefail; merge-green 1 2>&1 | tail -1 && echo ok && merge-green 1 --yes")
        self.assertPasses("sh -c 'set -o pipefail; merge-green 1 | tail -1 && merge-green 1 --yes'")

    def test_without_pipefail_it_is_refused(self):
        self.assertRefused("merge-green 1 | tail -1 && merge-green 1 --yes")
        self.assertRefused("set -e; merge-green 1 | tail -1 && merge-green 1 --yes")

    def test_semicolon_or_or_between_them_is_refused_even_with_pipefail(self):
        self.assertRefused("set -o pipefail; merge-green 1 | tail -1; merge-green 1 --yes")
        self.assertRefused("set -o pipefail; merge-green 1 | tail -1 || merge-green 1 --yes")
        self.assertRefused("set -o pipefail; merge-green 1 | tail -1 && echo ok; merge-green 1 --yes")
        self.assertRefused("set -o pipefail; merge-green 1 | tail -1; echo ok && merge-green 1 --yes")
        self.assertRefused("set -o pipefail; merge-green 1 | merge-green 1 --yes")

    def test_pipefail_turned_off_or_set_later_or_in_another_shell_is_refused(self):
        self.assertRefused("set -o pipefail; set +o pipefail; merge-green 1 | tail -1 && merge-green 1 --yes")
        self.assertRefused("merge-green 1 | tail -1; set -o pipefail; merge-green 1 --yes")
        self.assertRefused("set -o pipefail; sh -c 'merge-green 1 | tail -1 && merge-green 1 --yes'")

    def test_pipefail_does_not_excuse_a_dry_run_that_is_not_piped(self):
        self.assertRefused("set -o pipefail; merge-green 1 && merge-green 1 --yes")


class ReviewRoundTests(ChainCase):
    """The gate must make the real run depend on the test, and pipefail must be on in the shell that runs the chain."""

    def test_an_or_in_the_condition_makes_the_test_no_gate(self):
        for command in ("d=$(merge-green 1); if [[ $d == x ]] || true; then merge-green 1 --yes; fi",
                        "d=$(merge-green 1); true || [[ $d == x ]] && merge-green 1 --yes",
                        "d=$(merge-green 1); if true || [[ $d == x ]]; then merge-green 1 --yes; fi"):
            self.assertRefused(command)

    def test_an_or_of_tests_on_the_output_is_a_gate(self):
        self.assertPasses("d=$(merge-green 1); if [[ $d == a ]] || [[ $d == b ]]; then merge-green 1 --yes; fi")
        self.assertPasses("d=$(merge-green 1); [[ $d == a ]] || [[ $d == b ]] && merge-green 1 --yes")

    def test_a_default_arm_among_joined_patterns_is_refused(self):
        for command in ("d=$(merge-green 1); case $d in x|*) merge-green 1 --yes;; esac",
                        "d=$(merge-green 1); case $d in *|x) merge-green 1 --yes;; esac",
                        "d=$(merge-green 1); case $d in a) :;; b|c|*) merge-green 1 --yes;; esac"):
            self.assertRefused(command)
        self.assertPasses("d=$(merge-green 1); case $d in a|b) merge-green 1 --yes;; *) :;; esac")

    def test_pipefail_that_is_not_on_for_the_chain_is_refused(self):
        for setting in ("(set -o pipefail)", "if cond; then set -o pipefail; fi", "set -o pipefail | cat",
                        "cond && set -o pipefail"):
            self.assertRefused(f"{setting}; merge-green 1 | tail -1 && merge-green 1 --yes")
        self.assertRefused("set -o pipefail &\nmerge-green 1 | tail -1 && merge-green 1 --yes")

    def test_pipefail_on_in_the_shell_that_runs_the_chain_passes(self):
        self.assertPasses("set -o pipefail && merge-green 1 | tail -1 && merge-green 1 --yes")
        self.assertPasses("(set -o pipefail; merge-green 1 | tail -1 && merge-green 1 --yes)")
        self.assertPasses("{ set -o pipefail; merge-green 1 | tail -1 && merge-green 1 --yes; }")

    def test_a_grep_pattern_or_an_overwritten_variable_is_no_gate(self):
        self.assertRefused('d=$(merge-green 1); echo hi | grep -q "$d" && merge-green 1 --yes')
        self.assertRefused("d=$(merge-green 1); d=ok; if [[ $d == ok ]]; then merge-green 1 --yes; fi")

    def test_a_grep_fed_the_output_is_a_gate(self):
        self.assertPasses('d=$(merge-green 1); grep -q ok <<< "$d" && merge-green 1 --yes')
        self.assertPasses('d=$(merge-green 1); if printf %s "$d" | grep -q ok; then merge-green 1 --yes; fi')
