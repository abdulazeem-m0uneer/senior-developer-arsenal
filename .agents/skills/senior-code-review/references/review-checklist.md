# Senior Engineering Review Checklist

Use this checklist during every code review to ensure zero gaps in reliability, security, and performance.

---

## 1. Security & OWASP Verification
- [ ] **SQL Injection**: Are all database queries parameterized? Check raw SQL queries in Dapper, EF Core `FromSqlRaw`, and Node.js `pg.query`.
- [ ] **Authentication & Authorization**: Is there an authorization check on every new or modified endpoint? Are resource IDs checked against the current tenant/user (preventing IDOR)?
- [ ] **Mass Assignment / Over-posting**: Are DTOs used for request binding instead of direct entity binding?
- [ ] **Data Exposure**: Are entity models returning internal columns (hashed passwords, internal flags, PII) directly in API responses?
- [ ] **Secrets Management**: Are there any hardcoded connection strings, API tokens, or secrets?
- [ ] **ReDoS & Parsing**: Are regex patterns protected against catastrophic backtracking? Are large JSON inputs limited in size?

---

## 2. Database & Data Integrity
- [ ] **N+1 Query Problems**: Are database queries triggered inside loops? Check `.Include()` in EF Core or batched queries in Node.
- [ ] **Indexes**: Does every new query filter (`WHERE`) or join condition (`ON`) have a supporting index?
- [ ] **Postgres Data Types**: Are timestamps defined as `TIMESTAMPTZ`? Are currency amounts `NUMERIC`?
- [ ] **Transaction Scope**: Are multi-step mutations wrapped in transactions? Are transactions kept as short as possible to prevent lock contention?
- [ ] **Concurrency & Locking**: Are concurrent updates handled with optimistic concurrency (row version/etag) or pessimistic locking (`FOR UPDATE SKIP LOCKED`)?
- [ ] **Migration Safety**: Does the migration avoid blocking DDL? Is `CREATE INDEX CONCURRENTLY` used for PostgreSQL?

---

## 3. Concurrency & Performance
- [ ] **C# Async Safety**: Are there any blocking calls (`.Result`, `.Wait()`, `.GetAwaiter().GetResult()`)?
- [ ] **Cancellation Propagation**: Is `CancellationToken` accepted and forwarded through all async calls in C#?
- [ ] **Node.js Event Loop**: Are there any synchronous I/O operations (`readFileSync`, `execSync`) in request handlers?
- [ ] **Resource Disposal**: Are database connections, HTTP clients, and file streams disposed with `using` (C#) or proper stream pipelines (Node.js)?
- [ ] **Memory Allocation**: Are large arrays or strings repeatedly allocated in hot loops?

---

## 4. Architecture & Clean Code
- [ ] **Single Responsibility**: Does each class or function do one thing well?
- [ ] **Dependency Inversion**: Are business rules dependent on abstractions rather than concrete infrastructure implementations?
- [ ] **Error Handling**: Are errors categorized and mapped to clear domain errors rather than generic 500 exceptions?
- [ ] **Testability & Coverage**: Are business logic paths tested with comprehensive unit tests? Are edge cases (zero items, boundary limits) verified?
