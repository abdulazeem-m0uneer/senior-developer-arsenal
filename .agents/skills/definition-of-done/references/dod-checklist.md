# Definition of Done Checklist

Master checklist to instantiate per feature. Each item lists what "done" means and the evidence that proves it. Mark an item `N/A` only with a written reason.

---

## 1. Behaviour

| # | Item | Done means | Evidence |
| :---: | :--- | :--- | :--- |
| 1 | Acceptance criteria | Every criterion is implemented and observable | Passing test per criterion (`file:line`) or a recorded manual run |
| 2 | Error paths | Each failure mode returns a defined error; nothing is swallowed | `file:line` of the handler plus a test that triggers it |
| 3 | Edge cases | Empty / null, boundaries, invalid input, permission denial, concurrency, dependency failure are handled or ruled out | Test per case, or reason the case cannot occur |
| 4 | Backward compatibility | Existing callers, stored data, and public contracts still work | Contract or regression tests green; no breaking change without a version bump |

---

## 2. Tests

| # | Item | Done means | Evidence |
| :---: | :--- | :--- | :--- |
| 5 | Tests for the change | Every changed behaviour has a test | Mapping of changed behaviour to test name |
| 6 | Tests can fail | Each new test fails when the change is reverted or broken | Red run recorded before the green run |
| 7 | Full suite | Whole suite passes, nothing skipped or disabled to get there | Command, exit status, pass / fail / skip counts |
| 8 | Determinism | New tests pass on repeated and reordered runs | Repeat-run output |

---

## 3. Static Gates

| # | Item | Done means | Evidence |
| :---: | :--- | :--- | :--- |
| 9 | Lint | Zero errors and no new warnings or suppressions | Lint command and exit status |
| 10 | Type-check | Zero type errors; no new `any`, `dynamic`, or ignore comments | Type-check command and exit status |
| 11 | Build | Release build succeeds | Build command and exit status |

---

## 4. Risk

| # | Item | Done means | Evidence |
| :---: | :--- | :--- | :--- |
| 12 | Input validation | Every new boundary validates its input with a schema | `file:line` of the validator |
| 13 | Authorization | Every new or changed endpoint enforces authentication and ownership or tenant checks | `file:line` plus a test for the denied case |
| 14 | Secrets and data exposure | No secret in code or logs; responses expose no internal fields | Search results for key patterns; response shape checked |
| 15 | Queries | No N+1, no unindexed filter on a large table, parameterized SQL only | Query plan or query log; `file:line` |
| 16 | Performance | No blocking call on a hot path; payloads and loops are bounded | Measurement against the stated target, or reasoning with `file:line` |

---

## 5. Operability

| # | Item | Done means | Evidence |
| :---: | :--- | :--- | :--- |
| 17 | Observability | New I/O boundaries log structured events with a correlation ID; failures are visible | `file:line` of log and metric calls |
| 18 | Migrations | Schema changes are scripted, forward-safe under load, and reversible or explicitly irreversible | Migration applied and rolled back on a scratch database |
| 19 | Rollback path | The change can be reverted or disabled without data loss | Flag, revert plan, or down migration, exercised once |
| 20 | Configuration | New settings have defaults, validation, and are documented for every environment | `file:line` of config schema and sample env file |

---

## 6. Hygiene

| # | Item | Done means | Evidence |
| :---: | :--- | :--- | :--- |
| 21 | Docs | Public behaviour, setup steps, and API changes are documented | Path of the updated doc or API spec |
| 22 | Changelog | User-visible change is recorded | Changelog entry or release note line |
| 23 | No leftovers | No `TODO` / `FIXME`, commented-out code, debug output, or unused imports, variables, exports, dependencies in the change | Search over the changed files returns nothing |
| 24 | File size | No file exceeds 1000 lines after the change | Line counts of the changed files |
| 25 | SOLID and reuse | Single responsibility per unit, dependencies point inward, no duplicated logic that already existed | `file:line` review notes; search for existing helpers |
| 26 | Commit hygiene | Atomic commits with conventional messages; no secrets or binaries committed | Commit log of the branch |

---

## 7. Applicability Guide

| Change type | Usually N/A | Never N/A |
| :--- | :--- | :--- |
| Bug fix | 21 (unless behaviour was documented wrongly), 20 | 2, 5, 6, 7 (regression test is mandatory) |
| New feature | none | 1 to 11, 23, 24 |
| Refactor | 1, 22 | 4, 7, 9 to 11, 25 |
| Schema or data change | 21 | 4, 18, 19 |
| Config or infra change | 1, 25 | 11, 19, 20 |
| Docs only | 2 to 20 | 21, 23 |
