# Backend Performance & Profiling Reference

Diagnostic guide for detecting latency hotspots, query bottlenecks, and resource starvation across .NET, Node.js, and databases.

---

## 1. Database Hotspot Patterns

- **Missing Indexes on Filters**: Columns in `WHERE`, `JOIN`, and `ORDER BY` clauses causing Sequential Scans.
- **Unindexed Foreign Keys**: Deleting parent records acquires table locks or triggers full table scans on child tables.
- **Naive Large Offset Pagination**: `OFFSET 100000 LIMIT 20` scans 100,020 rows; convert to keyset/cursor pagination.
- **PostgreSQL Diagnostics**: Run `EXPLAIN (ANALYZE, BUFFERS)` to check Shared Hit Blocks vs Read Blocks.

---

## 2. Event Loop & Concurrency Starvation

- **Node.js**:
  - Synchronous FS/Crypto calls (`fs.readFileSync`, `crypto.pbkdf2Sync`) blocking the single thread.
  - Catastrophic regex backtracking (ReDoS) freezing event loop iterations.
- **.NET / C#**:
  - Sync-over-async (`.Result`, `.Wait()`) exhausting the CLR ThreadPool.
  - Creating `HttpClient` instances per request leading to socket exhaustion; mandate `IHttpClientFactory`.
- **Resource Cleanup**:
  - Unclosed database connections or missing `using` declarations causing pool exhaustion.
