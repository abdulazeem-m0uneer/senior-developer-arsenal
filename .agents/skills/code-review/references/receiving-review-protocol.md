# Receiving Review Feedback: Verify, Push Back, Then Fix

## 1. Response Pattern

```text
READ        all findings, without reacting
UNDERSTAND  restate each requirement in your own words, or ask
VERIFY      check the claim against the code: callers, tests, platform, history
EVALUATE    technically sound for THIS codebase?
RESPOND     technical acknowledgement, or reasoned pushback
IMPLEMENT   one item at a time; test each
```

Anything unclear: stop before implementing anything. Items may be related; a partial understanding produces the wrong fix. `Understood 1, 2, 3, 6. Need clarification on 4 and 5 before proceeding.` Never implement the clear ones and ask about the rest later.

---

## 2. Verify Before Implementing

For each finding, before any edit:

| Check | Question |
| :--- | :--- |
| Correctness | Is it right for this codebase, stack, and version? |
| Breakage | Does the suggested change break existing behaviour or a caller? |
| Fence | Why is the current implementation the way it is? (`git log -S`, grep callers) |
| Platform | Does it hold on every supported platform and version? |
| Context | Does the reviewer see the full picture (prior decisions, constraints)? |
| Usage | `Implement this properly`: grep for callers first. Unused: propose removal instead. |

Cannot verify: say so. `I cannot verify this without <X>. Investigate, ask, or proceed?`

Conflicts with a recorded decision or the owner's prior instruction: stop and raise it with the owner before implementing either side.

Source matters: the owner's own feedback is implemented after understanding; external reviewers' feedback is checked carefully first. Both report to the same person; neither outranks the code.

---

## 3. When and How to Push Back

Push back when the suggestion breaks working behaviour, the reviewer lacks context, it adds an unused feature, it is wrong for this stack, a compatibility reason exists, or it contradicts a recorded architectural decision.

How: technical reasoning, not defence. Ask a specific question. Cite the test or code that proves the current behaviour. Involve the owner when it is architectural.

```text
Reviewer: "Remove legacy code."
Reply:    "Build target is 10.15+; this API needs 13+. Legacy path keeps 10.15 working.
           The current implementation has the wrong bundle id though. Fix that, or drop pre-13?"
```

Wrong after pushing back: `Checked <X>; it does <Y>. Implementing.` One line; no apology, no defence of the earlier position.

---

## 4. Acknowledging Correct Feedback

The fix is the acknowledgement. `Fixed at <file:line>: <what changed>.` No thanks, no praise, no `you are absolutely right`; the arsenal's anti-sycophancy rule applies to reviewers too.

---

## 5. Implementation Order

1. Clarify everything unclear first.
2. Blocking findings (breakage, security, data loss).
3. Trivial fixes (typos, imports, names).
4. Complex fixes (refactor, logic).
5. One finding per change; run the covering tests after each; full suite once at the end.
6. Re-request review on the new commit hash; the earlier verdict applied to the earlier hash only.

---

## 6. Review Thread Mechanics

Reply inside the inline comment thread (`gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies`), not as a new top-level comment. Resolve a thread only after the fix is pushed and named in the reply.

---

## 7. Mistakes

| Mistake | Fix |
| :--- | :--- |
| Performative agreement | State the requirement, or act |
| Blind implementation | Verify against the code first |
| Batch without testing | One at a time, test each |
| Assuming the reviewer is right | Check whether it breaks something |
| Avoiding pushback | Correctness over comfort; name the tension, then say what you saw |
| Partial implementation | Clarify all items first |
| Cannot verify, proceed anyway | State the limit, ask for direction |

Adapted from obra/superpowers (MIT).
