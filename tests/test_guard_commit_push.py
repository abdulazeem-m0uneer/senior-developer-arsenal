"""Tests for the opt-in commit-then-push lesson guard (hooks/guard_commit_push.py, wired in guard_lessons)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import guard_commit_push  # noqa: E402
import guard_lessons  # noqa: E402
import test_guard  # noqa: E402

ENTRY = {"rule": "commit-then-push", "lesson": "G028", "programs": ["push_once.py", "merge-green"],
         "min_version": "1.39.0"}
COMMIT = 'git commit -m "feat: x"'


class PushCase(unittest.TestCase):
    """A project whose registry names commit-then-push, and a 1.39.0 hook."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.project = self.dir / "project"
        (self.project / ".agents").mkdir(parents=True)
        env = {"LESSONS_GUARDS_GLOBAL_FILE": str(self.dir / "home" / "lesson-guards.json"),
               "LESSONS_GUARD_HITS_FILE": str(self.dir / "home" / "hits.jsonl")}
        for patch in (mock.patch.dict(os.environ, env), mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 39, 0))):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.registry(ENTRY)

    def registry(self, *guards):
        (self.project / ".agents" / "lesson-guards.json").write_text(json.dumps({"guards": list(guards)}),
                                                                     encoding="utf-8")

    def judge(self, command, events=None, agent_id=None):
        session = (lambda: {"events": events, "red": set(), "keys": set(), "check_keys": None}) \
            if events is not None else None
        return guard_lessons.judge(command, str(self.project), session, agent_id=agent_id)

    def assertRefused(self, command, events=None, agent_id=None):
        hit = self.judge(command, events, agent_id)
        self.assertIsNotNone(hit, command)
        self.assertEqual((hit.rule, hit.lesson), ("commit-then-push", "G028"), command)
        return hit

    def assertPasses(self, command, events=None, agent_id=None):
        self.assertIsNone(self.judge(command, events, agent_id), command)


