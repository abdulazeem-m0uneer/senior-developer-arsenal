# Finishing a Development Branch

## 1. Gate: Green Suite on This Tree

```bash
<project test command>        # on the exact tree about to be integrated
```

Red: report the failures and stop. `Tests passed earlier this session` proves the tree it ran on, not this one.

---

## 2. Detect the Environment

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" && pwd -P)
WORKTREE_PATH=$(git rev-parse --show-toplevel)       # capture now; cleanup runs from elsewhere
git rev-parse --show-superproject-working-tree       # a path here means submodule, not worktree
```

| State | Menu | Cleanup |
| :--- | :--- | :--- |
| `GIT_DIR == GIT_COMMON` (plain checkout) | 3 options | none |
| linked worktree, named branch | 3 options | by provenance (section 6) |
| linked worktree, detached HEAD | 2 options (no local merge) | host-managed; leave it |

---

## 3. Confirm the Base

The base is what the branch forked from: the plan, the conversation, or the upstream names it. Unknown: ask `This branch split from <best guess>; correct?` Merging into the wrong base is expensive to undo.

---

## 4. The Menu

```text
Implementation complete. Options:
1. Merge into <base> locally
2. Push and open a pull request
3. Keep the branch as-is
Which?
```

Detached HEAD: `1. Push as a new branch and open a PR  2. Keep as-is`.

Present it as written and wait. Integration is the user's decision. Discard is not on the menu: it exists only when the user asks for it in so many words, confirmed by typing `discard` after seeing the branch name, the commit list, and the worktree path that will be deleted.

---

## 5. Execute

**Merge locally**
```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel); cd "$MAIN_ROOT"
git checkout <base> && git pull && git merge <branch>
<project test command>                               # on the merged result
```
Merged result red: stop, leave branch and worktree in place, investigate; nothing was pushed. Green: cleanup (section 6), then `git branch -d <branch>`.

**Push and PR**
```bash
git push -u origin <branch>                          # detached: git push origin HEAD:refs/heads/<new-branch>
gh pr create --base <base> --fill                    # follow the repo PR template; report the URL
```
Keep the worktree: review fixes happen there. Push rejected means the remote moved: investigate; force-push only on explicit request.

**Keep as-is**: report `Branch <name> kept; worktree at <path>.`

---

## 6. Cleanup by Provenance

Runs after a local merge or a confirmed discard, from the main repo root, using the captured `WORKTREE_PATH`.

- Plain checkout: nothing to clean.
- Worktree under `.worktrees/` or `worktrees/`: this workflow owns it: `git worktree remove "$WORKTREE_PATH" && git worktree prune`.
- Removal refused (`contains modified or untracked files`): those files exist nowhere else. Never `--force` on your own. Show `git -C "$WORKTREE_PATH" status --porcelain -uall` and ask: commit them to the branch, move them to the main root, or delete (unrecoverable).
- Anywhere else: the host owns the workspace; leave it, use the platform's exit tool if one exists.
- Never clean another worktree because it looks stale.

---

## 7. PR Body

```markdown
## Summary
<the smallest visual that makes the change clear: pseudocode for logic, a call tree
for control flow, a component tree for UI, a shallow file tree for layout, a diff of
any of these when the shape already exists, Mermaid for interaction>

## Evidence
- **Before:** <failing run / screenshot>   **After:** <passing run / screenshot>

## Merge Danger
**Door:** one-way | two-way   <why>
**Blast radius:** <one word>   <consumers, layout, mobile, data>
```

Screenshots for visual changes; execution output for everything else; no preamble.

---

## 8. Rationalizations

| Excuse | Reality |
| :--- | :--- |
| `They obviously want it merged` | Present the menu; wait. |
| `"Yeah, get rid of it" is confirmation` | Only the typed word `discard`. |
| `PR is up, the worktree is clutter` | Review fixes land there; it stays until merged. |
| `Removal refused; --force finishes the job` | The refusal means unique files. Ask. |
| `The merged-result failure is probably flaky` | A red merged result stops everything. |

Adapted from obra/superpowers (MIT); PR body shape from mattpocock/skills (MIT), crediting Dex Horthy's show-me skill.
