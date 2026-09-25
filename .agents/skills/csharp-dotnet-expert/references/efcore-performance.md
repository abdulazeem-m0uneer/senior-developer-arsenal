# Entity Framework Core & Dapper Performance Guide

A comprehensive senior engineering reference for optimizing .NET data access pipelines.

---

## 1. EF Core Query Optimization Patterns

### Pattern 1: No-Tracking Queries for Reads
Always disable change tracking for read-only queries. Tracking adds substantial memory overhead and snapshot comparisons:
```csharp
// ❌ Bad: Changes tracked unnecessarily
var users = await dbContext.Users.Where(u => u.IsActive).ToListAsync(ct);

// ✅ Good: No change tracker overhead
var users = await dbContext.Users.AsNoTracking().Where(u => u.IsActive).ToListAsync(ct);
```

### Pattern 2: Selective Projections (Avoid `SELECT *`)
```csharp
// ❌ Bad: Fetches all columns including large blobs or text fields
var orders = await dbContext.Orders.AsNoTracking().Where(o => o.CustomerId == customerId).ToListAsync(ct);

// ✅ Good: Generates lean SQL selecting only required fields
var orders = await dbContext.Orders
    .AsNoTracking()
    .Where(o => o.CustomerId == customerId)
    .Select(o => new OrderSummaryDto(o.Id, o.OrderNumber, o.TotalAmount, o.CreatedAt))
    .ToListAsync(ct);
```

### Pattern 3: Cartesian Explosion & Query Splitting
When joining multiple collection navigations, EF Core generates massive Cartesian duplicate rows.
```csharp
// ✅ Good: Executes separate queries per collection and stitches in memory
var customer = await dbContext.Customers
    .AsNoTracking()
    .AsSplitQuery()
    .Include(c => c.Orders)
    .Include(c => c.Invoices)
    .FirstOrDefaultAsync(c => c.Id == customerId, ct);
```

### Pattern 4: Batched Updates & Deletes (.NET 7+)
Avoid loading entities into memory just to modify or delete them:
```csharp
// ✅ Good: Generates a single SQL UPDATE statement without tracking
await dbContext.Orders
    .Where(o => o.Status == OrderStatus.Expired)
    .ExecuteUpdateAsync(s => s.SetProperty(o => o.Status, OrderStatus.Cancelled), ct);

// ✅ Good: Generates a single SQL DELETE statement
await dbContext.AuditLogs
    .Where(l => l.Timestamp < cutoffDate)
    .ExecuteDeleteAsync(ct);
```

---

## 2. When to Use Dapper

Use **Dapper** when:
1. Executing complex analytical queries with window functions (`ROW_NUMBER() OVER (...)`).
2. Requiring microsecond-level serialization performance for high-frequency endpoints.
3. Writing complex bulk-upsert operations using database-specific syntax (e.g., PostgreSQL `ON CONFLICT DO UPDATE`).

### Dapper Best Practice Example:
```csharp
public async Task<IReadOnlyList<UserDashboardDto>> GetDashboardUsersAsync(Guid tenantId, CancellationToken ct)
{
    const string sql = """
        SELECT u.id, u.email, u.full_name, COUNT(o.id) AS total_orders
        FROM users u
        LEFT JOIN orders o ON o.user_id = u.id
        WHERE u.tenant_id = @TenantId
        GROUP BY u.id, u.email, u.full_name
        ORDER BY total_orders DESC
        LIMIT 50;
        """;

    var command = new CommandDefinition(sql, new { TenantId = tenantId }, cancellationToken: ct);
    await using var connection = await dbConnectionFactory.CreateConnectionAsync(ct);
    var results = await connection.QueryAsync<UserDashboardDto>(command);
    return results.AsList();
}
```