class RefusalTests(PushCase):
    def test_commit_then_push_with_every_separator(self):
        for sep in (" && ", "; ", "\n", " || "):
            self.assertRefused(f"{COMMIT}{sep}git push origin feat")

    def test_status_alone_is_not_enough(self):
        self.assertRefused(f"{COMMIT} && git status && git push")

    def test_log_alone_is_not_enough(self):
        self.assertRefused(f"{COMMIT} && git log -1 && git push")

    def test_status_and_log_before_the_commit_do_not_count(self):
        self.assertRefused(f"git status; git log -1; {COMMIT}; git push")

    def test_rev_parse_alone_is_not_enough(self):
        self.assertRefused(f"{COMMIT} && git rev-parse HEAD && git push")

    def test_rev_parse_of_another_ref_is_not_a_log(self):
        self.assertRefused(f"{COMMIT} && git status && git rev-parse origin/main && git push")

    def test_registry_push_wrappers(self):
        for push in ("python3 scripts/push_once.py feat", "./merge-green 12", "bash tools/push_once.py"):
            self.assertRefused(f"{COMMIT} && {push}")

    def test_git_dash_c_forms(self):
        self.assertRefused('git -C /work/repo commit -m x && git -C /work/repo push')
        self.assertRefused('git -c user.name=a -C /w commit -am x; git --git-dir=/w/.git push origin HEAD')

    def test_commit_and_push_inside_an_if_without_the_evidence(self):
        self.assertRefused(f"if grep -q ok gate.log; then {COMMIT}; git push; fi")

    def test_inside_sh_c(self):
        self.assertRefused(f"bash -c '{COMMIT} && git push'")

    def test_a_second_push_after_a_second_commit(self):
        self.assertRefused(f"{COMMIT} && git status && git log -1 && git push && {COMMIT} && git push")

    def test_amend_counts_as_a_commit(self):
        self.assertRefused("git commit --amend --no-edit && git push --force-with-lease")

    def test_reason_names_the_fix(self):
        reason = self.assertRefused(f"{COMMIT} && git push").reason
        self.assertIn("git status", reason)
        self.assertIn("git log -1", reason)

    def test_a_push_in_a_double_quoted_substitution(self):
        self.assertRefused(f'{COMMIT}; echo "$(git push)"')
        self.assertRefused(f'{COMMIT}; echo "pushed: `git push`"')
        self.assertRefused(f'{COMMIT}; echo "a $(echo "b $(git push)")"')

    def test_a_wrapper_named_through_a_shell_variable(self):
        self.assertRefused(f"{COMMIT}; S=push_once.py; python3 $S")
        self.assertRefused(f"{COMMIT}; S=scripts/merge-green; $S 12")

    def test_a_wrapper_behind_a_launcher(self):
        self.assertRefused(f"{COMMIT}; env FOO=1 python3 scripts/push_once.py feat")

    def test_rev_parse_that_prints_the_branch_is_not_the_log(self):
        self.assertRefused(f"{COMMIT}; git status; git rev-parse --abbrev-ref HEAD; git push")
        self.assertRefused(f"{COMMIT}; git status; git rev-parse --symbolic-full-name HEAD; git push")

    def test_output_written_to_a_file_is_not_read(self):
        self.assertRefused(f"{COMMIT}; git status > s.txt; git log -1 > l.txt; git push")
        self.assertRefused("git commit -m x && git status && git log -1 > log.txt && git push origin")
        self.assertRefused(f"{COMMIT}; git status >> s.txt; git log -1; git push")
        self.assertRefused(f"{COMMIT}; git status &> s.txt; git log -1; git push")
        self.assertRefused(f"{COMMIT}; git status; git log -1 1> l.txt; git push")
        self.assertRefused(f"{COMMIT}; git status; git log -1 >& l.txt; git push")

    def test_output_counted_by_a_pipe_is_not_read(self):
        self.assertRefused("git commit -m x && git status --porcelain=v2 | wc -l && git log -1 && git push origin")
        self.assertRefused(f"{COMMIT}; git status; git log -1 | wc; git push")
        self.assertRefused(f"{COMMIT}; git status | grep -c M; git log -1; git push")
        self.assertRefused(f"{COMMIT}; git status | grep --count M; git log -1; git push")
        self.assertPasses(f"{COMMIT}; git status | grep M; git log -1; git push")
        self.assertPasses(f"{COMMIT}; git status && wc -l notes.txt && git log -1 && git push")

    def test_output_a_later_pipe_stage_discards_is_not_read(self):
        self.assertRefused("git commit -m x && git status | cat > /dev/null; git log -1; git push")
        self.assertRefused("git commit -m x && git status | tee /dev/null >/dev/null; git log -1; git push")
        self.assertRefused(f"{COMMIT}; git status; git log -1 | sed 1p | cat >> l.txt; git push")
        self.assertPasses(f"{COMMIT}; git status | cat; git log -1 | tee l.txt; git push")
        self.assertPasses(f"{COMMIT}; git status | cat 2>/dev/null; git log -1; git push")
        self.assertPasses(f"{COMMIT}; git status | cat; cat > /dev/null < f; git log -1; git push")

    def test_a_number_spaced_from_the_redirection_is_an_argument_not_a_descriptor(self):
        self.assertRefused("git commit -m x && git status && git log -n 3 >f && git push")
        self.assertRefused(f"{COMMIT}; git status; git log -n 2 > f; git push")
        self.assertRefused(f"{COMMIT}; git status; git log -n 2 >& f; git push")
        self.assertPasses(f"{COMMIT}; git status; git log -n 3 2>f; git push")
        self.assertPasses(f"{COMMIT}; git status; git log -n 3 2>&1; git push")

    def test_a_log_of_no_commits_is_not_the_log(self):
        for log in ("git log --oneline -0", "git log -n 0", "git log -n0", "git log --max-count=0",
                    "git log --max-count 0"):
            self.assertRefused(f"git commit -m x && git status && {log} && git push origin")
        self.assertPasses("git commit -m x && git status && git log -10 && git push origin")

    def test_output_thrown_away_is_not_read(self):
        self.assertRefused(f"{COMMIT}; git status >/dev/null; git log -1 >/dev/null; git push")
        self.assertRefused(f"{COMMIT}; git status &>/dev/null; git log -1; git push")
        self.assertRefused(f"{COMMIT}; git status; git log -1 >/dev/null 2>&1; git push")
        self.assertRefused(f"{COMMIT}; git status 1>/dev/null; git log -1; git push")

    def test_the_push_in_the_other_arm_of_an_if_is_judged_against_its_own_arm(self):
        self.assertRefused(f"if x; then {COMMIT}; git push; else git status; fi")
        self.assertRefused(f"{COMMIT}; if x; then git push; fi")
        self.assertRefused(f"{COMMIT}; if x; then git push; else git push --force; fi")

    def test_evidence_in_the_other_arm_does_not_count(self):
        self.assertRefused(f"{COMMIT}; if x; then git status; git log -1; else git push; fi")
        self.assertRefused(f"{COMMIT}; git status; if x; then git log -1; else :; fi; git push")

    def test_a_commit_of_an_earlier_call_with_no_reads_before_the_push(self):
        self.assertRefused("git push", [{"event": "git_commit"}])
        self.assertRefused("git status && git push", [{"event": "git_commit"}, {"event": "git_status"}])
        self.assertRefused("git push", [{"event": "git_commit"}, {"event": "git_log"}])
        self.assertRefused("git status && git push", [{"event": "git_commit"}])
        self.assertRefused("python3 scripts/push_once.py feat", [{"event": "git_commit"}])

    def test_a_reading_before_the_commit_does_not_count(self):
        self.assertRefused("git push", [{"event": "git_status"}, {"event": "git_log"}, {"event": "git_commit"}])

    def test_a_second_commit_resets_the_reads(self):
        events = [{"event": "git_commit"}, {"event": "git_status"}, {"event": "git_log"}, {"event": "git_commit"}]
        self.assertRefused("git push", events)


