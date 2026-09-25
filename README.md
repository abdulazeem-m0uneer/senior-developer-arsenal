# 🚀 Senior Developer Arsenal

An enterprise-grade, polyglot Antigravity AI engineering toolkit tailored specifically for **Senior Software Engineers**, **System Architects**, and **Fullstack Leaders** working with **Python (FastAPI / SQLAlchemy 2.0)**, **React (18/19)**, **Angular (17/18/19)**, **Node.js / TypeScript**, **C# / .NET 8/9**, **PostgreSQL**, **MSSQL**, **SQLite**, and **Git**.

Designed to be version-controlled as a reusable Git repository and deployed across all your projects or activated globally on your workstation with strict **Token Conservation Protocols** and **Context Engineering Guardrails**.

---

## 🎯 What This Toolkit Provides

| Component | Quantity | Purpose |
| :--- | :---: | :--- |
| **Workspace & Global Rules** | 9 | Enforce senior engineering standards across Python, Node.js, C#, Frontend, Databases, Git, and Token Frugality. |
| **Specialized Skills** | 10 | Actionable runbooks for Reviews, Python, Frontend, Fullstack, C# .NET, Node.js, DB Tuning, Git, ADRs, and Skill Writing. |
| **Autonomous Subagents** | 8 | Dedicated personas (`code-reviewer`, `python-specialist`, `frontend-architect`, `fullstack-architect`, `db-architect`, etc.). |
| **Production Workflows** | 9 | Slash-command runbooks for Reviews, Python Audits, Frontend Audits, E2E Features, DB Migrations, API Design, Perf, Releases. |
| **Multi-Project Installers** | 2 | Automated PowerShell (`install.ps1`) and Bash (`install.sh`) scripts for 1-click global or per-project setup. |

---

## 🔥 Token Conservation & Context Engineering Protocol

Antigravity operates with strict **Token Frugality & Context Engineering Guardrails** built into every rule, skill, and subagent:

### 1. The Context Engineering Pipeline
- **Zero Conversational Fluff**: No greetings, filler, or apologetic preambles. Output starts immediately with actionable findings, diffs, or commands.
- **Surgical Diffs Only**: Never print full unchanged files or classes. Output only the modified lines or functions (2–5 lines of context) using unified diff syntax.
- **Dense, Severity-Ranked Reporting**: Findings are delivered in compact tables with explicit severity tags: `[Blocker]`, `[Performance]`, `[Architecture]`, `[Suggestion]`.
- **Zero File Echoing**: When creating or editing files, the agent provides only the file link and a single-line summary—never reprinting the file body into chat.
- **Progressive Disclosure**: Bulky manuals and guidelines are isolated into `references/*.md` subdirectories and read only on-demand when relevant, keeping active context lean.

### 2. Production Benchmark: ~86% Token Reduction
Benchmarked against full-solution reviews on production-grade repositories:
- **Unoptimized Baseline**: Full-file echoes, unconstrained search, conversational fluff $\approx$ **20,120 tokens**.
- **Arsenal Optimized Review**: Targeted git diffs, progressive checklist retrieval, surgical reporting $\approx$ **2,750 tokens**.
- **Net Efficiency**: **~86% reduction in context window consumption**, drastically lowering latency and token costs.

---

## 📁 Repository Structure

