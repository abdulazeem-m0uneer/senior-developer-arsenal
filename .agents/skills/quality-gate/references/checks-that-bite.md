# Checks That Bite: Planted Inputs & Changed-Lines Coverage

How to make a check prove on every run that it still fails on what it forbids, and how to measure coverage on the lines a change touched.

---

## 1. Why a Check Must Prove It Bites

A check passes for two reasons: the tree is clean, or the check is broken. A typo in a path pattern, a preset that stopped loading, a parser upgrade that renamed a node type: each turns a rule into a silent pass. The only defence is to feed the check inputs that must fail, every run, and fail the gate when one of them passes.

---

## 2. The Self-Test Template

```javascript
// check: no skipped or focused tests. Fix: remove the modifier.
const PLANTED = [
  { name: 'plain skip',            source: `it.skip('x', () => {})`,            bad: true },
  { name: 'modifier in a chain',   source: `it.concurrent.only('x', () => {})`, bad: true },
  { name: 'split across lines',    source: `describe\n  .skip('x', () => {})`,  bad: true },
  { name: 'bracket form',          source: `it['skip']('x', () => {})`,         bad: true },
  { name: 'commented-out test',    source: `// it('x', () => {})`,              bad: true },
  { name: 'ordinary test',         source: `it('x', () => {})`,                 bad: false },
];

function selfTest() {
  for (const planted of PLANTED) {
    const found = problemsIn(planted.source).length > 0;   // the same pure function the real run uses
    if (found !== planted.bad) fail(`the check no longer bites: ${planted.name}`);
  }
}

selfTest();                      // first, every run
report(problemsIn(realFiles())); // then the real tree
```

| Rule | Reason |
| :--- | :--- |
| Planted inputs include at least one that must pass | A check that rejects everything also "bites"; the passing case catches it |
| Planted inputs never touch the repository | In memory, or a temporary directory removed afterwards; a planted violation on disk trips other checks |
| The self-test calls the same function as the real run | Testing a copy proves nothing about the original |
| Tool-backed rules run the real tool with the real config on throwaway trees | The config file is what breaks, so the config file is what must be exercised |
| Every bypass found once becomes a planted case | The fix and its proof land together; the same hole cannot reopen |

For a boundary rule: build a temporary tree in which the forbidden import exists, run the import-graph tool with the one real config, and require that the named rule fires for each planted file.

---

## 3. Changed-Lines Coverage

A global percentage rewards old tests: a change can add two hundred untested lines to a well-covered codebase and move the figure by a decimal. Measure the change itself.

**Algorithm**

1. Base is the merge base with the target branch: `git merge-base origin/main HEAD`.
2. Changed lines: `git diff --unified=0 <base>...HEAD -- <production paths>`; parse each `@@ -a,b +c,d @@` header into the added range: `d` lines starting at line `c`.
3. Leave out tests, test helpers, generated files, and hand-wired entry points, using the same exclusions as the coverage tool's own config.
4. From the coverage report (statement ranges with hit counts, branches with per-arm hit counts):
   - a statement counts when its range overlaps a changed line; it is covered when it ran;
   - a branch counts when any arm starts on a changed line; it is covered when every arm ran.
5. Fail under the threshold (90% is a workable floor), printing each uncovered `file:line`.

**Edge cases the check must get right**

| Case | Wrong behaviour | Right behaviour |
| :--- | :--- | :--- |
| One value edited inside a multi-line literal that never ran | "No changed statements", pass | Count the enclosing statement through range overlap |
| Only the `else` arm edited | Branch ignored | Branch counts when any arm is on a changed line |
| Changed production file absent from the report | Skipped, pass | Fail: every production file must appear, tested or not |
| Wrong working directory, paths do not match | Zero lines measured, pass | Fail when changed files exist but none matched |
| Change with no production line (docs, tests) | Division by zero or fail | Pass, stating "no measurable lines" |
| Uncommitted work | Measured locally, not in CI | Diff commits only; say so in the output |

Ready-made tools: `diff-cover` (any Cobertura or LCOV report), `jest --changedSince` with per-file thresholds, `coverlet` plus `reportgenerator` history for .NET. A custom script is under two hundred lines and is worth owning when branch-level accuracy matters.

---

## 4. Test Discipline

| Banned | Why |
| :--- | :--- |
| `skip`, `only`, `todo`, conditional skip, "expected to fail" modifiers | Each makes the suite green while a behaviour is unproven |
| `xit`, `xdescribe`, `fit`, `[Ignore]`, `@pytest.mark.skip` without a tracked reason | Same, in other spellings |
| A test commented out | A disabled test nobody can see |
| A test file the runner never collects | Ask the runner (`vitest list`, `jest --listTests`, `pytest --collect-only -q`, `dotnet test --list-tests`) and compare with the files on disk |

A test that truly cannot run in one environment is excluded by the runner's config with a written reason, never by a modifier in the test.

---

## 5. Generated-File Drift

```text
generate(in memory) -> compare with the committed file -> identical: pass
                                                       -> different: fail, print "run: <command> --write"
```

- [ ] One generator per file; the check and the writer are the same script with a `--write` flag.
- [ ] Output is deterministic: sorted keys, no timestamps, fixed line endings.
- [ ] Typical targets: API specification from route contracts, environment example from the config schema, client types from the specification, dependency notices from the lockfile.
- [ ] The committed file is reviewed in the diff, so a contract change is visible to the reviewer.