class PassTests(PushCase):
    def test_status_and_log_between(self):
        for sep in (" && ", "; ", "\n"):
            self.assertPasses(sep.join([COMMIT, "echo rc=$?", "git status", "git log -1", "git push origin feat"]))

    def test_log_then_status_order(self):
        self.assertPasses(f"{COMMIT} && git log -1 --format=%H && git status --short && git push")

    def test_rev_parse_head_and_status_are_equivalent(self):
        self.assertPasses(f"{COMMIT} && git rev-parse HEAD && git status && git push")
        self.assertPasses(f"{COMMIT} && git status && git rev-parse --verify HEAD && git push")

    def test_wrapper_with_the_evidence(self):
        self.assertPasses(f"{COMMIT} && git status && git log -1 && python3 scripts/push_once.py feat")

    def test_dry_run_commit(self):
        self.assertPasses("git commit --dry-run -m x && git push")

    def test_push_without_a_commit(self):
        self.assertPasses("git push origin feat")
        self.assertPasses("git status && git push")
        self.assertPasses("python3 scripts/push_once.py feat")

    def test_commit_without_a_push(self):
        self.assertPasses(f"{COMMIT} && git status && git log -1")
        self.assertPasses(COMMIT)

    def test_push_before_the_commit(self):
        self.assertPasses(f"git push && {COMMIT}")

    def test_gated_script_with_the_evidence_inside_the_if(self):
        self.assertPasses(f"if grep -q green gate.log; then {COMMIT}; echo rc=$?; git log -1; git status; "
                          "git push origin feat; fi")

    def test_gated_script_over_several_lines(self):
        self.assertPasses(f"if grep -q green gate.log; then\n  {COMMIT}\n  echo rc=$?\n  git status\n  git log -1\n"
                          "  git push\nfi")

    def test_git_dash_c_forms_with_the_evidence(self):
        self.assertPasses("git -C /w commit -m x && git -C /w status && git -C /w log -1 && git -C /w push")

    def test_a_pipe_to_a_filter_still_reads_the_output(self):
        self.assertPasses(f"{COMMIT} && git status | head -5 && git log -1 | cat && git push")

    def test_a_heredoc_that_only_writes_a_script_is_never_judged(self):
        self.assertPasses(f"cat > ship.sh <<'EOF'\n{COMMIT}\ngit push\nEOF\nchmod +x ship.sh")

    def test_quoted_text_is_not_a_command(self):
        self.assertPasses('echo "git commit -m x && git push"')
        self.assertPasses('grep -n "git commit" notes.md && git push')

    def test_a_wrapper_is_judged_only_when_the_entry_names_it(self):
        self.registry({**ENTRY, "programs": ["other.py"]})
        self.assertPasses(f"{COMMIT} && python3 scripts/push_once.py feat")
        self.assertRefused(f"{COMMIT} && git push")

    def test_off_until_an_entry_names_it(self):
        self.registry()
        self.assertPasses(f"{COMMIT} && git push")

    def test_disabled_entry_passes(self):
        self.registry({**ENTRY, "enabled": False})
        self.assertPasses(f"{COMMIT} && git push")

    def test_older_hook_skips_the_entry(self):
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 38, 0)):
            self.assertPasses(f"{COMMIT} && git push")

    def test_substitutions_in_double_quotes_are_read(self):
        self.assertPasses(f'{COMMIT}; echo "head=$(git rev-parse HEAD)"; git status; git push')
        self.assertPasses(f'{COMMIT}; echo "$(git log -1)"; git status; git push')
        self.assertPasses(f'{COMMIT}; echo "`git log -1`"; echo "$(git status)"; git push')
        self.assertPasses(f"{COMMIT}; echo $(git rev-parse HEAD); git status; git push")
        self.assertPasses(f"{COMMIT}; echo `git log -1`; git status; git push")

    def test_a_substitution_in_single_quotes_is_text(self):
        self.assertPasses("echo '$(git push)'; " + COMMIT)
        self.assertPasses(f"{COMMIT}; echo '$(git push)'")

    def test_an_unbalanced_substitution_never_raises(self):
        self.assertPasses(f'{COMMIT}; echo "$(git log -1')

    def test_a_push_dry_run_sends_nothing(self):
        self.assertPasses(f"{COMMIT}; git push --dry-run")
        self.assertPasses(f"{COMMIT}; git push -n origin feat")
        self.assertPasses(f"{COMMIT}; git push -un origin feat")
        self.assertPasses(f"{COMMIT}; python3 scripts/push_once.py --dry-run feat")
        self.assertPasses(f"{COMMIT}; python3 scripts/push_once.py feat --dry-run")
        self.assertPasses(f"{COMMIT}; python3 scripts/push_once.py --note=x --dry-run")

    def test_dry_run_as_the_value_of_another_option_still_pushes(self):
        self.assertRefused(f"{COMMIT}; python3 scripts/push_once.py --note --dry-run")
        self.assertRefused(f"{COMMIT}; python3 scripts/push_once.py -m --dry-run feat")
        self.assertRefused(f"{COMMIT}; python3 scripts/push_once.py feat -- --dry-run")

    def test_an_n_after_o_in_a_cluster_is_the_option_value(self):
        self.assertRefused(f"{COMMIT}; git push -on origin")
        self.assertRefused(f"{COMMIT}; git push -uon origin")
        self.assertPasses(f"{COMMIT}; git push -no ci.skip origin")
        self.assertPasses(f"{COMMIT}; git push -fn origin")

    def test_a_push_option_value_is_not_a_dry_run_flag(self):
        self.assertRefused(f"{COMMIT}; git push -o ci.skip origin")

    def test_a_push_option_value_in_a_cluster_is_not_the_repository(self):
        self.assertRefused(f"{COMMIT} && git push -uo ./x origin main")
        self.assertRefused(f"{COMMIT} && git push -fo ../opt origin")
        self.assertPasses(f"{COMMIT} && git push -uf ./x main")
        self.assertPasses(f"{COMMIT} && git push -ouv ./x")

    def test_exclusive_arms_are_not_one_chain(self):
        self.assertPasses(f"if x; then {COMMIT}; else git push; fi")
        self.assertPasses(f"if x; then {COMMIT}; elif y; then git push; else git push; fi")
        self.assertPasses(f"case $1 in a) {COMMIT};; b) git push;; esac")

    def test_the_evidence_inside_the_same_arm(self):
        self.assertPasses(f"if x; then {COMMIT}; git status; git log -1; git push; else git push; fi")

    def test_stderr_thrown_away_or_sent_to_stderr_still_reads(self):
        self.assertPasses(f"{COMMIT}; git status 2>/dev/null; git log -1 2>&1; git push")
        self.assertPasses(f"{COMMIT}; git status >&2; git log -1 1>&2; git push")

    def test_a_read_of_the_commit_in_the_earlier_call(self):
        events = [{"event": "git_commit"}, {"event": "git_status"}, {"event": "git_log"}]
        self.assertPasses("git push", events)
        self.assertPasses("python3 scripts/push_once.py feat", events)
        self.assertPasses("git status && git log -1 && git push", [{"event": "git_commit"}])

    def test_a_commit_already_pushed_is_settled(self):
        self.assertPasses("git push", [{"event": "git_commit"}, {"event": "git_push"}])

    def test_no_commit_in_the_session(self):
        self.assertPasses("git push", [])
        self.assertPasses("git push", [{"event": "git_status"}, {"event": "git_log"}, {"event": "call"}, 3, "x"])

    def test_a_push_dry_run_in_a_later_call_passes(self):
        self.assertPasses("git push --dry-run", [{"event": "git_commit"}])


