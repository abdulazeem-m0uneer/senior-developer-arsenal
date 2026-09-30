# 🚀 Senior Developer Arsenal

An enterprise-grade, polyglot Antigravity AI engineering toolkit tailored specifically for **Senior Software Engineers**, **System Architects**, and **Fullstack Leaders** working with **Python (FastAPI / SQLAlchemy 2.0)**, **React (18/19)**, **Angular (17/18/19)**, **Node.js / TypeScript**, **C# / .NET 8/9**, **PostgreSQL**, **MSSQL**, **SQLite**, and **Git**.

Designed to be version-controlled as a reusable Git repository and deployed across all your projects or activated globally on your workstation with strict **Token Conservation Protocols**, **Applied Rationality**, and **Context Engineering Guardrails**.

---

## 🎯 What This Toolkit Provides

| Component | Quantity | Purpose |
| :--- | :---: | :--- |
| **Workspace & Global Rules** | 11 | Enforce senior engineering standards across Python, Node.js, C#, Frontend, UI/UX, Databases, Git, Token Frugality, and Defensive Epistemology. |
| **Specialized Skills** | 22 | Actionable runbooks adhering to modern Agent Skills standards (`SKILL.md` + progressive `references/`) with slash commands and negative triggers. |
| **Autonomous Subagents** | 10 | Dedicated personas (`code-reviewer`, `epistemic-debugger`, `python-specialist`, `frontend-architect`, `ui-ux-architect`, `fullstack-architect`, `db-architect`, etc.). |
| **Multi-Project Installers** | 2 | Automated PowerShell (`install.ps1`) and Bash (`install.sh`) scripts for 1-click global or per-project setup. |

---

## 🔥 Token Conservation & Defensive Epistemology Protocol

Antigravity operates with strict **Token Frugality & Epistemic Hygiene Guardrails** built into every rule, skill, and subagent:

### 1. Applied Rationality & Rule 0 on Failure
- **Rule 0 on Failure**: When a tool, script, or test fails unexpectedly, the agent **STOPS immediately**. No silent retries, no guessing, no speculative tool chaining. It outputs the raw error, current hypothesis, proposed action, and confirms before touching code.
- **Make Beliefs Pay Rent (Prediction Protocol)**: Before executing non-trivial actions, the agent states its expected outcome (`EXPECT`). Immediately after execution, it verifies reality (`MATCHES: yes/no`). If reality diverges, the agent **debugs its mental model**, not reality.
- **Notice Confusion & Epistemic Hygiene**: Surprise is proof that the mental model is flawed. The agent distinguishes verified facts (`"I verified X"`) from theories (`"I believe X"`). *"I don't know"* is a first-class, valid output.
- **Anti-Sycophancy & Pushback**: Zero conversational filler, zero apologetic text, and zero brown-nosing (*"You're absolutely right"*). Conflicting user instructions are surfaced explicitly rather than quietly guessing.
- **Chesterton's Fence**: Before modifying or removing code, the agent articulates *why* it exists.

### 2. The Context Engineering Pipeline
- **Surgical Diffs Only**: Never print full unchanged files or classes. Output only the modified lines or functions (2–5 lines of context) using unified diff syntax.
- **Dense, Severity-Ranked Reporting**: Findings are delivered in compact tables with explicit severity tags: `[Blocker]`, `[Performance]`, `[Architecture]`, `[Suggestion]`.
- **Zero File Echoing**: When creating or editing files, the agent provides only the file link and a single-line summary—never reprinting the file body into chat.
- **Progressive Disclosure**: Bulky manuals and guidelines are isolated into `references/*.md` subdirectories and read only on-demand when relevant, keeping active context lean.

