# Antigravity Subagents for Senior Engineers

This directory contains definitions and specialized prompts for domain-focused subagents.

---

## Available Subagents

1. **`code-reviewer`** (`prompts/code-reviewer.md`):
   - **Role**: Senior Staff Code Reviewer.
   - **Focus**: Exhaustive multi-pass code reviews (Security, Performance, Layering, Edge Cases, Test Coverage).
2. **`db-architect`** (`prompts/db-architect.md`):
   - **Role**: Senior Database Architect & Query Optimizer.
   - **Focus**: PostgreSQL (primary), SQLite, MSSQL schemas, EXPLAIN ANALYZE profiling, indexing (B-Tree, GIN, BRIN), non-blocking migrations.
3. **`dotnet-specialist`** (`prompts/dotnet-specialist.md`):
   - **Role**: Principal .NET & C# Engineer.
   - **Focus**: .NET 8/9, ASP.NET Core, EF Core tuning (`AsNoTracking`, split queries), Dapper, async/cancellation, memory allocation.
4. **`node-specialist`** (`prompts/node-specialist.md`):
   - **Role**: Principal Node.js & TypeScript Engineer.
   - **Focus**: Non-blocking event loop, streams/backpressure, worker threads, Fastify/Express/NestJS, Zod validation.
5. **`security-auditor`** (`prompts/security-auditor.md`):
   - **Role**: Application Security Auditor.
   - **Focus**: OWASP Top 10, SQLi, BOLA/IDOR, prototype pollution, secrets detection.

---

## How to Invoke in Antigravity

Antigravity provides two built-in tools for subagents:
- `define_subagent`: Registers a customized subagent with its system prompt and tool capabilities.
- `invoke_subagent`: Launches the subagent in an isolated context and receives its results automatically.

You can also prompt the primary agent directly:
> *"Invoke the code-reviewer subagent to audit the changes between main and this branch."*
> *"Launch the db-architect subagent to inspect this query and suggest PostgreSQL indexes."*
