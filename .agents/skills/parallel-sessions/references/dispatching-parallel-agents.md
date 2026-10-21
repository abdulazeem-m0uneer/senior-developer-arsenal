# Dispatching Parallel Subagents

Rules for splitting one session's work across several subagents at once, as opposed to several sessions sharing one repository (the rest of this skill).

---

## 1. Decide: One Agent, Sequential Agents, or Parallel

| Situation | Dispatch |
| :--- | :--- |
| Failures related: fixing one may fix another | One agent investigates all |
| Independent domains, no shared files or resources | Parallel, one agent per domain |
| Independent but they would touch the same files, ports, database, or fixtures | Sequential |
| You do not yet know what is broken | No dispatch; investigate first (`investigate`) |
| Understanding needs the whole system state | One agent, or yourself |

Independence test: can each problem be understood and fixed without context from the others, and do the fixes touch disjoint code? Both yes: parallel.

Parallel implementers on one branch are never allowed in plan execution (`implementation-plan`): conflicting commits. Parallel is for investigation, review passes, and fixes in disjoint files.

---

## 2. Group by Domain

Group failures by what is broken, not by where the error appears:

```text
agent-tool-abort.test.ts         (3 failures)  -> abort flow
batch-completion.test.ts         (2 failures)  -> batch completion
tool-approval-race.test.ts       (1 failure)   -> approval race
```

One domain, one agent. Three failures in one file with one cause are one domain.

---

## 3. Brief Shape

Every brief is focused, self-contained, and explicit about output. Never hand over the session history.

```text
Fix the 3 failing tests in src/agents/agent-tool-abort.test.ts:
1. "aborts tool with partial output" - expects 'interrupted at' in message
2. "mixed completed and aborted tools" - fast tool aborted instead of completed
3. "tracks pendingToolCount" - expects 3 results, gets 0

Steps: read the test file; find the root cause (timing or real bug); fix by replacing
arbitrary timeouts with event-based waiting, or fixing the abort implementation.
Constraints: do NOT raise timeouts; do NOT change files outside src/agents/.
Return: root cause and what changed, under 15 lines. Full notes to <report path>.
```

| Fault | Fix |
| :--- | :--- |
| `Fix all the tests` | Name the file or subsystem |
| `Fix the race condition` with no location | Paste the error text and test names |
| No constraints | `Tests only`, `no production code`, or the allowed paths |
| `Fix it` as the output contract | `Return root cause and changes` |

Issue every dispatch in the same response: same response = parallel; one per response = sequential.

---

## 4. Integrate

1. Read each summary; an agent report is a claim, not evidence.
2. `git status --short` and `git diff --stat`: did two agents edit the same file? Reconcile by hand before anything else.
3. Run the full suite on the combined tree, not each agent's subset.
4. Spot-check one fix per agent: agents make systematic errors (raising a timeout instead of fixing the wait is the classic).

---

## 5. Waiting

Do local work while children run. When idle, wait in bounded stretches (5-10 minutes), then post one status line and reconcile: list live children, chase any that finished without reporting. Never poll with short timeouts; never one silent open-ended wait.

Adapted from obra/superpowers (MIT).
