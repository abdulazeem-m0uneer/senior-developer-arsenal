"""typed-sha: a SHA given to gh pr merge --match-head-commit or a git push lease must come from git, not be typed."""
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_guard_unseen_hash import FULL, SHORT, RuleCase, SCRIPT, assistant_text, tool_result

import guard_lessons  # noqa: E402  (test_guard_unseen_hash put hooks/ on the path)
import guard_unseen_hash  # noqa: E402

UNPRINTED = "9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d"  # a 40-character id no tool printed
ENTRY = {"rule": "typed-sha", "lesson": "G030", "min_version": "1.30.0"}
NEW_HOOK = mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 30, 0))


class TypedShaCase(RuleCase):
    """A registry naming typed-sha, a hook of 1.30.0, and a transcript where a tool printed only FULL."""

    def setUp(self):
        super().setUp()
        NEW_HOOK.start()
        self.addCleanup(NEW_HOOK.stop)
        self.registry(ENTRY)
        self.path = self.write(assistant_text(f"head is {UNPRINTED}"), tool_result("toolu_1", f"{FULL}\n"))

    def judge(self, command, transcript="session", agent_id=None):
        return guard_lessons.judge(command, str(self.project), agent_id=agent_id,
                                   transcript=self.path if transcript == "session" else transcript)

    def assertRefused(self, command, transcript="session", **kwargs):
        hit = self.judge(command, transcript, **kwargs)
        self.assertIsNotNone(hit, command)
        self.assertEqual((hit.lesson, hit.rule), ("G030", "typed-sha"), command)
        return hit

    def assertPasses(self, command, transcript="session", **kwargs):
        self.assertIsNone(self.judge(command, transcript, **kwargs), command)


