# Review Passes

One pass per dimension. Run each over the whole scope with only that dimension in mind. Record candidates as `file:line` plus a one-line suspicion.

---

## Pass 1: Correctness
- [ ] Each function does what its name, contract, and the ticket say; compare against the stated intent, not against the code itself.
- [ ] Boundaries: off-by-one, empty and single-element collections, zero, negative, maximum, overflow, rounding of money.
- [ ] Null / undefined / `None` on every dereference that follows an optional lookup.
- [ ] Every branch of each conditional is reachable and correct; inverted or duplicated conditions; missing `else` or default case.
- [ ] Error handling: no swallowed exceptions, no catch-all that hides the cause, errors propagate with context, cleanup runs on failure.
- [ ] Time: time zones, DST, month end, clock source injected rather than read inline.
- [ ] State machines: invalid transitions rejected; repeated calls are idempotent where required.

## Pass 2: Security
- [ ] Every entry point authenticates and authorizes; object lookups filter by owner or tenant from the verified session.
- [ ] Attacker-controlled input never reaches SQL, shell, file paths, URLs to fetch, templates, or deserializers without validation or parameterization.
- [ ] No secret in code, config committed to the repository, logs, or error responses.
- [ ] Responses expose only intended fields; mass assignment is blocked by explicit request models.
- [ ] Tokens, cookies, and comparisons of secrets follow hardened defaults (expiry, flags, constant-time compare).

## Pass 3: Data Integrity
- [ ] Multi-step writes are atomic: one transaction, or an outbox / saga with compensation.
- [ ] Constraints live in the database (unique, foreign key, not null, check), not only in application code.
- [ ] Migrations are forward-safe under load, reversible or explicitly irreversible, and preserve existing rows.
- [ ] Idempotency on retried writes (keys, upserts); no duplicate side effects after a timeout.
- [ ] Correct types: timestamps with time zone, exact numerics for money, enums constrained.

## Pass 4: Concurrency
- [ ] Read-modify-write sequences are protected (optimistic version, row lock, atomic update).
- [ ] Check-then-act races: uniqueness checks, balance checks, "exists then create".
- [ ] Shared mutable state: module singletons, static fields, caches without synchronization.
- [ ] Async correctness: every promise or task awaited; no sync-over-async; cancellation propagated; no blocking I/O on an event loop.
- [ ] Lock ordering, lock duration, and work done while holding a transaction open.

## Pass 5: Performance
- [ ] Queries inside loops (N+1); missing batching or eager loading.
- [ ] Filters and joins on large tables have supporting indexes; no non-sargable predicates.
- [ ] Unbounded results, payloads, loops, recursion, retries, and in-memory collections.
- [ ] Resource lifetime: connections, streams, handles, and timers are released on every path.
- [ ] Hot-path allocations, repeated parsing or serialization, missing caching where the data is stable.

## Pass 6: Tests
- [ ] Every changed behaviour has a test that would fail without the change.
- [ ] Error paths and edge cases are tested, not only the happy path.
- [ ] Assertions check outcomes; no assertion-free tests, no tests that only verify a mock was called.
- [ ] No skipped, disabled, or weakened tests; no fixed sleeps or dependence on test order.
- [ ] Test doubles match the real behaviour of the dependency they replace.

## Pass 7: API Contracts
- [ ] Request and response shapes, status codes, and error format match the published contract or spec.
- [ ] No breaking change (removed or renamed field, changed type, new required input) without versioning.
- [ ] Pagination, filtering, and sorting are bounded and consistent; idempotency declared for unsafe methods.
- [ ] Client and server types stay in sync; generated clients were regenerated.
- [ ] Events and messages: schema versioned, consumers tolerate unknown fields.

## Pass 8: Config & Infrastructure
- [ ] New settings have validation, safe defaults, and are present for every environment.
- [ ] Container and pipeline changes: pinned versions, non-root user, no secret baked into an image or log.
- [ ] Timeouts, retries with backoff, and circuit breakers on every outbound call.
- [ ] Feature flags default to the safe state and have a removal plan.
- [ ] Observability: structured logs with correlation IDs, metrics on I/O boundaries, no sensitive data logged.

## Pass 9: Docs & Maintainability
- [ ] Public behaviour, setup, and operational steps are documented where the project keeps such docs.
- [ ] Names reveal intent; one responsibility per unit; dependencies point inward.
- [ ] No duplicated logic that an existing helper already provides; no dead code, commented-out blocks, or stray debug output.
- [ ] No file above 1000 lines; no function too long to hold in one screen without reason.
- [ ] Comments explain why, and none contradicts the code beside it.

---

## Pass Applicability

| Scope contains | Passes that are mandatory |
| :--- | :--- |
| Any code | 1, 6, 9 |
| HTTP, queue, or CLI entry points | 2, 7 |
| Database access or migrations | 3, 4, 5 |
| Async, parallel, or background work | 4 |
| Build, container, pipeline, or settings files | 8 |

Mark a pass "not applicable" only with the reason stated in the report.