GATE = "git status && git log -1"


class SubstitutionTests(PushCase):
    """A substitution inside a quoted option value must not hide the subcommand behind it."""

    def test_a_quoted_substitution_as_the_git_directory(self):
        self.assertRefused(f'{COMMIT} && git -C "$(pwd)" push')
        self.assertRefused(f'git -C "$(git rev-parse --show-toplevel)" commit -m x && git push')

    def test_a_quoted_substitution_as_a_config_value(self):
        self.assertRefused(f'git -c k="$(x)" commit -m y && git push')
        self.assertRefused(f'{COMMIT} && git -c k="`x`" push')

    def test_a_substitution_in_the_path_of_a_wrapper(self):
        self.assertRefused(f'{COMMIT} && python3 "$(dirname $0)/push_once.py"')

    def test_an_unquoted_substitution_as_the_git_directory(self):
        self.assertRefused(f"{COMMIT} && git -C $(pwd) push")
        self.assertRefused("git -C $(git rev-parse --show-toplevel) commit -m x && git push")

    def test_the_evidence_with_the_same_forms_passes(self):
        self.assertPasses(f'{COMMIT} && {GATE} && git -C "$(pwd)" push')
        self.assertPasses(f'git -C "$(pwd)" commit -m x && git -C "$(pwd)" status && git -C "$(pwd)" log -1 && git push')

    def test_a_read_inside_a_substitution_is_captured_not_shown(self):
        self.assertRefused(f'{COMMIT} && python3 "$(git status; git log -1; echo .)/push_once.py"')
        self.assertRefused(f"{COMMIT} && h=$(git log -1 --format=%H) && git status && git push")
        self.assertRefused(f'{COMMIT} && git status && git push origin "$(git rev-parse HEAD)":refs/heads/b')
        self.assertRefused(f'{COMMIT} && test -z "$(git status --porcelain)" && test -n "$(git log -1)" && git push')
        self.assertRefused(f"{COMMIT} && git status && x=`git log -1` && git push")

    def test_a_substitution_an_echo_prints_is_shown(self):
        self.assertPasses(f'{COMMIT} && echo "$(git status)" && printf "%s" "$(git log -1)" && git push')

    def test_a_commit_or_push_inside_a_substitution_still_runs(self):
        self.assertRefused('x=$(git commit -m y) && git push')
        self.assertRefused(f'{COMMIT} && x=$(git push)')

    def test_a_substitution_in_the_commit_message_is_not_the_commit(self):
        self.assertPasses('git status && git log -1 && git commit -m "$(cat msg.txt)"')


class ArmAndBackgroundTests(PushCase):
    """A read that runs only when the commit failed, or beside the push, is not read before it."""

    def test_a_read_in_an_or_arm_does_not_count(self):
        self.assertRefused(f"{COMMIT} || git status; git log -1; git push")
        self.assertRefused(f"{COMMIT}; git status || git log -1; git push")

    def test_an_or_arm_that_is_not_a_read_leaves_the_reads_counting(self):
        self.assertPasses(f"{COMMIT} || exit 1; git status; git log -1; git push")
        self.assertPasses(f"{COMMIT} && git status && git log -1 || echo bad; git push")

    def test_reads_in_a_backgrounded_list_do_not_count(self):
        self.assertRefused(f"{COMMIT} && git status && git log -1 & git push")
        self.assertRefused(f"{COMMIT}; git status & git log -1; git push")

    def test_a_push_sent_to_the_background_after_the_reads_passes(self):
        self.assertPasses(f"{COMMIT}; git status; git log -1; git push &")

    def test_a_commit_in_the_background_is_still_a_commit(self):
        self.assertRefused(f"{COMMIT} & git push")


