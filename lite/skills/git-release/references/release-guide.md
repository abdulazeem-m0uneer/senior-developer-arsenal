# Release Preparation & SemVer Guide

Reference guide for calculating SemVer version bumps and generating changelogs from Conventional Commits.

---

## 1. SemVer 2.0 Calculation Matrix

Inspect commit history since the last release tag (`git log <last-tag>..HEAD --oneline`):

| Commit Type in Range | SemVer Bump | Example |
| :--- | :---: | :--- |
| Any commit containing `BREAKING CHANGE:` or `!` after type | **MAJOR** (`X.0.0`) | `feat!: remove legacy v1 endpoint` |
| One or more `feat:` commits (no breaking changes) | **MINOR** (`0.X.0`) | `feat(auth): add OAuth2 provider` |
| Only `fix:`, `perf:`, `refactor:`, `chore:`, `docs:` | **PATCH** (`0.0.X`) | `fix(cart): prevent negative quantity` |

---

## 2. Changelog Structure Template

```markdown
# Release vX.Y.Z (YYYY-MM-DD)

### 🚀 Features
- **auth**: add OAuth2 Google provider ([`a1b2c3d`](file:///...))

### 🐛 Bug Fixes
- **cart**: prevent negative item quantity on checkout ([`e4f5g6h`](file:///...))

### ⚡ Performance Improvements
- **orders**: add GIN index on customer metadata ([`i7j8k9l`](file:///...))

### ⚠️ Breaking Changes
- **api**: remove deprecated `/api/v0/users` endpoint ([`m1n2o3p`](file:///...))
```
