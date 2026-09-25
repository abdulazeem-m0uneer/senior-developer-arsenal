# 🚀 Senior Developer Arsenal

An enterprise-grade, polyglot Antigravity AI engineering toolkit tailored specifically for **Senior Software Engineers** working with **Node.js / TypeScript**, **C# / .NET**, **PostgreSQL**, **MSSQL**, **SQLite**, and **Git**.

Designed to be version-controlled as a reusable Git repository and deployed across all your projects or activated globally on your workstation.

---

## 🎯 What This Toolkit Provides

| Component | Quantity | Purpose |
| :--- | :---: | :--- |
| **Workspace & Global Rules** | 6 | Enforce senior-level code quality, security, async discipline, DB safety, and git hygiene. |
| **Specialized Skills** | 6 | Runbooks and checklists for reviews, query tuning, architecture design, and framework deep-dives. |
| **Specialized Subagents** | 5 | Dedicated agent personas (`code-reviewer`, `db-architect`, `dotnet-specialist`, `node-specialist`, `security-auditor`). |
| **Production Workflows** | 5 | Ready-to-run workflows for reviews, safe migrations, API design, performance audits, and release cuts. |
| **Multi-Project Installers** | 2 | Automated PowerShell (`install.ps1`) and Bash (`install.sh`) scripts for 1-click global or per-project setup. |

---

## 📁 Repository Structure

```text
senior-developer-arsenal/
├── .agents/
│   ├── rules/                              # Behavioral guidelines & constraints
│   │   ├── senior-engineer-core.md         # Architecture, clean code, code review principles
│   │   ├── csharp-dotnet-standards.md      # .NET 8/9, EF Core, Dapper, async/await, Result pattern
│   │   ├── nodejs-standards.md             # TS Strict, non-blocking event loop, streams, security
│   │   ├── database-standards.md           # PostgreSQL (primary), MSSQL, SQLite optimization & safety
│   │   └── git-standards.md                # Conventional Commits, atomic commits, rebase workflows
│   ├── skills/                             # Actionable on-demand skills
│   │   ├── senior-code-review/             # Deep multi-pass code reviews with checklists and rubrics
│   │   ├── csharp-dotnet-expert/           # C# / .NET 8/9, EF Core performance, Dapper, async pipelines
│   │   ├── nodejs-backend-expert/          # Fastify/Express/NestJS, event loop latency, streams, security
│   │   ├── database-architect/             # EXPLAIN ANALYZE, indexing (B-Tree, GIN, BRIN), non-blocking DDL
│   │   ├── git-workflow-master/            # Interactive rebase, conflict resolution, SemVer release tags
│   │   └── architecture-design-adr/        # Architecture Decision Records (ADRs) & trade-off frameworks
│   ├── subagents/                          # Subagent configuration profiles & prompts
│   │   ├── subagent-definitions.json       # Declarative JSON manifest for subagent registration
│   │   ├── README.md                       # Subagent delegation documentation
│   │   └── prompts/
│   │       ├── code-reviewer.md            # Senior Staff Code Reviewer persona
│   │       ├── db-architect.md             # Database Architect & Query Tuning persona
│   │       ├── dotnet-specialist.md        # Principal .NET & C# Systems persona
│   │       ├── node-specialist.md          # Principal Node.js & TypeScript Systems persona
│   │       └── security-auditor.md         # Application Security Auditor persona
│   └── workflows/                          # Standardized workflow runbooks
│       ├── code-review.md                  # /code-review workflow
│       ├── database-migration.md           # /database-migration workflow
│       ├── api-design.md                   # /api-design workflow
│       ├── perf-audit.md                   # /perf-audit workflow
│       └── git-release.md                  # /git-release workflow
├── AGENTS.md                               # Root agent configuration file
├── GEMINI.md                               # Workspace rules marker
├── install.ps1                             # PowerShell installer for Windows
├── install.sh                              # Bash installer for Linux/WSL/macOS
├── .gitignore                              # Git exclusion rules
└── README.md                               # Comprehensive documentation
```

---

## 🛠️ How to Use in Every Project

You have two powerful options to use this toolkit:

### Option A: Global Installation (Recommended)
Install once into your user profile so **every project** opened in Antigravity automatically inherits these skills and rules:

```powershell
# In PowerShell:
cd C:\Users\Abdulazeem\Desktop\senior-developer-arsenal
.\install.ps1 -Global
```
*This installs the skills into `~/.gemini/config/skills/` and rules into `~/.gemini/config/rules/`.*

---

### Option B: Per-Project Installation
Inject or symlink the `.agents/` directory directly into a target repository:

