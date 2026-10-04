# 🚀 Senior Developer Arsenal

[![CI](https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/actions/workflows/ci.yml/badge.svg)](https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/actions/workflows/ci.yml)
[![Stars](https://img.shields.io/github/stars/abdulazeem-m0uneer/senior-developer-arsenal?style=flat)](https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/stargazers)
[![Forks](https://img.shields.io/github/forks/abdulazeem-m0uneer/senior-developer-arsenal?style=flat)](https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/network/members)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An enterprise-grade, polyglot AI engineering toolkit for **Senior Software Engineers**, **System Architects**, and **Fullstack Leaders** working with **Python (FastAPI / SQLAlchemy 2.0)**, **React (18/19)**, **Angular (17/18/19)**, **Node.js / TypeScript**, **C# / .NET 8/9**, **PostgreSQL**, **MSSQL**, **SQLite**, and **Git**.

One source of truth (`.agents/`), usable from **any AI coding agent**: Claude Code, Codex CLI, OpenCode, Cursor, Windsurf, GitHub Copilot, Gemini CLI, and Google Antigravity. Deploy it per project or globally with strict **Token Conservation Protocols**, **Applied Rationality**, and **Context Engineering Guardrails**.

---

## 📈 GitHub Trending Rank

<!-- BEGIN trending -->
| Period | Rank on [GitHub Trending](https://github.com/trending) |
| :--- | :--- |
| Today | Not trending |
| This week | Not trending |
| This month | Not trending |

_Last change detected: 2026-10-04 (UTC). Checked daily by `.github/workflows/trending.yml`._
<!-- END trending -->

GitHub offers no trending API, so [`scripts/trending_rank.py`](scripts/trending_rank.py) reads the public trending page once a day and rewrites this table only when a rank changes.

---

## 🎯 What This Toolkit Provides

| Component | Quantity | Purpose |
| :--- | :---: | :--- |
| **Rules** | 12 | Enforce senior engineering standards: SOLID, a 1000-line file cap, mandatory tests with every change, plus Python, Node.js, C#, Frontend, UI/UX, Databases, Git, Token Frugality, and Defensive Epistemology. |
| **Specialized Skills** | 30 | Actionable runbooks following the Agent Skills standard (`SKILL.md` + progressive `references/`) with slash commands and negative triggers. |
| **Autonomous Subagents** | 13 | Dedicated personas (`code-reviewer`, `qa-engineer`, `test-engineer`, `security-auditor`, `devops-engineer`, `epistemic-debugger`, and stack specialists). |
| **Supported Agents** | 8 | Claude Code (plugin), Codex CLI, OpenCode, Cursor, Windsurf, GitHub Copilot, Gemini CLI, Antigravity. |
| **Installers** | 2 | PowerShell (`install.ps1`) and Bash (`install.sh`) with identical options, non-destructive installs, and clean uninstall. |

---

## 🔥 Token Conservation & Defensive Epistemology Protocol

The arsenal operates with strict **Token Frugality & Epistemic Hygiene Guardrails** built into every rule, skill, and subagent:

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
├── .agents/                     # Single source of truth (edit here only)
│   ├── rules/                   # 12 rules with trigger/description/globs frontmatter
│   ├── skills/<name>/           # 30 skills: SKILL.md + references/ (+ scripts/ where bundled)
│   ├── subagents/               # subagent-definitions.json + prompts/<name>.md
│   └── mcp/servers.json         # Canonical MCP server definitions (CodeGraph, Hindsight)
├── dist/                        # GENERATED per-agent output (do not edit)
│   ├── <agent>/agents|rules/    # Native subagent and rule formats for each agent
│   ├── mcp/<flavor>/            # MCP server entries in each client's config shape
│   └── manifest.tsv             # What each installer copies where
├── .claude-plugin/              # GENERATED Claude Code plugin + marketplace manifests
├── plugins/                     # GENERATED opt-in Claude plugins for the MCP servers
├── scripts/
│   ├── build.py                 # Generator: --validate, --check, or write dist/
│   ├── mcp_merge.py             # Safe JSON merge for MCP configs (used by install.sh)
│   ├── trending_rank.py         # Updates the trending table in this README
│   ├── arsenal                  # CLI wrapper over install.sh
│   └── arsenal.ps1              # CLI wrapper over install.ps1
├── tests/                       # smoke.sh and smoke.ps1 installer tests
├── .github/workflows/           # ci.yml (lint + smoke tests) and trending.yml
├── .githooks/commit-msg         # Conventional Commits validator hook
├── docs/                        # TARGETS.md, UBUNTU-INTEGRATION.md
├── AGENTS.md                    # Root instruction file read by every agent
├── GEMINI.md                    # Imports AGENTS.md for Gemini CLI / Antigravity
├── install.sh / install.ps1     # Installers (same options on both)
├── CONTRIBUTING.md, LICENSE, VERSION
└── README.md
```

---

## 🛠️ Installation

### Claude Code (plugin)

```text
/plugin marketplace add abdulazeem-m0uneer/senior-developer-arsenal
/plugin install arsenal@senior-developer-arsenal
```

Skills appear as `/arsenal:<skill>` and subagents as `arsenal:<name>`. A plugin cannot ship rules, so add them with the installer: `./install.sh --global --target claude`. Optional MCP servers: `/plugin install arsenal-codegraph@senior-developer-arsenal` and `/plugin install arsenal-hindsight@senior-developer-arsenal`.

### Every other agent (installer)

```bash
git clone https://github.com/abdulazeem-m0uneer/senior-developer-arsenal.git
cd senior-developer-arsenal

# Linux / macOS / WSL
./install.sh --global --target all                              # every supported agent, user-wide
./install.sh --project ~/code/my-api --target cursor,copilot    # one repository
./install.sh --project ~/code/my-api --target codex --link      # live symlinks

# Windows PowerShell (5.1 or 7+)
.\install.ps1 -Global -Target all
.\install.ps1 -Project "C:\repos\my-api" -Target cursor,copilot
```

`--target` accepts `antigravity` (default, so existing commands behave as before), `gemini`, `claude`, `codex`, `opencode`, `cursor`, `windsurf`, `copilot`, or `all`.

| Agent | Skills | Subagents | Rules |
| :--- | :--- | :--- | :--- |
| **Claude Code** | plugin | plugin | `.claude/rules/arsenal/` |
| **Codex CLI** | `.agents/skills/` | `.codex/agents/*.toml` | `AGENTS.md` index + `.agents/rules/` |
| **OpenCode** | `.agents/skills/` | `.opencode/agents/*.md` | `AGENTS.md` index + `.agents/rules/` |
| **Cursor** | `.agents/skills/` | `.cursor/agents/*.md` | `.cursor/rules/*.mdc` |
| **Windsurf** | `.agents/skills/` | not supported by the agent | `.windsurf/rules/*.md` |
| **GitHub Copilot** | `.agents/skills/` | `.github/agents/*.agent.md` | `.github/instructions/*.instructions.md` |
| **Gemini CLI** | `.agents/skills/` | `.gemini/agents/*.md` | `GEMINI.md` importing `AGENTS.md` |
| **Antigravity** | `.agents/skills/` (`~/.gemini/config/skills/` globally) | `.agents/agents/*.md` | `.agents/rules/` |

Global and project paths for every agent are listed in [docs/TARGETS.md](docs/TARGETS.md).

### Installer behavior

| Option (`install.sh` / `install.ps1`) | Effect |
| :--- | :--- |
| `--link` / `-Symlink` | Link each item to this repository instead of copying. |
| `--force` / `-Force` | Replace files the installer did not create. Without it, your own files are skipped and reported. |
| `--uninstall` / `-Uninstall` | Remove exactly what the installer created for the chosen targets. |
| `--dry-run` / `-DryRun` | Print the plan without touching anything. |
| `--status` / `-Status` | Show how many items are present per agent. |
| `--cli` / `-Cli` | Put the `arsenal` command on your PATH (`arsenal sync`, `arsenal link .`, `arsenal remove .`). |

- **Non-destructive**: installs item by item, never deletes a directory it does not own, and adds a marked block to an existing `AGENTS.md` instead of replacing it (line endings, encoding, and permissions are kept).
- **Skips what it cannot change safely**: instruction files that are symlinks, are not UTF-8, or have damaged block markers are reported and left untouched, as is any destination whose parent folder links back into the arsenal.
- **Project paths**: any folder except your home directory (use `--global` for that) and the arsenal repository itself.
- **Upgrading from a pre-1.0 install**: files copied by the old installer are not recognized as owned; run once with `--force`.

### Scan a repository to pick the right skills

After installing into a project, ask the agent to run the `repo-scan` skill, or run its script directly:

```bash
python .agents/skills/repo-scan/scripts/detect_stack.py /path/to/project
```

It detects the stack (Node.js, React, Angular, .NET, Python, SQL, Docker, CI, tests) and reports which skills, rules, and subagents apply, plus gaps such as missing tests or files over 1000 lines.

### Conventional Commits hook

```bash
git config core.hooksPath .githooks
```

### MCP servers (optional)

| Server | Flag | Requirement |
| :--- | :--- | :--- |
| [CodeGraph](https://github.com/colbymchenry/codegraph) AST intelligence | `--codegraph` / `-CodeGraph` | `npm install -g @colbymchenry/codegraph`, then `codegraph init` in each project. |
| [Hindsight](https://github.com/vectorize-io/hindsight) long-term memory | `--hindsight` / `-Hindsight` (`--bank <id>`) | A Hindsight server on `http://localhost:8888`. |

```bash
./install.sh --global --target cursor,codex --codegraph --hindsight
```

The server entry is merged into each agent's MCP config. Existing entries are preserved, a timestamped backup is written, and a config that cannot be parsed is left untouched. CodeGraph also ships its own `codegraph install`, which additionally writes agent instructions.

Memory helper bundled with the `agent-memory` skill:

```bash
python .agents/skills/agent-memory/scripts/memory.py retain --bank "my-project" --content "We enforce UUIDv7 and WAL mode on SQLite."
python .agents/skills/agent-memory/scripts/memory.py recall --bank "my-project" --query "What are our SQLite settings?"
```

---

## 📐 Engineering Standards & Rules (Always-On)

Three core rules plus the testing rule are always on; the rest load by file glob or by relevance (see each rule's frontmatter):

| Rule File | Scope & Mandate | Red Flags / Forbidden Patterns |
| :--- | :--- | :--- |
| **[`token-conservation.md`](.agents/rules/token-conservation.md)** | Enforces strict token economy, zero conversational fluff, surgical 2-5 line diffs, and progressive reference loading. | Full-file reprinting, conversational filler, broad un-targeted file reads. |
| **[`defensive-epistemology.md`](.agents/rules/defensive-epistemology.md)** | Applied rationality, Rule 0 failure stop, prediction protocol (`EXPECT`/`MATCHES`), Chesterton's Fence, anti-sycophancy. | Silent tool retries, "this should work" traps, deleting ununderstood code, blind flailing. |
| **[`senior-engineer-core.md`](.agents/rules/senior-engineer-core.md)** | **SOLID always**, **1000-line file cap**, tests with every change, Clean Architecture, Result pattern error handling, defensive boundary validation. | SOLID violations, files over 1000 lines, framework bleed into Domain, silent exception swallowing. |
| **[`testing-standards.md`](.agents/rules/testing-standards.md)** | Every feature, bug fix, refactor, or other change ships with tests; regression test first for bug fixes; deterministic, behavior-focused tests. | Untested changes, skipped or deleted tests, vacuous assertions, flaky tests. |
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

The arsenal includes 30 specialized skills conforming to the Agent Skills standard (agentskills.io), featuring isolated progressive disclosure references (`references/`), slash commands, and negative triggers:

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

### 23. security-audit (/security-audit)
- **When to use**: Security audits, vulnerability hunts, and pre-release hardening (OWASP Top 10, injection, IDOR/BOLA, secrets, SSRF, supply chain).
- **Includes**: [vulnerability-patterns.md](.agents/skills/security-audit/references/vulnerability-patterns.md), [audit-checklist.md](.agents/skills/security-audit/references/audit-checklist.md).

### 24. test-strategy (/test-strategy)
- **When to use**: Designing a test suite, choosing unit vs integration vs end-to-end scope, test doubles, and fixing flaky tests.
- **Includes**: [test-layering-and-doubles.md](.agents/skills/test-strategy/references/test-layering-and-doubles.md), [edge-cases-and-flakiness.md](.agents/skills/test-strategy/references/edge-cases-and-flakiness.md).

### 25. test-every-change (/test-every-change)
- **When to use**: Every code change. Maps each changed behavior to required tests: regression test first for bug fixes, happy/error/edge cases for features, characterization tests before refactors.

### 26. qa-engineer (/qa-engineer)
- **When to use**: Acceptance criteria, test plans and test cases, exploratory testing charters, bug reports, and release sign-off.

### 27. definition-of-done (/definition-of-done)
- **When to use**: Before reporting any feature complete. Builds the per-feature Definition of Done and verifies every item with evidence, ending in a DONE / NOT DONE verdict.

### 28. deep-review (/deep-review)
- **When to use**: Exhaustive, multi-pass, evidence-verified review of a whole change or subsystem, with a false-positive elimination pass and a re-review loop after fixes.

### 29. repo-scan (/repo-scan)
- **When to use**: Onboarding the arsenal into a repository. Detects the stack and reports which skills, rules, and subagents apply, plus gaps.
- **Includes**: bundled `scripts/detect_stack.py`.

### 30. devops-ci (/devops-ci)
- **When to use**: Dockerfile hardening, GitHub Actions pipelines, caching, secrets handling, deploy strategies, and rollback.
- **Includes**: [dockerfile-hardening.md](.agents/skills/devops-ci/references/dockerfile-hardening.md), [pipeline-and-deploy.md](.agents/skills/devops-ci/references/pipeline-and-deploy.md).

---

## 🤖 Autonomous Subagents

The arsenal defines 13 specialized subagent profiles in `.agents/subagents/subagent-definitions.json`; `scripts/build.py` converts them into each agent's native format:

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
| **`security-auditor`** | Application Security Auditor | OWASP Top 10, SQLi, BOLA/IDOR, secrets audit, and secure cryptographic comparisons. Read-only. |
| **`test-engineer`** | Senior Test Engineer (SDET) | Test strategy, unit/integration/e2e authoring, edge cases, flaky-test diagnosis. |
| **`qa-engineer`** | Senior QA Engineer | Acceptance criteria, test plans, exploratory and regression testing, release sign-off. |
| **`devops-engineer`** | Senior DevOps & Platform Engineer | Dockerfiles, GitHub Actions, caching, secrets, deploy and rollback strategies. |

### How to Invoke Subagents
In any agent chat, invoke subagents using natural language:
```text
"Invoke epistemic-debugger to find why the payment queue intermittently deadlocks."
"Invoke python-specialist to refactor the database access layer to async SQLAlchemy 2.0."
"Invoke ui-ux-architect to audit the checkout screen against anti-slop gates and contrast."
"Invoke code-reviewer to audit unstaged git changes."
"Launch db-architect to analyze this slow query execution plan."
```

---

## 📋 Unified Agent Skills & Slash Commands

All workflows have been consolidated into first-class, token-efficient skills under `.agents/skills/` adhering to the Agent Skills standard (`agentskills.io`). Each skill provides a slash command (prefixed `arsenal:` in the Claude Code plugin) and natural language triggers:

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
| **Agent Memory** | `/memory` | Retains and recalls architectural decisions through Hindsight. | Stored and recalled project memory. |
| **CodeGraph** | `/codegraph` | Structural code navigation: callers, callees, impact, symbol lookup. | Precise `file:line` pointers instead of file reads. |
| **Security Audit** | `/security-audit` | OWASP Top 10, injection, authz, secrets, SSRF, supply chain. | Severity-ranked vulnerability table with fixes. |
| **Test Strategy** | `/test-strategy` | Test pyramid, layering, doubles, flaky-test diagnosis. | Test plan and authored tests. |
| **Test Every Change** | `/test-every-change` | Derives and writes the tests each change requires. | Tests for the diff plus a green full suite. |
| **QA Engineer** | `/qa-engineer` | Acceptance criteria, test cases, exploratory testing, sign-off. | Test plan, bug reports, release sign-off. |
| **Definition of Done** | `/definition-of-done` | Builds and verifies the per-feature Definition of Done. | Evidence-backed DONE / NOT DONE verdict. |
| **Deep Review** | `/deep-review` | Multi-pass, evidence-verified review with a re-review loop. | Verified, severity-ranked findings. |
| **Repo Scan** | `/repo-scan` | Detects the stack and maps it to arsenal skills, rules, subagents. | Applicability report plus gaps. |
| **DevOps & CI** | `/devops-ci` | Dockerfiles, pipelines, deploy and rollback strategies. | Hardened Dockerfile and workflow changes. |

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

```bash
arsenal update --target all          # git pull, then reinstall globally
# or
git pull && ./install.sh --global --target all
```

Claude Code plugin users: `/plugin marketplace update senior-developer-arsenal`.

Contributors edit `.agents/` only, then run `python3 scripts/build.py` and commit the regenerated `dist/`. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 🧭 Recommended Next Skills

Candidates not yet in the arsenal, in rough priority order:

| Skill | Why |
| :--- | :--- |
| `accessibility-audit` | Dedicated WCAG 2.2 AA audit with assistive-technology test scripts, beyond the UI/UX gates. |
| `observability` | Structured logging, metrics, tracing (OpenTelemetry), SLOs, and alert design. |
| `incident-response` | Production triage runbook, mitigation-first workflow, and blameless postmortem template. |
| `dependency-upgrade` | Safe major-version upgrades: changelog triage, codemods, staged rollout, CVE response. |
| `refactor-legacy` | Characterization tests, strangler-fig migration, and seam extraction for untested code. |
| `threat-model` | STRIDE-based design-time threat modeling to complement the code-level security audit. |
| `docs-writer` | README, API reference, runbook, and changelog authoring to a consistent standard. |
| `kubernetes-ops` | Manifests, Helm, resource limits, probes, and rollout debugging. |
| `data-privacy` | PII inventory, retention, GDPR/CCPA data-subject request handling. |
| `mobile-expert` | React Native / Flutter architecture, performance, and release pipelines. |

Scaffold any of them with the `create-skill` skill.

---

## 📄 License & Attribution

Crafted for high-performance software engineering teams. Released under the [MIT License](LICENSE): free to use, customize, and extend across all personal and enterprise repositories.