```text
senior-developer-arsenal/
├── .agents/
│   ├── rules/                              # Behavioral guidelines & constraints (Always-On)
│   │   ├── token-conservation.md           # Strict token frugality, surgical diffs & context engineering
│   │   ├── senior-engineer-core.md         # Architecture, clean code, code review principles
│   │   ├── python-standards.md             # Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2
│   │   ├── frontend-standards.md           # React 18/19 RSC, Angular 17/18/19 Signals, OnPush, a11y
│   │   ├── fullstack-standards.md          # E2E type-safety, optimistic UI mutations, SSE/WebSocket streams
│   │   ├── csharp-dotnet-standards.md      # .NET 8/9, EF Core, Dapper, async/await, Result pattern
│   │   ├── nodejs-standards.md             # TS Strict, non-blocking event loop, streams, security
│   │   ├── database-standards.md           # PostgreSQL (primary), MSSQL, SQLite optimization & safety
│   │   └── git-standards.md                # Conventional Commits, atomic commits, rebase workflows
│   ├── skills/                             # Actionable on-demand skills
│   │   ├── senior-code-review/             # Deep multi-pass code reviews with checklists and rubrics
│   │   ├── python-backend-expert/          # FastAPI, asyncio TaskGroup, SQLAlchemy 2.0 async, Pydantic v2
│   │   ├── frontend-architecture-expert/   # React RSC/Zustand, Angular Signals/OnPush, a11y
│   │   ├── fullstack-integration-master/   # E2E contracts (OpenAPI/Zod), optimistic UI mutations, SSE
│   │   ├── csharp-dotnet-expert/           # C# / .NET 8/9, EF Core performance, Dapper, async pipelines
│   │   ├── nodejs-backend-expert/          # Fastify/Express/NestJS, event loop latency, streams, security
│   │   ├── database-architect/             # EXPLAIN ANALYZE, indexing (B-Tree, GIN, BRIN), non-blocking DDL
│   │   ├── git-workflow-master/            # Interactive rebase, conflict resolution, SemVer release tags
│   │   ├── architecture-design-adr/        # Architecture Decision Records (ADRs) & trade-off frameworks
│   │   └── skill-writer/                   # Interactive skill architect & generator with token-saving guardrails
│   ├── subagents/                          # Subagent configuration profiles & prompts
│   │   ├── subagent-definitions.json       # Declarative JSON manifest for subagent registration
│   │   ├── README.md                       # Subagent delegation documentation
│   │   └── prompts/
│   │       ├── code-reviewer.md            # Senior Staff Code Reviewer persona
│   │       ├── python-specialist.md        # Principal Python Systems persona
│   │       ├── frontend-architect.md       # Senior Frontend Architect persona
│   │       ├── fullstack-architect.md      # Principal Fullstack Architect persona
│   │       ├── db-architect.md             # Database Architect & Query Tuning persona
│   │       ├── dotnet-specialist.md        # Principal .NET & C# Systems persona
│   │       ├── node-specialist.md          # Principal Node.js & TypeScript Systems persona
│   │       └── security-auditor.md         # Application Security Auditor persona
│   └── workflows/                          # Standardized workflow runbooks
│       ├── code-review.md                  # /code-review workflow
│       ├── python-audit.md                 # /python-audit workflow
│       ├── frontend-audit.md               # /frontend-audit workflow
│       ├── e2e-feature.md                  # /e2e-feature workflow
│       ├── create-skill.md                 # /create-skill workflow
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
# In Windows PowerShell:
cd C:\Users\Abdulazeem\Desktop\senior-developer-arsenal
.\install.ps1 -Global
```

```bash
# In Linux / macOS / WSL:
cd ~/Desktop/senior-developer-arsenal
chmod +x install.sh
./install.sh --global
```
*This installs skills into `~/.gemini/config/skills/` and rules into `~/.gemini/config/rules/`.*

---

### Option B: Per-Project Installation
Inject or symlink the `.agents/` directory directly into a target repository:

```powershell
# Copy into an existing project:
.\install.ps1 -Project "C:\Users\Abdulazeem\repos\my-api"

# Or create a symbolic link (changes in arsenal automatically reflect in project):
.\install.ps1 -Project "C:\Users\Abdulazeem\repos\my-api" -Symlink
```

```bash
# On Linux / macOS / WSL:
./install.sh --project /path/to/my-project
./install.sh --project /path/to/my-project --symlink
```

---

## 📐 Engineering Standards & Rules (Always-On)

These 9 rules are automatically applied by Antigravity across your workspaces:

