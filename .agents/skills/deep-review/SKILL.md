---
name: deep-review
description: 'Exhaustive, high-accuracy multi-pass review of a change or repository area: independent passes (correctness, security, data integrity, concurrency, performance, tests, API contracts, config, docs), each finding verified against the code (file:line), false-positive elimination, severity ranking, and re-review until clean. Use when the user asks for a thorough or complete review or a pre-release audit. Triggers on: "deep review", "review everything", "thorough review", "/deep-review". Do not use for a single-pass diff review (use code-review) or a security-only audit (use security-audit).'
---

# Deep Multi-Pass Review Procedure

This skill guides the agent through an exhaustive review in which accuracy outranks speed: several independent passes over the same code, each finding proven against the source before it is reported, and a loop that ends only when a full pass finds nothing new.

---

## 1. When to Use This Skill

Activate this skill when:
- The user asks to review "everything", a whole branch, a large pull request, or an entire module or service.
- A change is high-risk: money, authorization, data migration, concurrency, or a public API.
- A previous quick review missed defects, or a release needs an audit with no false positives.
- The user runs the `/deep-review` slash command.

*Boundary*: For a routine single-pass review of a small diff, use `code-review`. For a source-to-sink vulnerability audit with CVSS scoring, use `security-audit`. For confirming that finished work meets its completion gate, use `definition-of-done`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Define Scope and Build the Inventory
1. Fix the scope: a diff range (`git diff <base>...HEAD --stat`) or a directory. List every file in scope; nothing is reviewed by sampling.
2. Map the structure before reading bodies: entry points, callers and callees of changed symbols, data stores touched, external calls. Prefer a symbol or call-graph index when one is available; otherwise use your search tool.
3. Read the intent: ticket, description, commit messages, existing tests. Record what the code is supposed to do.
4. Establish the baseline from your shell: build, lint, type-check, and test results before any judgement.

### Step 2: Run the Independent Passes
Run each pass in [Review Passes](./references/review-passes.md) separately, over the whole scope, looking for one class of problem at a time: correctness, security, data integrity, concurrency, performance, tests, API contracts, config and infrastructure, docs. Log each suspicion as a candidate with `file:line`; do not judge severity yet. When independent reviewers are available, give each pass to a different one with the code only, never with conclusions from another pass.

### Step 3: Verify Every Candidate
Apply [Finding Verification & Reporting](./references/finding-verification.md) to each candidate:
1. Open the cited lines with your file-read tool and re-read the surrounding function and its callers.
2. Prove it: a failing test, a concrete input that triggers the fault, or a step-by-step trace through the real code path.
3. Classify as `Confirmed`, `Refuted`, or `Unproven`. Only `Confirmed` findings are reported as defects; `Unproven` items go to a separate list of questions.

### Step 4: Eliminate False Positives
Re-examine every confirmed finding as its opponent: is it guarded upstream, unreachable, intended, covered by a framework default, or already tested? Drop duplicates, merge findings with one root cause, and remove style opinions that no project rule supports.

### Step 5: Rank and Report
Assign severity (`[Blocker]`, `[High]`, `[Medium]`, `[Low]`) by impact and likelihood, order the findings, and attach a surgical fix or a precise fix direction to each.

### Step 6: Re-Review Until Clean
After fixes land, verify each fix against its original proof, then re-run every pass over the changed lines and their callers. A fix is new code and gets the same scrutiny. Stop only when a complete pass yields zero new confirmed findings and the baseline commands are green.

---

## 3. Verification Protocol

1. Coverage: every file in the inventory was read in at least one pass, and every pass ran or is marked not applicable with a reason.
2. Accuracy: every reported finding cites `file:line` that exists at the reviewed commit and carries its proof; no finding rests on a guess about code that was not opened.
3. Baseline: build, lint, type-check, and the full test suite were run and their results are stated.
4. Output the findings table, ordered by severity:

| # | Severity | Pass | Location | Finding | Proof | Fix |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | [Blocker] | Data integrity | `src/orders/refund.ts:88` | Refund and stock update are not in one transaction | Killing the process after line 88 leaves the refund without restock; reproduced with `refund.crash.spec.ts` | Wrap lines 80-97 in a single transaction |
| 2 | [High] | Concurrency | `src/cart/cart.service.ts:41` | Read-modify-write without a version check | Two parallel requests both pass the check at line 39 | Add optimistic concurrency on `version` |

Close with: passes run, files reviewed, candidates raised / confirmed / refuted / unproven, and the loop iteration number.

---

## 4. ⚡ Token-Saving Execution Rule

- **Findings Table First**: No preamble; start with the verdict line and the table.
- **Evidence, Not Excerpts**: Cite `file:line` and the proof in one sentence; never paste whole functions.
- **Report Confirmed Only**: Refuted candidates are counted, not described.
