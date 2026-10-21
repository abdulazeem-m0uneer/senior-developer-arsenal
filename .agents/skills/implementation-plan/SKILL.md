---
name: implementation-plan
description: 'Implementation plan runbook: turns an approved brief into bite-sized tasks for an engineer who has never seen the codebase, each task naming exact files, signatures, test assertions, and verification commands, with a file map, interfaces between tasks, a review-focus list, a self-review for coverage and type drift, then execution either inline or by one fresh implementer and one fresh reviewer per task with a ledger that survives context loss. Use when a brief or spec is approved and work spans more than one sitting or one file, or when the user runs /implementation-plan. Triggers on: "write the plan", "break this down", "implementation plan", "execute the plan", "/implementation-plan". Do not use for requirements discovery (use requirements-grilling), board status (use delivery-board-sync), or an unattended run''s authority and budget (use autonomous-run).'
---

# Implementation Plan Procedure

This skill guides the agent through writing a plan that records every decision the implementer cannot make alone, and then executing it task by task with a review gate and a recoverable record.

---

## 1. When to Use This Skill

Activate this skill when:
- A design brief or spec is approved and the work has more than one task.
- The user asks to break work down, write the plan, or execute an existing plan.
- A plan exists and execution must resume after a context reset or a handoff.
- The user runs the `/implementation-plan` slash command.

*Boundary*: Unanswered requirements go back to `requirements-grilling`. Mirroring tasks onto a tracker is `delivery-board-sync`. Written authority, budget, and the end report for an unattended run are `autonomous-run`; this skill supplies the per-task loop it works through. Branch integration is `git-workflow-master`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Scope and File Map
1. One plan per subsystem that can ship on its own; a brief covering several gets several plans, agreed in order.
2. Before any task: list every file to create or modify and its one responsibility. Files that change together live together; split by responsibility, not by layer. Follow the codebase's existing structure; include a split only for a file the plan must touch that is already unwieldy.

### Step 2: Write the Tasks
Consult: [Plan Format & Self-Review](./references/plan-format.md)
1. A task is the smallest unit that carries its own test cycle and is worth a fresh reviewer's gate. Fold setup, config, scaffolding, and docs into the task whose deliverable needs them; split only where a reviewer could reject one task and approve its neighbour.
2. Each task names: files (create / modify with line ranges / test), interfaces consumed and produced (exact signatures), then steps. A step is one action with one checkable result: write failing test, run it and see it fail, implement the signature, run it and see it pass, commit.
3. A plan is the set of decisions the implementer cannot make alone. Test steps carry the assertions as code with the spec's exact values; code steps carry the signature and file, not the body (a body only for an algorithm the tests do not determine). Lines that decide nothing (`handle edge cases`, `add validation`, `TBD`) are gaps.

### Step 3: Self-Review Before Handover
1. Spec coverage: every requirement points to a task. Step scan: every step lets the implementer write exactly one reasonable thing. Type consistency: names and signatures in later tasks match earlier ones. Review focus: the five untested input classes most likely to bite a user, each pinned to a test in the owning task. Proportion: a plan longer than the code it describes has written the code.
2. Fix inline; no second review pass.
3. Hand over: link the plan, ask the user to confirm it captures the brief and to pick execution: **inline** (you implement every task, one fresh whole-branch reviewer at the end; cheapest) or **subagent-driven** (fresh implementer plus fresh reviewer per task, whole-branch review at the end; most thorough). Recommend one with one sentence on task coupling, count, and the cost of a shipped mistake.

### Step 4: Execute With a Ledger
Consult: [Execution Loop](./references/execution-loop.md)
1. Work in an isolated worktree, never on the default branch without consent. Create the plan's ledger file first; after any context loss, trust the ledger and `git log` over memory and resume at the first task without a `complete` line.
2. Pre-flight: one table row per pair of tasks sharing a file or interface (produces vs consumes) and one per task (its tests against its code). Rule on each conflict with the spec as the authority; ledger every ruling as `Ruling: <decision> / <why> / <cost if wrong>`.
3. Run the loop in the reference: brief by file, implementer, review package, task reviewer, bounded fix rounds, completion line. Never fix findings in the controller session.
4. Do not stop between tasks to ask whether to continue. Stop only for: an irreversible or destructive operation, a security-sensitive action, a side effect outside the worktree (merge, push to shared branch, publish), or a plan so broken every path is a guess.

### Step 5: Final Review and Finish
1. Whole-branch review from the merge base on the most capable model, pointed at the ledger's deferred and parked lines. Findings get one fix dispatch with the complete list, one scoped re-review, then adjudication; no second fix wave.
2. Report every `Ruling:` line from the ledger in order with its cost if wrong; a ruling that dies with the workspace was a decision made in secret. Delete the plan's workspace; git is the record. Continue with `git-workflow-master` branch finishing.

---

## 3. Verification Protocol

```bash
grep -c '^### Task' docs/plans/<plan>.md                  # task count equals todo count
grep -nE 'TBD|handle edge cases|appropriate validation|write tests for the above' docs/plans/<plan>.md   # must be empty
grep -n '^Task [0-9]*: complete' .plan-workspace/progress.md   # resume point after any context loss
grep -n 'Ruling:' .plan-workspace/progress.md               # every one goes in the final report
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Plan | Task 7 calls `clearFullLayers()`; Task 3 defined `clearLayers()` | Implementer invents a second function | `[Blocker]` | Align names in the self-review |
| Plan | Code block of 80 lines where the test and signature determine the body | Plan is a transcript; implementer transcribes bugs | `[Architecture]` | Replace with signature and test |
| Loop | Controller re-dispatched Tasks 1-3 after compaction | Hours of duplicate work, conflicting commits | `[Blocker]` | Ledger first; resume from its `complete` lines |
| Loop | Dispatch prompt carries 40k chars of prior-task history | Subagent drowns; cost explodes | `[Performance]` | Brief file, interfaces, constraints only |

---

## 4. ⚡ Token-Saving Execution Rule

- **Brief by File**: Extract a task's text to a file and pass the path; never paste the whole plan into a dispatch.
- **Reports by File**: Implementers and reviewers write full reports to files and return under 15 lines.
- **One Line Between Calls**: Narrate at most one line; the ledger and tool results carry the record.

Adapted from obra/superpowers (MIT).
