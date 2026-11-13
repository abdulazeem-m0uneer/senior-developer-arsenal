---
name: test-every-change
description: 'Tests for every code change: regression test before a bug fix, happy, error and edge cases for a feature, characterization tests before a refactor. Use when implementing a feature, fixing a bug, refactoring, or changing any code or config. Triggers: "add tests for this change", "regression test", /test-every-change. Not for suite design or flaky tests (use test-strategy) or manual test plans (use qa-engineer).'
---

# Test Every Change Procedure

This skill enforces one rule: no change to behaviour, code, configuration, or schema is complete until a test or check proves it, and that proof has been seen to fail without the change.

---

## 1. When to Use This Skill

Activate this skill when:
- Implementing a new feature or extending an existing one.
- Fixing a bug of any size, including a one-line fix.
- Refactoring, renaming, upgrading a dependency, or changing configuration, infrastructure, or a database migration.
- A diff exists without matching tests, or the user runs the `/test-every-change` slash command.

*Boundary*: For designing a suite, choosing layers and test doubles, or diagnosing flaky tests, use `test-strategy`. For manual test plans and test cases, use `qa-engineer`. For the final completion gate, use `definition-of-done`. For enforcing these rules in one command, use `quality-gate`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Inventory the Change
1. List what changed or will change from your shell: `git status --short` and `git diff <base>...HEAD --stat`.
2. Break the change into behaviours: each new or altered branch, input, output, error, state transition, query, config key, and migration is one row.
3. Find the existing test setup: runner, naming convention, fixtures, and the command that runs the whole suite. Run it once and record the baseline.

### Step 2: Map Each Behaviour to Required Tests
Fill the mapping using the [Change-to-Test Matrix](./references/change-to-test-matrix.md). No row may be left without a test or an explicit, justified exemption.

### Step 3: Apply the Rule for the Change Type
Loop discipline for every type: Consult: [TDD Loop & Honest Tests](./references/tdd-loop-and-honest-tests.md). Production code written before its failing test is deleted and rewritten from the test, not kept as reference; name the production change that would fail each test before writing its body.
- **Bug fix**: write the regression test first and run it; it must fail for the reported reason (red). Apply the fix. Run it again (green). Never write the test after the fix without proving it red against the unfixed code.
- **New feature**: one test for the happy path of each acceptance criterion, one per error path, and the edge cases: empty / null, boundaries, invalid input, permission denial, concurrency, dependency failure.
- **Refactor**: before touching the code, pin current behaviour with characterization tests and see them pass. Refactor. The same tests must pass unchanged.
- **Config, infra, migration**: add the matching check: config schema validation test, container or pipeline build, migration applied and rolled back against a real engine, and a data assertion on existing rows.
- **Dependency upgrade**: run the full suite before and after; add a test for any behaviour the changelog says changed.

### Step 4: When No Test Framework Exists
Follow [Bootstrap & Exemptions](./references/bootstrap-and-exemptions.md): set up the smallest standard runner for the stack with one command to run it, then write the tests. Only when a test is truly impossible, record the exemption in writing: what cannot be tested, why, and the manual verification performed instead. "No framework yet" and "no time" are not valid reasons.

### Step 5: Prove the Tests and Run Everything
1. Each new test has been observed failing (code reverted, branch inverted, or fix absent) and then passing.
2. Run the full suite, not only the new tests. A failure elsewhere is caused by the change until proven otherwise; fix it or report it, never skip or delete the test.
3. Measure coverage of the changed lines and branches against the base branch, not the global percentage; uncovered changed lines get a test or a written exemption.
4. Leave no skipped, focused, or todo test behind (`.skip`, `.only`, `[Fact(Skip=...)]`, `@pytest.mark.skip`).
5. With the Claude Code plugin, a `Stop` hook (`hooks/guard.py`) blocks once when source files changed in the session and no test file did. Answer it with the test, or with the written exemption from Step 4; never by touching a test file to silence it.

---

## 3. Verification Protocol

1. Every row of the change inventory maps to at least one named test or a written exemption.
2. Red and green runs are both recorded for regression and feature tests.
3. The full suite, lint, and type-check were run after the last edit and are green; skipped-test count did not increase.
4. Output the mapping table:

| Changed behaviour | Change type | Test (`file:line`) | Red seen | Green seen |
| :--- | :--- | :--- | :---: | :---: |
| Refund rejected after 30 days | Bug fix | `refund.service.spec.ts:58` | yes | yes |
| `POST /refunds` returns 403 for another tenant | Feature | `refunds.api.spec.ts:91` | yes | yes |
| `REFUND_WINDOW_DAYS` must be a positive integer | Config | `config.schema.spec.ts:33` | yes | yes |
| Log wording changed | Cosmetic | exempt: no behaviour change, verified by reading the diff | n/a | n/a |

Full suite: `<command>` exit `<code>`, `<passed>` passed, `<failed>` failed, `<skipped>` skipped.

---

## 4. ⚡ Token-Saving Execution Rule

- **Tests Only**: Output new or changed test functions, never whole files.
- **Mapping Table, No Narration**: Report the table and the suite result line; omit testing theory.
- **Failures First**: On a red suite, show only failing test names and the first assertion message.

**Next**: when every mapped test passes, review the change with `code-review` (`deep-review` for a large or high-risk change).
