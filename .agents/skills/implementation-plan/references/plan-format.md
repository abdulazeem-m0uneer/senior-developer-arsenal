# Plan Format & Self-Review

---

## 1. Plan Header

```markdown
# <Feature> Implementation Plan

**Goal**: <one sentence>
**Architecture**: <2-3 sentences>
**Stack**: <key libraries, versions>
**Brief**: <path to the approved brief; the plan argues from it, executors read both>

## Global Constraints
<one line each, exact values copied from the brief: version floors, naming rules,
platform limits. Every task implicitly includes this section.>

## Review Focus
<the five input classes or failure modes the brief implies but no task's tests
exercise, most likely to bite a user first: input or condition, expected behaviour.
Each line is also pinned as a test in the task that owns the code.>
```

The brief is a vision document: it says what must happen, not everything the software will meet. Its silence on an input is not permission for that input to break the program.

---

## 2. Task Block

````markdown
### Task N: <component>

**Files:**
- Create: `src/refunds/window.ts`
- Modify: `src/refunds/policy.ts:40-72`
- Test: `tests/refunds/window.test.ts`

**Interfaces:**
- Consumes: `RefundPolicy.windowDays(): number` (Task 2)
- Produces: `isWithinWindow(order: Order, now: Date): boolean`

- [ ] **Step 1: Write the failing test**
```ts
it('rejects a refund on day 31', () => {
  expect(isWithinWindow(orderAt('2025-01-01'), new Date('2025-02-01'))).toBe(false);
});
```
- [ ] **Step 2: Run it, expect failure**
  Run: `npx vitest run tests/refunds/window.test.ts -t 'day 31'`
  Expected: FAIL, `isWithinWindow is not defined`
- [ ] **Step 3: Implement `isWithinWindow(order: Order, now: Date): boolean` in `src/refunds/window.ts`**
  <one line on approach only where the signature and test leave a choice>
- [ ] **Step 4: Run it, expect pass**
  Run: same command. Expected: PASS
- [ ] **Step 5: Commit**
  `git add tests/refunds/window.test.ts src/refunds/window.ts && git commit -m "feat(refunds): enforce refund window"`
````

---

## 3. What Each Step Carries

| Step kind | Carries | Never carries |
| :--- | :--- | :--- |
| Test | Test name, assertions as code, the brief's exact values | Vague `test the above` |
| Code | Exact signature (name, params, return), file, pinned values | A body the signature and tests already determine |
| Verification | Command and the output that means pass | `check it works` |
| Cross-task reference | The other task's Interfaces block | A copy of that task's code |

A step is done when the implementer can write exactly one reasonable thing from it: unambiguous, not complete.

---

## 4. Task Right-Sizing

- A task ends with an independently testable deliverable and is worth a fresh reviewer's gate.
- Fold in: setup, config, scaffolding, docs the deliverable needs.
- Split only where a reviewer could reject one half and approve the other.
- Several small same-shape edits (same constant change across files) are one batched task listing every file and its change.
- Wide mechanical refactors (rename a column, retype a shared symbol) are sequenced expand / migrate-in-batches / contract, each batch its own task blocked by the expand; CI stays green batch to batch because the old form still exists.
- Vertical over horizontal: each task cuts a complete path through the layers it needs and is demoable alone; a horizontal slice of one layer is not a task.

---

## 5. Self-Review Checklist

| # | Check | Failure sign |
| :-: | :--- | :--- |
| 1 | Brief coverage: every requirement points to a task | A requirement with no task |
| 2 | Step scan: one reasonable thing per step, nothing more | `TBD`, `handle edge cases`, a type no task defines, or a function body already determined |
| 3 | Type consistency: later tasks use the names and signatures earlier tasks produce | `clearLayers()` in Task 3, `clearFullLayers()` in Task 7 |
| 4 | Review focus: five untested input classes listed and each pinned to a test | Empty section without having checked |
| 5 | Proportion: plan length against brief length | Code blocks are most of the document |

Fix inline; no re-review.

---

## 6. Handover Message

```text
Plan saved at docs/plans/<file>.md. Please review it.
Execution options:
- Inline: I implement every task here; one fresh reviewer on the whole branch at the end. Cheapest; no per-task review.
- Subagent-driven: fresh implementer and fresh reviewer per task, whole-branch review at the end. Most thorough; a fresh context per task and per review.
Recommendation: <one>, because <task coupling, task count, cost of a shipped mistake>.
Does the plan capture what you want, and which approach?
```

Adapted from obra/superpowers (MIT); vertical-slice and expand/contract rules from mattpocock/skills (MIT).