class ConditionTests(PushCase):
    """A read in the condition of an if always runs, so it counts for a push after fi."""

    def test_a_status_in_an_if_condition(self):
        self.assertPasses(f"{COMMIT}; if git status | grep -q .; then echo dirty; exit 1; fi; git log -1; git push")

    def test_both_reads_in_conditions(self):
        self.assertPasses(f"{COMMIT}; if git status | grep -q .; then exit 1; fi; "
                          "if git log -1 | grep -q .; then echo ok; fi; git push")

    def test_the_push_inside_the_arm_after_a_condition_read(self):
        self.assertPasses(f"{COMMIT}; if git status | grep -q .; then git log -1; git push; fi")

    def test_a_while_condition_read(self):
        self.assertPasses(f"{COMMIT}; while git status | grep -q xyz; do sleep 1; done; git log -1; git push")

    def test_an_elif_condition_runs_only_when_the_first_failed(self):
        self.assertRefused(f"{COMMIT}; if x; then y; elif git status; then z; fi; git log -1; git push")

    def test_a_read_in_the_arm_still_does_not_count_after_fi(self):
        self.assertRefused(f"{COMMIT}; if x; then git status; fi; git log -1; git push")


class SessionScopeTests(PushCase):
    """Events of another repository or another agent are not this push's commit."""

    def event(self, kind, cwd=None, agent=None):
        return {"event": kind, **({"cwd": cwd} if cwd else {}), **({"agent": agent} if agent else {})}

    def test_a_commit_in_another_directory(self):
        self.assertPasses("git push", [self.event("git_commit", "/elsewhere/repo-a")])

    def test_a_commit_in_this_directory(self):
        self.assertRefused("git push", [self.event("git_commit", str(self.project))])

    def test_a_commit_of_another_agent(self):
        self.assertPasses("git push", [self.event("git_commit", str(self.project), "sub-1")])

    def test_a_commit_of_the_same_agent(self):
        self.assertRefused("git push", [self.event("git_commit", str(self.project), "sub-1")], agent_id="sub-1")

    def test_the_main_session_does_not_see_a_subagent_read_or_push(self):
        events = [self.event("git_commit", str(self.project)), self.event("git_status", str(self.project), "sub-1"),
                  self.event("git_log", str(self.project), "sub-1")]
        self.assertRefused("git push", events)

    def test_a_commit_of_git_dash_c_a_is_not_the_push_of_b(self):
        self.assertPasses("git -C /b push", [self.event("git_commit", "/a")])
        self.assertRefused("git -C /a push", [self.event("git_commit", "/a")])
        self.assertPasses("git -C /a commit -m x && git -C /b push")
        self.assertRefused("git -C /a commit -m x && git -C /a push")

    def test_a_cd_into_the_repository_before_the_push(self):
        self.assertRefused("cd /a && git push", [self.event("git_commit", "/a")])
        self.assertPasses("cd /b && git push", [self.event("git_commit", "/a")])
        self.assertRefused("cd /a && git commit -m x && cd /a && git push")
        self.assertPasses("cd /a && git commit -m x && cd /b && git push")

    def test_a_relative_git_dash_c_is_under_the_call_directory(self):
        self.assertRefused("git -C sub push", [self.event("git_commit", str(self.project / "sub"))])
        self.assertPasses("git -C other push", [self.event("git_commit", str(self.project / "sub"))])

    def test_a_status_and_log_of_the_other_repository_do_not_count(self):
        events = [self.event("git_commit", "/a"), self.event("git_status", "/b"), self.event("git_log", "/b")]
        self.assertRefused("git -C /a push", events)
        self.assertPasses("git -C /a push", events + [self.event("git_status", "/a"), self.event("git_log", "/a")])

    def test_a_push_settles_only_its_own_repository(self):
        events = [self.event("git_commit", "/a"), self.event("git_commit", "/b"), self.event("git_push", "/b")]
        self.assertRefused("git -C /a push", events)
        self.assertPasses("git -C /b push", events)

    def test_an_unknown_directory_counts_for_any(self):
        self.assertRefused("cd $X && git push", [self.event("git_commit", "/a")])
        self.assertRefused("git -C $D push", [self.event("git_commit", "/a")])

    def test_a_subdirectory_or_parent_of_the_repository_is_the_same_repository(self):
        self.assertRefused("git commit -m x && cd src && git push origin")
        self.assertRefused("git commit -m x && git -C src push origin")
        self.assertRefused("cd src && git commit -m x && cd .. && git push origin")
        self.assertRefused("cd src && git push origin", [self.event("git_commit", str(self.project))])
        self.assertRefused("git -C src push origin", [self.event("git_commit", str(self.project))])
        self.assertRefused("cd .. && git -C project push origin", [self.event("git_commit", str(self.project / "src"))])
        self.assertRefused("git push origin", [self.event("git_commit", str(self.project / "src"))])

    def test_a_sibling_whose_name_starts_the_same_is_another_repository(self):
        self.assertPasses("git -C /ab push", [self.event("git_commit", "/a")])
        self.assertPasses("git -C /a push", [self.event("git_commit", "/ab/src")])
        self.assertPasses("git -C /a commit -m x && git -C /ab push")

    def test_reads_in_a_subdirectory_count_for_the_repository(self):
        self.assertPasses("cd src && git status && git log -1 && git push origin",
                          [self.event("git_commit", str(self.project))])

    def test_sibling_subdirectories_of_one_repository_are_that_repository(self):
        top = self.project / "repo"
        for sub in (".git", "src", "docs"):
            (top / sub).mkdir(parents=True)
        self.assertRefused(f"cd {top}/docs && git push", [self.event("git_commit", str(top / "src"))])
        self.assertRefused("cd repo/src && git commit -m x && cd ../docs && git push")
        self.assertPasses(f"cd {top} && git status && git log -1 && git push",
                          [self.event("git_commit", str(top / "src"))])
        self.assertPasses("cd repo/src && git commit -m x && cd ../docs && git status && git log -1 && git push")

    def test_a_worktree_or_submodule_git_file_marks_its_own_repository(self):
        (self.project / "outer" / ".git").mkdir(parents=True)
        (self.project / "outer" / "mod").mkdir()
        (self.project / "outer" / "mod" / ".git").write_text("gitdir: ../.git/modules/mod\n", encoding="utf-8")
        self.assertEqual(guard_commit_push.repository_top(str(self.project / "outer" / "mod" / "x")),
                         str(self.project / "outer" / "mod"))
        self.assertEqual(guard_commit_push.repository_top(str(self.project / "outer" / "src")),
                         str(self.project / "outer"))
        self.assertEqual(guard_commit_push.repository_top("/no-such-dir-xyz/a"), "/no-such-dir-xyz/a")
        self.assertIsNone(guard_commit_push.repository_top(None))

    def test_reads_in_a_directory_above_the_commit_do_not_count(self):
        events = [self.event("git_commit", "/work/a"), self.event("git_status", "/work"), self.event("git_log", "/work")]
        self.assertRefused("git -C /work/a push", events)
        self.assertRefused("cd /work/a && git commit -m x && cd .. && git status && git log -1 && cd a && git push")
        self.assertPasses("git -C /work/a push", events + [self.event("git_status", "/work/a/src"),
                                                            self.event("git_log", "/work/a")])

    def test_events_without_a_directory_still_count(self):
        self.assertRefused("git push", [{"event": "git_commit"}])


