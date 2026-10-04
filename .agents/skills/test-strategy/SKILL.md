---
name: test-strategy
description: 'Test strategy and test authoring runbook: test pyramid layering, unit vs integration vs end-to-end scope, edge-case enumeration, test doubles, flaky-test diagnosis, and coverage that matters, using Vitest/Jest, xUnit, pytest, and Playwright. Use when the user asks to write or improve tests, plan a test suite, fix flaky tests, or raise meaningful coverage. Triggers on: "write tests", "test strategy", "add coverage", "flaky test", "/test-strategy". Do not use for reviewing a diff for defects (use code-review) or building a full vertical feature slice (use e2e-feature).'
---

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
- Push every case to the lowest layer that can prove it.

### Step 3: Enumerate Cases Before Writing
Consult: [Edge Cases & Flakiness](./references/edge-cases-and-flakiness.md)
1. List the happy path, then walk the edge-case matrix: empty/null, boundaries, invalid input, permission denial, concurrency, dependency failure.
2. Convert input variations into table-driven tests (`it.each`, `[Theory]` with `[InlineData]`, `@pytest.mark.parametrize`).
3. For every bug fix, write the failing regression test first and confirm it fails for the right reason.

### Step 4: Author Deterministic Tests
1. One behaviour per test, Arrange-Act-Assert layout, name states scenario and expected outcome.
2. Assert on observable outcomes (return value, persisted state, emitted event, HTTP response), not on private calls.
3. Control time, randomness, and network explicitly; never sleep for a fixed duration.
4. Each test creates its own data and leaves no shared state behind.

### Step 5: Diagnose Flaky or Slow Tests
Reproduce by repetition and order shuffling, classify the cause (timing, shared state, order dependence, real network, unawaited async), then fix the cause. Do not add retries or longer timeouts as the fix.

---

## 3. Verification Protocol

1. Run the full suite with coverage and confirm it is green:
   - Vitest / Jest: `npx vitest run --coverage` or `npx jest --ci --coverage`
   - .NET: `dotnet test --collect:"XPlat Code Coverage"`
   - Python: `pytest --cov --cov-branch --cov-report=term-missing`
   - Playwright: `npx playwright test --trace on-first-retry`
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
