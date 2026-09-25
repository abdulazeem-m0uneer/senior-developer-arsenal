# Git Version Control & Pull Request Standards

These rules enforce clean, traceable, and atomic version control practices across all projects.

---

## 1. Conventional Commits Specification

All commit messages must follow the Conventional Commits 1.0.0 format:

```text
<type>(<scope>): <short imperative description>

[optional body explaining motivation and context]

[optional footer: BREAKING CHANGE or issue references]
```

### Allowed Types
- **`feat`**: A new feature for the user or API.
- **`fix`**: A bug fix.
- **`perf`**: A code change that improves performance without altering functionality.
- **`refactor`**: A code change that neither fixes a bug nor adds a feature.
- **`test`**: Adding missing tests or correcting existing tests.
- **`docs`**: Documentation changes only.
- **`chore`**: Maintenance, build script changes, package updates.
- **`ci`**: CI/CD pipeline and configuration changes.

### Examples
- ✅ `feat(auth): implement refresh token rotation with redis blacklist`
- ✅ `fix(orders): prevent race condition during simultaneous checkout`
- ✅ `perf(db): add partial index for pending background jobs`
- ❌ `update code`
- ❌ `wip`
- ❌ `fixed stuff`

---

## 2. Commit Hygiene & Branching

- **Atomic Commits**: Each commit must encapsulate a single logical change. Do not bundle unrelated refactoring with feature additions.
- **Always Green**: Every commit should build successfully and pass unit tests.
- **Linear & Clean History**:
  - Prefer rebasing feature branches against `origin/main` rather than creating intermediate merge commits:
    ```bash
    git fetch origin
    git rebase origin/main
    ```
  - Before requesting review or opening a PR, clean up history with an interactive rebase (`git rebase -i`) to squash temporary debugging commits.
- **Branch Naming**:
  - `feat/feature-name`
  - `fix/bug-description`
  - `perf/optimization-target`
  - `refactor/subsystem-name`

---

## 3. Pull Request Standards

Every PR must provide:
1. **Context & Problem Statement**: What business problem or technical bug is being addressed?
2. **Implementation Summary**: Bullet points detailing the architectural or code changes.
3. **Database Changes**: Does this PR include migrations? Are there any locking or indexing implications?
4. **Verification & Testing**: List commands and tests executed to verify correctness.
5. **Breaking Changes**: Explicit flag if public APIs, schema contracts, or environment variables have changed.
