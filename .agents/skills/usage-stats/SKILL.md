---
name: usage-stats
description: 'Local numbers on how the arsenal helped in your sessions. Use when asked for usage stats or an arsenal report.'
---
<!-- routing (read by the skill router, not loaded into the skill listing): Local numbers on how the arsenal helped in your own sessions. Triggers: "usage stats", "how useful is the arsenal", "arsenal report", "marketing numbers", /usage-stats. Not for run token spend (use autonomous-run). -->

# Usage Stats Procedure

This skill turns the user's own Claude Code sessions into honest numbers about what the arsenal caught and did: blocks that led to a test, failed checks that went green, destructive commands and repeat mistakes stopped, skills used, lessons recorded and later enforced. Everything stays on this machine.

---

## 1. When to Use This Skill

Activate this skill when:
- The user asks how useful the arsenal is, what it caught, or which skills are used.
- The user wants numbers for a README, a post or a talk about the arsenal.
- The usage block in the README is stale.
- The user runs the `/usage-stats` slash command.

*Boundary*: For the token spend of one unattended run, use `autonomous-run` (`usage_report.py`). For a controlled with-and-without comparison, use the eval suite in `evals/` (`docs/EVALS.md`). For what went wrong and why, use `lessons-learned`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Make Sure There Is Data
1. Resolve the script path relative to the directory that contains this file: `<skill-dir>/scripts/usage_stats.py`.
2. With the Claude Code plugin, a `SessionEnd` hook (`usage_stats.py record`) adds each finished session to `~/.agents/arsenal-usage.jsonl` (`$ARSENAL_USAGE_FILE`). `ARSENAL_USAGE=off` stops that hook; it does not stop an explicit backfill. The hook only starts a detached `usage_stats.py record --transcript <path>` and returns, so a short SessionEnd deadline never cuts it off; the same command records one transcript by hand.
3. First run, or sessions from before the hook: `python3 <skill-dir>/scripts/usage_stats.py backfill` reads every transcript under `~/.claude/projects` (`--dir` for another folder). It can run any number of times: a session is replaced, never added twice.

### Step 2: Produce the Report
1. `python3 <skill-dir>/scripts/usage_stats.py report --markdown` (add `--days 30` for a window, `--json` for raw numbers).
2. For the README: `report --readme README.md` rewrites only the block between `<!-- BEGIN usage -->` and `<!-- END usage -->`.

### Step 3: Present It Honestly
1. Quote each number with its definition and its base, as the report prints it ("12 of 15 missing-test blocks were followed by a test edit").
2. Say these are counts from the user's own sessions, not proof of cause: there is no comparison group. For a causal claim, point to the evals.
3. Never invent, round up or extrapolate a number; a 0 of 0 is reported as such.

### Step 4: Diagnose One Session
1. `python3 <skill-dir>/scripts/usage_stats.py diagnose --last` (or `--session <id>`, or a transcript path; `--json` for machines) reads one session and its subagents.
2. It reports four kinds of finding:
   - `missed-skill`: a prompt held a skill's multi-word trigger phrase and that skill never fired. Pasted blocks are ignored, and so are prompts that name three or more skills, compaction summaries, task notifications and prompts over 4,000 characters (a scheduled routine's brief is not a request: on real sessions these were 38 of 49 matches).
   - `untested-change`: source was edited and no test was.
   - `unverified-done`: "done" was claimed after the last edit with no passing check after it.
   - `unlearned-fail`: a check failed, never passed again, and no lesson followed.
   Each finding has the turn's timestamp and a one-line fix. Prompts, commands and paths are never printed.
3. A `missed-skill` finding is a hypothesis. A repeat across sessions means the skill's trigger phrases or its description need work, or the phrase is too common to be a trigger. Fix the description and re-run the trigger eval; never ignore it.
4. Subagent transcripts (`<session>/subagents/`) count toward their session's skills and subagents in `record`, `backfill` and `diagnose`. Their tokens are not added, so nothing is counted twice.

