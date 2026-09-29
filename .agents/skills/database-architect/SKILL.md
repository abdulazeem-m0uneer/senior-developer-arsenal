---
name: database-architect
description: Comprehensive relational database architecture, query optimization, indexing, and migration skill. Use when the user asks to design schemas, optimize slow queries with EXPLAIN ANALYZE, build index strategies, or plan non-blocking migrations in PostgreSQL, SQLite, or MSSQL. Triggers on: "database architecture", "EXPLAIN ANALYZE", "index strategy", "slow query", "PostgreSQL", "MSSQL", "SQLite WAL". Do not use for application API routes (use api-design).
---

# Database Architecture & Query Optimization Skill

This skill guides the agent through high-performance schema design, index strategy, query plan optimization, and safe database operations across PostgreSQL, MSSQL, and SQLite.

---

## 1. When to Use This Skill

Activate this skill when:
- Designing or reviewing database schemas, relationships, constraints, and data types.
- Diagnosing slow queries or inspecting execution plans (`EXPLAIN ANALYZE`).
- Formulating index strategies (B-Tree, GIN, BRIN, Partial/Filtered, Covering).
- Planning safe, non-blocking zero-downtime schema migrations.
- Tuning connection pooling (PgBouncer, Npgsql, node-postgres) and transaction isolation levels.

*Boundary*: For application API endpoints and route design, use `api-design`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: PostgreSQL Tuning (Primary Database)
Consult: [PostgreSQL Tuning & Indexing Guide](./references/postgres-tuning.md)
1. **Profile Queries**: Run `EXPLAIN (ANALYZE, BUFFERS, SETTINGS) <sql>` to check row estimates, buffer hits/reads, and sequential scans.
2. **Indexing Selection**:
   - Standard lookups & range filters: **B-Tree** (composite ordering: equality first, then range/sort).
   - Filtered subsets: **Partial Index** (`WHERE status = 'ACTIVE'`).
   - JSONB / full-text / array containment: **GIN Index**.
   - Massive append-only logs / timeseries: **BRIN Index**.
3. **Non-Blocking Execution**:
   - Always run `CREATE INDEX CONCURRENTLY`.
   - Set `SET lock_timeout = '3s';` before any schema changes to prevent cascading queue locks.

### Step 2: Microsoft SQL Server Tuning
Consult: [MSSQL Architecture & Performance Guide](./references/mssql-guidelines.md)
1. **Clustered Index Selection**: Ensure clustered keys are narrow, unique, and monotonically increasing.
2. **Covering Indexes**: Eliminate Key Lookups using `INCLUDE (col1, col2)`.
3. **Concurrency**: Enable `READ_COMMITTED_SNAPSHOT` (RCSI) to avoid read locks blocking write locks.

### Step 3: SQLite Production Tuning
Consult: [SQLite Production Tuning Guide](./references/sqlite-production.md)
1. **WAL Mode**: Always execute `PRAGMA journal_mode = WAL;`.
2. **Batch Transactions**: Wrap multiple inserts inside explicit transactions.
3. **Timeouts**: Set `PRAGMA busy_timeout = 5000;` to prevent `database is locked` errors during concurrent access.

---

## 3. Verification Protocol

1. Run `EXPLAIN (ANALYZE, BUFFERS)` on the optimized query.
2. Verify that Sequential Scans on large tables are replaced with Index Scans or Index Only Scans.
3. Confirm Shared Read Blocks are drastically reduced and buffer hit ratio is $\ge 99\%$.

---

## 4. ⚡ Token-Saving Execution Rule

- **Direct DDL/DML**: Output only the necessary SQL statements and indexes. Omit conversational explanations of obvious SQL syntax.
- **Execution Plan Distillation**: Extract only critical plan metrics (Node type, Total cost, Actual time, Buffers hit/read). Never paste 200 lines of raw text execution plans unless requested.
