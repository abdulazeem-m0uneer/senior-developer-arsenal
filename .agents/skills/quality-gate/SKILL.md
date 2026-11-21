---
name: quality-gate
description: 'One local command that equals CI. Use to make local checks match CI, set up pre-push checks, or explain a failing check.'
---
<!-- routing (read by the skill router, not loaded into the skill listing): Use whenever the user wants local checks to match CI, one pre-push command, or an explanation of a failing check. Designs and runs one local command that equals CI. Triggers: "quality gate", "run the gate", "pre-push checks", "same as CI locally", "failures only after pushing", /quality-gate. Not for building the pipeline (use devops-ci) or choosing tests for a change (use test-every-change). -->

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

### Step 7: One Gate at a Time
Several sessions on one machine pushing at once each run the heavy gate. Serialize it with `scripts/gate_lock.py`, never with a plain lock file: a killed run (closed terminal, OOM kill, crash) leaves a plain file behind and every later push waits for nobody.
1. Wrap the pre-push gate: `python3 scripts/gate_lock.py run --wait-minutes 30 -- npm run gate`. The only truth is an OS lock the kernel drops when every process holding it is gone; the holder record (pid, start, host, command, `--max-minutes`, default 45) is information. The command's exit code is passed through (128 + N when it died of signal N). Lock held: it waits up to `--wait-minutes`, then exits 5 `busy: held by pid N since T (cmd)` plus how to stop it (`kill N`) and, past the limit, a "running 73 min, over its 45 min limit" hint. Held with no record: it prints how to find the holder (`fuser <lock>` or `lsof <lock>`).
2. Stale means the lock is free while a record is left behind (killed run, reused pid): the next `run` takes the lock, prints one `cleared stale gate lock: pid N (dead|reused) ...` line and goes on. Age never clears anything and there is no override: a live hung gate is stopped by killing the printed pid.
3. The gate runs in its own process group and keeps the lock file open. When it ends, leftovers in the group are stopped (SIGTERM, SIGKILL after `--grace-seconds`, default 10; one line `stopped N leftover gate processes`), so a stray background process cannot keep the lock. SIGTERM, SIGINT and SIGHUP sent to `run` reach the whole group and escalate to SIGKILL after the grace. Every group signal goes through one guarded helper that refuses pgid <= 1 (`killpg(1)` is `kill(-1)`), its own group and its parent's. A lock file that cannot be opened or locked is exit 2. The tool never deletes the lock file; if someone removes it during a run, the record's lock inode tells a new run so and it stays busy ("lock file was replaced while pid N runs") instead of clearing a live gate (limit: a reused pid then stays busy until it ends or the record is deleted). A failed lock is retried 3 times, 50 ms apart, so a racing `status` is not mistaken for a gate. `gate_lock.py status [--json]` reports free, held or held with no record.
4. A crashed git or hook leaves `.git/index.lock` and every git command then fails "Another git process seems to be running". `gate_lock.py git-lock [--repo DIR] [--older-than-minutes 10]` lists such locks (also `refs/**/*.lock` and worktrees) with the exact `rm` command, exit 1 when found. It never deletes: confirm no git process runs, then remove it yourself.
5. Hook configs, one line each: lefthook `pre-push: commands: gate: run: python3 scripts/gate_lock.py run --wait-minutes 30 -- npm run gate`; husky `.husky/pre-push`: `python3 scripts/gate_lock.py run --wait-minutes 30 -- npm run gate`; pre-commit `- id: gate`, `entry: python3 scripts/gate_lock.py run --wait-minutes 30 --`, `language: system`, `stages: [pre-push]`, `pass_filenames: false`. Lock path: `--lock` or `$ARSENAL_GATE_LOCK`, default `~/.cache/arsenal/gate.lock`.

---

## 3. Verification Protocol

```bash
git diff --name-only $(git merge-base origin/main HEAD)...HEAD   # what changed decides what runs first
TURBO_FORCE=true npm run gate                                    # Node.js: task cache off
dotnet build --no-incremental && dotnet test --no-build --collect:"XPlat Code Coverage"   # .NET: full rebuild, then test that build
pytest -p no:cacheprovider --cov --cov-report=xml && diff-cover coverage.xml --compare-branch=origin/main --fail-under=90
git status --porcelain                                           # must be empty: the gate rewrote nothing
python3 scripts/gate_lock.py status                              # "free", "held (pid N, age, cmd)" or "held, no record (...)"
python3 scripts/gate_lock.py git-lock                            # exit 0: no leftover .git/*.lock; 1 lists them with the rm command
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Parity | CI runs a licence check the local gate omits | Red CI after a green local run | `[Blocker]` | Add it to the single entry point |
| Honesty | Boundary rule has a typo and matches no file | Check passes while enforcing nothing | `[Arch]` | Add planted violations that must fail |
| Tests | `it.only` left in a suite | 400 tests silently not run | `[Blocker]` | Remove it; add the test-discipline check |

---

## 4. ⚡ Token-Saving Execution Rule

- **Narrowest Command**: Run the one test file or package that changed; the full gate once before offering the change.
- **First Failure Only**: Quote the failing check's name and its first error lines, never the passing output.
- **Header, Not Folder**: Read the header of the one failing check; do not load every check to understand one.

**Next**: when the full gate is green, `definition-of-done` checks the change before it is reported complete.