```powershell
# Copy into an existing project:
.\install.ps1 -Project "C:\Users\Abdulazeem\repos\my-api"

# Or create a symbolic link (changes in arsenal automatically reflect in project):
.\install.ps1 -Project "C:\Users\Abdulazeem\repos\my-api" -Symlink
```

---

## ⚡ Active Skills & Capabilities

### 1. `senior-code-review`
- **When to use**: Auditing pull requests, checking recent diffs, or validating branch changes.
- **Includes**:
  - `references/review-checklist.md`: Exhaustive 20-point checklist covering SQLi, IDOR, N+1 queries, async safety, and test coverage.
  - `references/feedback-rubric.md`: Standardized review report template categorizing findings into `[Blocker]`, `[Performance]`, `[Architecture]`, and `[Suggestion]`.

### 2. `csharp-dotnet-expert`
- **When to use**: Writing or optimizing C# (.NET 8/9), ASP.NET Core, EF Core, or Dapper code.
- **Includes**:
  - `references/efcore-performance.md`: No-tracking reads, selective projections, split queries (`AsSplitQuery`), batch updates (`ExecuteUpdateAsync`), and Dapper integration.
  - `references/dotnet-async-best-practices.md`: Eliminating sync-over-async (`.Result`/`.Wait()`), `CancellationToken` flow, `ValueTask` hot paths, and `SemaphoreSlim`.

### 3. `nodejs-backend-expert`
- **When to use**: Developing Fastify, Express, or NestJS services, configuring connection pools, or profiling latency.
- **Includes**:
  - `references/event-loop-perf.md`: Event loop latency monitoring, worker threads for CPU tasks, stream processing with backpressure (`stream.pipeline`), and memory leak prevention.
  - `references/node-security.md`: Zod schema validation, Helmet security headers, rate limiting, and prototype pollution defenses.

### 4. `database-architect`
- **When to use**: Profiling queries, designing schemas, choosing indexes, or planning zero-downtime migrations.
- **Includes**:
  - `references/postgres-tuning.md`: `EXPLAIN (ANALYZE, BUFFERS)` analysis, composite B-Tree ordering, GIN for JSONB, BRIN for time-series, `SKIP LOCKED` queues, and `CREATE INDEX CONCURRENTLY`.
  - `references/mssql-guidelines.md`: Covering indexes with `INCLUDE`, `READ_COMMITTED_SNAPSHOT` (RCSI), sargable queries, and parameter sniffing fixes.
  - `references/sqlite-production.md`: WAL mode (`PRAGMA journal_mode=WAL;`), synchronous pragmas, 64MB cache tuning, and bulk transaction batching.

### 5. `git-workflow-master`
- **When to use**: Git operations, interactive rebases, atomic commits, conflict resolution, or release tagging.
- **Includes**:
  - `references/conventional-commits.md`: Conventional Commits standard matrix (`feat`, `fix`, `perf`, `refactor`, `breaking change`) and SemVer impact guide.

### 6. `architecture-design-adr`
- **When to use**: Authoring Architecture Decision Records (ADRs) or evaluating system trade-offs.
- **Includes**:
  - `references/adr-template.md`: Production-ready ADR template with evaluation matrix and consequence tracking.

---

## 🤖 Subagents

Delegate complex tasks to specialized subagents defined in `.agents/subagents/`:

| Subagent Name | Role | Focus Area |
| :--- | :--- | :--- |
| **`code-reviewer`** | Senior Staff Code Reviewer | Multi-pass reviews focusing on security, performance, correctness, and architecture. |
| **`db-architect`** | Senior Database Architect | Query execution plan tuning, index strategy, and zero-downtime migrations (PostgreSQL/MSSQL/SQLite). |
| **`dotnet-specialist`** | Principal .NET & C# Engineer | .NET 8/9, Clean Architecture, EF Core profiling, Dapper, and zero-allocation async programming. |
| **`node-specialist`** | Principal Node.js Engineer | Non-blocking event loop optimization, streams, Fastify/Express, and runtime resilience. |
| **`security-auditor`** | Application Security Auditor | OWASP Top 10, SQLi, BOLA/IDOR, secrets audit, and secure cryptographic comparisons. |

---

## 📋 Ready-to-Run Workflows

- **`/code-review`**: Runs diff analysis, executes test/build commands, and outputs a severity-ranked code review.
- **`/database-migration`**: Performs pre-migration lock safety audits, writes safe non-blocking DDL, and produces rollback scripts.
- **`/api-design`**: Designs RESTful contracts, DTO records, schema validations (Zod/FluentValidation), and RFC 7807 problem details.
- **`/perf-audit`**: Systematic scan for query bottlenecks, event loop blocking, memory leaks, and thread pool starvation.
- **`/git-release`**: Tests code, scans Conventional Commits, calculates SemVer bump, and drafts release notes.