class MatchHeadCommitTests(TypedShaCase):
    def test_a_short_literal_is_refused_with_how_to_pass_the_sha(self):
        hit = self.assertRefused(f"gh pr merge 5 --squash --match-head-commit {SHORT}")
        self.assertIn('--match-head-commit "$(git rev-parse HEAD)"', hit.reason)
        self.assertIn('--force-with-lease=<ref>:"$(git rev-parse origin/<ref>)"', hit.reason)
        self.assertIn("short or was never printed in this session", hit.reason)

    def test_a_short_literal_is_refused_even_when_printed_and_without_a_transcript(self):
        for transcript in ("session", None, str(self.dir / "missing.jsonl")):
            for value in (f" {SHORT}", f"={SHORT}", f" '{FULL[:39]}'", f'="{FULL[:12].upper()}"'):
                self.assertRefused(f"gh pr merge 5 --match-head-commit{value}", transcript)

    def test_a_printed_full_sha_passes_in_every_form(self):
        for value in (f" {FULL}", f"={FULL}", f' "{FULL}"', f"='{FULL}'", f" {FULL.upper()}"):
            self.assertPasses(f"gh pr merge 5 --match-head-commit{value}")

    def test_a_full_sha_no_tool_printed_is_refused(self):
        for value in (f" {UNPRINTED}", f"={UNPRINTED}", f' "{UNPRINTED}"'):
            self.assertRefused(f"gh pr merge 5 --match-head-commit{value} --squash")

    def test_without_a_usable_transcript_an_unprinted_full_sha_passes(self):
        for transcript in (None, "", str(self.dir / "missing.jsonl"), str(self.dir)):
            self.assertPasses(f"gh pr merge 5 --match-head-commit {UNPRINTED}", transcript)

    def test_substitutions_and_variables_pass(self):
        for value in ('"$(git rev-parse HEAD)"', "$(git rev-parse HEAD)", '"$HEAD_SHA"', "${HEAD_SHA}",
                      "`git rev-parse HEAD`", f'"$(echo {UNPRINTED})"', f"{UNPRINTED[:20]}$(true)"):
            self.assertPasses(f"gh pr merge 5 --match-head-commit {value}")
            self.assertPasses(f"gh pr merge 5 --match-head-commit={value}")
        self.assertPasses('H=$(git rev-parse HEAD); gh pr merge 5 --match-head-commit "$H"')
        self.assertPasses('H="$(git rev-parse HEAD)"; gh pr merge 5 --match-head-commit "$H"')
        self.assertPasses('gh pr merge 5 --match-head-commit "$(git rev-parse --short=40 HEAD)"')

    def test_a_pin_from_git_is_never_judged_even_with_rev_parse_short(self):
        # Only a typed SHA is judged; GitHub itself refuses a short pin that git printed.
        for value in (' "$(git rev-parse --short HEAD)"', '="$(git rev-parse --short HEAD)"',
                      " $(git rev-parse --short HEAD)", ' "$(git -C "$(pwd)" rev-parse --short HEAD)"',
                      ' "$(git rev-parse --short=41 HEAD)"', ' "$(git -C repo rev-parse --short=12 origin/main)"'):
            self.assertPasses(f"gh pr merge 5 --match-head-commit{value}", None)
        self.assertPasses('S=$(git rev-parse --short HEAD); gh pr merge 5 --match-head-commit "$S"', None)

    def test_a_long_pin_is_judged_in_linear_time(self):
        started = time.monotonic()
        self.assertPasses("gh pr merge 5 --match-head-commit '" + "$(" * 50000 + "'", None)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_a_pin_in_a_wait_loop_condition_is_judged(self):
        self.assertRefused(f"while ! gh pr merge 5 --match-head-commit {SHORT}; do sleep 5; done", None)
        self.assertRefused(f"until gh pr merge 5 --match-head-commit={UNPRINTED}; do sleep 5; done")

    def test_a_sha_typed_into_a_variable_of_the_same_line_is_judged(self):
        for setter in ("H=", "export H=", "H='", "H=$'"):
            quote = "'" if setter.endswith("'") else ""
            self.assertRefused(f'{setter}{UNPRINTED}{quote}; gh pr merge 5 --match-head-commit "$H"')
            self.assertRefused(f"{setter}{SHORT}{quote} && gh pr merge 5 --match-head-commit=${{H}}", None)
            self.assertPasses(f'{setter}{FULL}{quote}; gh pr merge 5 --match-head-commit "$H"')
        self.assertRefused(f"OLD={UNPRINTED[:9]}; git push --force-with-lease=main:$OLD origin main")
        self.assertPasses(f"OLD={FULL[:9]}; git push --force-with-lease=main:\"$OLD\" origin main")
        self.assertPasses(f'H={UNPRINTED} gh pr merge 5 --match-head-commit "$H"')  # $H expands before H is set

    def test_an_ansi_c_quoted_sha_is_judged_as_typed(self):
        self.assertRefused(f"gh pr merge 5 --match-head-commit $'{UNPRINTED}'")
        self.assertRefused(f"gh pr merge 5 --match-head-commit=$'{SHORT}'", None)
        self.assertRefused(f"git push --force-with-lease=main:$'{UNPRINTED}' origin main")
        self.assertPasses(f"gh pr merge 5 --match-head-commit $'{FULL}'")

    def test_through_sh_c_wrappers_and_repo_option(self):
        self.assertRefused(f"sh -c 'gh pr merge 5 --match-head-commit {SHORT}'")
        self.assertRefused(f'bash -lc "gh pr merge 5 --match-head-commit={UNPRINTED}"')
        self.assertRefused(f"timeout 60 gh pr merge 5 --match-head-commit {SHORT}")
        self.assertRefused(f"env GH_PAGER= gh -R o/r pr merge 5 --match-head-commit {UNPRINTED}")
        self.assertRefused(f"git fetch && gh pr merge 5 --match-head-commit {SHORT}")
        self.assertPasses(f"sh -c 'gh pr merge 5 --match-head-commit {FULL}'")

    def test_other_commands_and_values_are_not_judged(self):
        for command in (f"gh pr view 5 --match-head-commit {SHORT}", f"gh pr merge 5 --body {SHORT}",
                        "gh pr merge 5 --squash", "gh pr merge 5 --match-head-commit", "gh pr merge 5 "
                        "--match-head-commit=", f"git log {UNPRINTED}", f"echo gh pr merge --match-head-commit {SHORT}",
                        "gh pr merge 5 --match-head-commit main", "gh pr merge 5 --match-head-commit HEAD~1"):
            self.assertPasses(command)

    def test_a_subagent_is_judged_on_its_own_transcript(self):
        agent = self.dir / "session" / "subagents" / "agent-a9.jsonl"
        agent.parent.mkdir(parents=True)
        agent.write_text(json.dumps(tool_result("toolu_1", UNPRINTED)) + "\n", encoding="utf-8")
        self.assertPasses(f"gh pr merge 5 --match-head-commit {UNPRINTED}", agent_id="a9")
        self.assertRefused(f"gh pr merge 5 --match-head-commit {FULL}", agent_id="a9")  # the parent's output


