---
name: ci-wait
description: 'Waits for the checks of a pull request and separates an outside failure (registry rate limit, runner that never started, network, billing, the CI provider itself) from a failure of the change, rerunning only the outside ones at most twice and merging only the tested commit. Use when the user asks to wait for CI, judge whether a red run is flaky, or runs /ci-wait. Triggers on: "wait for CI", "is CI green", "rerun the failed jobs", "flaky pipeline", "merge when green", "/ci-wait". Do not use for writing the pipeline itself (use devops-ci) or for merge strategy (use git-workflow-master).'
---

# CI Wait & Failure Triage Procedure

This skill guides the agent through waiting for a pull request's checks with one bundled command, classifying a red run as an outside failure or a failure of the change, and merging only the commit that was tested.

---

## 1. When to Use This Skill

Activate this skill when:
- A pull request has been pushed and its checks must finish before the next action.
- A run is red and nobody has yet established whether the change or the infrastructure broke it.
- A merge is authorised "on green" and the exact tested commit must be the one that lands.
- Jobs sit queued or fail in seconds without running a single step.
- The user runs the `/ci-wait` slash command.

*Boundary*: For designing, hardening, or speeding up the pipeline, use `devops-ci`. For reproducing the same checks locally before pushing, use `quality-gate`. For branch, rebase, and merge strategy, use `git-workflow-master`. For root-causing a failure of the change, use `investigate`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Pre-flight
1. Confirm `gh auth status` succeeds and the pull request number is known (`gh pr view --json number,headRefOid,mergeable`).
2. If `mergeable` is `CONFLICTING`, stop: no check will ever run. Rebase first, then wait.
3. Confirm who authorised the merge. Waiting never implies permission to merge.

### Step 2: Wait With the Bundled Script
1. Resolve the script path relative to the directory that contains this file, then run `python3 <skill-dir>/scripts/ci_wait.py <pr>`.
2. Run it in the background with a budget of one CI run (default 40 minutes) plus reruns; do not write a second wait loop and do not read logs by hand first.
3. Tune only with flags: `--timeout`, `--interval`, `--max-reruns`, `--rerun-delay`. Never poll faster than 15 seconds: it burns API quota and gains nothing.

### Step 3: Act on the Exit Code
Consult: [Outside Failures & Exit Code Playbook](./references/outside-failures.md)
1. `0`: green. The script prints the tested commit and the merge command.
2. `1`: the change failed, or an outside failure survived every rerun. Read the printed job, step, and error lines; fix, push, run the script again.
3. `2`: the pull request or run could not be read. Check the number, the repository, and authentication.
4. `3`: not finished in time, or no checks reported. Check `mergeable` and the workflow triggers, look at the run once, then run the script again.
5. `4`: jobs never started (billing, no runner). Not the change; a rerun will not help. Report to whoever owns the CI account.

### Step 4: Handle Outside Failures Honestly
1. An outside failure is retried, never worked around: no skipped job, no weakened check, no merge on red.
2. The script reruns only the failed jobs, at most twice, with a delay so a rate limit can clear.
3. When the script reports a change failure but the log plainly shows a registry, network, or provider fault, add the phrase to `OUTSIDE_CAUSES` in the script (with a test) in the change that met it.
4. The same outside cause three times in a week is a pipeline defect: add a mirror, a cache, or a retry at the step (`devops-ci`).

### Step 5: Merge Only the Tested Commit
1. Merge with `gh pr merge <pr> --match-head-commit <sha>` using the commit the script printed; the merge is refused if anything was pushed since.
2. If the head moved, the green result belongs to an older commit: wait again.
3. Record the commit and the run link in the pull request or the task.

---

## 3. Verification Protocol

```bash
gh pr view <pr> --json headRefOid,mergeable,mergeStateStatus   # head commit and conflicts
python3 <skill-dir>/scripts/ci_wait.py <pr>; echo "exit $?"    # 0 green, 1 change, 2 unreadable, 3 timeout, 4 never started
gh pr checks <pr> --json name,bucket,link                      # every bucket is pass or skipping
gh pr merge <pr> --squash --match-head-commit <sha>            # only the tested commit lands
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Merge | Merged without `--match-head-commit` after a late push | Untested commit on the main branch | `[Blocker]` | Revert or verify the landed commit; always pin the commit |
| Triage | Red job skipped or marked optional to get green | A real defect ships | `[Blocker]` | Restore the job; fix the change or rerun the outside failure |
| Pipeline | Image pulls hit the registry rate limit weekly | Random red runs, wasted reruns | `[Suggestion]` | Authenticate pulls or add a pull-through mirror |

---

## 4. ⚡ Token-Saving Execution Rule

- **One Command**: Run the script and read its last lines; never stream the whole run log into the conversation.
- **Decisive Lines Only**: Quote the failed job, the failed step, and at most twelve error lines.
- **No Narrated Waiting**: Report once when the wait ends, with the exit code, the commit, and the next action.
