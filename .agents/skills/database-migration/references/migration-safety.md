# Non-Blocking Database Migration Safety Reference

Checklists and rules for zero-downtime database migrations across PostgreSQL, MSSQL, and SQLite.

---

## 1. PostgreSQL Safe DDL Rules

### A. Lock Timeouts (Mandatory)
Always set a tight lock timeout before acquiring an Exclusive lock to avoid queuing behind long read queries:
```sql
SET lock_timeout = '3s';
```

### B. Index Creation
- **Never**: `CREATE INDEX idx_name ON table(col);` (Locks table against writes).
- **Always**: `CREATE INDEX CONCURRENTLY idx_name ON table(col);` (Cannot run inside a multi-statement transaction).

### C. Adding Columns with Defaults
- **Postgres 11+**: `ALTER TABLE orders ADD COLUMN status text NOT NULL DEFAULT 'pending';` is safe (metadata-only update).
- **Volatile Defaults**: `DEFAULT clock_timestamp()` or non-immutable expressions still require a table rewrite; backfill in batches instead.

### D. Adding Foreign Keys
1. Add constraint as `NOT VALID` (only acquires quick ShareRowExclusiveLock, validates new rows only):
   ```sql
   ALTER TABLE orders ADD CONSTRAINT fk_orders_customer
     FOREIGN KEY (customer_id) REFERENCES customers(id) NOT VALID;
   ```
2. Validate constraint concurrently without table locks:
   ```sql
   ALTER TABLE orders VALIDATE CONSTRAINT fk_orders_customer;
   ```

---

## 2. Rollback Companion Script

Every migration `V{timestamp}__name.sql` must have a tested companion rollback script `U{timestamp}__name.sql`.
- Drop added columns or constraints.
- Drop concurrently added indexes (`DROP INDEX CONCURRENTLY IF EXISTS`).