class ScriptFedToAShellTests(PushCase):
    """A here-document a shell runs is commands; one that is only written or read as data is not."""

    def test_bash_reads_the_body(self):
        self.assertRefused(f"bash <<'E'\n{COMMIT}\ngit push\nE")

    def test_bash_dash_s(self):
        self.assertRefused(f"bash -s <<E\n{COMMIT} && git push\nE")

    def test_a_pipe_into_bash(self):
        self.assertRefused(f"cat <<'E' | bash\n{COMMIT}\ngit push\nE")

    def test_sh_with_dash_options(self):
        self.assertRefused(f"sh -e <<E\n{COMMIT}\ngit push\nE")

    def test_a_body_with_the_evidence_passes(self):
        self.assertPasses(f"bash -s <<'E'\n{COMMIT}\n{GATE}\ngit push\nE")

    def test_commands_after_the_body_are_still_judged(self):
        self.assertRefused(f"bash <<'E'\necho hi\nE\n{COMMIT}; git push")

    def test_a_script_file_makes_the_body_its_input_data(self):
        self.assertPasses(f"bash run.sh <<'E'\n{COMMIT}\ngit push\nE")

    def test_bash_dash_c_makes_the_body_its_input_data(self):
        self.assertPasses(f"bash -c 'cat' <<'E'\n{COMMIT}\ngit push\nE")

    def test_cat_and_tee_write_it_as_data(self):
        self.assertPasses(f"cat <<'E' > ship.sh\n{COMMIT}\ngit push\nE")
        self.assertPasses(f"tee ship.sh <<'E'\n{COMMIT}\ngit push\nE")

    def test_a_body_with_an_apostrophe_still_parses(self):
        self.assertRefused(f"bash <<'E'\necho \"it's\"\n{COMMIT}\ngit push\nE")


class RemoteCommandTests(PushCase):
    def test_ssh_remote_commit_and_push(self):
        self.assertRefused(f"ssh host 'cd r && {COMMIT} && git push'")

    def test_ssh_remote_with_the_evidence(self):
        self.assertPasses(f"ssh host 'cd r && {COMMIT} && {GATE} && git push'")

    def test_ssh_remote_of_a_wrapper(self):
        self.assertRefused(f"ssh host '{COMMIT} && python3 push_once.py x'")

    def test_the_remote_commit_and_a_local_push_are_one_chain(self):
        self.assertRefused(f"ssh host '{COMMIT}' && git push")

    def test_observe_sees_the_remote_commands(self):
        self.assertEqual(guard_commit_push.observe("ssh host 'git status && git log -1'", []),
                         ["git_status", "git_log"])


class CheapPathTests(PushCase):
    """Calls that cannot matter are not parsed."""

    def test_a_pushed_commit_does_not_parse_the_next_call(self):
        parse = mock.Mock(side_effect=AssertionError("parsed"))
        events = [{"event": "git_commit"}, {"event": "git_push"}]
        self.assertIsNone(guard_commit_push.problem("ls -la", ENTRY, parse, events))
        parse.assert_not_called()

    def test_an_unpushed_commit_still_parses(self):
        parse = mock.Mock(return_value=[])
        guard_commit_push.problem("ls -la", ENTRY, parse, [{"event": "git_commit"}])
        parse.assert_called()

    def test_a_call_with_no_git_in_it_is_not_parsed_by_the_tracker(self):
        parse = mock.Mock(side_effect=AssertionError("parsed"))
        self.assertEqual(guard_commit_push.observe("ls -la", ["push_once.py"], parse), [])
        parse.assert_not_called()

    def test_a_wrapper_name_still_reaches_the_parser(self):
        self.assertEqual(guard_commit_push.observe("python3 s/push_once.py x", ["push_once.py"]), ["git_push"])


