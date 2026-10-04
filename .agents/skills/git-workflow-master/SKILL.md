---
name: git-workflow-master
description: 'Advanced Git operations, rebase workflows, branch management, conventional commits, and pull request crafting. Use when formatting commits, rebasing onto main, resolving merge conflicts, crafting release tags, or auditing git history. Triggers on: "git rebase", "merge conflict", "conventional commits", "squash commits", "git bisect". Do not use for automated release version bumping and tag publishing (use git-release).'
---

# Git Workflow & Advanced Operations Skill

This skill guides the agent through advanced Git operations, maintaining a clean linear history, standardizing Conventional Commits, and safely resolving branch divergence.

---

## 1. When to Use This Skill

Activate this skill when:
- Preparing commits following the Conventional Commits specification.
- Rebasing a feature branch onto `main` and squashing intermediate commits.
- Resolving complex merge conflicts with precision and zero code regression.
- Drafting clean Pull Request descriptions and release notes.
- Diagnosing regressions using `git bisect`.

*Boundary*: For automated SemVer calculation, release tagging, and changelog drafting, use `git-release`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Atomic Conventional Commits
Consult: [Conventional Commits Reference](./references/conventional-commits.md)
Format every commit message with type, optional scope, and imperative summary:
```bash
git commit -m "feat(billing): support stripe webhook idempotency keys" -m "Saves processed event IDs into PostgreSQL table with unique constraint to prevent duplicate processing during network retries."
```

### Step 2: Clean Linear Rebase Workflow
Keep feature branches up to date with `main` without creating noisy merge commits:
```bash
# 1. Fetch latest changes from remote
git fetch origin main

# 2. Rebase feature branch on top of main
git rebase origin/main

# 3. If conflicts arise, inspect conflicting files
git status
# ... resolve conflicts surgically ...
git add <resolved-files>
git rebase --continue
```

### Step 3: Interactive Rebase & Squashing
Before opening a PR, squash noisy work-in-progress commits into atomic units:
```bash
git rebase -i HEAD~4
```

### Step 4: Safe Merge Conflict Resolution Protocol
1. **Never guess**: Inspect both incoming (`THEIRS`) and current (`OURS`) changes.
2. **Preserve invariants**: Ensure both intended changes coexist cleanly.
3. **Verify build and tests**: Run tests immediately after conflict resolution before completing the rebase.

---

## 3. Verification Protocol

1. Verify commit messages conform to Conventional Commits: header length $\le 100$ characters, imperative mood, lowercase type.
2. Verify clean git status: `git status` reports nothing to commit, working tree clean.
3. Verify linear log: `git log --graph --oneline -n 5` demonstrates clean linear history without merge bubbles.

---

## 4. ⚡ Token-Saving Execution Rule

- **Command-First**: Provide direct Git CLI commands. Avoid lengthy explanations of standard Git flags unless asked.
- **Log Summaries**: Use `git log --oneline -n <N>` to prevent context window saturation.
