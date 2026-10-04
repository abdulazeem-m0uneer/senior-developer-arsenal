---
name: database-migration
description: 'Safe, non-blocking database migration design and verification workflow for PostgreSQL, SQLite, and MSSQL. Use when the user asks to create migrations, alter tables, add indexes, or runs /database-migration. Triggers on: "database migration", "schema migration", "alter table", "add column", "/database-migration". Do not use for query plan profiling or indexing strategy (use database-architect).'
---

# Safe Database Migration Procedure

Follow this procedure when creating, verifying, or rolling back schema migrations in production databases.

---

## 1. When to Use This Skill

Activate this skill when:
- Authoring EF Core migrations, Flyway/Liquibase scripts, or raw SQL DDL files.
- Adding non-blocking indexes (`CREATE INDEX CONCURRENTLY`), columns, or constraints on high-throughput tables.
- Preparing zero-downtime database deployment scripts with rollback companions.
- The user runs the `/database-migration` slash command.

*Boundary*: For query execution plan analysis (`EXPLAIN ANALYZE`) or deep indexing architecture, use `database-architect`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Pre-Migration Lock & Safety Assessment
Consult: [Migration Safety Reference](./references/migration-safety.md)
1. Identify target table size and read/write throughput.
2. Check lock level required: Avoid table-rewriting operations during peak load.
3. Enforce statement lock timeout: `SET lock_timeout = '3s';`.

### Step 2: Non-Blocking DDL Authoring
1. Indexes: Use `CREATE INDEX CONCURRENTLY` in PostgreSQL (outside transaction block).
2. Foreign Keys: Add with `NOT VALID`, then validate in a second step via `VALIDATE CONSTRAINT`.
3. Column Renames: Use expand/contract pattern (add new column $\to$ dual-write $\to$ backfill $\to$ drop old) rather than renaming active columns.

### Step 3: Author Companion Rollback Script
Ensure every migration script has an accompanying idempotent rollback file (`U{timestamp}__rollback.sql` or EF Core `Down()` method).

---

## 3. Verification Protocol

1. Run migration against a local/staging database instance.
2. Verify table locks were not held: assert duration $< 500$ms for metadata alterations.
3. Execute the rollback script and verify schema returns cleanly to initial state without orphaned constraints.

---

## 4. ⚡ Token-Saving Execution Rule

- Output only the specific SQL DDL script or EF Core migration code snippet.
- Never output full database schemas or unchanged model snapshots.
