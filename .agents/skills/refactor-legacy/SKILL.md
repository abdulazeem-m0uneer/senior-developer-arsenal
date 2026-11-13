---
name: refactor-legacy
description: 'Change untested code safely in place: pin behaviour with characterization tests, then refactor in tiny green steps. Use to change, clean up or extend code that has no tests. Triggers: "legacy code", "safely refactor", "characterization test", "golden master", "strangler fig", /refactor-legacy. Not for rebuilding elsewhere (use legacy-parity) or new-feature tests (use test-every-change).'
---

# Refactor Legacy Procedure

This skill guides the agent through changing code that has no tests without breaking it: pin what it does now, open a seam, move in small verified steps, and replace large units one slice at a time.

---

## 1. When to Use This Skill

Activate this skill when:
- A bug fix, feature, or cleanup must touch code that has no tests, or tests that cannot fail.
- The code cannot be put under test because it builds its own dependencies, reads the clock, or calls the network.
- A large unit (module, service, endpoint family) must be replaced while it stays in production.
- A diff to untested code is about to be written before its current behaviour is pinned.
- The user runs the `/refactor-legacy` slash command.

*Boundary*: Rebuilding a system elsewhere while matching its behaviour is `legacy-parity`. Tests for new behaviour, or a bug-fix regression test, are `test-every-change`. Moving data is `database-migration`. Recording a decision about a discovered bug is `decision-log`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Scope Small and Write Down What Must Stay
1. Pick the smallest area that holds the change: one function, one class, one endpoint. Name what is out of scope.
2. Write the behaviour to keep as bullets: inputs, outputs, side effects, errors, ordering, rounding, including behaviour that looks wrong.
3. Run the existing suite once and record the baseline, including failures that predate you.

### Step 2: Find the Change Point and Its Callers
1. Use `codegraph` when connected (callers, callees, impact); otherwise targeted search for the symbol, route, or literal, then read only the matching lines.
2. List every caller, including reflection, config, jobs, and scripts. Note the narrowest place where the change can be made once.
3. Prefer the smallest change point: many callers mean pin at the shared function, not at each caller.

### Step 3: Pin Current Behaviour Before Touching It
Consult: [Seams & Characterization](./references/seams-and-characterization.md)
1. Run the code with chosen inputs, record the actual outputs, review each for sanity, and assert them as characterization tests. Use a golden-master snapshot when outputs are large; review the snapshot as you would a diff.
2. Control non-determinism first: inject or freeze clocks, seed randomness, stub ids, sort unordered output, fake external calls.
3. Cover every branch the change can reach. Add inputs until the change point's branches are all exercised.
4. If it cannot be run in a test, go to Step 4 first, then return here.

### Step 4: Break Dependencies With the Smallest Safe Move
Consult: [Seams & Characterization](./references/seams-and-characterization.md)
1. Choose the seam: object seam (substitute a collaborator), link seam (swap the module at build or load time), or preprocessing seam (last resort).
2. Use the smallest move that opens it: parameterize the constructor or method, extract an interface, extract and override, or wrap or sprout a method or class for new logic.
3. Do the move with no other edit, preserving the signature for existing callers. Verify by compiling or type-checking and running the smoke path by hand, since no test covers it yet.

### Step 5: Refactor in Tiny Steps
Consult: [Safe-Step Checklist](./references/safe-step-checklist.md)
1. One transformation per step (rename, extract, move, inline); run the pins after each; revert a red step at once instead of debugging forward.
2. Keep structure and behaviour in separate commits. A behaviour change never hides inside a refactor commit.
3. Do not edit a pinned test to make it pass. A pin that must change means behaviour changed: stop and decide.

### Step 6: Mutation-Check the Pins
1. Break the code on purpose in five ways: a constant, a branch condition, a dropped side effect, an empty return, a removed validation.
2. At least one test must fail for each; revert after each. A survivor means add a pin before continuing.

### Step 7: Replace Large Units Incrementally
Consult: [Strangler Fig Playbook](./references/strangler-fig-playbook.md)
1. When the unit is too big for steps 5 and 6, route traffic through a seam and replace one slice at a time, comparing old and new outputs before each cutover.
2. Delete the old path only after the last slice has run clean in production for the agreed period.

### Step 8: Handle Discovered Bugs and Know When to Stop
1. A bug found while pinning is recorded, not silently fixed. Pin it as current behaviour with a comment naming it, or ask the owner and record the answer with `decision-log`. Fix it in its own commit with its own regression test (`test-every-change`).
2. Stop and rewrite only when the criteria in [Strangler Fig Playbook](./references/strangler-fig-playbook.md) hold; otherwise keep going in small steps.

---

## 3. Verification Protocol

```bash
<test command>                          # pins and full suite green after every step
<test command> -k characterization      # or: --grep, --filter, -m; the pins alone
git diff --stat <base>...HEAD           # refactor commits touch no test expectations
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Pins | Snapshot was accepted without reading it | A bug is frozen as truth unseen | `[Blocker]` | Review each value; record bugs as bugs |
| Pins | Mutation (flip a branch) left all tests green | Branch unprotected | `[Blocker]` | Add an input that reaches it |
| Seam | Move also changed a default value | Behaviour changed under a refactor label | `[Architecture]` | Revert; make the move alone |
| Commits | Structure and behaviour in one commit | Review and rollback both blind | `[Suggestion]` | Split the commit |

---

## 4. Negative Triggers

- Rebuilding the system elsewhere to match the old one: use `legacy-parity`.
- Writing tests for new behaviour or a bug-fix regression: use `test-every-change`.
- Moving or transforming stored data: use `database-migration`.
- Code that already has trustworthy tests: refactor with `minimal-change` and run them; skip the pinning steps.

---

## 5. Token Conservation Directive

- **Search, Then Read Lines**: Use `codegraph` or targeted search for callers; open only the lines the change point needs.
- **Pin the Slice**: Characterize the change point and its direct callers only, never the whole module.
- **Report Briefly**: Output the verification table and the suite result line, with no narration of technique.
