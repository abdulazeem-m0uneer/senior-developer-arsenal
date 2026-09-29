---
name: database-migration
description: Safe, non-blocking database migration design and verification workflow for PostgreSQL, SQLite, and MSSQL.
---

# Database Migration Workflow

Use this workflow to author, audit, and execute database migrations with zero downtime.

## Steps

1. **Schema & Intent Analysis**:
   - Identify the database engine in use (PostgreSQL, SQLite, or MSSQL).
   - Clarify the data model changes: new tables, column additions, type modifications, or index changes.

2. **Pre-Migration Safety Audit**:
   - **PostgreSQL**:
     - Are indexes created with `CREATE INDEX CONCURRENTLY`?
     - Are table locks avoided? Is `SET lock_timeout = '2s';` declared?
     - Are timestamps using `TIMESTAMPTZ`?
     - Are primary keys `BIGINT IDENTITY` or `UUIDv7`?
   - **SQLite**:
     - Are changes wrapped in `BEGIN TRANSACTION ... COMMIT`?
     - Are foreign key constraints preserved during table recreations?
   - **MSSQL**:
     - Are non-clustered indexes using `INCLUDE` to eliminate key lookups?
     - Are operations batched to prevent transaction log bloat?

3. **Draft Up and Down (Rollback) Scripts**:
   - Always produce both the `Up` migration and an exact, verified `Down` rollback script.
   - For column renames, use the Expand and Contract pattern (do not rename columns in-place on high-traffic production databases).

4. **Verification & Dry Run**:
   - Apply the migration in a test or local database container.
   - Run sample queries against the migrated schema using `EXPLAIN ANALYZE`.
   - Test the rollback script to verify complete reversion without orphan constraints.
