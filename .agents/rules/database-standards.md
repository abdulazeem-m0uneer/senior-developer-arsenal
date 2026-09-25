# Relational Database Engineering Standards

These rules enforce strict data integrity, indexing strategies, query performance, and migration safety across **PostgreSQL** (primary), **SQLite**, and **MSSQL**.

---

## 1. PostgreSQL Core Standards (Primary Database)

### Data Types & Modeling
- **Timestamps**: Always use `TIMESTAMPTZ` (UTC). Never use `TIMESTAMP WITHOUT TIME ZONE`.
- **Primary Keys**: Prefer `BIGINT GENERATED ALWAYS AS IDENTITY` or `UUIDv7` (time-ordered UUID to preserve B-Tree locality and avoid index fragmentation).
- **Monetary / Financial**: Always use `NUMERIC(precision, scale)`. Never use `FLOAT` or `DOUBLE PRECISION` for currency calculations.
- **Semi-Structured Data**: Use `JSONB` instead of `JSON` for indexing, querying, and binary storage efficiency.

### Indexing Strategy
- **Composite Index Ordering**: Place equality columns first, followed by range/inequality and sort columns (`(tenant_id, status, created_at)`).
- **Partial / Filtered Indexes**: If querying a small subset of rows (e.g. `WHERE status = 'PENDING'`), create partial indexes:
  ```sql
  CREATE INDEX idx_orders_pending ON orders (created_at) WHERE status = 'PENDING';
  ```
- **GIN Indexes**: Use GIN indexes for JSONB containment (`@>`), full-text search (`tsvector`), or array elements.
- **Foreign Keys**: Always create an index on foreign key columns unless the child table is negligible in size. Missing FK indexes cause full table scans and lock escalation during cascading updates/deletes.

### Query Performance & Diagnostics
- Profile slow queries using `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)`.
- Watch for:
  - **Sequential Scans on large tables**: Missing or non-selective index.
  - **High Buffer Reads**: Query is hitting disk rather than shared buffers cache.
  - **External Sort / Disk Spill**: `work_mem` is exceeded by sorting or hash joins.
  - **Offset Pagination Bottlenecks**: Avoid `LIMIT 50 OFFSET 100000`. Use keyset / cursor pagination (`WHERE id > :last_seen_id ORDER BY id ASC LIMIT 50`).

### Zero-Downtime Migration Safety
- Never run blocking DDL in peak traffic without setting a short `lock_timeout` (e.g., `SET lock_timeout = '3s';`).
- Always create indexes concurrently: `CREATE INDEX CONCURRENTLY idx_name ON table_name (column);`.
- Use the **Expand and Contract** pattern for breaking column renames:
  1. Add new column (nullable or with default).
  2. Double-write in application code.
  3. Backfill data in small batches.
  4. Switch reads to new column.
  5. Drop old column.

---

## 2. SQLite Standards

When using SQLite (local development, testing, desktop apps, embedded services):
- **Enable WAL Mode**: Write-Ahead Logging allows concurrent readers alongside a writer:
  ```sql
  PRAGMA journal_mode = WAL;
  ```
- **Performance Pragmas**:
  ```sql
  PRAGMA synchronous = NORMAL;
  PRAGMA busy_timeout = 5000;
  PRAGMA foreign_keys = ON;
  PRAGMA cache_size = -64000; -- 64MB cache
  ```
- **Transactions for Bulk Operations**:
  - SQLite auto-commits every individual statement by default, causing severe disk fsync latency.
  - Always wrap multiple insert/update statements inside an explicit `BEGIN TRANSACTION ... COMMIT;` block.

---

## 3. MSSQL Standards

When developing or integrating with Microsoft SQL Server:
- **Concurrency & Locking**:
  - Recommend enabling `READ_COMMITTED_SNAPSHOT` (RCSI) at the database level to eliminate reader-writer blocking.
- **Sargability (Search Argument Ability)**:
  - Never wrap indexed columns in functions within `WHERE` or `JOIN` clauses.
  - ❌ `WHERE DATEPART(year, CreatedAt) = 2026`
  - ✅ `WHERE CreatedAt >= '2026-01-01' AND CreatedAt < '2027-01-01'`
- **Covering Indexes**:
  - Use `INCLUDE` columns on non-clustered indexes to avoid Key Lookups against the clustered index:
  ```sql
  CREATE NONCLUSTERED INDEX idx_users_email ON Users (Email) INCLUDE (FirstName, LastName, Status);
  ```
- **Transaction Scope**: Keep transactions as short as possible to avoid lock escalation to table locks.