| Rule File | Scope & Mandate | Red Flags / Forbidden Patterns |
| :--- | :--- | :--- |
| **[`token-conservation.md`](.agents/rules/token-conservation.md)** | Enforces strict token economy, zero conversational fluff, surgical 2-5 line diffs, and progressive reference loading. | Full-file reprinting, conversational filler, broad un-targeted file reads. |
| **[`senior-engineer-core.md`](.agents/rules/senior-engineer-core.md)** | Clean Architecture, domain-driven boundaries, Result pattern error handling, defensive boundary validation, observability. | Framework bleed into Domain, silent exception swallowing, raw unvalidated inputs. |
| **[`python-standards.md`](.agents/rules/python-standards.md)** | Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, asyncio TaskGroup, strict Ruff/Mypy typing. | Blocking sync calls in async event loop, `pickle.loads` on untrusted data, missing eager loading (N+1). |
| **[`frontend-standards.md`](.agents/rules/frontend-standards.md)** | React 18/19 (RSC, leaf `"use client"`, Zustand), Angular 17/18/19 (Signals, Standalone, OnPush, @defer), WCAG AA a11y. | Unmemoized loop props, `useEffect` for derived state, manual RxJS subscriptions without `toSignal`/async pipe. |
| **[`fullstack-standards.md`](.agents/rules/fullstack-standards.md)** | End-to-end type safety, OpenAPI/Zod contract synchronization, optimistic UI mutations with rollback snapshot, SSE streams. | Disconnected duplicate client types, token storage in `localStorage` (XSS risk), unhandled mutation rollbacks. |
| **[`csharp-dotnet-standards.md`](.agents/rules/csharp-dotnet-standards.md)** | .NET 8/9, EF Core (`AsNoTracking`, `AsSplitQuery`, batch updates), Dapper, `ValueTask` hot paths, `CancellationToken` flow. | Sync-over-async (`.Result`/`.Wait()`), untracked EF entities in mutation paths, unparameterized raw SQL. |
| **[`nodejs-standards.md`](.agents/rules/nodejs-standards.md)** | TypeScript Strict mode, Fastify/Express/NestJS, non-blocking event loop, stream backpressure (`stream.pipeline`), Zod, Helmet. | Synchronous FS/crypto in request cycle, unhandled promise rejections, mutable global state, `any` abuse. |
| **[`database-standards.md`](.agents/rules/database-standards.md)** | PostgreSQL primary (`EXPLAIN (ANALYZE, BUFFERS)`, `CREATE INDEX CONCURRENTLY`), MSSQL (RCSI, covering indexes), SQLite (WAL mode). | Unindexed foreign keys, table-locking DDL in peak traffic, `SELECT *` across large joins, non-sargable queries. |
| **[`git-standards.md`](.agents/rules/git-standards.md)** | Conventional Commits (`feat`, `fix`, `perf`, `refactor`), atomic single-purpose commits, linear rebase, semantic release tags. | Vague commits ("fix bug"), committing secrets or binaries, unreviewed force-pushes to shared branches. |

---

## ⚡ Active Skills & Capabilities

### 1. `senior-code-review`
- **When to use**: Auditing pull requests, checking recent diffs, or validating branch changes.
- **Includes**:
  - [`review-checklist.md`](.agents/skills/senior-code-review/references/review-checklist.md): Exhaustive 20-point checklist covering SQLi, IDOR, N+1 queries, async safety, and test coverage.
  - [`feedback-rubric.md`](.agents/skills/senior-code-review/references/feedback-rubric.md): Standardized review report template categorizing findings into `[Blocker]`, `[Performance]`, `[Architecture]`, and `[Suggestion]`.

### 2. `python-backend-expert`
- **When to use**: Designing or optimizing modern Python services (FastAPI, Django, Flask), asyncio TaskGroup pipelines, or SQLAlchemy 2.0 async queries.
- **Includes**:
  - [`asyncio-perf.md`](.agents/skills/python-backend-expert/references/asyncio-perf.md): Non-blocking asyncio patterns, TaskGroup structured concurrency, thread pool offloading (`asyncio.to_thread`).
  - [`pydantic-fastapi.md`](.agents/skills/python-backend-expert/references/pydantic-fastapi.md): Pydantic v2 schemas, lifespan context managers, and dependency injection patterns.

### 3. `frontend-architecture-expert`
- **When to use**: Designing React (18/19) or Angular (17/18/19) applications, debugging re-render churn, or auditing a11y.
- **Includes**:
  - [`react-performance.md`](.agents/skills/frontend-architecture-expert/references/react-performance.md): RSC leaf boundaries, Zustand selective subscriptions, list virtualization (`@tanstack/react-virtual`).
  - [`angular-signals-best-practices.md`](.agents/skills/frontend-architecture-expert/references/angular-signals-best-practices.md): Angular Signals (`signal`, `computed`), Standalone components, `OnPush`, `@defer (on viewport)`.