class ForceWithLeaseTests(TypedShaCase):
    def test_an_unprinted_expected_value_is_refused(self):
        for value in (UNPRINTED, UNPRINTED[:7], UNPRINTED[:12], f'"{UNPRINTED}"'):
            self.assertRefused(f"git push --force-with-lease=main:{value} origin main")
        self.assertRefused(f"git -C repo push origin feat --force-with-lease=feat:{UNPRINTED[:9]}")
        self.assertRefused(f"sh -c 'git push --force-with-lease=main:{UNPRINTED} origin main'")

    def test_a_printed_value_passes_short_or_full(self):
        for value in (FULL, SHORT, FULL[:12], f"'{FULL}'"):
            self.assertPasses(f"git push --force-with-lease=main:{value} origin main")

    def test_without_a_transcript_a_lease_value_passes(self):
        self.assertPasses(f"git push --force-with-lease=main:{UNPRINTED[:7]} origin main", None)
        self.assertPasses(f"git push --force-with-lease=main:{UNPRINTED} origin main", None)

    def test_substitutions_other_forms_and_other_values_pass(self):
        for command in ('git push --force-with-lease=main:"$(git rev-parse origin/main)" origin main',
                        "git push --force-with-lease=main:$OLD origin main", "git push --force-with-lease origin main",
                        "git push --force-with-lease=main origin main", "git push --force-with-lease=main: origin main",
                        f"git push --force-with-lease main:{UNPRINTED} origin main",  # not a form git accepts
                        "git push --force-with-lease=main:origin/main origin main",
                        f"git push --force-with-lease=main:x:{UNPRINTED} origin main",  # git expects 'x:<sha>'
                        f"git push --force-with-lease=main:{UNPRINTED[:6]} origin main",  # under 7: not a SHA
                        f"git push --force-with-lease=main:{UNPRINTED}0 origin main",  # over 40
                        f"git push origin {UNPRINTED}:main", f"git fetch --force-with-lease=main:{UNPRINTED}",
                        f"git stash push --force-with-lease=main:{UNPRINTED}",  # push is not the subcommand
                        'git push --force-with-lease=main:"$(git rev-parse --short origin/main)" origin main'):
            self.assertPasses(command)


class FailOpenTests(TypedShaCase):
    def test_a_call_without_either_option_is_not_parsed_again(self):
        import guard_typed_sha
        with mock.patch.object(guard_typed_sha, "plain_quotes", wraps=guard_typed_sha.plain_quotes) as parse:
            self.assertFalse(guard_lessons.typed_sha("git log --oneline -5 && gh pr view 5", None, None))
            self.assertEqual(parse.call_count, 0)
            self.assertTrue(guard_lessons.typed_sha(f"gh pr merge 5 --match-head-commit {SHORT}", None, None))
            self.assertEqual(parse.call_count, 1)

    def test_a_transcript_error_leaves_only_the_short_check(self):
        with mock.patch.object(guard_unseen_hash, "read_tail", side_effect=OSError("boom")):
            self.assertPasses(f"gh pr merge 5 --match-head-commit {UNPRINTED}")
            self.assertPasses(f"git push --force-with-lease=main:{UNPRINTED} origin main")
            self.assertRefused(f"gh pr merge 5 --match-head-commit {SHORT}")

    def test_a_timeout_after_one_unseen_token_judges_none_for_typed_sha(self):
        ticks = iter([0, 0, 1])  # the deadline is 0.2: the first absence search runs, the second times out
        path = self.write(tool_result("toolu_1", "nothing here"))
        tokens = [UNPRINTED, "1234567" + UNPRINTED[7:]]
        self.assertEqual(guard_unseen_hash.unseen_tokens(tokens, path, clock=lambda: next(ticks)), [UNPRINTED])
        ticks = iter([0, 0, 1])
        self.assertEqual(guard_unseen_hash.unseen_tokens(tokens, path, clock=lambda: next(ticks), partial=False), [])

    def test_a_timeout_in_the_hook_leaves_only_the_short_check(self):
        real_tick, calls = guard_unseen_hash.Transcript.tick, []

        def second_tick_times_out(transcript):
            calls.append(1)
            if len(calls) > 1:
                raise guard_unseen_hash.OutOfTime()
            real_tick(transcript)

        with mock.patch.object(guard_unseen_hash.Transcript, "tick", second_tick_times_out):
            self.assertPasses(f"gh pr merge 5 --match-head-commit abcdef1{UNPRINTED[7:]} && "  # in no entry at all
                              f"git push --force-with-lease=main:1234567{UNPRINTED[7:]} origin main")
        self.assertEqual(len(calls), 2)

    def test_one_transcript_read_for_the_whole_call(self):
        command = "; ".join(f"git push --force-with-lease=main:{FULL[:n]} origin main" for n in range(7, 41))
        with mock.patch.object(guard_unseen_hash, "read_tail", wraps=guard_unseen_hash.read_tail) as read:
            self.assertPasses(command)
            self.assertRefused(command + f"; gh pr merge 5 --match-head-commit {UNPRINTED}")
        self.assertEqual(read.call_count, 2)


