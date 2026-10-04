# Subagents for Senior Engineers

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
6. **`frontend-architect`** (`prompts/frontend-architect.md`):
   - **Role**: Senior Frontend Architect.
   - **Focus**: React 18/19 (RSC, Zustand), Angular 17/18/19 (Signals, OnPush, @defer), a11y.
7. **`fullstack-architect`** (`prompts/fullstack-architect.md`):
   - **Role**: Principal Fullstack Architect.
   - **Focus**: E2E type-safety (OpenAPI/Zod), optimistic UI mutations, SSE/WebSocket streams.
8. **`python-specialist`** (`prompts/python-specialist.md`):
   - **Role**: Principal Python Systems Engineer.
   - **Focus**: Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, asyncio event loops.
9. **`epistemic-debugger`** (`prompts/epistemic-debugger.md`):
   - **Role**: Epistemic Debugger & Root Cause Specialist.
   - **Focus**: Applied rationality, 5+ competing hypotheses, 5-Whys causal tree, Rule 0 failure stop, Chesterton's Fence.
10. **`ui-ux-architect`** (`prompts/ui-ux-architect.md`):
   - **Role**: Senior Design System & UI/UX Architect.
   - **Focus**: DTCG tokens, WCAG 2.2 AA compliance, state-complete components, 10 anti-slop verification gates, and zero-emoji enforcement.
11. **`test-engineer`** (`prompts/test-engineer.md`):
   - **Role**: Senior Test Engineer (SDET).
   - **Focus**: Test strategy, unit/integration/e2e authoring, edge-case enumeration, flaky-test diagnosis.
12. **`devops-engineer`** (`prompts/devops-engineer.md`):
   - **Role**: Senior DevOps & Platform Engineer.
   - **Focus**: Dockerfile hardening, GitHub Actions pipelines, caching, secrets, deploy and rollback strategies.
13. **`qa-engineer`** (`prompts/qa-engineer.md`):
   - **Role**: Senior QA Engineer.
   - **Focus**: Acceptance criteria, test plans, exploratory and regression testing, bug reports, release sign-off.

---

## Source Format and Generated Outputs

`subagent-definitions.json` plus `prompts/<name>.md` are the single source of truth. `scripts/build.py` converts them into each agent's native format under `dist/`:

| Agent | Generated file | Installed to |
| :--- | :--- | :--- |
| Claude Code | `dist/claude/agents/<name>.md` | loaded by the `arsenal` plugin |
| Codex CLI | `dist/codex/agents/<name>.toml` | `.codex/agents/` |
| OpenCode | `dist/opencode/agents/<name>.md` | `.opencode/agents/` |
| Cursor | `dist/cursor/agents/<name>.md` | `.cursor/agents/` |
| GitHub Copilot | `dist/copilot/agents/<name>.agent.md` | `.github/agents/` |
| Antigravity | `dist/antigravity/agents/<name>.md` | `.agents/agents/` |
| Gemini CLI | `dist/gemini/agents/<name>.md` | `.gemini/agents/` |

Never edit files under `dist/`; edit the source here and run `python3 scripts/build.py`.

## How to Invoke

Prompt the primary agent directly:
> *"Invoke the code-reviewer subagent to audit the changes between main and this branch."*
> *"Launch the db-architect subagent to inspect this query and suggest PostgreSQL indexes."*