### 3. Production Benchmark: ~86% Token Reduction
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
│   │   ├── defensive-epistemology.md       # Applied rationality, Rule 0 failure stop, prediction protocol
│   │   ├── senior-engineer-core.md         # Architecture, clean code, code review principles
│   │   ├── python-standards.md             # Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2
│   │   ├── frontend-standards.md           # React 18/19 RSC, Angular 17/18/19 Signals, OnPush, a11y
│   │   ├── ui-ux-standards.md              # DTCG tokens, anti-slop gates, WCAG 2.2 AA, complete states
│   │   ├── fullstack-standards.md          # E2E type-safety, optimistic UI mutations, SSE/WebSocket streams
│   │   ├── csharp-dotnet-standards.md      # .NET 8/9, EF Core, Dapper, async/await, Result pattern
│   │   ├── nodejs-standards.md             # TS Strict, non-blocking event loop, streams, security
│   │   ├── database-standards.md           # PostgreSQL (primary), MSSQL, SQLite optimization & safety
│   │   └── git-standards.md                # Conventional Commits, atomic commits, rebase workflows
│   ├── skills/                             # Actionable on-demand skills (Agent Skills standard)
│   │   ├── api-design/                     # REST/RPC API contracts, RFC 7807 problem details
│   │   ├── architecture-design-adr/        # Architecture Decision Records (ADRs) & trade-off frameworks
│   │   ├── code-review/                    # Multi-pass senior code reviews, checklists, rubrics
│   │   ├── create-skill/                   # Interactive skill architect & generator with token-saving guardrails
│   │   ├── csharp-dotnet-expert/           # C# / .NET 8/9, EF Core performance, Dapper, async pipelines
│   │   ├── database-architect/             # EXPLAIN ANALYZE, indexing (B-Tree, GIN, BRIN), non-blocking DDL
│   │   ├── database-migration/             # Zero-downtime, non-blocking migrations & rollback verification
│   │   ├── e2e-feature/                    # Vertical slice feature implementation (DB -> Backend -> UI)
│   │   ├── frontend-architecture-expert/   # React RSC/Zustand, Angular Signals/OnPush, a11y
│   │   ├── frontend-audit/                 # Re-render churn, OnPush detection, lazy loading audit
│   │   ├── fullstack-integration-master/   # E2E contracts (OpenAPI/Zod), optimistic UI mutations, SSE
│   │   ├── git-release/                    # SemVer calculation, commit analysis, release notes
│   │   ├── git-workflow-master/            # Interactive rebase, conflict resolution, SemVer release tags
│   │   ├── investigate/                    # Applied rationality, 5+ hypotheses, 5-Whys causal analysis
│   │   ├── nodejs-backend-expert/          # Fastify/Express/NestJS, event loop latency, streams, security
│   │   ├── perf-audit/                     # Query bottlenecks, event loop lag, memory leak diagnosis
│   │   ├── python-audit/                   # Ruff, strict Mypy typing, asyncio blocking call audit
│   │   ├── python-backend-expert/          # FastAPI, asyncio TaskGroup, SQLAlchemy 2.0 async, Pydantic v2
│   │   ├── ui-ux-architect/                # DTCG tokens, state completeness, 10 anti-slop gates
│   │   └── ui-ux-audit/                    # Anti-slop gate audit matrix & remediation
│   ├── subagents/                          # Subagent configuration profiles & prompts
│   │   ├── subagent-definitions.json       # Declarative JSON manifest for subagent registration
│   │   ├── README.md                       # Subagent delegation documentation
│   │   └── prompts/
│   │       ├── code-reviewer.md            # Senior Staff Code Reviewer persona
│   │       ├── epistemic-debugger.md       # Epistemic Debugger & Root Cause Specialist persona
│   │       ├── python-specialist.md        # Principal Python Systems persona
│   │       ├── frontend-architect.md       # Senior Frontend Architect persona
│   │       ├── ui-ux-architect.md          # Senior Design System & UI/UX Architect persona
│   │       ├── fullstack-architect.md      # Principal Fullstack Architect persona
│   │       ├── db-architect.md             # Database Architect & Query Tuning persona
│   │       ├── dotnet-specialist.md        # Principal .NET & C# Systems persona
│   │       ├── node-specialist.md          # Principal Node.js & TypeScript Systems persona
│   │       └── security-auditor.md         # Application Security Auditor persona
│   ├── workflows/                          # Legacy workflows safely archived (*.md.bak)
│   └── skills.json                         # Explicit skills manifest for deterministic discovery
├── .githooks/
│   └── commit-msg                          # Automated Conventional Commits validator hook
├── scripts/
│   ├── arsenal                             # Native CLI helper for Ubuntu / Linux / WSL
│   └── verify_ui_ux.py                     # Automated UI/UX anti-slop verification gate script
├── docs/
│   └── UBUNTU-INTEGRATION.md               # Dedicated guide for Ubuntu OS & WSL integration
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
# In Ubuntu / Linux / WSL:
cd ~/Desktop/senior-developer-arsenal
chmod +x install.sh scripts/arsenal
./install.sh --global --cli
```
*Installs skills into `~/.gemini/config/skills/`, rules into `~/.gemini/config/rules/`, and provides the `arsenal` command in your terminal.*
*(See [Ubuntu & Linux Integration Guide](docs/UBUNTU-INTEGRATION.md) for full Linux details).*

---

### Option B: Per-Project Installation
Inject or symlink the `.agents/` directory directly into a target repository:

```powershell
# In Windows PowerShell (Copy or Symlink):
.\install.ps1 -Project "C:\Users\Abdulazeem\repos\my-api"
.\install.ps1 -Project "C:\Users\Abdulazeem\repos\my-api" -Symlink
```

```bash
# In Ubuntu / Linux using the 'arsenal' CLI:
cd ~/projects/my-api
arsenal link .          # Creates live symlinks to the arsenal
# Or manually via install.sh:
./install.sh --project /path/to/my-project --link
```

---

### Option C: Automated Conventional Commits Hook
Enforce standardized commit messages automatically across your repository:

```bash
# Enable the pre-configured commit-msg hook:
git config core.hooksPath .githooks
```
*Rejects non-compliant commit messages before they enter git history.*

---

### Option E: CodeGraph AST Intelligence (Save Reading Tokens)
Provide Antigravity agents with AST-level code intelligence via [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph).

#### Why It's Useful:
- **Drastic Token Reduction (~85%)**: Replaces brute-force full-file reads and recursive greps with direct AST queries (codegraph_callers, codegraph_callees, codegraph_symbol, codegraph_impact).
- **Instant Blast Radius Analysis**: Understands complete dependency graphs before renaming or refactoring methods.
- **Accurate Line Targeting**: Delivers pinpoint file:L30-L45 references instead of loading thousands of lines of context.

#### 1-Click Installer Command:
```powershell
# In Windows PowerShell:
.\install.ps1 -CodeGraph
```
```bash
# In Ubuntu / Linux / WSL:
./install.sh --codegraph
```
---

### Option D: Persistent Agent Memory (Hindsight Biomimetic Memory)
Provide Antigravity agents with cross-session long-term memory using [vectorize-io/hindsight](https://github.com/vectorize-io/hindsight).

#### Why It's Useful:
- **Zero Loss of Architectural Context**: Prevents agents from "forgetting" past decisions, custom rules, or solved edge cases between chat sessions.
- **Massive Token Conservation**: Instead of re-reading large READMEs, ADR files, and past chat logs, agents perform high-precision hybrid retrieval (`recall`) and synthesized reflection (`reflect`).
- **Evidence-Based Consolidated Observations**: Stores deduplicated beliefs with proof counters and lineage tracking, resolving contradictions automatically.

#### 1-Click Installer Command:
```powershell
# In Windows PowerShell:
.\install.ps1 -Hindsight
```

```bash
# In Ubuntu / Linux / WSL:
./install.sh --hindsight
```

#### CLI / Script Usage:
```bash
# Store an architectural decision or resolved bug finding:
python scripts/memory.py retain --bank "my-project" --content "We enforce UUIDv7 and WAL mode on SQLite."

