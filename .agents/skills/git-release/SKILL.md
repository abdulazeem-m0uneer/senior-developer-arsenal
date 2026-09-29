---
name: git-release
description: Release preparation workflow to verify build & tests, inspect commit history, bump version according to SemVer, and draft release notes.
---

# Git Release Workflow

Use this workflow when preparing a production release or merging a milestone.

## Steps

1. **Verify Working Tree & Branch**:
   - Ensure working tree is clean (`git status`).
   - Sync with remote upstream:
     ```bash
     git fetch origin main
     git rebase origin/main
     ```

2. **Execute Full Test Suite**:
   - For C# / .NET:
     ```powershell
     dotnet test --configuration Release
     ```
   - For Node.js:
     ```bash
     npm run test
     npm run build
     ```

3. **Analyze Conventional Commits & Determine SemVer Bump**:
   - Run `git log --oneline <last-tag>..HEAD`.
   - If commits contain `BREAKING CHANGE:` or `!`: **MAJOR** bump.
   - If commits contain `feat:` without breaking changes: **MINOR** bump.
   - If only `fix:`, `perf:`, `refactor:`, `chore:`: **PATCH** bump.

4. **Draft Release Notes & Tag**:
   - Format release notes grouped by:
     - 🚀 Features
     - 🐛 Bug Fixes
     - ⚡ Performance Improvements
     - ⚠️ Breaking Changes
   - Tag the release:
     ```bash
     git tag -a v1.x.x -m "Release v1.x.x"
     ```
