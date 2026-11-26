---
name: test-strategy
description: 'Test suite design: pyramid, test doubles, flaky tests, coverage. Use to plan or fix a test suite.'
---

> **Lite edition:** steps that run a bundled script (a `scripts/` or `templates/` path) need the full arsenal (https://github.com/abdulazeem-m0uneer/senior-developer-arsenal). Here, do that step by hand or skip it and say so.

<!-- routing (read by the skill router, not loaded into the skill listing): Test suite design: pyramid, unit vs integration vs end-to-end scope, test doubles, flaky-test diagnosis. Use to plan or improve a test suite, fix flaky tests or raise coverage. Triggers: "write tests", "test strategy", "add coverage", "flaky test", /test-strategy. Not for the tests of one change (use test-every-change), reviewing a diff (use code-review) or manual test plans (use qa-engineer). -->

# Test Strategy & Test Authoring Procedure

This skill guides the agent through deciding what to test at which layer, enumerating the cases that matter, and writing deterministic tests in Vitest/Jest, xUnit, pytest, and Playwright.

---

## 1. When to Use This Skill

Activate this skill when:
- Writing tests for new or untested code, or planning the suite for a new module or service.
- Deciding whether a behaviour belongs in a unit, integration, or end-to-end test.
- Diagnosing intermittent (flaky) failures or a slow suite.
- Raising coverage on risky code rather than chasing a percentage.
- The user runs the `/test-strategy` slash command.

*Boundary*: For judging a diff for defects, use `code-review`. For implementing a feature across database, API, and UI, use `e2e-feature`; return here to design its tests.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Discover the Stack & Baseline
1. Read the project manifest (`package.json`, `*.csproj`, `pyproject.toml`) to identify the runner, assertion library, and existing conventions (file naming, fixtures, factories).
2. Run the existing suite once from your shell and record: pass/fail counts, wall time, slowest tests, current coverage.
3. Reuse existing helpers and fixtures before creating new ones.

### Step 2: Assign Each Behaviour to a Layer
Consult: [Test Layering & Test Doubles](./references/test-layering-and-doubles.md)
- **Unit** (majority): pure domain rules, calculations, state machines, mappers, validators. No I/O, milliseconds each.
- **Integration**: repositories against a real database engine, HTTP handlers through the real routing and validation stack, message consumers. Replace only third-party systems you do not own.
- **End-to-end** (few): critical user journeys only (sign-in, checkout, core CRUD), driven through the browser with Playwright.
- **Smoke** (after every deploy): the journeys again, against the running environment, with data the suite creates through the API; see `smoke-test`.
- Push every case to the lowest layer that can prove it.

### Step 3: Enumerate Cases Before Writing
Consult: [Edge Cases & Flakiness](./references/edge-cases-and-flakiness.md)
1. List the happy path, then walk the edge-case matrix: empty/null, boundaries, invalid input, permission denial, concurrency, dependency failure.
2. Convert input variations into table-driven tests (`it.each`, `[Theory]` with `[InlineData]`, `@pytest.mark.parametrize`).
3. For every bug fix, write the failing regression test first and confirm it fails for the right reason.
4. For parsers and native code, add fuzzing: [Optional Fuzzing](./references/fuzzing-tooling.md).

### Step 4: Author Deterministic Tests
1. One behaviour per test, Arrange-Act-Assert layout, name states scenario and expected outcome.
2. Assert on observable outcomes (return value, persisted state, emitted event, HTTP response), not on private calls.
3. Control time, randomness, and network explicitly; never sleep for a fixed duration.
4. Each test creates its own data and leaves no shared state behind.
5. API tests go through the real routes and create their preconditions through the API; a direct database insert is kept for states the API cannot produce (a race, corrupt data).

### Step 5: Diagnose Flaky or Slow Tests
Reproduce by repetition and order shuffling, classify the cause (timing, shared state, order dependence, real network, unawaited async), then fix the cause. Do not add retries or longer timeouts as the fix.

### Step 6: Audit the Suite for Tests That Cannot Fail
Consult: [Test Audit](./references/test-audit.md)
1. Run `python3 <skill-dir>/scripts/test_audit.py <test dirs>` (exit 1 findings, 0 clean, 2 usage error).
2. Fix each finding at its cause: add the missing assertion, delete or un-skip the skipped test, remove `.only`, merge the duplicate into a table-driven test, replace a source grep with a call to the code.
3. Done when the audit exits 0, or each remaining finding has a one-line reason in the report.

---

## 3. Verification Protocol

1. Run the full suite with coverage and confirm it is green:
   - Vitest / Jest: `npx --no-install vitest run --coverage` or `npx --no-install jest --ci --coverage`
   - .NET: `dotnet test --collect:"XPlat Code Coverage"`
   - Python: `pytest --cov --cov-branch --cov-report=term-missing`
   - Playwright: `npx --no-install playwright test --trace on-first-retry`
2. Prove each new test can fail: break the code under test (or revert the fix) and confirm the test goes red.
3. Run new tests repeatedly and in shuffled order to confirm determinism.
4. Report in a compact table:

| Layer | Target | Cases added | Gap closed |
| :--- | :--- | :---: | :--- |
| Unit | `PriceCalculator.applyDiscount` | 7 | Negative quantity, zero total, rounding boundary |
| Integration | `POST /orders` | 4 | 401 without token, 404 for foreign tenant, duplicate idempotency key |

---

## 4. ⚡ Token-Saving Execution Rule

- **Tests Only**: Output only new or changed test functions, never whole unchanged files.
- **Failures First**: When reporting a run, show only failing test names and the first relevant assertion message.
- **No Narration**: Skip explanations of testing theory; state the layer decision and the case list.
