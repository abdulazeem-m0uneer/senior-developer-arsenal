# PostgreSQL Advanced Performance & Indexing Guide

Authoritative reference for tuning PostgreSQL schemas, queries, and connection pools.

---

## 1. Analyzing Execution Plans (`EXPLAIN ANALYZE`)

Always run with `BUFFERS` to see cache vs. disk I/O:
```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT o.id, o.total_amount, u.email
FROM orders o
JOIN users u ON u.id = o.user_id
WHERE o.status = 'COMPLETED'
  AND o.created_at >= '2026-01-01'
ORDER BY o.created_at DESC
LIMIT 50;
```

### Plan Red Flags:
1. **Seq Scan on Large Tables**: Missing index or predicate selectivity too low.
2. **Buffers: read > hit**: Query is suffering disk I/O bottlenecks. Increase `shared_buffers` or optimize index coverage.
3. **Sort Method: external merge Disk**: Sort spilled to disk. Consider increasing `work_mem` or creating an index matching the `ORDER BY` clause.
4. **Rows Removed by Filter**: The index was visited, but a secondary filter eliminated large numbers of rows. Create a composite index covering both columns.

---

## 2. PostgreSQL Index Taxonomy

### B-Tree Composite Indexing Rule:
Order columns as **Equality First -> Range -> Sort**:
```sql
-- Query: WHERE tenant_id = '...' AND created_at >= '...' ORDER BY created_at DESC
CREATE INDEX idx_tenant_created ON audit_logs (tenant_id, created_at DESC);
```

### Partial Indexes (Huge Space & Speed Win):
Only index rows that are actually queried:
```sql
-- Fast lookup for unprocessed queue items; ignores millions of processed rows
CREATE INDEX idx_jobs_pending ON background_jobs (priority DESC, created_at ASC)
WHERE status = 'PENDING';
```

### GIN Indexes for JSONB:
```sql
-- Query: WHERE attributes @> '{"tier": "enterprise"}'
CREATE INDEX idx_accounts_attributes ON accounts USING GIN (attributes jsonb_path_ops);
```

### BRIN Indexes for Append-Only Big Data:
For billion-row time-series or audit tables sorted on disk:
```sql
-- Takes ~1% of the space of a B-Tree index
CREATE INDEX idx_metrics_brin ON device_metrics USING BRIN (recorded_at);
```

---

## 3. High-Concurrency Queue Pattern (`SKIP LOCKED`)

To process jobs or orders across multiple worker nodes without race conditions or deadlocks:
```sql
WITH next_job AS (
  SELECT id
  FROM background_jobs
  WHERE status = 'PENDING'
  ORDER BY priority DESC, created_at ASC
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
UPDATE background_jobs
SET status = 'PROCESSING', started_at = NOW()
WHERE id = (SELECT id FROM next_job)
RETURNING *;
```

---

## 4. Zero-Downtime Migration Checklist

1. **Creating Indexes**: Always use `CONCURRENTLY`:
   ```sql
   CREATE INDEX CONCURRENTLY idx_users_phone ON users (phone_number);
   ```
2. **Adding Columns**:
   - In PostgreSQL 11+, `ADD COLUMN col TEXT DEFAULT 'val'` is instant (metadata only).
   - If adding a NOT NULL column without a default, add as nullable first, populate in chunks, then add the constraint.
3. **Setting Safe Lock Timeouts**:
   ```sql
   SET lock_timeout = '2s';
   ALTER TABLE orders ADD COLUMN external_reference VARCHAR(64);
   ```
