---
name: code-review
description: Comprehensive workflow to conduct a senior software engineer code review on staged or recent git changes.
---

# Senior Code Review Workflow

Follow this procedure whenever requested to perform a code review or audit changes.

## Steps

1. **Inspect Git Context**:
   - Check status and recent diffs:
     ```bash
     git status
     git diff HEAD~1..HEAD
     ```
   - If specific files or PR branch are specified by the user, read the target files directly.

2. **Run Static Checks**:
   - For .NET / C#:
     ```powershell
     dotnet build --configuration Release
     ```
   - For Node.js / TypeScript:
     ```bash
     npm run lint
     npm run typecheck
     ```

3. **Systematic Multi-Dimensional Audit**:
   - **Security**: Verify parameterized queries (no SQLi), authentication/authorization on all endpoints, no secrets committed, inputs validated with Zod/FluentValidation.
   - **Database**: Check for N+1 queries, unindexed filters, lack of `AsNoTracking` or `TIMESTAMPTZ`, long transaction locks.
   - **Concurrency & Async**: Verify cancellation token propagation, no `.Result`/`.Wait()` in C#, no synchronous I/O blocking Node.js event loop.
   - **Clean Architecture**: Verify boundaries (Domain vs Application vs Infrastructure/Controllers).

4. **Generate Structured Review Report**:
   - Produce a markdown report using the senior feedback rubric:
     - **Verdict**: [ Approved | Approved with Suggestions | Changes Requested ]
     - **Summary**: Concise high-level appraisal (max 2 sentences).
     - **Ranked Findings**: Grouped by `🚨 [Blocker]`, `⚡ [Performance]`, `🏗️ [Architecture]`, and `💡 [Suggestion]`.
     - **Concrete Diffs**: Exact 2-5 line snippets for fixes. Never paste full unchanged files.

5. **Token Conservation Mandate**:
   - Omit generic review intros and outros. Output only the structured report.

