---
name: senior-code-review
description: Comprehensive senior software engineer code review procedure. Use when reviewing pull requests, inspecting code changes, auditing git diffs, or evaluating architectural soundness, security, and performance.
---

# Senior Code Review Procedure

This skill guides the agent through an exhaustive, senior-level code review process across Node.js, C#, PostgreSQL, SQLite, and MSSQL codebases.

---

## 1. Review Objectives

As a Senior / Staff Engineer, your review goes beyond style and syntax:
1. **Defect & Edge Case Discovery**: Identify subtle concurrency races, null dereferences, transaction leaks, and boundary calculation errors.
2. **Security & Vulnerability Auditing**: Screen for SQL injection, mass-assignment vulnerabilities, broken authorization (IDOR), and sensitive data leaks.
3. **Performance & Scalability**: Spot N+1 queries, unindexed table scans, blocking event loop tasks, and thread pool starvation.
4. **Architectural Coherence**: Ensure boundaries between presentation, domain, and data access are strictly honored.

---

## 2. Review Workflow

### Step 1: Context & Diff Inspection
1. Run `git status` and `git diff` (or inspect target files) to analyze the scope of change:
   ```bash
   git diff HEAD~1..HEAD
   ```
2. Understand the feature's intent and identify all modified layers (API endpoints, business services, database migrations).

### Step 2: Systematic Checklist Evaluation
Evaluate the changes against the detailed [Senior Review Checklist](./references/review-checklist.md):
- **Architecture**: Single Responsibility, proper dependency injection, clean layering.
- **Security**: Parameterization, authorization, input validation.
- **Data Access**: Query efficiency, indexing, transaction boundary isolation.
- **Language Idioms**: Modern C# async patterns, Node.js non-blocking principles.
- **Testing**: Adequate test coverage for positive, negative, and edge scenarios.

### Step 3: Structure the Review Feedback
Format the final review report according to the [Feedback Rubric](./references/feedback-rubric.md):
- **Executive Summary**: High-level verdict (`Approved`, `Approved with Suggestions`, or `Changes Requested`).
- **Severity-Ranked Findings**: Group observations by severity:
  - `🚨 [Blocker]`: Must be resolved before merge (bugs, data loss, security risks).
  - `⚡ [Performance]`: Query bottlenecks, resource leaks, memory bloat.
  - `🏗️ [Architecture]`: Layer violations, bad abstractions, tight coupling.
  - `💡 [Suggestion / Nit]`: Code readability, minor idioms, naming.
- **Concrete Code Snippets**: Provide exact replacement code diffs illustrating the recommended fix.
