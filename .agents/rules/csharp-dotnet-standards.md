# C# & .NET Senior Engineering Standards

These rules enforce idiomatic, high-performance, and secure development for .NET 8 / .NET 9 and modern C# (12/13).

---

## 1. Modern C# Language Idioms

- **Nullable Reference Types**: `<Nullable>enable</Nullable>` must be active. Eliminate null warning suppressions (`!`) unless backed by an explicit invariant or assertion.
- **Immutability First**:
  - Use `record` or `readonly record struct` for DTOs, messages, and domain events.
  - Use `init`-only properties for immutable objects.
- **Pattern Matching**: Prefer switch expressions, property patterns, and relational patterns over nested `if/else` ladders.
- **Primary Constructors**: Use primary constructors for dependency injection in classes and service declarations when clarity is enhanced.
- **Clean Architecture Layers**:
  - `Domain`: Pure business entities, value objects, domain logic. No external dependencies.
  - `Application`: Use-cases, CQRS handlers (MediatR/dispatchers), DTOs, interfaces.
  - `Infrastructure`: EF Core DbContext, Dapper repositories, external API clients, message bus adapters.
  - `Api / Presentation`: Controllers or Minimal APIs, middleware, authentication, request validation.

---

## 2. Asynchronous Programming & Concurrency

- **Avoid Sync-over-Async**: Never call `.Result`, `.Wait()`, or `.GetAwaiter().GetResult()` on tasks. This causes thread pool starvation and deadlocks.
- **Propagate `CancellationToken`**:
  - Accept a `CancellationToken ct = default` in every async method that performs I/O.
  - Forward the cancellation token to all database, HTTP, and disk calls.
- **`ValueTask` Usage**:
  - Use `ValueTask` / `ValueTask<T>` for high-throughput methods where the result is often available synchronously (e.g. cache hits, validation checks).
  - Never await a `ValueTask` multiple times or call `.AsTask()` unnecessarily.
- **Rate-Limiting & Throttling**:
  - Use `SemaphoreSlim` instead of `lock` for asynchronous synchronization.
  - Always release semaphores in a `finally` block.

---

## 3. Data Access: EF Core vs. Dapper

### EF Core Standards
- **Read-Only Queries**: Always append `.AsNoTracking()` or configure tracking behavior per-query.
- **Selective Projections**: Never load entire entities if only a subset of fields is needed. Project using `.Select(x => new DTO { ... })` to generate lean SQL queries.
- **Cartesian Product Mitigation**: When including multiple 1-to-many navigation properties, use `.AsSplitQuery()` to prevent exponential row explosion.
- **Avoiding N+1**:
  - Never trigger navigation properties in a loop.
  - Use explicit eager loading (`.Include()`) or batched projections.
- **Safe SQL Execution**: Always use `FromSqlInterpolated` or `FromSql` with parameters. Never use string concatenation with raw SQL.

### Dapper Standards
- Use Dapper for high-throughput reads, complex multi-table analytical queries, or bulk operations where EF Core overhead is unacceptable.
- Always use anonymous objects or `DynamicParameters` for parameterized values.
- Explicitly open, execute, and dispose `IDbConnection` instances (preferably with `await using`).

---

## 4. ASP.NET Core & API Design

- **Error Handling**:
  - Implement `IExceptionHandler` (.NET 8+) or custom middleware returning RFC 7807 `ProblemDetails`.
  - Never leak exception stack traces, connection strings, or internal infrastructure details to the client in production.
- **Validation**:
  - Use `FluentValidation` validators auto-registered in the service container.
  - Validate before handler execution. Return 400 Bad Request with standardized error breakdowns.
- **Dependency Injection**:
  - Understand lifetimes: `Transient` (lightweight, stateless), `Scoped` (per HTTP request, required for `DbContext`), `Singleton` (application-wide, thread-safe).
  - Never inject a `Scoped` service (like `DbContext`) into a `Singleton` service without an explicit `IServiceScopeFactory`.
- **HttpClient**:
  - Use `IHttpClientFactory` or typed HTTP clients. Never instantiate `new HttpClient()` per request (avoids socket exhaustion).
