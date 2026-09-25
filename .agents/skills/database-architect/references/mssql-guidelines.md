# Microsoft SQL Server Architecture & Performance Guide

Guidelines for schema design, T-SQL optimization, and index strategies in MSSQL.

---

## 1. Concurrency with Snapshot Isolation

In high-concurrency read-heavy workloads, default `READ COMMITTED` causes readers to block writers and writers to block readers.
Recommend enabling **RCSI (Read Committed Snapshot Isolation)**:
```sql
ALTER DATABASE [YourDbName]
SET READ_COMMITTED_SNAPSHOT ON
WITH ROLLBACK IMMEDIATE;
```

---

## 2. Covering Indexes with `INCLUDE`

Avoid expensive Key Lookups against the clustered index by including non-key payload columns:
```sql
-- Query: SELECT Id, FirstName, LastName, Balance FROM Customers WHERE Email = @Email
CREATE NONCLUSTERED INDEX idx_customers_email
ON dbo.Customers (Email)
INCLUDE (FirstName, LastName, Balance);
```

---

## 3. Sargability (Search Argument Ability)

Never apply scalar functions to columns inside the `WHERE` clause:
```sql
-- ❌ BAD: Forces a full index scan or table scan
SELECT OrderId, Total
FROM dbo.Orders
WHERE DATEDIFF(day, OrderDate, GETDATE()) <= 7;

-- ✅ GOOD: Allows index seek
SELECT OrderId, Total
FROM dbo.Orders
WHERE OrderDate >= DATEADD(day, -7, CAST(GETDATE() AS DATE));
```

---

## 4. Parameter Sniffing Mitigation

If a stored procedure has wildly variable execution plans depending on parameter values:
- Use `OPTION (RECOMPILE)` for infrequently called, complex analytical queries.
- Use `OPTIMIZE FOR (@Param = ...)` or copy parameters into local variables inside the stored procedure body.
