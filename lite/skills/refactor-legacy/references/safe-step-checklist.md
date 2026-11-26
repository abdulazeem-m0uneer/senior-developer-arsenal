# Safe-Step Checklist

## 1. Before Each Step

- [ ] Working tree clean; last commit is green.
- [ ] The step is one named transformation (rename, extract, move, inline, parameterize).
- [ ] The pins that cover the touched lines exist and pass.
- [ ] You can state in one sentence what must not change.

## 2. During the Step

- [ ] Edit only the lines the transformation needs; no formatting sweep, no drive-by fixes (`minimal-change`).
- [ ] Keep public signatures for existing callers; add an overload rather than changing one.
- [ ] Keep error handling and validation when moving code.
- [ ] No behaviour edit. If one is needed, finish this step, commit, and do it separately.

## 3. After the Step

- [ ] Build or type-check passes.
- [ ] Pins pass; then the full suite. A red result means revert, not debug forward.
- [ ] Pinned expectations unchanged in the diff.
- [ ] Commit with a message that begins `refactor:` (structure) or `fix:` / `feat:` (behaviour), never both.

## 4. Step Size Guide

| Signal | Action |
| :--- | :--- |
| Step took more than a few minutes to verify | Split it |
| Two files changed for unrelated reasons | Split it |
| A test needed editing | Stop: behaviour changed; decide first |
| Build is red and the cause is unclear | Revert to the last green commit |
| A pin fails and the new value looks right | Behaviour change: separate commit, owner decision if user-visible |

## 5. Discovered Bug Log

| Field | Content |
| :--- | :--- |
| Where | `path:line` |
| Observed | Input and actual output |
| Expected | Reasoning, and who could confirm |
| Disposition | Pinned as current, fixed in its own commit, or open question |
| Reference | Entry in `decision-log` if the owner decided |

## 6. Stop Conditions

- The pins cannot be made deterministic after the sources in the seams reference are controlled.
- A step cannot be made smaller than "edit many callers at once".
- Suite or smoke path was already red and the cause is unknown; get a green baseline first.
- The change grows beyond the area written in Step 1; return to scoping and ask.
- The owner has not decided a behaviour that the pins disagree on.

## 7. Done Check

- [ ] Every change point branch is pinned and mutation-checked.
- [ ] Scaffolding from seams is removed or recorded for removal.
- [ ] Discovered bugs have a disposition.
- [ ] Structure and behaviour sit in separate commits.
- [ ] Full suite, lint, and type-check green; skipped-test count unchanged.