class RegistryTests(PushCase):
    def test_entry_is_valid_without_programs(self):
        self.registry({"rule": "commit-then-push", "lesson": "G028", "min_version": "1.39.0"})
        self.assertRefused(f"{COMMIT} && git push")

    def test_other_keys_are_refused(self):
        with self.assertRaises(guard_lessons.RegistryError):
            guard_lessons.validate({"rule": "commit-then-push", "paths": ["x"]}, "t")

    def test_programs_must_be_a_list_of_names(self):
        with self.assertRaises(guard_lessons.RegistryError):
            guard_lessons.validate({"rule": "commit-then-push", "programs": "push_once.py"}, "t")

    def test_the_rule_is_documented(self):
        self.assertIn("commit-then-push", guard_lessons.__doc__)


class PushOnceSubcommandTests(PushCase):
    """push_once.py hook and check only judge a push (the pre-push hook, a manual check): neither pushes."""
    SCRIPT = ".agents/skills/quality-gate/scripts/push_once.py"

    def test_the_pre_push_hook_handler_is_no_push(self):
        self.assertPasses(f"cd /tmp/c && {COMMIT} && printf 'x' | python3 {self.SCRIPT} hook origin /tmp/o.git")
        self.assertPasses(f"{COMMIT}; python3 {self.SCRIPT} hook origin git@github.com:o/r.git < lines.txt")

    def test_the_manual_check_is_no_push(self):
        self.assertPasses(f"{COMMIT} && python3 {self.SCRIPT} check --remote origin --branch feat")
        self.assertPasses(f"{COMMIT} && ./push_once.py check")

    def test_a_git_push_after_the_check_is_still_refused(self):
        self.assertRefused(f"{COMMIT} && python3 {self.SCRIPT} check && git push origin feat")

    def test_any_other_run_of_it_still_counts_as_a_push(self):
        self.assertRefused(f"{COMMIT} && python3 {self.SCRIPT} feat")
        self.assertRefused(f"{COMMIT} && python3 {self.SCRIPT} --base main hook")  # an option first: not the subcommand
        self.assertRefused(f"{COMMIT} && python3 {self.SCRIPT}")

    def test_the_tracker_records_no_push_for_them(self):
        for sub in ("hook origin /tmp/o.git", "check --remote origin"):
            self.assertEqual(guard_commit_push.observe(f"python3 {self.SCRIPT} {sub}", ["push_once.py"]), [])


class LocalRemoteTests(PushCase):
    """A push to a repository on this machine (a scratch bare repository) reaches no shared remote."""

    def test_a_push_to_a_local_path_or_file_url_passes(self):
        for remote in ("/tmp/fix/o.git", "./o.git", "../o.git", "sub/o.git", "~/r.git", ".", "..",
                       "file:///tmp/o.git", '"/tmp/with space/o.git"'):
            self.assertPasses(f"{COMMIT} && git push -q {remote} mine:refs/heads/development")

    def test_a_variable_set_to_a_local_path_earlier_in_the_call_passes(self):
        self.assertPasses("O=/tmp/fix/o.git; C=/tmp/fix/c; git init -q --bare -b development $O && cd $C && "
                          f"{COMMIT} && git push -q $O mine:refs/heads/development")
        self.assertPasses(f'T=/tmp/fix; O="$T/o.git"; {COMMIT} && git push "${{O}}" mine')

    def test_network_remotes_and_unknown_variables_still_count(self):
        for remote in ("origin", "git@github.com:o/r.git", "https://github.com/o/r.git", "ssh://host/r.git",
                       "host:r.git", "$UNSET_REMOTE", "$UNSET/o.git", "--repo=origin", ""):
            self.assertRefused(f"{COMMIT} && git push {remote} feat".replace("  ", " "))

    def test_a_variable_from_a_substitution_is_not_known(self):
        self.assertRefused(f"O=$(mktemp -d)/o.git; {COMMIT} && git push $O feat")

    def test_a_variable_set_after_the_push_does_not_count(self):
        self.assertRefused(f"{COMMIT} && git push $O feat; O=/tmp/o.git")

    def test_the_tracker_records_no_push_to_a_local_remote(self):
        self.assertEqual(guard_commit_push.observe("git push /tmp/o.git x && git push origin x", []), ["git_push"])

    def test_a_positional_repository_overrides_repo(self):
        # git sends to the operand, not --repo: `git push --repo /tmp/b.git origin x` reaches origin.
        for options in ("--repo /tmp/b.git origin", "--repo=/tmp/b.git origin", "origin --repo /tmp/b.git"):
            self.assertRefused(f"{COMMIT} && git push {options} HEAD:refs/heads/t")
            self.assertEqual(guard_commit_push.observe(f"git push {options} x", []), ["git_push"], options)

    def test_repo_is_the_fallback_without_an_operand(self):
        self.assertPasses(f"{COMMIT} && git push -q --repo /tmp/b.git")
        self.assertPasses(f"{COMMIT} && git push -q --repo=/tmp/o.git")
        # with a refspec only, git takes it as the repository (`mine:x` is an scp-style host)
        self.assertRefused(f"{COMMIT} && git push -q --repo=/tmp/o.git mine:refs/heads/development")
        self.assertPasses(f"{COMMIT} && git push --repo origin /tmp/b.git x")


