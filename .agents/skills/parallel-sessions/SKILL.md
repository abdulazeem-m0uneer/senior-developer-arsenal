---
name: parallel-sessions
description: 'Runbook for several agents or people working in one repository at once: read the remote default branch before judging what exists, check open pull requests before building anything shared, one worktree per task, staging by explicit path, and sequence numbers taken at commit time. Use when the user asks to work alongside other sessions, avoid duplicated work, or runs /parallel-sessions. Triggers on: "another session", "shared checkout", "parallel agents", "use a worktree", "/parallel-sessions". Do not use for rebasing (use git-workflow-master) or waiting on pipelines (use ci-wait).'
---

# Parallel Sessions Procedure

This skill guides the agent through working safely in a repository that other agents or people are changing at the same moment, so that nothing is duplicated, overwritten, or merged unreviewed.

---

## 1. When to Use This Skill

Activate this skill when:
- More than one agent session, or an agent and a person, work in the same repository or the same checkout.
- The same request may have been sent to several sessions at once.
- The working tree holds changes, stashes, or branches that this session did not create.
- A task adds something shared: a migration, a numbered document entry, tooling, an agent guide, a common module.
- The user runs the `/parallel-sessions` slash command.

*Boundary*: For commit messages, branch naming, rebasing, and conflict resolution technique, use `git-workflow-master`. For waiting on a pipeline before merging, use `ci-wait`. For numbering and wording a decision entry, use `decision-log`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Read the Remote, Not the Checkout
1. `git fetch --prune` first. The local checkout may sit on another session's branch and be hours behind.
2. Answer "what does this repository have" from the remote default branch: `git ls-tree` and `git show origin/<default>:<path>`, never from the files on disk.
3. Record the checkout's branch and `git status --short` before any edit. Every modified or untracked file you did not create belongs to someone else.

### Step 2: Check Who Else Is Building It
1. List open pull requests and the branches pushed in the last day; read titles and changed paths, not diffs.
2. Read the last day of commits on the default branch: some work is pushed directly and never appears as a pull request.
3. If the thing exists or is in flight, build only what is missing and say so. Review or extend the other author's branch only when they or the lead ask for it.

### Step 3: Isolate the Task in Its Own Worktree
Consult: [Worktree Command Sheet & Collision Table](./references/worktrees-and-collisions.md)
1. One task, one branch, one worktree, created from the freshly fetched default branch. The shared checkout stays untouched.
2. Give the worktree its own dependency install, ports, and scratch database so two sessions never share runtime state.
3. Never switch branch, reset, clean, or restore in a checkout that holds changes that are not yours.

### Step 4: Stage, Stash, and Number Without Collisions
1. Stage by explicit path. `git add -A`, `git add .`, and `git commit -a` are banned in a shared checkout: they sweep in the neighbour's files.
2. Name every stash (`git stash push -m "<task>: <why>" -- <paths>`) and restore it by that name, never with a bare `git stash pop`.
3. Take shared sequence numbers (migration number, decision number, error code) at commit time: fetch, check the number is free, renumber if it was taken.
4. Keep changes to shared files small and merge them quickly; three long-lived branches on one table always conflict.

### Step 5: Merge the Reviewed Commit and Clean Up
1. Merge only the commit that was reviewed and that the pipeline ran on; pin the merge to that commit hash so a late push cannot ride along.
2. After the merge, fetch until the remote default branch shows it, and only then rebase a follow-up branch.
3. Remove the worktree, delete the local and remote branch, and prune. Stale worktrees mislead the next session.
4. Stop only the processes you started, by process id or by the port you own. Never kill by a broad name pattern: it takes down the other sessions' servers and test runs.

---

## 3. Verification Protocol

```bash
git fetch --prune origin
git status --short                                   # before editing: note every entry that is not yours
git worktree list                                    # one line per task; none left over from merged work
git diff --cached --name-only                        # exactly the files of this task, nothing else
git stash list                                       # every entry carries a task name
git log --oneline origin/HEAD..HEAD                  # only this task's commits are ahead of the default branch
git rev-parse HEAD                                   # must equal the reviewed, pipeline-green commit before merge
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Staging | `git add -A` in the shared checkout staged 14 foreign files | Another session's half-done work lands in your commit | `[Blocker]` | Unstage all, stage by path, move the task to a worktree |
| Baseline | Gap judged from a stale local branch | Duplicate of a feature merged an hour ago | `[Architecture]` | Fetch, read the remote default branch, remove the duplicate |
| Merge | Branch received a push after review | Unreviewed code reaches the default branch | `[Security]` | Re-review, then merge pinned to the reviewed hash |
| Processes | `pkill -f node` used to free a port | Kills every other session's servers and tests | `[Blocker]` | Kill by process id or port owner only |

---

## 4. ⚡ Token-Saving Execution Rule

- **Titles Before Diffs**: Read pull request titles and changed-path lists to detect overlap; open a diff only for a real collision.
- **Remote Reads by Path**: Use `git show origin/<default>:<path>` for the one file needed instead of checking out or listing the tree.
- **Report Collisions Only**: State what was already built by others and what you built instead; no narration of clean checks.