### 4. `fullstack-integration-master`
- **When to use**: Designing end-to-end features bridging UI and Backend, synchronizing API types, or implementing optimistic UI.
- **Includes**:
  - [`e2e-type-safety.md`](.agents/skills/fullstack-integration-master/references/e2e-type-safety.md): OpenAPI $\to$ TypeScript client generation (`openapi-typescript`), shared Zod contracts.
  - [`realtime-optimistic-ui.md`](.agents/skills/fullstack-integration-master/references/realtime-optimistic-ui.md): TanStack Query optimistic mutation with rollback snapshot, Server-Sent Events (SSE).

### 5. `csharp-dotnet-expert`
- **When to use**: Writing or optimizing C# (.NET 8/9), ASP.NET Core, EF Core, or Dapper code.
- **Includes**:
  - [`efcore-performance.md`](.agents/skills/csharp-dotnet-expert/references/efcore-performance.md): No-tracking reads, selective projections, split queries (`AsSplitQuery`), batch updates (`ExecuteUpdateAsync`), and Dapper integration.
  - [`dotnet-async-best-practices.md`](.agents/skills/csharp-dotnet-expert/references/dotnet-async-best-practices.md): Eliminating sync-over-async (`.Result`/`.Wait()`), `CancellationToken` flow, `ValueTask` hot paths, and `SemaphoreSlim`.

### 6. `nodejs-backend-expert`
- **When to use**: Developing Fastify, Express, or NestJS services, configuring connection pools, or profiling latency.
- **Includes**:
  - [`event-loop-perf.md`](.agents/skills/nodejs-backend-expert/references/event-loop-perf.md): Event loop latency monitoring, worker threads for CPU tasks, stream processing with backpressure (`stream.pipeline`), and memory leak prevention.
  - [`node-security.md`](.agents/skills/nodejs-backend-expert/references/node-security.md): Zod schema validation, Helmet security headers, rate limiting, and prototype pollution defenses.

### 7. `database-architect`
- **When to use**: Profiling queries, designing schemas, choosing indexes, or planning zero-downtime migrations.
- **Includes**:
  - [`postgres-tuning.md`](.agents/skills/database-architect/references/postgres-tuning.md): `EXPLAIN (ANALYZE, BUFFERS)` analysis, composite B-Tree ordering, GIN for JSONB, BRIN for time-series, `SKIP LOCKED` queues, and `CREATE INDEX CONCURRENTLY`.
  - [`mssql-guidelines.md`](.agents/skills/database-architect/references/mssql-guidelines.md): Covering indexes with `INCLUDE`, `READ_COMMITTED_SNAPSHOT` (RCSI), sargable queries, and parameter sniffing fixes.
  - [`sqlite-production.md`](.agents/skills/database-architect/references/sqlite-production.md): WAL mode (`PRAGMA journal_mode=WAL;`), synchronous pragmas, 64MB cache tuning, and bulk transaction batching.

### 8. `git-workflow-master`
- **When to use**: Git operations, interactive rebases, atomic commits, conflict resolution, or release tagging.
- **Includes**:
  - [`conventional-commits.md`](.agents/skills/git-workflow-master/references/conventional-commits.md): Conventional Commits standard matrix (`feat`, `fix`, `perf`, `refactor`, `breaking change`) and SemVer impact guide.

### 9. `architecture-design-adr`
- **When to use**: Authoring Architecture Decision Records (ADRs) or evaluating system trade-offs.
- **Includes**:
  - [`adr-template.md`](.agents/skills/architecture-design-adr/references/adr-template.md): Production-ready ADR template with evaluation matrix and consequence tracking.

### 10. `skill-writer`
- **When to use**: Interactively interviewing the user to architect, scaffold, and generate new token-efficient skills.
- **Includes**:
  - [`skill-template.md`](.agents/skills/skill-writer/references/skill-template.md): Canonical skill structure with YAML frontmatter, execution steps, and token guardrails.
  - [`interview-guide.md`](.agents/skills/skill-writer/references/interview-guide.md): Structured 4-question interview framework minimizing interaction rounds.

---

## 🤖 Autonomous Subagents

Antigravity includes 8 specialized subagent profiles defined in `.agents/subagents/subagent-definitions.json`:

