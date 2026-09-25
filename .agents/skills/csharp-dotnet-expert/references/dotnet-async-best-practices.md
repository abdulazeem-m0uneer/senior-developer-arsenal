# C# Asynchronous Programming & Concurrency Best Practices

Guidelines for high-throughput asynchronous execution without deadlocks or thread pool exhaustion.

---

## 1. Avoid Sync-over-Async Antipatterns

Never block an asynchronous task:
```csharp
// ❌ WRONG: Can cause thread pool starvation and deadlocks in ASP.NET Core
var user = GetUserAsync(id).Result;
var token = GenerateTokenAsync().GetAwaiter().GetResult();
SaveAsync().Wait();

// ✅ CORRECT: Fully asynchronous call chain
var user = await GetUserAsync(id, ct);
var token = await GenerateTokenAsync(ct);
await SaveAsync(ct);
```

---

## 2. Cancellation Token Flow

Every asynchronous method should accept and propagate `CancellationToken`:
```csharp
public async Task<OrderResponse> ProcessOrderAsync(CreateOrderCommand cmd, CancellationToken ct = default)
{
    // Check cancellation early if preceding steps took time
    ct.ThrowIfCancellationRequested();

    var inventoryOk = await inventoryService.CheckStockAsync(cmd.Items, ct);
    if (!inventoryOk) throw new OutOfStockException();

    var paymentResult = await paymentGateway.ChargeAsync(cmd.PaymentInfo, ct);
    await orderRepository.SaveAsync(cmd.ToEntity(paymentResult), ct);

    return new OrderResponse(paymentResult.TransactionId);
}
```

---

## 3. ValueTask vs Task

Use `ValueTask<T>` when:
1. The method completes synchronously in the majority of calls (e.g., read from in-memory cache, short-circuit validation).
2. The method is called on high-frequency hot paths where GC allocations from heap-allocated `Task<T>` instances matter.

```csharp
public ValueTask<CachedUser?> GetUserAsync(string id, CancellationToken ct = default)
{
    if (memoryCache.TryGetValue(id, out CachedUser? user))
    {
        return ValueTask.FromResult(user);
    }

    return FetchFromDatabaseAsync(id, ct);

    async ValueTask<CachedUser?> FetchFromDatabaseAsync(string userId, CancellationToken token)
    {
        var dbUser = await dbContext.Users.FindAsync(new object[] { userId }, token);
        if (dbUser != null)
        {
            memoryCache.Set(userId, dbUser, TimeSpan.FromMinutes(10));
        }
        return dbUser;
    }
}
```

---

## 4. Asynchronous Synchronization with `SemaphoreSlim`

Never use the `lock` statement with `await`. Use `SemaphoreSlim`:
```csharp
private readonly SemaphoreSlim _gate = new(initialCount: 1, maxCount: 1);

public async Task PerformExclusiveOperationAsync(CancellationToken ct)
{
    await _gate.WaitAsync(ct);
    try
    {
        await CriticalSectionAsync(ct);
    }
    finally
    {
        _gate.Release();
    }
}
```
