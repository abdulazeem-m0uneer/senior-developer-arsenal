---
name: quality-gate
description: 'Designs and runs one local command that equals CI: smallest check first, a table from failing check to fix, checks that prove they bite on planted bad inputs, coverage of changed lines, no skipped tests, drift checks for generated files, a final uncached run. Use when the user asks to set up a local gate, make local checks match CI, explain a failing check, or runs /quality-gate. Triggers on: "quality gate", "run the gate", "pre-push checks", "changed-lines coverage", "/quality-gate". Do not use for building the pipeline (use devops-ci) or choosing tests for a change (use test-every-change).'
---

# Quality Gate Procedure

This skill guides the agent through building one local gate command that runs exactly what CI runs, using it cheaply while working, and keeping every check honest enough that a green result means something.

---

## 1. When to Use This Skill

Activate this skill when:
- A repository has checks scattered across CI jobs and no single local command that reproduces them.
- The gate or CI fails and the fastest route from the failing check to its fix is needed.
- A new check is being added, or an existing one was bypassed and must be made to bite.
- A change is about to be offered for review and needs its final local proof.
- The user runs the `/quality-gate` slash command.

*Boundary*: For authoring the workflow files, caching, and runners, use `devops-ci`. For waiting on the remote run and triaging a red one, use `ci-wait`. For choosing the tests a change needs, use `test-every-change`. For the evidence checklist before calling work finished, use `definition-of-done`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Make One Command Equal CI
1. List every step CI executes from the workflow files; list every script the manifest or task runner exposes. The gate is the union, in CI's order.
2. Expose it as one entry point (`npm run gate`, `make gate`, `./build.sh gate`, `nox -s gate`): static checks first, then type-check, lint, tests, then changed-lines coverage.
3. CI calls the same entry point, split into jobs if needed. Two lists of checks drift within a month; one list cannot.
4. Record in the gate's header anything CI runs that the local command cannot (image build, deployed smoke) so nobody assumes it is covered.

### Step 2: Run the Smallest Check First
Consult: [Gate Check Catalogue & Run Matrix](./references/gate-check-catalogue.md)
1. Map the changed paths (`git diff --name-only <base>...HEAD`) to the narrowest command: one test file, one package, the static checks only.
2. Run the full gate once, at the end. Running it after every edit wastes minutes and hides which edit broke what.
3. Pipe long output through `tail` or a filter; read the first failure, not the last.

### Step 3: Go From the Failing Check to What It Wants
1. Read only the failing check's header or rule description, never the whole checks folder.
2. Look the check up in the catalogue: each row says what it wants and the usual fix.
3. Fix the cause in the code. Never lower a threshold, add an ignore, skip a hook, or delete a test to get green; a check that is wrong is corrected in its own reviewed change that says why.

### Step 4: Make Every Check Prove It Bites
Consult: [Checks That Bite: Planted Inputs & Changed-Lines Coverage](./references/checks-that-bite.md)
1. Each custom check runs its rule against planted bad inputs on every run, before the real tree, and fails if any planted input passes.
2. Planted inputs live in memory or a temporary directory, never in the repository.
3. Every bypass found once (a split modifier, a renamed import, an empty config) becomes a planted case in the same change that fixes it.

### Step 5: Enforce the Rules That Global Numbers Miss
1. Coverage is measured on the lines and branches the change adds or alters, against the merge base; a global percentage lets new code hide behind old tests.
2. No skipped, focused, or pending test, and every test file is actually collected by its runner.
3. Generated files (API specification, environment example, client types) are regenerated in memory and compared; drift fails with the exact command that rewrites them.

### Step 6: Final Run and Report
1. Commit first: a changed-lines check that diffs commits cannot see uncommitted work.
2. Run the whole gate once with every cache disabled, so no replayed result stands in for a real run.
3. Report the command, the exit status, and the decisive line of each stage.

---

## 3. Verification Protocol

```bash
git diff --name-only $(git merge-base origin/main HEAD)...HEAD   # what changed decides what runs first
TURBO_FORCE=true npm run gate                                    # Node.js: task cache off
dotnet test --no-incremental --collect:"XPlat Code Coverage"     # .NET: no incremental build reuse
pytest -p no:cacheprovider --cov --cov-report=xml && diff-cover coverage.xml --compare-branch=origin/main --fail-under=90
git status --porcelain                                           # must be empty: the gate rewrote nothing
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Parity | CI runs a licence check the local gate omits | Red CI after a green local run | `[Blocker]` | Add it to the single entry point |
| Honesty | Boundary rule has a typo and matches no file | Check passes while enforcing nothing | `[Architecture]` | Add planted violations that must fail |
| Tests | `it.only` left in a suite | 400 tests silently not run | `[Blocker]` | Remove it; add the test-discipline check |

---

## 4. ⚡ Token-Saving Execution Rule

- **Narrowest Command**: Run the one test file or package that changed; the full gate once before offering the change.
- **First Failure Only**: Quote the failing check's name and its first error lines, never the passing output.
- **Header, Not Folder**: Read the header of the one failing check; do not load every check to understand one.