### Step 5: Daily CI Cost of a Repository
1. `python3 <skill-dir>/scripts/usage_stats.py ci --repo OWNER/NAME` (`--days 7` for a week, 400 at most; `--json` for machines; `--max-runs 50` caps the attempts read) prints one line per day, a day without runs included: `<date> runs <n>, red <n>, wasted <m> min (timeout <m>, coverage <m>, test <m>, lint/type <m>, superseded <m>, outside <m>, unknown <m>); repeats without a guard <n>`.
2. It lists the runs with `gh run list --created >=<first day>` (at most 200). When the list reaches that limit, the oldest day it reached and every day before it end with `partial: gh listed its 200-run limit, older runs not counted`.
3. `red` counts red attempts (failure, timed_out, cancelled, startup_failure) on the day the run was created. gh lists only a run's latest attempt, so every earlier attempt of a re-run run is read too: a flaky failure fixed by "Re-run failed jobs" still counts. Each attempt (`gh run view <id> --attempt <k>`) is classified and timed as `ci-wait`'s `ci_learn.py <id> --dry-run` does; no ledger is written. An attempt whose view shows it did not fail is not red. One whose failed log gh will not serve (`--log-failed` exits non-zero, as for a job that never started, such as a billing lock) is classified from its jobs, with a note on stderr. `--max-runs` caps attempts, not runs: the earlier attempts of a re-run run use it even when they passed. Attempts past it, oldest first, are not in the minutes (a skipped latest attempt still counts as red), and the line then says `skipped <k> attempt(s) over --max-runs <N> (not in the minutes)` ("attempt" for 1), before any partial note. A listed run without a readable `createdAt` is not counted, with a note on stderr.
4. "Repeats without a guard" is the lessons with 2 or more hits and no guard or holding exemption (a lesson promoted only to the `lessons-promoted.md` rule stub counts: a rule is not a guard), in the project ledger (`$LESSONS_FILE` or `.agents/lessons.md`) and the global one (`$LESSONS_GLOBAL_FILE` or `~/.agents/lessons.md`), read now: the same number on every line. Give each a guard (`lessons.py promote ID --guard PATH`) or an exemption.
5. Exit 2 on a bad argument, a gh failure on the list or a run's `--json` view (the run id is named), any gh call that hangs past 120 s (a failed log included) or a ledger that is not a readable file; nothing is printed on stdout then, so a partial day never passes for a whole one.

---

## 3. What Is Stored, and What Never Is

| Stored per session | Never stored |
| :--- | :--- |
| session id, first and last day, Claude Code and arsenal versions | prompts, replies, commands, outputs |
| project as a salted hash of the folder (salt: `<store>.salt`, random per machine) | folder names, file paths, repository names |
| arsenal skill and subagent names with call counts | code, diffs, file contents |
| counts: Stop-gate blocks and what followed, denials, failed and passing checks, source and test edits, tokens | the reason text of a block or denial |
| lesson ids recorded, repeated or enforced | lesson text |

Only sessions where the arsenal was active are kept. Nothing is sent anywhere.

---

## 4. Verification Protocol

```bash
python3 <skill-dir>/scripts/usage_stats.py backfill; echo "exit $?"            # 0, prints transcripts read and sessions kept
python3 <skill-dir>/scripts/usage_stats.py report --markdown; echo "exit $?"   # 0, every number with its base
python3 <skill-dir>/scripts/usage_stats.py report --readme README.md; echo "exit $?"  # 2 when the README has no usage block
python3 <skill-dir>/scripts/usage_stats.py ci --repo OWNER/NAME; echo "exit $?"  # 0, one line per day; 2 on a gh failure
```

---

## 5. ⚡ Token-Saving Execution Rule

- **One Command**: Run the report and quote it; never read the store or transcripts by hand.
- **Headline First**: Lead with the three strongest numbers and their bases, then the table.

**Next**: to back a number with a controlled comparison, run the evals described in `docs/EVALS.md`.
