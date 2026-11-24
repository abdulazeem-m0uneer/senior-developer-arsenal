# Recorded Red Runs & the CI Check

`scripts/tdd.py` turns the red step of the [TDD loop](./tdd-loop-and-honest-tests.md) into something a reviewer and CI can check: the first commit of a feature or fix branch carries the failing test and a `Test-Red` trailer that records the failing run.

## 1. Record the Red Run

1. Write the failing test, nothing else. Stage it.
2. Commit it with the trailer printed by `tdd.py red`:

```bash
red=$(python3 .agents/skills/test-every-change/scripts/tdd.py red -- pytest tests/test_refunds.py) &&
  git commit -m "fix(refunds): reject refunds after the window" --trailer "$red"
```

The short form `git commit --trailer "$(tdd.py red -- pytest tests/test_refunds.py)"` works too, but when the tests pass git still commits, without the trailer (an empty `--trailer` is ignored); `tdd.py` prints "the tests pass" and exits 1, which means the test does not cover the new behaviour yet. Or print the line first and paste it as the last paragraph of the commit message, after a blank line, so git reads it as a trailer (a line pasted straight under prose is still accepted by the check, but git does not treat it as a trailer):

```text
Test-Red: 1 sha256:3f0c...e9 pytest tests/test_refunds.py
```

3. Write the code in the next commits until the test is green.

| Field | Meaning |
| :--- | :--- |
| exit code | The runner's non-zero exit. 126, 127, 124 and 129 to 159 (a timeout or signal seen through a shell), pytest's 4 and 5 (no test ran), a signal and the timeout are launch failures, never red (exit 2). Only the exit code is judged: a unittest module name typo still counts as red, so let `--verify` re-run it. A runner that exits with its failure count (mocha) can reach 124 to 159: wrap it as `sh -c '<runner> \|\| exit 1'`. |
| `sha256:` | Digest of the last 4 KB of output after removing colours, timings (`0.12s`, `12 ms`, `1m2s`) and temp paths, so the same failure gives the same digest on a re-run. |
| command | Shell-quoted. No shell is used: pass `sh -c '...'` for pipes. Run below the repository top, it is recorded as `sh -c 'cd <dir> \|\| exit 127; exec <command>'`, so `--verify` runs it in the same directory. It must fit on one line. |

Options: `--timeout S` (default 600). Output is read with a bounded buffer (last 64 KB). Ctrl-C or SIGTERM stops the test command's whole process group and exits 2.

## 2. Check a Branch

```bash
python3 .agents/skills/test-every-change/scripts/tdd.py check --base origin/main [--head HEAD] [--branch NAME] [--verify] [--json]
```

