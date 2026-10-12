---
name: autonomous-run
description: 'Rules for a long unattended agent run (overnight, away period): scoped written authority that expires, a token budget measured by a bundled script, work in plan order, proof that the application starts, merging only on green CI plus a clean review, parked blockers, and an end report. Use when the user asks for unattended work, sets a usage budget, or runs /autonomous-run. Triggers on: "work while I am away", "overnight run", "continue without me", "usage budget", "/autonomous-run". Do not use for waiting on one pipeline (use ci-wait) or updating the task board (use delivery-board-sync).'
---

# Autonomous Run Procedure

This skill guides the agent through a long unattended run: fixing what it is allowed to do, staying inside a time and token budget, advancing the plan without stopping on blockers, and leaving a report the user can verify.

---

## 1. When to Use This Skill

Activate this skill when:
- The user leaves and asks for the work to continue (overnight, a day off, an away period).
- The user grants standing permission to merge, or says not to stop and ask.
- A daily or weekly token, cost, or time budget must be respected across a run.
- A run is ending and the user needs a report of what was merged, parked, and spent.
- The user runs the `/autonomous-run` slash command.

*Boundary*: For waiting on a single pipeline and reading its result, use `ci-wait`. For moving tasks on the board at the start and end of the run, use `delivery-board-sync`. For what the start-up proof should exercise, use `smoke-test`. For the review itself, use `code-review` or `deep-review`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Fix the Authority in Writing
Consult: [Authority, Budget & End Report](./references/authority-budget-and-report.md)
1. Restate the grant in one block and get a yes before the user leaves: what may be merged and where, what is never done, when it expires.
2. Never included unless named in that message: production releases, destructive operations (data deletion, history rewrite, infrastructure removal), spending, changes to secrets or access.
3. The grant ends at its expiry or when the user returns, whichever is first; afterwards ask again. Silence widens nothing: where the grant does not cover an action, park it.

### Step 2: Set the Window and the Budget
1. Record the time window (start, end, time zone) and begin winding down an hour before the end.
2. Record the budget as a share of the allowance (for example one fifth of a weekly quota per working day) and wind down at about 85% of the share.
3. Measure with this skill's `scripts/usage_report.py`, which sums token usage from session transcripts in JSON-lines form. Resolve the script path relative to the directory that contains this file. It needs Python 3.9+ and no packages.
4. Run it before each large piece of work and in the end report; do not estimate usage from memory.

### Step 3: Prove the Application Starts
1. Before changing anything: start every process the application has (server, worker, scheduler), apply migrations, and confirm the health endpoint answers with no errors in the logs. A broken baseline is the first item of the run.
2. Repeat the same proof at the end, on the final merged commit. Green ticks are not proof that it starts.

### Step 4: Work the Plan in Order
1. Read the task board and the plan first; take items in plan order and finish the earlier period before the next.
2. Keep changes small: one item, one branch, one pull request, one review pass.
3. Build what the specification says; where it is silent, record the gap as an open question and never guess.
4. A blocked item is parked with its question, a recommendation, and what it blocks. It never stops the run: take the next item that needs no decision.

### Step 5: Merge Only on Evidence
1. Merge when all hold: the review has no open finding, CI is green on the exact commit that was reviewed, and the application still starts.
2. Pin the merge to the reviewed commit hash so a later push cannot ride along.
3. If any condition fails, do not merge and do not bypass a check. Fix, re-review the fix, re-run.
4. Append every merge to a running list as it happens: item, pull request, commit, time.

### Step 6: Wind Down and Report
1. At the threshold or the end of the window: start nothing new, finish and merge what is in flight, or leave it as a labelled open pull request.
2. Run the start-up proof, update the task board, then write the end report: done with evidence, parked with questions, usage against the budget.

---

## 3. Verification Protocol

```bash
python scripts/usage_report.py --dir <transcripts-dir> --since-hour 14 --tz Europe/London   # usage since the window opened
python scripts/usage_report.py --dir <transcripts-dir> --since 2025-03-04T18:00:00+00:00 --top 3 --json
curl -fsS http://127.0.0.1:<port>/healthz                    # the started application answers
gh pr checks <number> --required                             # every required check passed
gh pr merge <number> --rebase --match-head-commit <reviewed-sha>   # refuses if the branch moved after review
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Authority | Release to production under a grant that named only the development branch | Unapproved change reaches users | `[Blocker]` | Roll back, report first, never infer scope |
| Merge | Merged on green CI of an earlier commit | Unreviewed code on the default branch | `[Security]` | Revert or review the delta; pin merges to the reviewed hash |
| Budget | Run stopped mid-review when the quota ran out | Half-done work, no report | `[Blocker]` | Measure before each large task; wind down at 85% |
| Start-up | All checks green, the worker crashes on boot | The user returns to a dead application | `[Blocker]` | Start every process at the start and the end |

---

## 4. ⚡ Token-Saving Execution Rule

- **Narrow Reads**: Grep and line ranges only; cap the output of every command; never re-read a file already in context.
- **One Review Pass**: One reviewer per pull request and one re-check of its fixes; never re-run a review that already passed on the same commit.
- **Few, Larger Helpers**: Prefer one subagent with a wide brief over many small ones, and measure usage before launching it.
