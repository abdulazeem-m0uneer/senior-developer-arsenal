---
name: code-review
description: Comprehensive senior software engineer code review procedure. Use when the user asks to review pull requests, inspect git diffs, audit code changes, or runs /code-review. Triggers on: "review code", "audit PR", "inspect diff", "/code-review". Do not use for frontend re-render audits (use frontend-audit) or UI/UX visual audits (use ui-ux-audit).
---

# Senior Code Review Procedure

This skill guides the agent through an exhaustive, senior-level code review across Node.js, C#, Python, PostgreSQL, SQLite, and MSSQL codebases.

---

## 1. When to Use This Skill

Activate this skill when:
- Reviewing pull requests, staged changes, or recent git commits (`HEAD~1..HEAD`).
- Auditing architectural integrity, security vulnerabilities (SQLi, IDOR, secrets), or concurrency hazards.
- The user runs the `/code-review` slash command or asks for code feedback.

*Boundary*: For frontend performance or re-render profiling, use `frontend-audit`. For UI/UX design tokens and anti-slop verification, use `ui-ux-audit`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Context & Diff Inspection
1. Inspect git status and changes:
   ```bash
   git status
   git diff HEAD~1..HEAD
   ```
2. Identify all modified architectural layers (Domain, Application Services, Repositories, API Endpoints, Migrations).

### Step 2: Multi-Dimensional Checklist Evaluation
Evaluate changes against the [Senior Review Checklist](./references/review-checklist.md):
- **Security**: Parameterized queries, authentication/authorization on endpoints, boundary input validation (Zod, FluentValidation, Pydantic).
- **Database**: N+1 queries, unindexed filters, lack of `AsNoTracking`, missing `TIMESTAMPTZ`, transaction lock contention.
- **Concurrency & Async**: CancellationToken flow, no `.Result`/`.Wait()` in C#, no synchronous I/O blocking Node.js/Python event loops.
- **Clean Architecture**: Dependency direction, single responsibility, no domain leaks.

### Step 3: Structure the Review Feedback
Format the final review report according to the [Feedback Rubric](./references/feedback-rubric.md):
- **Executive Verdict**: `Approved`, `Approved with Suggestions`, or `Changes Requested`.
- **Ranked Findings**: Grouped strictly by:
  - `🚨 [Blocker]`: Must resolve before merge (data loss, security vulnerabilities, fatal bugs).
  - `⚡ [Performance]`: Query bottlenecks, event loop lag, memory bloat.
  - `🏗️ [Architecture]`: Layer violations, tight coupling, leaky abstractions.
  - `💡 [Suggestion / Nit]`: Idioms, readability, naming conventions.
- **Surgical Code Diffs**: Provide targeted 2–5 line diffs for fixes.

---

## 3. Verification Protocol

Before finalizing review output:
1. Verify build and static analysis pass:
   - .NET: `dotnet build --configuration Release`
   - Node.js: `npm run lint && npm run typecheck`
   - Python: `ruff check . && mypy .`
2. Run automated test suite (`dotnet test`, `npm test`, or `pytest`).

---

## 4. ⚡ Token-Saving Execution Rule

- **Zero Fluff**: Start immediately with the Executive Verdict and Findings table.
- **Surgical Snippets**: Never reprint unchanged files. Output only minimal diffs.
