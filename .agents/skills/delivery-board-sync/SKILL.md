---
name: delivery-board-sync
description: 'Keeps a task board in any tracker (Jira, Linear, GitHub Projects, Trello) in step with the plan document: the plan is the only source of the schedule, one task per plan item, a status moves only with evidence, and blocked items name who must answer what. Use when the user asks to update the board, seed tasks from the plan, or runs /delivery-board-sync. Triggers on: "update the board", "sync the tracker", "move the ticket", "create tasks from the plan", "/delivery-board-sync". Do not use for recording a decision (use decision-log) or proving work is done (use definition-of-done).'
---

# Delivery Board Sync Procedure

This skill guides the agent through mirroring the delivery plan onto a task board, moving each task only on evidence, and reporting at the end of the session exactly what was updated.

---

## 1. When to Use This Skill

Activate this skill when:
- A session starts, opens a pull request for, merges, or is blocked on an item of the delivery plan.
- The plan document changed and the board must follow.
- A board has to be seeded from a plan for the first time.
- The session is about to end and its work has not been reflected on the board.
- The user runs the `/delivery-board-sync` slash command.

*Boundary*: For writing the decision that unblocks an item, use `decision-log`. For proving an item is finished before it moves to done, use `definition-of-done`. For the rules of an unattended run that calls this skill at its start and end, use `autonomous-run`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Load the Board Configuration
Consult: [Board Config, Task Template & Evidence Table](./references/board-config-and-evidence.md)
1. Read the board config file in the repository before any tracker call. It names the tracker, the board, the plan document, and the status names as read from the board itself; never assume `In Progress` or `Done` exist under those names.
2. If the file is missing or the board id is empty, stop and ask for the board URL. Never take a board from memory, another project, or an example: tasks on the wrong board are the failure this step prevents.

### Step 2: Read the Plan, Not the Board
1. The plan document is the only source of the schedule. Where plan and board differ, the plan wins and the board is corrected.
2. Read only the configured sections. One plan item (a numbered step, a capability id, a milestone) is one task; a clause that only qualifies an item stays in that task's description.
3. Work that is not in the plan enters the plan first, as its own small change, and only then gets a task.
4. Take items in plan order: finish the earlier period before starting the next, and process answered items first.

### Step 3: Search Before Create
1. Search the board for the task's name prefix (`<key> <id>`) before creating anything. Create only what is missing.
2. Name the task with the plan's own wording, shortened, not reworded; link the description to the plan section on the default branch.
3. On a board shared by several projects, put this project's label on every task and touch only tasks that carry it.

### Step 4: Move Status Only With Evidence
1. Move the task at the moment it happens (branch started, pull request opened, merged, blocked), in the session that did the work.
2. Attach the evidence to every move: branch name, pull request link, CI run, merge commit. A claim is not evidence.
3. Never mark done on a claim. Done needs the merge on the default branch and the plan's own done check. Merged but check not met: the task stays in progress with a comment naming what is missing.
4. A blocked task says who must answer what, with the recommendation and the open-question entry. Then take the next unblocked item; the run does not stop.

### Step 5: Spend the Call Budget Deliberately
1. Know the tracker's rate or daily limit and set a budget per session. Spend it on status moves first, comments second, reads last.
2. Batch: collect the session's moves and apply them in one pass, using the bulk operation where the tracker has one.
3. Never list a whole board to find one task. When the budget is exhausted, write the owed updates into the end report instead of skipping them silently.

### Step 6: Reconcile and Report
1. Before the session ends, compare what the session did with the board: every touched plan item has the right status and its evidence comment.
2. State in the last message which tasks were updated, with their new status, and which could not be and why.
3. Never delete a task or add a status to the board without the board owner; report an item the plan no longer holds.

---

## 3. Verification Protocol

```bash
python3 -m json.tool .delivery-board.json >/dev/null && echo "config parses"   # the config file, wherever the project keeps it
git fetch origin && git log --oneline -1 origin/HEAD -- docs/plan.md          # the plan revision the board must match
gh pr view <number> --json state,mergeCommit,url                              # evidence for a move to done
git branch -r --contains <merge-commit> | grep -c 'origin/HEAD\|origin/main'  # must print 1 or more: it is on the default branch
gh run list --commit <merge-commit> --json conclusion,url --limit 3           # the CI run quoted in the comment
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Status | Task is done; pull request still open | The reader plans on work that does not exist | `[Blocker]` | Back to in progress, comment with the pull request link |
| Config | No board config; tasks created from a remembered URL | One project's tasks land on another's board | `[Blocker]` | Stop, ask for the URL, write the config, move the tasks |
| Duplicates | Two tasks share one plan id | Progress is split and both look stale | `[Architecture]` | Merge them, search by prefix before every create |
| Blocked | Blocked with no question and no named person | Nobody knows they are the one waited on | `[Suggestion]` | Add the question, the recommendation, who answers |

---

## 4. ⚡ Token-Saving Execution Rule

- **Prefix Search, Never List**: Find a task by its name prefix; never read a whole board or a whole plan document.
- **One Batch per Session Event**: Group status moves and evidence comments into a single pass instead of a call per thought.
- **Report as a Table**: End with one row per task (task, old status, new status, evidence); no prose about clean items.