class ObserveTests(unittest.TestCase):
    """The events the tracker records after a successful Bash call."""

    def test_events_in_order(self):
        self.assertEqual(guard_commit_push.observe(f"{COMMIT} && git status && git log -1 && git push", ["x.py"]),
                         ["git_commit", "git_status", "git_log", "git_push"])

    def test_rev_parse_head_is_the_log(self):
        self.assertEqual(guard_commit_push.observe("git rev-parse HEAD", []), ["git_log"])

    def test_wrapper_push_by_registry_name(self):
        self.assertEqual(guard_commit_push.observe("python3 scripts/push_once.py feat", ["push_once.py"]),
                         ["git_push"])
        self.assertEqual(guard_commit_push.observe("python3 scripts/push_once.py feat", []), [])

    def test_dry_runs_and_discarded_output_record_nothing(self):
        self.assertEqual(guard_commit_push.observe("git commit --dry-run -m x; git push -n; git status >/dev/null",
                                                   []), [])

    def test_other_commands_and_bad_input_record_nothing(self):
        self.assertEqual(guard_commit_push.observe("ls -la", []), [])
        self.assertEqual(guard_commit_push.observe(None, []), [])
        self.assertEqual(guard_commit_push.observe("git push", [3]), ["git_push"])


class TrackTests(test_guard.GuardCase):
    """guard.py track writes the events the rule reads in a later call."""

    def setUp(self):
        super().setUp()
        self.write(".agents/lesson-guards.json", json.dumps({"guards": [
            {"rule": "commit-then-push", "lesson": "G028", "programs": ["push_once.py"]}]}))

    def events(self):
        lines = self.state.read_text().splitlines() if self.state.exists() else []
        return [json.loads(line)["event"] for line in lines if json.loads(line)["event"].startswith("git_")]

    def test_a_successful_commit_status_log_and_push_are_recorded(self):
        self.bash(f"{COMMIT} && git status && git log -1")
        self.bash("git push origin feat")
        self.assertEqual(self.events(), ["git_commit", "git_status", "git_log", "git_push"])

    def test_events_carry_the_directory_and_the_agent(self):
        self.bash(COMMIT, agent_id="sub-1")
        self.bash("git status")
        lines = [json.loads(line) for line in self.state.read_text().splitlines()]
        commit, status = [line for line in lines if line["event"] in ("git_commit", "git_status")]
        self.assertEqual((commit["agent"], os.path.realpath(commit["cwd"])), ("sub-1", os.path.realpath(self.dir)))
        self.assertNotIn("agent", status)
        self.assertIn("cwd", status)

    def test_a_wrapper_push_is_recorded_by_the_entry_programs(self):
        self.bash("python3 scripts/push_once.py feat")
        self.assertEqual(self.events(), ["git_push"])

    def test_nothing_is_recorded_while_the_rule_is_off(self):
        self.write(".agents/lesson-guards.json", json.dumps({"guards": []}))
        self.bash(f"{COMMIT} && git push")
        self.assertEqual(self.events(), [])

    def test_a_failed_call_records_what_it_ran(self):
        self.bash(f"{COMMIT} && git push", failed=True, error="Exit code 1", is_interrupt=False)
        self.assertEqual(self.events(), ["git_commit", "git_push"])

    def test_reads_of_a_call_that_exits_non_zero_are_recorded(self):
        self.bash(COMMIT)
        self.bash("git log -1 --oneline; git status --porcelain | grep .", failed=True, error="Exit code 1")
        self.assertEqual(self.events(), ["git_commit", "git_log", "git_status"])

    def test_the_commit_of_a_call_that_fails_after_it_is_recorded(self):
        self.bash(f"{COMMIT} && npm test", failed=True, error="Exit code 1")
        self.assertEqual(self.events(), ["git_commit"])

    def test_an_interrupted_call_records_nothing(self):
        self.bash(f"{COMMIT} && git push", failed=True, error="interrupted", is_interrupt=True)
        self.assertEqual(self.events(), [])

    def test_the_directory_of_a_git_dash_c_commit_is_recorded(self):
        self.bash("git -C /a/repo commit -m x")
        self.bash("cd /b/repo && git commit -m y")
        lines = [json.loads(line) for line in self.state.read_text().splitlines()]
        self.assertEqual([line["cwd"] for line in lines if line["event"] == "git_commit"], ["/a/repo", "/b/repo"])

    def test_other_commands_record_nothing(self):
        self.bash("ls -la")
        self.assertEqual(self.events(), [])


class DirectTests(unittest.TestCase):
    def test_never_raises_and_passes_on_bad_input(self):
        self.assertIsNone(guard_commit_push.problem(None, {}))
        self.assertIsNone(guard_commit_push.problem("", {}))
        self.assertIn("git status", guard_commit_push.problem("git commit -m x && git push", {"programs": [3]}))

    def test_a_fault_in_the_parser_passes_the_command(self):
        with mock.patch.object(guard_lessons, "commands", side_effect=RuntimeError("boom")):
            self.assertIsNone(guard_commit_push.problem("git commit -m x && git push", {}))

    def test_refusal_text(self):
        self.assertIn("git status", guard_commit_push.problem("git commit -m x && git push", {}))


if __name__ == "__main__":
    unittest.main()
