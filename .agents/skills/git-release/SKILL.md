---
name: git-release
description: Release preparation workflow to verify build & tests, inspect commit history, bump version according to SemVer, and draft release notes. Use when the user asks to prepare a release, bump versions, cut a tag, or runs /git-release. Triggers on: "prepare release", "cut tag", "bump version", "release notes", "/git-release". Do not use for interactive git rebasing or merge conflict resolution (use git-workflow-master).
---

# Production Release Preparation Skill

Follow this procedure when cutting a milestone release, calculating SemVer version bumps, and authoring release changelogs.

---

## 1. When to Use This Skill

Activate this skill when:
- Preparing a production release tag from clean branch commits.
- Evaluating Conventional Commits history to determine Major, Minor, or Patch SemVer bumps.
- Drafting structured release notes and changelog summaries.
- The user runs the `/git-release` slash command.

*Boundary*: For interactive git rebasing, commit squashing, or resolving git merge conflicts, use `git-workflow-master`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Pre-Release Working Tree & Test Verification
1. Ensure working directory is clean: `git status`.
2. Sync with upstream: `git fetch origin main && git rebase origin/main`.
3. Execute full automated test suite:
   - C#: `dotnet test --configuration Release`
   - Node.js: `npm test && npm run build`
   - Python: `pytest`

### Step 2: SemVer Calculation
Consult: [Release Preparation & SemVer Guide](./references/release-guide.md)
1. Inspect commit range since last tag: `git log $(git describe --tags --abbrev=0)..HEAD --oneline`.
2. Determine bump level:
   - `BREAKING CHANGE:` or `!` $\to$ **MAJOR** bump.
   - `feat:` $\to$ **MINOR** bump.
   - `fix:`, `perf:`, `refactor:` $\to$ **PATCH** bump.

### Step 3: Author Release Changelog
Group commits into structured sections: `Features`, `Bug Fixes`, `Performance Improvements`, and `Breaking Changes`. Include commit hashes with clickable file links.

### Step 4: Tag & Publish
```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
```

---

## 3. Verification Protocol

1. Assert all tests pass with zero failures.
2. Assert calculated SemVer adheres strictly to Conventional Commits rules.
3. Verify git tag exists: `git tag -l "vX.Y.Z"`.

---

## 4. ⚡ Token-Saving Execution Rule

- Output only the calculated version bump, the formatted changelog markdown, and the git tag command.
- Do not dump full git log outputs into chat.