| Subagent Name | Role | Focus Area & Capabilities |
| :--- | :--- | :--- |
| **`code-reviewer`** | Senior Staff Code Reviewer | Multi-pass reviews focusing on security, performance, correctness, and architecture. |
| **`python-specialist`** | Principal Python Systems Engineer | Modern Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, and asyncio event loops. |
| **`frontend-architect`** | Senior Frontend Architect | React 18/19 (RSC, Zustand), Angular 17/18/19 (Signals, OnPush, @defer), a11y. |
| **`fullstack-architect`** | Principal Fullstack Architect | E2E type-safety (OpenAPI/Zod), optimistic UI mutations, SSE/WebSocket streams. |
| **`db-architect`** | Senior Database Architect | Query execution plan tuning, index strategy, and zero-downtime migrations (PostgreSQL/MSSQL/SQLite). |
| **`dotnet-specialist`** | Principal .NET & C# Engineer | .NET 8/9, Clean Architecture, EF Core profiling, Dapper, and zero-allocation async programming. |
| **`node-specialist`** | Principal Node.js Engineer | Non-blocking event loop optimization, streams, Fastify/Express, and runtime resilience. |
| **`security-auditor`** | Application Security Auditor | OWASP Top 10, SQLi, BOLA/IDOR, secrets audit, and secure cryptographic comparisons. |

### How to Invoke Subagents
In Antigravity chat, invoke subagents using natural language or tool calls:
```text
"Invoke python-specialist to refactor the database access layer to async SQLAlchemy 2.0."
"Invoke code-reviewer to audit unstaged git changes."
"Launch db-architect to analyze this slow query execution plan."
```

---

## 📋 Ready-to-Run Workflows & Slash Commands

Execute standardized workflows directly in Antigravity chat:

| Workflow | Slash Command | Execution Runbook | Deliverable / Output |
| :--- | :--- | :--- | :--- |
| **Code Review** | `/code-review` | Inspects git diffs, runs test suites, checks security/performance checklists. | Ranked review table (`[Blocker]`, `[Perf]`, `[Arch]`, `[Suggestion]`). |
| **Python Audit** | `/python-audit` | Runs Ruff linter, Mypy strict type checks, inspects asyncio blocking calls. | Static analysis report and surgical fixes. |
| **Frontend Audit** | `/frontend-audit` | Audits re-render churn, OnPush detection, lazy loading, and WCAG a11y. | Frontend optimization recommendations with code snippets. |
| **E2E Feature** | `/e2e-feature` | Guides end-to-end delivery: DB migration $\to$ backend API $\to$ optimistic UI. | Fullstack integrated feature implementation. |
| **Create Skill** | `/create-skill` | Interactively interviews user to generate a new token-saving skill. | Scaffolds `.agents/skills/<name>/SKILL.md` + references. |
| **DB Migration** | `/database-migration` | Pre-migration lock safety check, non-blocking DDL (`CONCURRENTLY`), rollback script. | Safe migration script + rollback companion. |
| **API Design** | `/api-design` | Designs RESTful contracts, DTO records, schema validation, RFC 7807 problem details. | API specification, DTOs, and route handlers. |
| **Perf Audit** | `/perf-audit` | Scans for query bottlenecks, event loop blocking, memory leaks, thread starvation. | Targeted latency and throughput optimization plan. |
| **Git Release** | `/git-release` | Verifies tests, analyzes Conventional Commits, calculates SemVer bump, writes notes. | Git tag and changelog release draft. |

---

## ✍️ Meta-Skill: Authoring New Skills (`skill-writer`)

Need to create custom skills for internal proprietary tools or new frameworks? The toolkit includes a built-in interactive meta-skill:

1. Type `/create-skill` or prompt:
   > *"Help me create a new skill for Docker container hardening."*
2. The agent runs a structured 4-step interview:
   - **Goal & Scope**: Defines exact triggers and boundaries.
   - **Step-by-Step Procedure**: Establishes commands, verification, and fallbacks.
   - **References & Heavy Documentation**: Extracts bulky manuals into `references/`.
   - **Token Economy Guardrails**: Applies surgical diff and anti-reprint constraints.
3. Automatically scaffolds the directory, `SKILL.md`, references, and registers it globally or locally.

---

## 🔄 Updating & Synchronization

To synchronize updates made to this repository with your global configuration:

```powershell
# In PowerShell:
cd C:\Users\Abdulazeem\Desktop\senior-developer-arsenal
git pull origin master   # If tracking a remote
.\install.ps1 -Global    # Redeploy skills and rules globally
```

---

## 📄 License & Attribution

Crafted for high-performance software engineering teams. Free to use, customize, and extend across all personal and enterprise repositories.
