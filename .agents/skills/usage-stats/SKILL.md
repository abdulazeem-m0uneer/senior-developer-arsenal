---
name: usage-stats
description: 'Local numbers on how the arsenal helped in your own sessions. Triggers: "usage stats", "how useful is the arsenal", "arsenal report", "marketing numbers", /usage-stats. Not for run token spend (use autonomous-run).'
---

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
```

---

## 5. ⚡ Token-Saving Execution Rule

- **One Command**: Run the report and quote it; never read the store or transcripts by hand.
- **Headline First**: Lead with the three strongest numbers and their bases, then the table.

**Next**: to back a number with a controlled comparison, run the evals described in `docs/EVALS.md`.