# Search memories using hybrid search (vector + BM25 + graph + temporal):
python scripts/memory.py recall --bank "my-project" --query "What are our SQLite settings?"

# Ask the agent to reason across its memory bank:
python scripts/memory.py reflect --bank "my-project" --query "Summarize all database constraints."
```

---

## 📐 Engineering Standards & Rules (Always-On)

These 11 rules are automatically applied by Antigravity across your workspaces:

| Rule File | Scope & Mandate | Red Flags / Forbidden Patterns |
| :--- | :--- | :--- |
| **[`token-conservation.md`](.agents/rules/token-conservation.md)** | Enforces strict token economy, zero conversational fluff, surgical 2-5 line diffs, and progressive reference loading. | Full-file reprinting, conversational filler, broad un-targeted file reads. |
| **[`defensive-epistemology.md`](.agents/rules/defensive-epistemology.md)** | Applied rationality, Rule 0 failure stop, prediction protocol (`EXPECT`/`MATCHES`), Chesterton's Fence, anti-sycophancy. | Silent tool retries, "this should work" traps, deleting ununderstood code, blind flailing. |
| **[`senior-engineer-core.md`](.agents/rules/senior-engineer-core.md)** | Clean Architecture, domain-driven boundaries, Result pattern error handling, defensive boundary validation, observability. | Framework bleed into Domain, silent exception swallowing, raw unvalidated inputs. |
| **[`python-standards.md`](.agents/rules/python-standards.md)** | Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, asyncio TaskGroup, strict Ruff/Mypy typing. | Blocking sync calls in async event loop, `pickle.loads` on untrusted data, missing eager loading (N+1). |
| **[`frontend-standards.md`](.agents/rules/frontend-standards.md)** | React 18/19 (RSC, leaf `"use client"`, Zustand), Angular 17/18/19 (Signals, Standalone, OnPush, @defer), WCAG AA a11y. | Unmemoized loop props, `useEffect` for derived state, manual RxJS subscriptions without `toSignal`/async pipe. |
| **[`ui-ux-standards.md`](.agents/rules/ui-ux-standards.md)** | DTCG 3-tier tokens, state completeness (6 states), WCAG 2.2 AA (4.5:1/3:1), target sizes (>=24px/>=44px/>=48px), Lucide SVG (currentColor). | Emoji in UI/labels, em-dashes in copy, blue Delete buttons, 3 equal stat cards, pure #000 on #fff, generic muddy drop shadows, missing focus rings. |
| **[`fullstack-standards.md`](.agents/rules/fullstack-standards.md)** | End-to-end type safety, OpenAPI/Zod contract synchronization, optimistic UI mutations with rollback snapshot, SSE streams. | Disconnected duplicate client types, token storage in `localStorage` (XSS risk), unhandled mutation rollbacks. |
| **[`csharp-dotnet-standards.md`](.agents/rules/csharp-dotnet-standards.md)** | .NET 8/9, EF Core (`AsNoTracking`, `AsSplitQuery`, batch updates), Dapper, `ValueTask` hot paths, `CancellationToken` flow. | Sync-over-async (`.Result`/`.Wait()`), untracked EF entities in mutation paths, unparameterized raw SQL. |
| **[`nodejs-standards.md`](.agents/rules/nodejs-standards.md)** | TypeScript Strict mode, Fastify/Express/NestJS, non-blocking event loop, stream backpressure (`stream.pipeline`), Zod, Helmet. | Synchronous FS/crypto in request cycle, unhandled promise rejections, mutable global state, `any` abuse. |
| **[`database-standards.md`](.agents/rules/database-standards.md)** | PostgreSQL primary (`EXPLAIN (ANALYZE, BUFFERS)`, `CREATE INDEX CONCURRENTLY`), MSSQL (RCSI, covering indexes), SQLite (WAL mode). | Unindexed foreign keys, table-locking DDL in peak traffic, `SELECT *` across large joins, non-sargable queries. |
| **[`git-standards.md`](.agents/rules/git-standards.md)** | Conventional Commits (`feat`, `fix`, `perf`, `refactor`), atomic single-purpose commits, linear rebase, semantic release tags. | Vague commits ("fix bug"), committing secrets or binaries, unreviewed force-pushes to shared branches. |

---

## ⚡ Active Skills & Capabilities

The arsenal includes 22 specialized skills conforming to modern Agent Skills standards (agentskills.io / Google Antigravity 2.0 / Claude), featuring isolated progressive disclosure references (`references/`), slash commands, and negative triggers:

### 1. code-review (/code-review)
- **When to use**: Auditing pull requests, reviewing recent commits, inspecting staged diffs, or evaluating branch code quality.
- **Includes**:
  - [review-checklist.md](.agents/skills/code-review/references/review-checklist.md): Exhaustive 20-point checklist covering SQLi, IDOR, N+1 queries, async safety, and test coverage.
  - [feedback-rubric.md](.agents/skills/code-review/references/feedback-rubric.md): Standardized review report template categorizing findings into [Blocker], [Performance], [Architecture], and [Suggestion].

### 2. investigate (/investigate)
- **When to use**: Diagnosing elusive bugs, intermittent test failures, unexplained crashes, production outages, or confusing regressions.
- **Includes**:
  - [investigation-template.md](.agents/skills/investigate/references/investigation-template.md): Structured artifact template with Facts vs. Assumptions, 5+ Competing Hypotheses, 5-Whys causal tree, and Chesterton's Fence audit.
  - [epistemic-checklist.md](.agents/skills/investigate/references/epistemic-checklist.md): Sanity checklist for hypothesis rigor, discriminative test isolation, and blast radius verification.

### 3. create-skill (/create-skill)
- **When to use**: Interactively interviewing the user to architect, scaffold, and generate new token-efficient skills.
- **Includes**:
  - [skill-template.md](.agents/skills/create-skill/references/skill-template.md): Canonical skill structure with YAML frontmatter, execution steps, and token guardrails.
  - [interview-guide.md](.agents/skills/create-skill/references/interview-guide.md): Structured 4-question interview framework minimizing interaction rounds.

### 4. api-design (/api-design)
- **When to use**: Designing RESTful or RPC API contracts, input validation schemas, DTO models, and RFC 7807 error representations.
- **Includes**:
  - [api-standards.md](.agents/skills/api-design/references/api-standards.md): RESTful URI design, RFC 7807 problem details, pagination standards, and schema validation.

### 5. architecture-design-adr (/architecture-design-adr)
- **When to use**: Authoring Architecture Decision Records (ADRs), designing subsystems, evaluating technology choices, or defining service boundaries.
- **Includes**:
  - [adr-template.md](.agents/skills/architecture-design-adr/references/adr-template.md): Production-ready ADR template with evaluation matrix and consequence tracking.

### 6. csharp-dotnet-expert (/csharp-dotnet-expert)
- **When to use**: Writing or optimizing C# (.NET 8/9), ASP.NET Core, EF Core, or Dapper code.
- **Includes**:
  - [efcore-performance.md](.agents/skills/csharp-dotnet-expert/references/efcore-performance.md): No-tracking reads, selective projections, split queries (AsSplitQuery), batch updates (ExecuteUpdateAsync), and Dapper integration.
  - [dotnet-async-best-practices.md](.agents/skills/csharp-dotnet-expert/references/dotnet-async-best-practices.md): Eliminating sync-over-async (.Result/.Wait()), CancellationToken flow, ValueTask hot paths, and SemaphoreSlim.

### 7. database-architect (/database-architect)
- **When to use**: Profiling queries, designing schemas, choosing indexes, or planning zero-downtime migrations.
- **Includes**:
  - [postgres-tuning.md](.agents/skills/database-architect/references/postgres-tuning.md): EXPLAIN (ANALYZE, BUFFERS) analysis, composite B-Tree ordering, GIN for JSONB, BRIN for time-series, SKIP LOCKED queues, and CREATE INDEX CONCURRENTLY.
  - [mssql-guidelines.md](.agents/skills/database-architect/references/mssql-guidelines.md): Covering indexes with INCLUDE, READ_COMMITTED_SNAPSHOT (RCSI), sargable queries, and parameter sniffing fixes.
  - [sqlite-production.md](.agents/skills/database-architect/references/sqlite-production.md): WAL mode (PRAGMA journal_mode=WAL;), synchronous pragmas, 64MB cache tuning, and bulk transaction batching.

### 8. database-migration (/database-migration)
- **When to use**: Designing, reviewing, or applying non-blocking database migrations with safe rollback scripts.
- **Includes**:
  - [migration-safety.md](.agents/skills/database-migration/references/migration-safety.md): Safe migration checklist, lock timeout configuration, concurrent indexing, and column addition safety.

### 9. e2e-feature (/e2e-feature)
- **When to use**: Implementing fullstack end-to-end features bridging database migrations, backend endpoints, and frontend UI views.
- **Includes**:
  - [vertical-slice.md](.agents/skills/e2e-feature/references/vertical-slice.md): Vertical slice architecture, migration safety, type synchronization, and optimistic mutation workflow.

### 10. frontend-architecture-expert (/frontend-architecture-expert)
- **When to use**: Designing React (18/19) or Angular (17/18/19) applications, debugging re-render churn, or auditing a11y.
- **Includes**:
  - [react-performance.md](.agents/skills/frontend-architecture-expert/references/react-performance.md): RSC leaf boundaries, Zustand selective subscriptions, list virtualization (@tanstack/react-virtual).
  - [angular-signals-best-practices.md](.agents/skills/frontend-architecture-expert/references/angular-signals-best-practices.md): Angular Signals (signal, computed), Standalone components, OnPush, @defer (on viewport).

### 11. frontend-audit (/frontend-audit)
- **When to use**: Auditing frontend performance, re-render bottlenecks, bundle size, change detection, and web accessibility.
- **Includes**:
  - [render-profiling.md](.agents/skills/frontend-audit/references/render-profiling.md): React DevTools / Angular DevTools profiling guides, memoization rules, and a11y audit steps.

### 12. fullstack-integration-master (/fullstack-integration-master)
- **When to use**: Designing end-to-end features bridging UI and Backend, synchronizing API types, or implementing optimistic UI.
- **Includes**:
  - [e2e-type-safety.md](.agents/skills/fullstack-integration-master/references/e2e-type-safety.md): OpenAPI -> TypeScript client generation (openapi-typescript), shared Zod contracts.
  - [realtime-optimistic-ui.md](.agents/skills/fullstack-integration-master/references/realtime-optimistic-ui.md): TanStack Query optimistic mutation with rollback snapshot, Server-Sent Events (SSE).

### 13. git-release (/git-release)
- **When to use**: Preparing software releases, verifying test suites, bumping versions according to SemVer, and authoring release notes.
- **Includes**:
  - [release-guide.md](.agents/skills/git-release/references/release-guide.md): Pre-release verification checklist, SemVer bump rules, Conventional Commits changelog generation, and tag creation.

### 14. git-workflow-master (/git-workflow-master)
- **When to use**: Git operations, interactive rebases, atomic commits, conflict resolution, or release tagging.
- **Includes**:
  - [conventional-commits.md](.agents/skills/git-workflow-master/references/conventional-commits.md): Conventional Commits standard matrix (feat, fix, perf, refactor, breaking change) and SemVer impact guide.

### 15. nodejs-backend-expert (/nodejs-backend-expert)
- **When to use**: Developing Fastify, Express, or NestJS services, configuring connection pools, or profiling latency.
- **Includes**:
  - [event-loop-perf.md](.agents/skills/nodejs-backend-expert/references/event-loop-perf.md): Event loop latency monitoring, worker threads for CPU tasks, stream processing with backpressure (stream.pipeline), and memory leak prevention.
  - [node-security.md](.agents/skills/nodejs-backend-expert/references/node-security.md): Zod schema validation, Helmet security headers, rate limiting, and prototype pollution defenses.

### 16. perf-audit (/perf-audit)
- **When to use**: Performance auditing to detect database query bottlenecks, event loop lag, memory leaks, and thread pool starvation.
- **Includes**:
  - [perf-profiling.md](.agents/skills/perf-audit/references/perf-profiling.md): Profiling procedures for Node.js event loop, .NET thread pool, and PostgreSQL query execution.

### 17. python-audit (/python-audit)
- **When to use**: Auditing Python codebases for type safety, lint compliance (Ruff), and asyncio concurrency hazards.
- **Includes**:
  - [python-rules.md](.agents/skills/python-audit/references/python-rules.md): Ruff configuration rules, Mypy strict type checking guidelines, and async event loop safety checklist.

### 18. python-backend-expert (/python-backend-expert)
- **When to use**: Designing or optimizing modern Python services (FastAPI, Django, Flask), asyncio TaskGroup pipelines, or SQLAlchemy 2.0 async queries.
- **Includes**:
  - [asyncio-perf.md](.agents/skills/python-backend-expert/references/asyncio-perf.md): Non-blocking asyncio patterns, TaskGroup structured concurrency, thread pool offloading (asyncio.to_thread).
  - [pydantic-fastapi.md](.agents/skills/python-backend-expert/references/pydantic-fastapi.md): Pydantic v2 schemas, lifespan context managers, and dependency injection patterns.

### 19. ui-ux-architect (/ui-ux-architect)
- **When to use**: Architecting design systems, DTCG tokens, state-complete components, or ensuring WCAG 2.2 AA compliance.
- **Includes**:
  - [dtcg-tokens.md](.agents/skills/ui-ux-architect/references/dtcg-tokens.md): Three-tier DTCG architecture, color/typography/spacing tokens, and zero-runtime CSS compilation.
  - [anti-slop-gates.md](.agents/skills/ui-ux-architect/references/anti-slop-gates.md): The 10 objective verification gates (Zero-Emoji, Intent Tokens, Contrast, States, Target Size, Overflow, Focus Trap, Copy, Hierarchy, Theme).

### 20. ui-ux-audit (/ui-ux-audit)
- **When to use**: Auditing UI templates, components, and stylesheets against anti-slop gates, contrast ratios, and touch targets.
- **Includes**:
  - [audit-matrix-template.md](.agents/skills/ui-ux-audit/references/audit-matrix-template.md): Compact Markdown audit matrix template and surgical 2-5 line diff remediation workflow.

### 21. agent-memory (/memory)
- **When to use**: Saving durable architectural decisions, recording resolved bug patterns from root-cause debugging, or retrieving project rules across sessions using Hindsight.
- **Includes**:
  - [memory-architecture.md](.agents/skills/agent-memory/references/memory-architecture.md): Biomimetic memory concepts (Facts, Observations, Mental Models) and hybrid search ranking (Vector, BM25, Graph, Temporal).

### 22. codegraph (/codegraph)
- **When to use**: Navigating codebases, finding callers/callees, assessing refactoring blast radius, or jumping to symbol definitions without full-file reading.
- **Includes**:
  - [codegraph-guide.md](.agents/skills/codegraph/references/codegraph-guide.md): AST knowledge graph structure, SQLite FTS5 index details, and token savings comparison.

---

## 🤖 Autonomous Subagents

Antigravity includes 10 specialized subagent profiles defined in `.agents/subagents/subagent-definitions.json`:

| Subagent Name | Role | Focus Area & Capabilities |
| :--- | :--- | :--- |
| **`code-reviewer`** | Senior Staff Code Reviewer | Multi-pass reviews focusing on security, performance, correctness, and architecture. |
| **`epistemic-debugger`** | Epistemic Debugger & Root Cause Specialist | Applied rationality, 5+ competing hypotheses, 5-Whys causal tree, Rule 0 failure stop. |
| **`python-specialist`** | Principal Python Systems Engineer | Modern Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, and asyncio event loops. |
| **`frontend-architect`** | Senior Frontend Architect | React 18/19 (RSC, Zustand), Angular 17/18/19 (Signals, OnPush, @defer), a11y. |
| **`ui-ux-architect`** | Senior Design System & UI/UX Architect | DTCG tokens, state completeness (6 states), WCAG 2.2 AA compliance, and 10 anti-slop gates. |
| **`fullstack-architect`** | Principal Fullstack Architect | E2E type-safety (OpenAPI/Zod), optimistic UI mutations, SSE/WebSocket streams. |
| **`db-architect`** | Senior Database Architect | Query execution plan tuning, index strategy, and zero-downtime migrations (PostgreSQL/MSSQL/SQLite). |
| **`dotnet-specialist`** | Principal .NET & C# Engineer | .NET 8/9, Clean Architecture, EF Core profiling, Dapper, and zero-allocation async programming. |
| **`node-specialist`** | Principal Node.js Engineer | Non-blocking event loop optimization, streams, Fastify/Express, and runtime resilience. |
| **`security-auditor`** | Application Security Auditor | OWASP Top 10, SQLi, BOLA/IDOR, secrets audit, and secure cryptographic comparisons. |

### How to Invoke Subagents
In Antigravity chat, invoke subagents using natural language or tool calls:
```text
"Invoke epistemic-debugger to find why the payment queue intermittently deadlocks."
"Invoke python-specialist to refactor the database access layer to async SQLAlchemy 2.0."
"Invoke ui-ux-architect to audit the checkout screen against anti-slop gates and contrast."
"Invoke code-reviewer to audit unstaged git changes."
"Launch db-architect to analyze this slow query execution plan."
```

---

## 📋 Unified Agent Skills & Slash Commands

All workflows have been consolidated into first-class, token-efficient skills under `.agents/skills/` adhering to modern Agent Skills standards (`agentskills.io` / Google Antigravity 2.0 / Claude). Each skill provides an instant slash command and natural language trigger:

| Skill | Slash Command | Focus Area & Trigger | Primary Deliverable |
| :--- | :--- | :--- | :--- |
| **Code Review** | `/code-review` | Inspects git diffs, runs test suites, checks security/performance checklists. | Ranked review table (`[Blocker]`, `[Perf]`, `[Arch]`, `[Suggestion]`). |
| **Investigate** | `/investigate` | Gathers ground truth, tests 5+ competing hypotheses, performs 5-Whys causal tree. | Formal investigation report + surgical regression fix. |
| **Create Skill** | `/create-skill` | Interactively interviews user to generate a new token-saving skill. | Scaffolds `.agents/skills/<name>/SKILL.md` + references. |
| **API Design** | `/api-design` | Designs RESTful contracts, DTO records, schema validation, RFC 7807 problem details. | API specification, DTOs, and route handlers. |
| **Architecture ADR** | `/architecture-design-adr` | Authors Architecture Decision Records (ADRs) and evaluates system trade-offs. | Formal ADR document with trade-off matrix. |
| **C# / .NET Expert** | `/csharp-dotnet-expert` | Writes or optimizes ASP.NET Core, EF Core queries, Dapper, async/await pipelines. | High-performance .NET code and query refactors. |
| **Database Architect** | `/database-architect` | Profiles query execution plans, indexes, connection pools, and non-blocking DDL. | Index strategy and query execution tuning. |
| **DB Migration** | `/database-migration` | Pre-migration lock safety check, non-blocking DDL (`CONCURRENTLY`), rollback script. | Safe migration script + rollback companion. |
| **E2E Feature** | `/e2e-feature` | Guides end-to-end delivery: DB migration -> backend API -> optimistic UI. | Fullstack integrated feature implementation. |
| **Frontend Architecture** | `/frontend-architecture-expert` | Designs React RSC/Zustand, Angular Signals/OnPush, eliminates re-renders. | Optimized component trees and state architecture. |
| **Frontend Audit** | `/frontend-audit` | Audits re-render churn, OnPush detection, lazy loading, and WCAG a11y. | Frontend optimization recommendations with code snippets. |
| **Fullstack Integration** | `/fullstack-integration-master` | Synchronizes contracts (OpenAPI/Zod), optimistic UI mutations, SSE/WebSocket streams. | End-to-end type-safe contract synchronization. |
| **Git Release** | `/git-release` | Verifies tests, analyzes Conventional Commits, calculates SemVer bump, writes notes. | Git tag and changelog release draft. |
| **Git Workflow** | `/git-workflow-master` | Git operations, interactive rebases, atomic commits, conflict resolution, SemVer tags. | Clean rebased branches, conflict resolutions. |
| **Node.js Expert** | `/nodejs-backend-expert` | Develops Fastify/Express/NestJS, event loop latency, streams backpressure, security. | Non-blocking server handlers and security middleware. |
| **Perf Audit** | `/perf-audit` | Scans for query bottlenecks, event loop blocking, memory leaks, thread starvation. | Targeted latency and throughput optimization plan. |
| **Python Audit** | `/python-audit` | Runs Ruff linter, Mypy strict type checks, inspects asyncio blocking calls. | Static analysis report and surgical fixes. |
| **Python Expert** | `/python-backend-expert` | FastAPI, asyncio TaskGroup pipelines, SQLAlchemy 2.0 async queries, Pydantic v2. | Production-grade async Python endpoints and models. |
| **UI/UX Architect** | `/ui-ux-architect` | Architecting design systems, DTCG tokens, state-complete components, WCAG 2.2 AA. | Token-driven CSS, complete component states. |
| **UI/UX Audit** | `/ui-ux-audit` | Executes 10 anti-slop gates, checks contrast ratios, target sizes, and state completeness. | Compact audit matrix (`[Gate]`, `[Target]`, `[Status]`, `[Fix]`) + surgical diffs. |

---

## ✍️ Meta-Skill: Authoring New Skills (`create-skill`)

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
