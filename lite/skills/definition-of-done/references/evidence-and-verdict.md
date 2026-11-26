# Evidence Commands & Verdict Template

What counts as evidence, the commands that produce it per stack, and the verdict report format.

---

## 1. Evidence Rules

| Acceptable | Not acceptable |
| :--- | :--- |
| Command run in this session, with exit status and the decisive output line | "Tests passed earlier", "CI was green yesterday" |
| `file:line` read in this session | "The author said it is handled" |
| A test that fails without the change and passes with it | A test that was never seen red |
| Query plan, response body, or log line captured now | "Should be fine", "looks correct" |
| `N/A` with a specific reason | Silent omission of an item |

- [ ] Evidence is newer than the last code change. Any edit invalidates earlier runs.
- [ ] A skipped, filtered, or partially run suite is reported as partial, never as green.
- [ ] If a command cannot be run (missing tool, no database, no credentials), the item is `UNVERIFIED`, not `PASS`.

---

## 2. Commands by Stack

Prefer the scripts the project defines; fall back to these.

| Gate | Node.js / TypeScript | .NET | Python |
| :--- | :--- | :--- | :--- |
| Tests | `npm test` or `npx vitest run` | `dotnet test` | `pytest` |
| Lint | `npm run lint` | `dotnet format --verify-no-changes` | `ruff check .` |
| Type-check | `npx tsc --noEmit` | part of the build | `mypy .` |
| Build | `npm run build` | `dotnet build --configuration Release` | `python -m build` or import smoke test |
| Dependency advisories | `npm audit --omit=dev` | `dotnet list package --vulnerable` | `pip-audit` |

---

## 3. Change-Set and Hygiene Checks

```bash
git status --short                                   # nothing unintended, nothing untracked that belongs
git diff <base>...HEAD --stat                        # the full change set
git diff <base>...HEAD --name-only | xargs wc -l     # file size: no changed file above 1000 lines
git diff <base>...HEAD | grep -nE '^\+.*(TODO|FIXME|console\.log|debugger|print\()'   # leftovers in added lines
git log <base>..HEAD --oneline                       # commit hygiene
```

Search the changed files with your search tool for: hardcoded secrets (`password=`, `api_key`, `BEGIN PRIVATE KEY`), suppressions (`eslint-disable`, `@ts-ignore`, `# type: ignore`, `#pragma warning disable`), skipped tests (`.skip`, `xit(`, `[Fact(Skip`, `@pytest.mark.skip`), and empty catch blocks.

---

## 4. Proving a Test Can Fail

| Situation | Method |
| :--- | :--- |
| Bug fix | Run the new test on the commit before the fix (`git stash` or checkout the parent) and record the failure |
| New feature | Temporarily break the new branch of code (invert a condition) and confirm the test goes red, then restore |
| Refactor | Characterization tests were green before the refactor and are green after, unchanged |

---

## 5. Migration and Rollback Checks

- [ ] Apply the migration to a scratch database; record the command and result.
- [ ] Run the down migration or documented rollback; confirm the schema returns to the prior state.
- [ ] For a large table: no long exclusive lock (index built concurrently or online; column added without rewrite).
- [ ] Old application version still runs against the new schema (expand before contract).
- [ ] Feature flag default and off-state verified when a flag is the rollback path.

---

## 6. Verdict Report Template

```text
Feature:  <one sentence>
Scope:    <base>...<head>, <n> files changed
Verdict:  DONE | NOT DONE   (<p> PASS, <f> FAIL, <u> UNVERIFIED, <n> N/A)
```

| # | Item | Status | Evidence |
| :---: | :--- | :---: | :--- |
| 1 | Acceptance criteria | PASS | `orders.spec.ts:22-71`, 6 tests green |
| 7 | Full suite | PASS | `npm test` exit 0: 412 passed, 0 failed, 0 skipped |
| 9 | Lint | FAIL | `npm run lint` exit 1: `no-unused-vars` at `orders.service.ts:14` |
| 18 | Migrations | UNVERIFIED | No scratch database available in this environment |
| 22 | Changelog | N/A | Internal refactor, no user-visible change |

Remaining work (one line per `FAIL` / `UNVERIFIED`):

| # | Action | Owner |
| :---: | :--- | :--- |
| 9 | Remove the unused import at `orders.service.ts:14`, re-run lint | implementer |
| 18 | Apply and roll back migration `0042` on a scratch database | implementer |

Status rules: `DONE` requires zero `FAIL` and zero `UNVERIFIED`. An `UNVERIFIED` item may be accepted only by the user, explicitly, and is then reported as `ACCEPTED RISK` with their wording, never as `PASS`.