class RegistryTests(TypedShaCase):
    def test_off_until_a_registry_entry_names_it(self):
        self.registry()
        self.assertPasses(f"gh pr merge 5 --match-head-commit {SHORT}")

    def test_bad_registry_values_are_skipped_and_never_refuse(self):
        for bad in ({"window_mb": 4}, {"allow": ["abc1234"]}, {"programs": ["send.sh"]}, {"enabled": "yes"},
                    {"lesson": "nope"}, {"reason": ""}, {"min_version": "1.30"}, {"shell": "bash"}):
            self.registry({**ENTRY, **bad})
            self.assertPasses(f"gh pr merge 5 --match-head-commit {SHORT}")
            self.assertTrue(guard_lessons.registry_problems(str(self.project)), bad)

    def test_enabled_false_and_a_reason_of_its_own(self):
        self.registry({**ENTRY, "enabled": False})
        self.assertPasses(f"gh pr merge 5 --match-head-commit {SHORT}")
        self.registry({**ENTRY, "reason": "Use merge_green.py."})
        self.assertEqual(self.judge(f"gh pr merge 5 --match-head-commit {SHORT}").reason, "Use merge_green.py.")

    def test_min_version_1_30_0_skips_on_older_hooks(self):
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 29, 1)):
            self.assertPasses(f"gh pr merge 5 --match-head-commit {SHORT}")
            self.assertEqual(guard_lessons.registry_problems(str(self.project)), [])  # skipped quietly
        self.assertRefused(f"gh pr merge 5 --match-head-commit {SHORT}")


class HookTests(TypedShaCase):
    """guard.py pre passes the hook input's transcript_path to typed-sha."""

    def pre(self, command, transcript):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command},
                   "cwd": str(self.project), "permission_mode": "default"}
        if transcript:
            payload["transcript_path"] = transcript
        base = {k: v for k, v in os.environ.items()
                if k not in ("ARSENAL_GUARD", "ARSENAL_LESSON_GUARDS", "ARSENAL_GUARD_DESTRUCTIVE",
                             "ARSENAL_RUN_LIMITS", "CLAUDE_PROJECT_DIR", "ARSENAL_PROFILE")}
        result = subprocess.run([sys.executable, str(SCRIPT), "pre"], cwd=self.project, input=json.dumps(payload),
                                capture_output=True, text=True, env=base)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None

    def test_the_hook_denies_with_and_without_a_transcript(self):
        self.registry({"rule": "typed-sha", "lesson": "G030"})  # the installed hook may be older than 1.30.0
        out = self.pre(f"gh pr merge 5 --match-head-commit {UNPRINTED}", self.path)
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("G030 (typed-sha)", out["permissionDecisionReason"])
        self.assertIsNone(self.pre(f"gh pr merge 5 --match-head-commit {FULL}", self.path))
        self.assertIsNone(self.pre(f"gh pr merge 5 --match-head-commit {UNPRINTED}", None))
        self.assertEqual(self.pre(f"gh pr merge 5 --match-head-commit {SHORT}", None)["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
