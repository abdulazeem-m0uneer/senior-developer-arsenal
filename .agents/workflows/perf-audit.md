---
name: perf-audit
description: Performance auditing workflow to detect database query bottlenecks, event loop lag, memory leaks, and thread pool starvation.
---

# Performance Audit Workflow

Use this workflow to conduct a systematic performance and scalability audit on an existing codebase.

## Steps

1. **Database Hotspot Profiling**:
   - Inspect all SQL queries and ORM repository operations.
   - Look for:
     - Missing indexes on `WHERE`, `JOIN`, and `ORDER BY` columns.
     - Unindexed foreign keys causing table scans on delete/update cascades.
     - Inefficient pagination using large `OFFSET`.
     - In C#: Verify read queries use `.AsNoTracking()` and split queries where applicable.
     - In PostgreSQL: Run `EXPLAIN (ANALYZE, BUFFERS)` on slow queries.

2. **Concurrency & Thread Pool / Event Loop Inspection**:
   - **C# / .NET**:
     - Search codebase for `.Result`, `.Wait()`, `.GetAwaiter().GetResult()`.
     - Check for `HttpClient` instantiation without factory.
     - Verify asynchronous lock usage (`SemaphoreSlim`).
   - **Node.js**:
     - Search for synchronous operations (`fs.*Sync`, `crypto.*Sync`).
     - Check regex patterns for catastrophic backtracking (ReDoS).
     - Check memory allocations in loops and verify streams with backpressure are used for large I/O.

3. **Resource Leak Detection**:
   - Check disposal of database connections, streams, HTTP responses, and timers.
   - Verify that caches have maximum size constraints and TTL eviction policies.

4. **Action Plan & Remediation**:
   - Rank findings by ROI (impact vs effort).
   - Produce benchmarks or profiling recommendations to validate fixes under load.
