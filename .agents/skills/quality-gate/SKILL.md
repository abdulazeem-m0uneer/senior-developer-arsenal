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
1. Wrap the pre-push gate: `python3 scripts/gate_lock.py run --wait-minutes 30 -- npm run gate`. An OS lock the kernel drops when every process holding it is gone decides while `run` lives. After `run` dies, the holder record (pid, start, host, command, gate group, `--max-minutes`, default 45) decides only until the gate group it names is empty (step 3). Nothing else, no age and no override, makes a lock stale. The command's exit code is passed through (128 + N when it died of signal N). Lock held: it waits up to `--wait-minutes`, then exits 5 `busy: held by pid N since T (cmd)` plus how to stop it (`kill N`) and, past the limit, a "running 73 min, over its 45 min limit" hint. Held with no record: it prints how to find the holder (`fuser <lock>` or `lsof <lock>`).
2. Stale means the lock is free and the recorded gate group is empty while a record is left behind (killed run, reused pid): the next `run` takes the lock, prints one `cleared stale gate lock: pid N (dead|reused) ...` line and goes on. Age never clears anything and there is no override: a live hung gate is stopped by killing the printed pid.
3. The gate runs in its own process group and never inherits the lock fd: only `run` holds it. The record names the gate's group, so a `run` killed with `kill -9` leaves a busy gate while that group lives ("pid N is gone but its gate (process group G) still runs"; stop it with `kill -- -G`, or delete the holder record if G is not the gate). The group counts only when it is not the caller's own or parent group and its leader, if alive, has the recorded start time, so a reused group id is not taken for the gate. When it ends, leftovers in the group are stopped (SIGTERM, SIGKILL after `--grace-seconds`, default 10; one line `stopped N leftover gate processes`), and a process that left the group (setsid, a detached server) does not hold the lock. SIGTERM, SIGINT and SIGHUP sent to `run` reach the whole group and escalate to SIGKILL after the grace. Every group signal goes through one guarded helper that refuses pgid <= 1 (`killpg(1)` is `kill(-1)`), its own group and its parent's. A lock file that cannot be opened or locked is exit 2. The tool never deletes the lock file; if someone removes it during a run, the record's lock inode tells a new run so and it stays busy ("lock file was replaced while pid N runs") instead of clearing a live gate (limit: a reused pid then stays busy until it ends or the record is deleted). A failed lock is retried 3 times, 50 ms apart, so a racing `status` is not mistaken for a gate. `gate_lock.py status [--json]` reports free, held or held with no record.
4. A crashed git or hook leaves `.git/index.lock` and every git command then fails "Another git process seems to be running". `gate_lock.py git-lock [--repo DIR] [--older-than-minutes 10]` lists such locks (also `refs/**/*.lock` and worktrees) with the exact `rm` command, exit 1 when found. It never deletes: confirm no git process runs, then remove it yourself.
5. Any locking job of your own: close the lock fd for its children (close-on-exec, `close_fds`; in shell `flock -o`, or open the fd only around the critical command). Never `exec 9>lock` and then start a long-lived child: a server, watcher or background test runner keeps the lock after the job exits, so the next job waits forever.
6. Pre-push checks, in [`templates/pre-push`](./templates/pre-push): the project's affected-tests command (`AFFECTED_TESTS_CMD`, writing `COVERAGE_REPORT`), then the two scripts below; each step's exit code stops the push. Tests and coverage measure HEAD, so they run only when a pushed branch is at HEAD (a deletion, a tag or another branch goes straight to `push_once.py`), and either opt-out skips them too.
   - `scripts/changed_coverage.py --report <lcov.info|cobertura.xml> --base <ref> [--min 90] [--json]`: covered / executable lines among the added and modified lines of `git diff -U0 <base>...HEAD` (lcov `DA`, Cobertura `<line number hits>`, a Cobertura filename first taken under each `<sources><source>` folder, a relative one from the report's folder, as coverage.py writes names relative to it; report paths absolute or relative to a sub-package: a path under the repository top, or relative to the report's folder or a parent of it, names that file for certain, `..` resolved; any other is matched against every file of HEAD by longest whole-component suffix, then fewest extra components, and a tie involving a changed file is reported and skipped; a changed file counts only its best-matching records). Exit 1 under `--min` with each file's uncovered changed lines (20 per file at most); 0 at or above, or when no changed line is executable; 2 for a missing or unreadable report or a git error. Changed files the report does not list are named on one line. A UTF-8 BOM, the TAB git puts after a path holding a space, non-ASCII paths and an added line starting with `++ ` are handled; the percent shown is floored.
   - `scripts/push_once.py hook <remote> <url> [--base REF]` (push lines on stdin) or `check [--remote origin] [--branch B] [--base REF]`: while `gh run list --repo <host/owner/repo of the pushed remote's URL> --branch <b>` shows a run in progress, queued, waiting, requested or pending that a push starts (event push, pull_request or pull_request_target; scheduled and workflow_dispatch runs are left alone) on the remote sha the push replaces (`--branch` matches the branch name only, so a fork's pull request run from a same-named branch does not block), a fast-forward push is refused ("run <id> on <sha> is still running; wait for it, or cancel it on purpose with gh run cancel <id>"), a new branch passes, and any other push passes only as a pure rebase (same multiset of `git patch-id --stable` over the context-free patches, `--unified=0`, of the branch's commits not in the base, so a base change next to a branch change is pure, leaving out commits whose change the base already has, so dropping a commit cherry-picked onto the base is pure; base `--base`, which the template sets to `PUSH_BASE`, else `<remote>/HEAD`, else main or master; a merge counts by its remerge diff, git 2.36+; a push dropping commits the base already has is refused). An SSH host is resolved with `ssh -G` (a `~/.ssh/config` alias names its real host) and `ssh.github.com` is github.com. A remote URL naming no GitHub-shaped OWNER/REPO (local path, `file://`) passes as not checked. Opt-outs `ARSENAL_PUSH_REBASE=1` (a merge train's rebase) and `ARSENAL_ALLOW_PUSH=1` pass, even when the check itself fails, and append one JSON line to `.agents/ci-optouts.log`. gh missing, failing or silent for 30 s passes with a warning. A git command the rebase check needs failing (git older than 2.36 has no `--diff-merges=remerge`) is exit 2 and blocks the push: fail-closed, unlike gh.
7. Hook configs, one line each: lefthook `pre-push: commands: gate: run: python3 scripts/gate_lock.py run --wait-minutes 30 -- npm run gate`; husky `.husky/pre-push`: `python3 scripts/gate_lock.py run --wait-minutes 30 -- npm run gate`; pre-commit `- id: gate`, `entry: python3 scripts/gate_lock.py run --wait-minutes 30 --`, `language: system`, `stages: [pre-push]`, `pass_filenames: false`. Lock path: `--lock` or `$ARSENAL_GATE_LOCK`, default `~/.cache/arsenal/gate.lock`.

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
python3 scripts/changed_coverage.py --report coverage/lcov.info --base origin/main   # exit 1 lists uncovered changed lines
python3 scripts/push_once.py check                               # exit 1: a CI run on this branch is still going
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Parity | CI runs a licence check the local gate omits | Red CI after a green local run | `[Blocker]` | Add it to the single entry point |
| Honesty | Boundary rule has a typo and matches no file | Check passes while enforcing nothing | `[Arch]` | Add planted violations that must fail |
| Tests | `it.only` left in a suite | 400 tests silently not run | `[Blocker]` | Remove it; add the test-discipline check |
| Locks | Gate script runs `exec 9>gate.lock; flock 9` then starts a dev server in the background | Server keeps the lock; every later push waits forever | `[Blocker]` | `flock -o` or `gate_lock.py run`, so children never get the lock fd |

---

## 4. ⚡ Token-Saving Execution Rule

- **Narrowest Command**: Run the one test file or package that changed; the full gate once before offering the change.
- **First Failure Only**: Quote the failing check's name and its first error lines, never the passing output.
- **Header, Not Folder**: Read the header of the one failing check; do not load every check to understand one.

**Next**: when the full gate is green, `definition-of-done` checks the change before it is reported complete.
