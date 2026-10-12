# Gate Check Catalogue & Run Matrix

Which command to run first for a given change, the generic checks worth having in a gate, and what each one wants when it fails.

---

## 1. Run the Smallest Thing First

| Changed | Run first | Node.js | .NET | Python |
| :--- | :--- | :--- | :--- | :--- |
| One file and its test | That test file | `npx vitest run src/orders/refund.test.ts` | `dotnet test --filter FullyQualifiedName~RefundTests` | `pytest tests/orders/test_refund.py` |
| One package or project | Its type-check, lint, tests | `npm run test -w packages/billing` | `dotnet test src/Billing.Tests` | `pytest packages/billing && ruff check packages/billing` |
| Anything structural (new package, dependency, config key, migration, endpoint) | Static checks only | `npm run gate:checks` | `dotnet format --verify-no-changes && dotnet build -warnaserror` | `ruff check . && mypy .` |
| An endpoint added or changed | Static checks, then the API smoke suite locally | see `smoke-test` | see `smoke-test` | see `smoke-test` |
| Before offering the change | The whole gate, cache off, once | `TURBO_FORCE=true npm run gate` | `dotnet test --no-incremental` | `pytest -p no:cacheprovider` |

Split the entry point so the cheap half needs no containers: `gate:checks` (static, about a minute) and `gate` (static, then type-check, lint, all tests, changed-lines coverage).

---

## 2. Catalogue of Generic Checks

| Check | What it catches | Cheap implementation | When it fails, it wants |
| :--- | :--- | :--- | :--- |
| Format | Unformatted files, noisy diffs | Formatter in check mode (`prettier --check`, `dotnet format --verify-no-changes`, `ruff format --check`) | Run the formatter in write mode on the listed paths |
| Lint, strict | Unsafe casts, unused names, environment read outside the config module | Linter with warnings-as-errors for the rules that matter | Narrow the type or move the code; never a blanket disable comment |
| Type-check | Contract breaks between modules | Compiler in no-emit mode over every project | Fix the type; a suppression needs a reason on the same line |
| Dead code | Unused files, exports, dependencies | A dead-code tool (`knip`, `vulture`, analyser warnings) | Delete it, or mark it public with the reason |
| Boundaries | Forbidden imports between layers or modules | Import-graph rules (`dependency-cruiser`, `import-linter`, architecture tests) | Move the shared piece to a lower layer; import through the module's public entry |
| Boundaries bite | A boundary rule that silently matches nothing | Run the same rule config on planted violating trees | Repair the rule, then keep the planted case |
| Duplication | Copied blocks above a token threshold, tests excluded | A copy-paste detector (`jscpd`, `pmd cpd`) | Extract one home for the block |
| File size | Production files past the agreed line cap | Twenty-line script counting lines per tracked file | Split by responsibility, not by line number |
| Test discipline | Skipped, focused, pending, or commented-out tests; test files no runner collects | Parse test files for the modifiers; ask the runner to list files and compare with the tree | Remove the modifier; fix the runner's include pattern |
| Changed-lines coverage | New or altered lines and branches without tests | Coverage report intersected with `git diff --unified=0 <base>...HEAD` | Add the tests; commit before measuring |
| Generated-file drift | API specification, environment example, client types out of date | Regenerate in memory, compare bytes, offer `--write` | Run the check with `--write` and commit the result |
| Contract version | A published contract changed without a version bump | Compare the package's files and version against the base branch | Bump the version in the same change |
| Schema drift | Model definitions and migrations disagree | Apply all migrations to a scratch database, diff against the model | Write the missing migration (`database-migration`) |
| Migration safety | Lock-heavy or irreversible statements; migration ordered before one already merged | Parse migration files for banned statements; compare names with the base branch | Rewrite as expand and contract; rename with a later timestamp |
| Licences | A dependency with a licence outside the allow-list | Read licences from the lockfile metadata | Replace the dependency or record an approved exception |
| Pinned versions | Floating image tags, unpinned actions, runtime version mismatch | Grep manifests for `latest`, ranges, and mutable tags | Pin the version or digest |
| One definition | The same route, error code, or config key declared twice | Collect declarations, fail on duplicates | Keep one, import it elsewhere |
| Slow call in transaction | Network call made while a database transaction is open | Syntax-tree scan for outbound-client calls inside transaction callbacks | Move the call outside; use an outbox |
| Smoke coverage | An endpoint with no smoke case and no written excuse | Compare the served route list with the cases' declared routes | Add the case (`smoke-test`) |
| Secrets | Credentials committed | A secret scanner on the diff (`gitleaks protect --staged`) | Remove, rotate the credential, purge from history |

Order inside the gate: cheapest and most frequent failures first (format, lint, discipline), containers and full tests last.

---

## 3. Rules for Any Custom Check

- [ ] One file per check; its first comment lines state the rule, the reason, and the command that fixes a failure.
- [ ] Exits non-zero with one line per problem: `path:line: what is wrong: what to do`.
- [ ] The decision is a pure function over inputs (file list, parsed tree, diff), so it can run on planted inputs.
- [ ] Runs its planted bad inputs first, every run; a planted input that passes is itself a failure.
- [ ] Reads syntax trees, not lines, when the rule is about code; a regular expression misses a modifier split across lines.
- [ ] Fails closed: a missing report, an empty file list, or a wrong working directory is a failure, never a pass.
- [ ] An exemption names one exact file with a reason, never a folder or a pattern.
- [ ] Warnings do not fail the gate and are not "fixed" by contorting code; promote a rule to an error or delete it.

---

## 4. Traps

| Trap | Effect | Guard |
| :--- | :--- | :--- |
| Task cache replays yesterday's green tests | The final run proves nothing | Disable the cache for the final run |
| Coverage measured on uncommitted work | Changed-lines figure differs from CI | Commit, then measure; trust CI's figure when they differ |
| Hook skipped with `--no-verify` | Local gate never ran | CI runs the same entry point; hooks are a convenience, CI is the gate |
| Gate rewrites files (formatter in write mode) | Green locally, red in CI | Gate runs check mode only; `git status --porcelain` empty afterwards |
| Threshold lowered "temporarily" | Never raised again | Thresholds change only in a reviewed change of their own |
