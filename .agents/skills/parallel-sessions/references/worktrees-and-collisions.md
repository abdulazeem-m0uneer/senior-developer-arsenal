# Worktree Command Sheet & Collision Table

Commands for reading the remote, isolating a task, staging safely, and cleaning up, followed by the collisions that parallel work produces and how to recover from each.

---

## 1. Read the True State

```bash
git fetch --prune origin
git remote show origin | grep 'HEAD branch'              # the default branch name, not an assumption
git ls-tree -r --name-only origin/main -- docs/ | head   # what the remote has under a path
git show origin/main:docs/plan.md | head -40             # one file from the remote, no checkout
git log --oneline --since='24 hours ago' origin/main     # includes direct pushes that never were pull requests
git for-each-ref --sort=-committerdate --count=15 \
  --format='%(committerdate:relative)  %(refname:short)  %(subject)' refs/remotes/origin
gh pr list --state open --json number,title,headRefName,files \
  --jq '.[] | "\(.number) \(.headRefName) \(.title) [\(.files | map(.path) | join(", "))]"'
```

Replace `main` with the default branch printed by the second command. On a host without the `gh` client, use its own command or API for the open pull request list; the check is not optional.

---

## 1a. Detect Existing Isolation Before Creating Any

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" && pwd -P)
git rev-parse --show-superproject-working-tree      # non-empty: a submodule, which also makes GIT_DIR != GIT_COMMON
git branch --show-current                           # empty: detached HEAD, host-managed workspace
```

| Result | Meaning | Action |
| :--- | :--- | :--- |
| `GIT_DIR != GIT_COMMON`, not a submodule, on a branch | Already in a linked worktree | Do not create another; report path and branch |
| Same, detached HEAD | Host-managed isolated workspace | Work here; a branch is named at finish time; cleanup belongs to the host |
| `GIT_DIR == GIT_COMMON` or submodule | Plain checkout | Ask once for consent to isolate unless the user already stated a preference; declined: work in place |

Once isolation is wanted: the harness's native worktree tool (`EnterWorktree`, a `/worktree` command, a `--worktree` flag) first, since it owns placement, branch creation, and cleanup and a manual `git worktree add` beside it creates state the harness cannot see; `git worktree add` only when no native tool exists. Never start implementation on the default branch without explicit consent.

---

## 2. One Worktree per Task

```bash
git check-ignore -q .worktrees || { echo '.worktrees/' >> .gitignore; git add .gitignore; git commit -m 'chore: ignore worktrees'; }   # project-local dirs must be ignored
git worktree add -b feat/refund-window ../wt-refund-window origin/main   # new branch from the fresh remote
cd ../wt-refund-window && <install dependencies>                         # each worktree has its own install
git worktree list                                                        # see every task in flight
git worktree remove ../wt-refund-window                                  # after merge; refuses if dirty
git branch -d feat/refund-window && git push origin --delete feat/refund-window
git worktree prune                                                       # drop records of folders deleted by hand
```

| Rule | Reason |
| :--- | :--- |
| Create from `origin/<default>`, never from the checkout's current `HEAD` | The checkout may be on someone's feature branch |
| Folder beside the repository, named after the task | Tools that scan the repository do not index it twice |
| A branch is checked out in one worktree only | Git refuses a second checkout; do not force it |
| Separate port, database name, and cache folder per worktree | Two test runs on one database corrupt each other |
| Environment files are copied in, never symlinked to the shared checkout | An edit in one task must not change another |
| Remove the worktree the moment its branch merges | A leftover worktree looks like work in progress |
| Directory: the user's stated preference, else an existing `.worktrees/` then `worktrees/`, else create `.worktrees/` | Explicit instruction beats observed layout |
| Baseline before any edit: install as the manifest dictates, run the full suite; red baseline is reported and the user decides | Every later failure is ambiguous otherwise |
| `git worktree add` refused by a sandbox: say so, work in place, still run setup and the baseline | A silent fallback hides where the work happened |

---

## 3. Stage, Stash, Commit

```bash
git add src/refunds/window.ts tests/refunds/window.test.ts   # explicit paths only
git add -p src/refunds/policy.ts                             # part of a file when a neighbour also edited it
git diff --cached --name-only                                # read the list before every commit
git stash push -m "refund-window: park fixture edits" -- tests/fixtures/refunds.json
git stash list | grep 'refund-window'                        # find your own entry, for example stash@{2}
git stash apply 'stash@{2}' && git stash drop 'stash@{2}'    # that entry by reference; re-list first, indexes shift
```

Banned in a shared checkout: `git add -A`, `git add .`, `git commit -a`, `git stash` with no message or path, `git stash pop` with no reference, `git checkout .`, `git restore .`, `git reset --hard`, `git clean -fd`. Each one acts on files that are not yours.

---

## 4. Shared Sequence Numbers

Applies to anything where two writers both take "the next free one": migration files, decision or question numbers, error codes, port assignments, feature-flag ids.

1. Write the work with a provisional number and tell any helper it is provisional.
2. Immediately before committing: fetch, then list the numbers on the remote default branch and on open pull request branches.
3. If yours is taken, renumber in every file of the change (`git diff --name-only origin/main...` gives the list) and re-run the checks that depend on it.
4. Merge quickly. A reserved number is safe only for as long as nobody else merges.

Prefer schemes that cannot collide when the project allows a choice: timestamped migration names instead of integers, ids allocated by a single script, one file per entry instead of one growing table.

---

## 5. Merge and Process Hygiene

```bash
REVIEWED=$(git rev-parse HEAD)                         # record at the moment review starts
gh pr merge <number> --rebase --match-head-commit "$REVIEWED"   # refuses if the branch moved
gh pr view <number> --json state,mergeCommit           # MERGED, with the commit that landed
git fetch origin && git log --oneline -3 origin/main   # wait until the fetch shows it before rebasing follow-ups
lsof -ti tcp:3107                                      # the process on the port this session owns
kill <pid>                                             # the id you started, nothing wider
```

A rebase or squash merge rewrites the hash, so confirm by the pull request state, not by looking for the reviewed hash on the default branch. Never stop work with `pkill -f <runtime>`, `killall <runtime>`, or a container-wide `down` on a shared host.

---

## 6. Collision Table

| Symptom | Cause | Recovery |
| :--- | :--- | :--- |
| Your commit contains files you never opened | `git add -A` or `commit -a` in a shared checkout | `git reset --soft HEAD~1`, unstage all, stage your paths only; if pushed, revert and tell the other author |
| Your feature already exists on the default branch | State was judged from a stale local checkout | Fetch, diff against the remote, delete the duplicate, keep only what the merged version lacks |
| Four pull requests solve the same request | One prompt went to several sessions | One lead session consolidates: pick a base, port the unique parts, close the rest with a note |
| Migration or decision number used twice | Number reserved early, another writer merged first | Renumber the unmerged change everywhere it is cited; never renumber what is already merged |
| Pull request turned "conflicting" with nobody touching it | A direct push to the default branch rewrote the same file | Re-apply by hand on the new base as one small change; do not replay three stale branches |
| Stash applied the wrong changes | Bare `git stash pop` took a neighbour's entry | `git stash list`, `git checkout -- <paths>` only for your paths, re-stash theirs under its original message |
| Uncommitted edits vanished from the shared checkout | Someone ran `reset --hard`, `clean`, or switched branch | `git fsck --lost-found` and editor local history; then move every task to a worktree |
| Rebase replays commits that were already merged | Follow-up branch rebased before the fetch showed the merge | `git fetch`, then `git rebase --onto origin/main <old-base> <branch>` |
| Tests fail with a port in use or rows from nowhere | Two sessions share a port or a database | Give each worktree its own port and database name |
| Dev server or test run of another session died | Processes killed by name pattern | Restart theirs, apologise in the hand-off note, kill by process id from now on |
| `fatal: '<branch>' is already checked out` | The branch lives in another worktree | Work there, or create a new branch; do not use `--force` |
| Merged code differs from what was reviewed | A push arrived between review and merge | Revert or re-review the delta; merge pinned to the reviewed hash from now on |
