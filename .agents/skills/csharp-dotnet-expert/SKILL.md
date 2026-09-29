---
name: csharp-dotnet-expert
description: Specialized C# and .NET engineering skill. Use when designing, building, refactoring, or optimizing ASP.NET Core APIs, Entity Framework Core, Dapper data layers, Clean Architecture solutions, or concurrent .NET code. Triggers on: "C#", ".NET", "ASP.NET Core", "EF Core", "Dapper", "Clean Architecture", "async deadlocks". Do not use for Python services (use python-backend-expert) or Node.js services (use nodejs-backend-expert).
---

# C# & .NET Engineering Skill

This skill guides the agent in building enterprise-grade, high-throughput .NET 8 / .NET 9 applications adhering to Clean Architecture principles.

---

## 1. When to Use This Skill

Activate this skill when:
- Authoring or refactoring ASP.NET Core Web APIs or Minimal APIs.
- Designing data access layers with Entity Framework Core or Dapper.
- Troubleshooting async deadlocks, thread pool starvation, or memory allocations.
- Structuring Clean Architecture / Domain-Driven Design (DDD) projects.
- Writing integration tests using `WebApplicationFactory` and Testcontainers.

*Boundary*: For Node.js/TypeScript services, use `nodejs-backend-expert`. For Python services, use `python-backend-expert`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Clean Architecture Project Organization
Follow this standard project separation:
```text
src/
├── Domain/               # Entities, Value Objects, Domain Exceptions, Repository Interfaces
├── Application/          # Commands, Queries, DTOs, FluentValidation, MediatR/Dispatchers
├── Infrastructure/       # EF Core DbContext, Dapper Repositories, Redis, External APIs
└── WebApi/               # Controllers / Minimal APIs, Middleware, Program.cs, AppSettings
```

### Step 2: High-Performance EF Core & Dapper
Consult: [EF Core & Dapper Performance Guide](./references/efcore-performance.md)
- Ensure `.AsNoTracking()` is used on read queries.
- Project directly to DTOs via `.Select()` to avoid pulling unused columns.
- Use `.AsSplitQuery()` when fetching 1-to-many child collections to prevent Cartesian explosion.
- For bulk operations and high-speed reporting, implement Dapper queries with parameterized inputs.

### Step 3: Concurrency & Async Mastery
Consult: [Async & Concurrency Best Practices](./references/dotnet-async-best-practices.md)
- Ensure `CancellationToken` is propagated to every asynchronous call.
- Eliminate all sync-over-async calls (`.Result`, `.Wait()`).
- Use `ValueTask<T>` on frequently cached synchronous code paths.
- Guard concurrent shared resources using `SemaphoreSlim(1, 1)` with `try/finally`.

---

## 3. Verification Protocol

Verify the solution using the .NET CLI:
```powershell
# 1. Restore & build with warnings as errors
dotnet build --configuration Release /p:TreatWarningsAsErrors=true

# 2. Run unit and integration tests
dotnet test --logger "console;verbosity=minimal"
```
Report status in a single line: `✅ Build & Tests Passed`. If errors occur, apply **Rule 0** and report raw compiler error.

---

## 4. ⚡ Token-Saving Execution Rule

- **Targeted Code Only**: Generate only the modified C# method, class, or LINQ expression. Do not output unchanged files or redundant boilerplate.
- **Terse CLI Reporting**: Print output lines only if compilation or test failures occur.
