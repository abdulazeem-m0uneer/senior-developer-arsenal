# Conventional Commits & Semantic Release Reference

Authoritative guide for formatting commit messages and automating semantic versioning.

---

## 1. Commit Structure

```text
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### Type Matrix:
| Type | SemVer Impact | Description |
| :--- | :--- | :--- |
| `feat` | MINOR | Introduces a new feature or endpoint. |
| `fix` | PATCH | Fixes a software bug or defect. |
| `perf` | PATCH | Improves execution speed, memory usage, or query latency. |
| `refactor`| PATCH / NONE | Code refactoring without behavior modification. |
| `test` | NONE | Adds or modifies unit, integration, or E2E tests. |
| `docs` | NONE | Documentation changes only. |
| `chore` | NONE | Build scripts, tooling configurations, dependency updates. |
| `ci` | NONE | CI/CD pipeline and workflow updates. |

### Breaking Changes:
Append `!` after the type/scope or include a `BREAKING CHANGE:` footer:
```text
feat(api)!: migrate auth token to RFC 9068 JWT format

BREAKING CHANGE: The legacy session cookie endpoint is removed. Clients must now send Bearer tokens in the Authorization header.
```

---

## 2. Senior Best Practices for Commit Messages

1. **Imperative Mood in Subject**: Use "add", "fix", "change", not "added", "fixes", "changing".
2. **Context in Body**: Use the body to explain:
   - What problem was solved?
   - Why was this approach selected over alternatives?
   - Any side effects or migration requirements?
3. **Reference Tracking**: Add issue numbers in the footer (`Closes #123`, `Fixes #456`).
