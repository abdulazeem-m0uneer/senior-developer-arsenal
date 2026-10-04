# Bootstrap & Exemptions

How to proceed when the repository has no test framework, and the narrow conditions under which a change may go without an automated test.

---

## 1. Decision Flow

| Situation | Action |
| :--- | :--- |
| Runner exists and works | Use it; follow its naming and fixture conventions |
| Runner exists but is broken | Fix the runner first; report the cause; do not work around it |
| No runner, stack has a standard one | Bootstrap the minimal setup below, then write the tests |
| No runner, adding one needs approval (new dependency policy, locked environment) | Ask once with the exact proposed setup; meanwhile write the tests so they are ready to run |
| Code cannot be reached by any automated test | Record an exemption (section 4) and perform manual verification |

---

## 2. Minimal Bootstrap per Stack

| Stack | Install | Minimal config | Run |
| :--- | :--- | :--- | :--- |
| Node.js / TypeScript | `npm i -D vitest` | `"test": "vitest run"` in the manifest scripts | `npm test` |
| Node.js without dependencies | none | built-in runner, files named `*.test.js` | `node --test` |
| React components | `npm i -D vitest jsdom @testing-library/react` | `test.environment: 'jsdom'` in the Vitest config | `npm test` |
| Angular | already scaffolded by the CLI | default test target | `npx ng test --watch=false` |
| .NET | `dotnet new xunit -o tests/App.Tests` then `dotnet add tests/App.Tests reference src/App` | add the project to the solution | `dotnet test` |
| Python | `pip install pytest` (add to the dev dependencies) | `[tool.pytest.ini_options] testpaths = ["tests"]` | `pytest` |
| Python without dependencies | none | `unittest` test cases under `tests/` | `python -m unittest discover` |
| SQL / migrations | disposable database (container or scratch schema) | script: apply, assert, roll back | project migration command |
| Shell scripts | none | script exiting non-zero on failure | `sh tests/smoke.sh` |
| Browser journeys | `npm init playwright@latest` | default config | `npx playwright test` |

Bootstrap rules:
- [ ] Add the smallest setup that runs with one command; no coverage gates, plugins, or reporters yet.
- [ ] Place tests where the stack convention expects them and commit the runner config with the first test.
- [ ] Add the test command to the project manifest or task runner so that others find it.
- [ ] If a pipeline exists, add the test command to it in the same change; if none exists, state that as a gap.
- [ ] Prefer a runner built into the platform when adding a dependency is not acceptable.

---

## 3. Making Untestable Code Testable

| Obstacle | Smallest refactor |
| :--- | :--- |
| Logic buried in a handler, controller, or script body | Extract a pure function; test the function |
| Direct use of clock, randomness, or environment | Pass them in as parameters or a small interface |
| Hard-wired database or HTTP client | Accept the client as a constructor or function argument |
| Global or static state | Wrap in an object created per test |
| Code runs on import / at module load | Move into a `main` function invoked by the entry point |

Pin existing behaviour with a characterization test at the nearest reachable seam before making these edits.

---

## 4. Exemptions

Valid only when no automated check can observe the change:

| Change | Why it may be exempt | Required instead |
| :--- | :--- | :--- |
| Comment, formatting, or rename with no semantic effect | No behaviour to assert | Build, lint, type-check, and full suite green |
| Documentation text | Not executable | Links and commands in the text checked by hand |
| Generated code | Tested through its generator or its consumers | Regeneration is reproducible; consumer tests green |
| Third-party console or dashboard setting | Not reachable from the repository | Written manual verification with date and result |
| One-off data repair script | Runs once | Dry run on a copy with before / after counts recorded |

Not valid reasons: no time, the change is small, the code is hard to test, there is no framework, the tests are slow, it worked when tried by hand.

Exemption record (include it in the final report):

```text
Change:      <file:line and what changed>
Not tested:  <the behaviour without an automated test>
Reason:      <why no automated check can observe it>
Verified by: <manual steps performed and their result>
Follow-up:   <what would make it testable, or "none">
```

---

## 5. Final Run Checklist

- [ ] New tests observed red, then green.
- [ ] Full suite run after the last edit; counts of passed, failed, and skipped recorded.
- [ ] No test skipped, deleted, or weakened to reach green.
- [ ] Lint and type-check green on test files as well as source files.
- [ ] Mapping table and any exemption records included in the report.
