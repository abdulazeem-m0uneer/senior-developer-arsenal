---
name: definition-of-done
description: 'Verification gate that builds a per-feature Definition of Done checklist and verifies every item with evidence (command output, file:line), ending in a DONE or NOT DONE verdict table. Use when the user asks whether a feature, fix, or task is finished, ready to merge, or ready to ship, and before reporting any work as complete. Triggers on: "definition of done", "is this done", "verify the feature", "ready to merge", "/definition-of-done". Do not use for hunting defects in a diff (use code-review or deep-review) or for writing the missing tests (use test-every-change).'
---

# Definition of Done Verification Gate

This skill guides the agent through building the Definition of Done for one feature or change and proving each item with evidence. A claim without evidence counts as not done.

---

## 1. When to Use This Skill

Activate this skill when:
- A feature, bug fix, or refactor is about to be reported as complete, merged, or released.
- The user asks "is this done?", "what is left?", or "can we ship this?".
- A task was handed over by another engineer or agent and its completion state must be confirmed, not assumed.
- The user runs the `/definition-of-done` slash command.

*Boundary*: This skill verifies; it does not hunt for defects or author tests. For defect discovery use `code-review` (single pass) or `deep-review` (exhaustive). For authoring the tests a change requires use `test-every-change`. For manual test plans and release sign-off use `qa-engineer`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Fix the Scope
1. State the feature in one sentence and list its acceptance criteria. If none are written, derive them from the ticket or request and confirm them before verifying.
2. Collect the change set from your shell (`git status`, `git diff <base>...HEAD --stat`) so that every changed file is known.
3. Discover the project commands for test, lint, type-check, and build from the manifest or task runner; do not invent them.

### Step 2: Build the Checklist
Instantiate the [Definition of Done Checklist](./references/dod-checklist.md) for this feature. Every item is either applicable or marked `N/A` with a one-line reason. The baseline items:
- **Behaviour**: every acceptance criterion met; error paths and edge cases handled.
- **Tests**: tests for the change exist, fail without it, and the full suite passes.
- **Static gates**: lint, type-check, and build are green with no new warnings.
- **Risk**: security and performance checked for the changed surface.
- **Operability**: logging and metrics on new I/O, a rollback path, migrations reversible or forward-safe.
- **Hygiene**: docs and changelog updated, no `TODO` / dead code / debug output, no file over 1000 lines, SOLID respected.

### Step 3: Verify Each Item With Evidence
Use the commands and evidence rules in [Evidence Commands & Verdict Template](./references/evidence-and-verdict.md).
1. Run the command or open the file for each item now. Earlier runs, summaries, and statements from the author are not evidence.
2. Record the evidence: the command with its exit status and the decisive output line, or `file:line` for code-level items.
3. Mark each item `PASS`, `FAIL`, `N/A` (with reason), or `UNVERIFIED` (could not be checked; say why).

### Step 4: Issue the Verdict
- `DONE` only when every applicable item is `PASS`.
- Any `FAIL` or `UNVERIFIED` item means `NOT DONE`. List the remaining work as concrete actions.
- After fixes, re-verify the failed items and every item the fix could have affected, then reissue the table. Never carry a `PASS` forward across a code change without re-running its command.

---

## 3. Verification Protocol

1. Every row in the verdict table has evidence produced in this session; no row rests on memory or on a reported result.
2. The full test suite, lint, type-check, and build were each run after the final code change, not before it.
3. Output the verdict table:

| # | Item | Status | Evidence |
| :---: | :--- | :---: | :--- |
| 1 | AC-1 Refund within 30 days | PASS | `refund.service.spec.ts:41` passes; manual call returned 200 with `status=Refunded` |
| 4 | Full test suite | PASS | `npm test` exit 0, 412 passed, 0 failed |
| 7 | Error paths handled | FAIL | `refund.service.ts:88` swallows the gateway timeout |
| 12 | Rollback path | UNVERIFIED | Down migration exists but was not executed |

**Verdict: NOT DONE** (1 FAIL, 1 UNVERIFIED). Remaining: handle the timeout at `refund.service.ts:88`; run the down migration against a scratch database.

---

## 4. ⚡ Token-Saving Execution Rule

- **Verdict First**: Start with `DONE` or `NOT DONE`, then the table; no narrative.
- **Decisive Lines Only**: Quote the single output line that proves the item, never the whole log.
- **Failures in Full, Passes in Brief**: Expand only `FAIL` and `UNVERIFIED` rows with the required action.
