# Edge Cases & Flakiness

Case-enumeration matrix, flaky-test diagnosis table, and coverage guidance.

---

## 1. Edge-Case Matrix

Walk every row for each public function or endpoint; write a test or record why the row does not apply.

| Dimension | Cases to enumerate |
| :--- | :--- |
| Empty / missing | `null`, `undefined` / `None`, empty string, whitespace-only, empty collection, missing optional field |
| Boundaries | Zero, one, max, max + 1, negative, off-by-one at each limit, first and last page |
| Numeric | Floating-point rounding (`0.1 + 0.2`), currency minor units, overflow, `NaN`, division by zero |
| Text | Unicode and combining characters, very long input, leading/trailing spaces, case differences, characters special to SQL or HTML |
| Time | Time-zone offsets, DST transitions, leap day, month end, midnight boundary, clock skew, expired versus not-yet-valid |
| Collections | Duplicates, unsorted input, single element, very large input, stable ordering of ties |
| Invalid input | Wrong type, malformed JSON, unknown enum value, extra unexpected fields, oversized payload |
| Authorization | Unauthenticated (401), wrong role (403), another tenant's resource (404 or 403), expired token |
| State | Already exists, already deleted, wrong lifecycle state, repeated request (idempotency) |
| Concurrency | Two writers on the same row, double submit, lost update, retry after timeout |
| Dependency failure | Timeout, connection refused, 429, 500, malformed response, partial success in a batch |

---

## 2. Flaky-Test Diagnosis

Reproduce first:

| Runner | Repeat | Shuffle order | Isolate |
| :--- | :--- | :--- | :--- |
| Vitest | `npx vitest run --retry=0` in a shell loop | `--sequence.shuffle` (`--sequence.seed=<n>` to replay) | `--no-file-parallelism` |
| Jest | shell loop over `npx jest path/to/test` | `--randomize` (`--seed=<n>` to replay) | `--runInBand`, `--detectOpenHandles` |
| pytest | `pytest --count=50 -x` (pytest-repeat) | pytest-randomly shuffles once installed (`-p randomly_seed=<n>` to replay, `-p no:randomly` to disable) | `pytest path::test_name`, `--lf` |
| xUnit | shell loop over `dotnet test --filter "FullyQualifiedName~OrderTests"` | No built-in shuffle; test collections already run in parallel | `[Collection("name")]` to serialize |
| Playwright | `npx playwright test --repeat-each=20` | `fullyParallel: true` in config | `--workers=1`, `--trace on` |

Then classify and fix the cause:

| Symptom | Likely cause | Fix |
| :--- | :--- | :--- |
| Fails only in CI or under load | Fixed sleeps, timing assumptions | Await the condition (web-first assertion, polling with deadline); use fake timers |
| Fails only when run with other tests | Shared mutable state: module singletons, static fields, shared DB rows | Fresh fixture per test; reset mocks (`vi.restoreAllMocks()`); unique data per test |
| Fails only in a specific order | Test depends on data created by another test | Each test arranges its own data; transaction rollback or truncate between tests |
| Fails around midnight or month end | Real clock, local time zone | Inject a clock; pin `TZ=UTC` in the test environment |
| Random failure, passes on rerun | Unawaited promise or task, unseeded randomness | Await or return every async call; seed the generator and log the seed |
| Fails with network errors | Real external call | Stub the HTTP boundary; block real network in tests |
| Port or file already in use | Fixed ports and paths under parallel workers | Ephemeral port (`0`), per-test temp directory (`tmp_path`, `mkdtemp`) |
| Assertion on collection order | Unordered query or hash-map iteration | Add explicit `ORDER BY` or compare as sets |

- [ ] Quarantine is temporary: tag the test, open a tracked issue, fix within the sprint.
- [ ] Retries are a detection signal in CI, never the remedy.

---

## 3. Coverage That Matters

- [ ] Measure **branch** coverage, not just lines; an `if` without an `else` test is a hidden gap.
- [ ] Prioritize by risk: money, authorization, data mutation, parsing of external input, concurrency. Generated code, DTOs, and framework glue can stay low.
- [ ] Gate on changed code (diff coverage) rather than a repo-wide number that invites trivial tests.
- [ ] A covered line with no assertion proves nothing; verify with mutation testing on critical modules (`npx stryker run`, `dotnet stryker`, `mutmut run`).

| Stack | Threshold configuration |
| :--- | :--- |
| Vitest | `test.coverage.thresholds: { lines: 80, branches: 75 }` in `vitest.config.ts` |
| Jest | `coverageThreshold: { global: { lines: 80, branches: 75 } }` |
| pytest-cov | `--cov-fail-under=80` (or `fail_under` under `[tool.coverage.report]`) |
| Coverlet (msbuild) | `dotnet test /p:CollectCoverage=true /p:Threshold=80 /p:ThresholdType=branch` |

---

## 4. Test Smells to Remove

- [ ] Assertion-free tests, or tests asserting only that a mock was called.
- [ ] Logic in tests (loops, conditionals) that can itself be wrong.
- [ ] One test covering many behaviours; the first failure hides the rest.
- [ ] Snapshot of a large object used instead of targeted assertions.
- [ ] Mirroring the implementation (asserting the exact sequence of internal calls).
- [ ] Shared "god fixture" that every test mutates.