The first commit is the oldest non-merge commit of `git rev-list --first-parent <base>..<head>`, so a merge from base before it is skipped. When the head is a pull request merge commit (GitHub's `refs/pull/N/merge`, whose first parent is in base), the check reads the pull request's head, its second parent. It is refused (exit 1, one line per problem) when it:

- changes no test file (folders `tests/`, `test/`, `__tests__/`, `spec/`, `specs/`, `e2e/`, `src/test/`, `androidTest/`, in any case, so `Tests/` too, and folders whose name ends in a separated test word, such as `Billing.Tests/`, `Api.UnitTests/`, `integration-tests/` or `unit_tests/`; names `test_*.py`, `*_test.py`, `tests.py`, `test.py`, `*.test.*`, `*.spec.*`, `*.e2e.*` and `*.cy.*` for js, jsx, ts, tsx, mjs, cjs, mts and cts, `*_test.go`, `*Test` and `*Tests` for java, kt, cs and swift, `*_spec.rb`, `*.test.sh`, `*.pw.ts` and `*.pw.js`; a Rust file whose change adds `#[test]` or `#[cfg(test)]`, the usual place for Rust unit tests);
- has no `Test-Red` trailer, or one not shaped as `tdd.py red` prints it;
- with `--verify`: the recorded command passes, or cannot run, in a temporary worktree checked out at that commit. No repository hook runs for that checkout. The checkout's ignored dependency folders (`node_modules`, `bower_components`, `.venv`, `venv`, `.tox`, `.nox`, `vendor`, `.bundle`, `deps`, `Pods`, `.dart_tool`, at any depth) are linked into the worktree so the command finds the tools it ran with; build output, generated code and caches are not, so the run never uses or overwrites the checkout's compiled code. `PYTHONPATH` starts with the worktree's `src/` and top, and absolute entries naming the checkout are moved to the worktree, so an editable install (`pip install -e .`) imports the commit's code, not the checkout's. Background processes the command leaves are stopped when it exits.

It applies to feature and fix work only. The branch name comes from `--branch`, else `$GITHUB_HEAD_REF`, else the checkout. A `feat/`, `feature/`, `fix/`, `bugfix/` or `hotfix/` branch applies, at any level (`alice/feat/x`); the first feature, fix or exempt segment decides. When the name has no such prefix, a commit on the branch typed `feat` or `fix` (`feat(api)!:` included) applies, so a first commit typed `test:` followed by `feat:` is checked. Exempt, exit 0 with the reason: `docs/`, `chore/`, `refactor/`, `ci/`, `build/`, `test/`, `revert/`, `renovate/`, `dependabot/` and any other work, a branch whose commits are all typed `(deps)` (`fix(deps): bump lodash`, the update bots' convention), a diff against base that touches no source file (only docs, config, lockfiles, images; source covers py, js, jsx, ts, tsx, mjs, cjs, mts, cts, vue, svelte, go, rs, java, kt, kts, cs, rb, php, swift, m, dart, scala, ex, exs, lua, c, cc, cpp, h, sh, ps1 and sql; build scripts that carry a code suffix, such as `build.gradle.kts`, `Package.swift`, `setup.py`, `*.config.ts` and `.eslintrc.cjs`, count as config), and an empty range.

Exit codes: 0 ok or exempt, 1 refused, 2 usage or git error. `--json` prints `{"result", "branch", "first_commit", "problems", "exempt_reason"}`. The check never changes the repository: the `--verify` worktree and only its own `.git/worktrees` entry are removed afterwards, also on Ctrl-C or SIGTERM (exit 2); other worktree entries are left alone.

## 3. GitHub Actions

```yaml
on: pull_request
jobs:
  red-first:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # the check reads the branch's history; the merge commit checked out is read through its PR head
      - env:
          BASE_REF: ${{ github.base_ref }}
          HEAD_REF: ${{ github.head_ref }}   # through env: a branch name put straight into run: is a shell injection
          OPENED_AT: ${{ github.event.pull_request.created_at }}
          CUTOFF: "2026-11-30T13:00:00+02:00"   # example rollout date: PRs opened before it have no Test-Red trailer
        run: |
          if [ "$(date -d "$OPENED_AT" +%s)" -lt "$(date -d "$CUTOFF" +%s)" ]; then
            echo "opened before the red-first rollout ($CUTOFF): not checked"; exit 0
          fi
          python3 .agents/skills/test-every-change/scripts/tdd.py check --base "origin/$BASE_REF" --branch "$HEAD_REF"
```

Set `CUTOFF` to the day the check is turned on. Without it, every branch opened earlier is refused for the missing trailer.

Add `--verify` in the job that already installs dependencies and runs the tests. It runs a command taken from the branch's commit, so use it only where that branch's tests would run anyway; never in a `pull_request_target` job with secrets.

## 4. Limits

- One red run is recorded per branch: the first commit. Later behaviours on the same branch follow the loop without a trailer.
- The digest is evidence that a failure was seen, not proof of which assertion failed; `--verify` re-runs it.
- A rebase that reorders commits changes which one is first: keep the test commit first.
- `--verify` links the checkout's dependency folders as they are now: a workspace package linked inside `node_modules` is the checkout's version, not the first commit's. Ignored generated code is missing in the worktree, so a test that needs it fails there, which counts as red. The `PYTHONPATH` entries cover `src/` and the top only: a Python package under a subdirectory (`packages/api/src`) installed in editable mode still imports the checkout's code.
