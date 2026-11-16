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
2. With the Claude Code plugin, a `SessionEnd` hook (`usage_stats.py record`) adds each finished session to `~/.agents/arsenal-usage.jsonl` (`$ARSENAL_USAGE_FILE`). `ARSENAL_USAGE=off` stops that hook; it does not stop an explicit backfill.
3. First run, or sessions from before the hook: `python3 <skill-dir>/scripts/usage_stats.py backfill` reads every transcript under `~/.claude/projects` (`--dir` for another folder). It can run any number of times: a session is replaced, never added twice.

### Step 2: Produce the Report
1. `python3 <skill-dir>/scripts/usage_stats.py report --markdown` (add `--days 30` for a window, `--json` for raw numbers).
2. For the README: `report --readme README.md` rewrites only the block between `<!-- BEGIN usage -->` and `<!-- END usage -->`.

### Step 3: Present It Honestly
1. Quote each number with its definition and its base, as the report prints it ("12 of 15 missing-test blocks were followed by a test edit").
2. Say these are counts from the user's own sessions, not proof of cause: there is no comparison group. For a causal claim, point to the evals.
3. Never invent, round up or extrapolate a number; a 0 of 0 is reported as such.

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
