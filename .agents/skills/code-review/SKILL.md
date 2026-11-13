---
name: code-review
description: 'Senior code review of a change. Use to review a pull request, inspect a git diff, or audit code changes. Triggers: "review code", "audit PR", "inspect diff", /code-review. Not for an exhaustive multi-pass audit (use deep-review), frontend re-render audits (use frontend-audit) or UI/UX visual audits (use ui-ux-audit).'
---

# Senior Code Review Procedure

This skill guides the agent through an exhaustive, senior-level code review across Node.js, C#, Python, PostgreSQL, SQLite, and MSSQL codebases.

---

## 1. When to Use This Skill

Activate this skill when:
- Reviewing pull requests, a branch, or staged and uncommitted changes.
- Auditing architectural integrity, security vulnerabilities (SQLi, IDOR, secrets), or concurrency hazards.
- The user runs the `/code-review` slash command or asks for code feedback.

*Boundary*: For frontend performance or re-render profiling, use `frontend-audit`. For UI/UX design tokens and anti-slop verification, use `ui-ux-audit`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Context & Diff Inspection
1. Fix the scope. A range or pull request the user names wins; otherwise review everything the branch adds over the default branch, committed or not:
   ```bash
   git status --short                                   # untracked files are in scope too: read them
   for base in "$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD)" origin/main origin/master main master; do
     [ -n "$base" ] && git rev-parse --verify --quiet "$base" >/dev/null && break; base=
   done
   [ -n "$base" ] && git diff "$(git merge-base "$base" HEAD)"   # branch commits plus staged and unstaged changes
   ```
   The default branch is the one `origin/HEAD` points to, else `origin/main`, `origin/master`, `main`, `master` in that order. When `base` stays empty (no remote and no such branch), do not run the diff: ask the user for the base. To fix a missing `origin/HEAD` run `git remote set-head origin --auto`, or ask `gh repo view --json defaultBranchRef --jq .defaultBranchRef.name`. Only when that diff is empty and the tree is clean (HEAD is on the default branch) review the last commit: `git diff HEAD~1..HEAD`.
2. Identify all modified architectural layers (Domain, Application Services, Repositories, API Endpoints, Migrations).
3. Record the base and the commit hash under review (`git rev-parse HEAD`); the verdict applies to that commit plus the uncommitted changes listed in step 1, and to nothing later.

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
  - `[Blocker]`: Must resolve before merge (data loss, security vulnerabilities, fatal bugs).
  - `[Perf]`: Query bottlenecks, event loop lag, memory bloat.
  - `[Arch]`: Layer violations, tight coupling, leaky abstractions.
  - `[Nit]`: Idioms, readability, naming conventions.
- **Surgical Code Diffs**: Provide targeted 2–5 line diffs for fixes.
- **Not Checked**: State plainly what was not reviewed (files skipped, tests not run, behaviour not exercised).

### Step 4: Re-Review After Fixes
A fix is new code. Review the new diff with the same checklist, try to refute each earlier finding against the fixed code, and reissue the verdict with the new commit hash.

### Step 5: When the Review Is Addressed to You
Consult: [Receiving Review Protocol](./references/receiving-review-protocol.md)
1. Read all findings before acting on any; restate each requirement in your own words or ask. Anything unclear blocks all implementation, not only that item.
2. Verify each finding against the code before implementing; push back with evidence when it is wrong for this codebase. The fix is the acknowledgement: no thanks, no praise.
3. Fix in order: blocking, trivial, complex; one at a time, test each; reply in the comment thread, not as a top-level comment; re-request review on the new hash.

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

**Next**: on `Approved` (fixes re-reviewed), run `quality-gate`; a large or high-risk change goes through `deep-review` first.
