---
name: git-workflow-master
description: Advanced Git operations, rebase workflows, branch management, conventional commits, and pull request crafting. Use when formatting commits, rebasing onto main, resolving merge conflicts, crafting release tags, or auditing git history.
---

# Git Workflow & Release Engineering Skill

This skill guides the agent through advanced Git operations, maintaining a clean linear history, standardizing Conventional Commits, and safely resolving branch divergence.

---

## 1. When to Use This Skill

Activate this skill when:
- Preparing commits following the Conventional Commits specification.
- Rebasing a feature branch onto `main` and squashing intermediate commits.
- Resolving complex merge conflicts with precision and zero code regression.
- Drafting clean Pull Request descriptions and release notes.
- Diagnosing regressions using `git bisect`.

---

## 2. Advanced Git Workflows

### A. Atomic Conventional Commits
Consult: [Conventional Commits Reference](./references/conventional-commits.md)
Format every commit message with type, optional scope, imperative description, and detailed body:
```bash
git commit -m "feat(billing): support stripe webhook idempotency keys" -m "Saves processed event IDs into PostgreSQL table with unique constraint to prevent duplicate processing during network retries."
```

### B. Clean Linear Rebase Workflow
Keep feature branches up to date with `main` without creating noisy merge commits:
```bash
# 1. Fetch latest changes from remote
git fetch origin main

# 2. Rebase feature branch on top of main
git rebase origin/main

# 3. If conflicts arise, inspect conflicting files
git status
# ... resolve conflicts in editor ...
git add <resolved-files>
git rebase --continue
```

### C. Interactive Rebase & Squashing
Before opening a PR or merging, squash noisy work-in-progress commits:
```bash
# Rebase the last 4 commits interactively
git rebase -i HEAD~4
```

### D. Safe Merge Conflict Resolution Protocol
1. **Never guess**: Inspect both the incoming changes (`THEIRS` / upstream) and your local branch changes (`OURS`).
2. **Preserve invariants**: Ensure both intended fixes coexist cleanly.
3. **Verify build and tests**: Run `dotnet test` or `npm test` immediately after conflict resolution before continuing the rebase.
