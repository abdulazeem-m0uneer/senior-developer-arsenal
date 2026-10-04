# Change-to-Test Matrix

For every kind of change: the tests it requires, the order of work, and how to prove the test is real.

---

## 1. Required Tests by Change Type

| Change | Required tests | Order of work |
| :--- | :--- | :--- |
| Bug fix | Regression test reproducing the reported failure, plus the neighbouring boundary | Test (red) -> fix -> test (green) -> full suite |
| New function or method | Happy path, each error path, edge-case matrix | Tests alongside or before the code |
| New endpoint or handler | 2xx path, validation failure (400 / 422), unauthenticated (401), forbidden or foreign tenant (403 / 404), not found, conflict or idempotent replay | In-process API test through the real pipeline |
| Changed condition or branch | A case on each side of the changed boundary | Test (red on old code) -> change -> green |
| New or changed query | Rows returned, empty result, ordering, tenant filter, pagination limits | Integration test against a real engine |
| Schema migration | Applies on a populated database, existing rows valid afterwards, down migration or rollback | Apply -> assert data -> roll back -> assert schema |
| Refactor without behaviour change | Characterization tests covering current outputs and side effects | Tests (green) -> refactor -> same tests (green), unchanged |
| Performance change | A measurement or benchmark with a threshold, plus unchanged functional tests | Measure before -> change -> measure after |
| Config or environment key | Schema validation: missing, malformed, default, and valid values | Validation test, then startup smoke check |
| Container, pipeline, infra | Build succeeds, lint of the definition file, smoke run of the artifact | Run the build locally or in a dry run |
| Dependency upgrade | Full suite before and after; test for each behaviour the changelog marks as changed | Baseline -> upgrade -> full suite |
| UI component | Render, each interactive state, keyboard path, error and empty states | Component test; end-to-end only for a critical journey |
| Deleted code | Tests for the removed behaviour deleted with it; callers proven gone by search and a green build | Search -> delete -> build -> full suite |
| Feature flag | Behaviour with the flag on and off | Two cases per flagged branch |

---

## 2. Edge Cases Required for Every New Behaviour

| Dimension | Minimum cases |
| :--- | :--- |
| Empty / missing | `null` / `undefined` / `None`, empty string, empty collection, absent optional field |
| Boundaries | Zero, one, limit, limit + 1, negative |
| Invalid input | Wrong type, malformed payload, unknown enum value, oversized input |
| Authorization | No identity, wrong role, another owner or tenant |
| State | Already exists, already deleted, wrong lifecycle state, repeated request |
| Concurrency | Two writers on the same record, double submit |
| Dependency failure | Timeout, error response, malformed response |

A row is skipped only with a note explaining why it cannot occur for this behaviour.

---

## 3. Regression Test Rules (Bug Fixes)

- [ ] The test reproduces the bug through the same entry point the user or caller hit, at the lowest layer that can show it.
- [ ] It is run before the fix and fails with a message that matches the reported symptom, not with a setup error.
- [ ] Its name states the scenario and the expected outcome, and references the issue ID where one exists.
- [ ] After the fix it passes, and reverting the fix makes it fail again.
- [ ] The search for the same defect pattern elsewhere in the codebase is done; each sibling occurrence gets its own test and fix.

---

## 4. Characterization Test Rules (Refactors)

- [ ] Cover every public entry point of the code being restructured, including error outputs and side effects.
- [ ] Assert current behaviour as it is, even where it looks wrong; record suspected bugs separately instead of fixing them mid-refactor.
- [ ] Tests are written and green before the first structural edit.
- [ ] Tests are not edited during the refactor. A test that must change means behaviour changed; treat that as a feature or a fix.

---

## 5. Proving a Test Is Real

| Check | Method |
| :--- | :--- |
| It can fail | Revert the change, invert the condition, or stash the fix; confirm red |
| It fails for the right reason | The failure message names the behaviour under test |
| It asserts an outcome | Return value, persisted state, emitted event, or response, not only that a call happened |
| It is deterministic | Passes on repeated runs and in shuffled order; no fixed sleeps, real clock, or real network |
| It is isolated | Creates its own data; leaves no shared state |

---

## 6. Mapping Worksheet

| # | Changed behaviour (`file:line`) | Type | Test name | Layer | Red | Green |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| 1 | `refund.service.ts:44` window check uses `>=` | Bug fix | rejects refund on day 31 | Unit | yes | yes |
| 2 | `refund.service.ts:44` boundary | Bug fix | accepts refund on day 30 | Unit | yes | yes |
| 3 | `0042_add_refund_reason.sql` | Migration | applies and rolls back on populated table | Integration | yes | yes |

Every row of the diff inventory appears here. An empty "Test name" cell is not allowed; use `exempt:` with the reason and the manual verification performed.
