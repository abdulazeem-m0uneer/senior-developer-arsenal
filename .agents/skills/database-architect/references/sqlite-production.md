# SQLite Production Tuning & Reliability Guide

Configuration rules for running SQLite reliably in production, embedded services, desktop apps, or integration test environments.

---

## 1. Mandatory Production Pragmas

Execute these pragmas immediately upon opening every SQLite connection:

```sql
-- 1. Enable Write-Ahead Logging (Allows concurrent readers while a write occurs)
PRAGMA journal_mode = WAL;

-- 2. Synchronous mode: NORMAL gives huge performance speedup with full durability in WAL mode
PRAGMA synchronous = NORMAL;

-- 3. Busy timeout: Wait up to 5000ms for locks to clear instead of throwing 'database is locked'
PRAGMA busy_timeout = 5000;

-- 4. Enforce relational foreign key constraints (OFF by default in SQLite!)
PRAGMA foreign_keys = ON;

-- 5. Allocate 64MB of in-memory page cache (negative number indicates kibibytes)
PRAGMA cache_size = -64000;

-- 6. Store temporary tables and indexes in memory
PRAGMA temp_store = MEMORY;
```

---

## 2. Bulk Insert Performance

Without explicit transactions, SQLite performs an `fsync` for each individual `INSERT` statement (limiting throughput to ~50-100 writes/sec):

```sql
-- Wrap bulk operations in a transaction (yields 50,000+ writes/sec)
BEGIN TRANSACTION;
INSERT INTO telemetry (sensor_id, value, recorded_at) VALUES ('A1', 42.1, 1727250000);
INSERT INTO telemetry (sensor_id, value, recorded_at) VALUES ('A2', 43.4, 1727250001);
-- ... thousands of rows ...
COMMIT;
```

---

## 3. Concurrency Model & WAL Checkpointing

- **Single Writer, Multiple Readers**: WAL mode supports unlimited simultaneous readers alongside one active writer.
- **Connection Sharing**: Keep one shared connection or a single-writer connection pool with multiple reader connections.
- **Checkpointing**: In long-running background processes, run `PRAGMA wal_checkpoint(TRUNCATE);` during idle windows to prevent the `-wal` file from growing excessively.
