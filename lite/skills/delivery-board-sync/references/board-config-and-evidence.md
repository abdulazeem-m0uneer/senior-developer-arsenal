# Board Config, Task Template & Evidence Table

A tracker-neutral configuration file, the shape of a task, the evidence each status move requires, and the rules for blocked items, plan changes, and call budgets.

---

## 1. Board Configuration File

One small file committed in the repository (for example `.delivery-board.json`). It is read before every tracker call. It holds no token, password, or session cookie.

```json
{
  "tracker": "jira | linear | github-projects | trello | other",
  "boardUrl": "https://tracker.example.com/boards/123",
  "boardId": "123",
  "listId": "456",
  "label": "billing-api",
  "statuses": {
    "open": "To Do",
    "started": "In Progress",
    "blocked": "Blocked",
    "answered": "Answered",
    "done": "Done"
  },
  "decisionLabels": { "business": "needs business decision", "technical": "needs technical decision" },
  "plan": {
    "document": "docs/delivery-plan.md",
    "sections": ["Week 1", "Week 2", "Week 3"],
    "key": "W<week> <lane>",
    "dueDate": "the Friday of the item's week",
    "doneCheck": "merged to the default branch and the item's acceptance line passes",
    "rules": ["an item waiting on a contract gets no task until the plan places it"]
  },
  "callBudget": { "perSession": 30, "perDay": 100 }
}
```

| Key | Rule |
| :--- | :--- |
| `boardUrl`, `boardId`, `listId` | Resolved once from the URL the board owner gave; never guessed, never copied from another project |
| `label` | Required when several projects share one board; left out when the board is this project's alone |
| `statuses` | The board's real names, read from the tracker. No review status on the board: `started` covers it. `blocked` and `answered` are left out where the board lacks them |
| `decisionLabels` | Route a blocked item to the person who can answer: business to the product owner, technical to the technical lead |
| `plan.key` | How a task name starts. On a shared board it begins with the project's own word so names never collide |
| `plan.doneCheck` | The plan's own test of finished; a merge alone does not satisfy it |
| `callBudget` | Set from the tracker's published limit, minus a margin for other sessions on the same account |

Setting up: resolve the board behind the URL, read its status names, check that no sibling project already uses the same list without a label, write the file, show it to the board owner, and only then seed tasks.

---

## 2. Task Template

```text
Name:         <plan.key>: <item id> <the plan's wording, shortened>
              W2 A: 2.3 Refund endpoint with idempotency key
Due date:     from plan.dueDate
Labels:       <label>, lane-a, week-02
Description:  <the plan item's full wording, with its decision and question references>
              Plan: <link to the plan section on the default branch>
              Done when: <plan.doneCheck for this item>
```

- The name prefix (`W2 A: 2.3`) is the identity of the task. It is what the search before create looks for.
- The description quotes the plan; it does not restate it in new words. The plan stays the single home of scope.

---

## 3. Status-to-Evidence Table

| Event | New status | Evidence written on the task | Never |
| :--- | :--- | :--- | :--- |
| Work on the item's branch begins | `started` | Branch name | Start two items to "reserve" them |
| Pull request opened | stays `started` | Pull request link | Move to done because the diff "looks complete" |
| Needs a person's decision | `blocked` + decision label | The question in one line, the recommendation, the open-question entry, who answers | Block without naming a person |
| The named person answered in full | decision task: `answered` | The answer quoted, the decision log entry | Mark answered on a partial reply |
| Answer written into the documents and merged | decision task: `done`; freed plan tasks back to `open` | Merge commit of the documents change | Close the plan task itself at this point |
| Answered in part | back to `blocked` | What is still missing | Guess the rest |
| Merged to the default branch and the done check holds | `done` | Merge commit, CI run on that commit | Done on a claim, a local run, or an approval alone |
| Merged but the done check does not hold | stays `started` | What is still missing, and the follow-up item | Close early: an open task is cheaper than a wrong one |
| Item is not code (a document, an account, a contract) | `done` | The commit, the URL that answers, or the dated confirmation | Done with no artefact named |
| Merged work reverted | back to `started` | Revert commit and the reason | Leave it done |

Evidence must be checkable by someone who was not in the session: a link or a hash, not a sentence.

---

## 4. Blocked Items

- A blocked item never stops the session. Take the next item in plan order that needs no decision.
- Building on a recommendation is allowed only when it was recorded before the task or confirmed by the lead on the task, and only where the change is cheap to reverse. Say so on the task. Never build on a recommendation the session wrote for itself.
- The question is written in the open-questions document first, then on the task. The board points to the document; it is not the home of the question.
- On a board with no blocked status, the task keeps its status and gets a comment naming the open-question entry.

---

## 5. When the Plan Changes

| Change in the plan | Board action |
| :--- | :--- |
| New item | Search by prefix, then create |
| Item moved to another period or lane | Rename the prefix, correct the due date and labels; keep the task and its history |
| Item removed | Report it to the board owner; do not delete the task |
| Work requested that the plan does not hold | Add it to the plan in its own change, then create the task |

---

## 6. Call Budget and Batching

| Priority | Call | Rule |
| :---: | :--- | :--- |
| 1 | Status move | Always made, in the session that did the work |
| 2 | Evidence comment | One comment per move, written together with it |
| 3 | Create | Only after a prefix search returned nothing |
| 4 | Search by prefix | One per item; cache the task id for the rest of the session |
| 5 | List or bulk read | Only when seeding or reconciling a whole plan section, filtered by label |

- When one access path is exhausted or unavailable (an integration with a daily cap), use the tracker's other official interface if the project has credentials for it. Read the credential from its file or the environment at call time; never print it, write it into a file, a commit, or a comment.
- When no path is left, the end report lists every update still owed so the next session can apply them.

---

## 7. End-of-Session Report

| Task | Was | Now | Evidence |
| :--- | :--- | :--- | :--- |
| W2 A: 2.3 Refund endpoint | In Progress | Done | merge `4f1c2ab`, CI run link |
| W2 A: 2.4 Refund receipt text | To Do | Blocked | question on fee wording, product owner to answer |
| W2 B: 2.6 Export job | In Progress | In Progress (not updated) | call budget exhausted; owed: comment with pull request link |
