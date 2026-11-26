# Execution Loop: Ledger, Dispatch, Review, Fix Rounds

Applies to subagent-driven execution; inline execution keeps the ledger, the brief, and the final review and drops the per-task reviewer.

---

## 1. Workspace and Ledger

```text
<repo>/.plan-workspace/<plan-slug>/     git-ignored; one per plan, never another plan's
  progress.md                           first line: "# ledger - plan: <plan path>"
  task-N-brief.md                       the task's text extracted from the plan
  task-N-report.md                      implementer's full report (and appended fix reports)
  review-N-<base7>-<head7>.diff         commit list + stat + `git diff -U10 BASE..HEAD`
```

Ledger lines, append-only:

```text
Preflight: <pair or task> / <checked> / <finding or clean>
Ruling: <decision> / <why> / <cost if wrong>
Task N: fix round R/5 (<X> addressed, <Y> open: <one-liners>; commits <a7>..<b7>)
Task N: minor (deferred): <one-liner>
Task N: parked: <finding> / Ruling: <why the code stands or why deferred>
Task N: complete (commits <base7>..<head7>, review clean | <K> parked)
```

After compaction or a new session: if the ledger's first line names this plan, every task with a `complete` line is done; resume at the first without one; a task whose last line is a fix round resumes at the next round. `git clean -fdx` destroys the workspace; recover from `git log`.

---

## 2. Model Selection

| Role | Model tier | Rule |
| :--- | :--- | :--- |
| Implementer, plan text contains the complete code or a 1-2 file mechanical change | cheapest | transcription plus testing |
| Implementer from prose, multi-file integration | mid | turn count beats token price; cheap models take 2-3x the turns |
| Design judgement, broad codebase understanding | most capable | |
| Task reviewer | scaled to diff size and risk; mid floor | a subtle concurrency diff gets the top tier |
| Scoped re-review of a small fix | cheap to mid | |
| Fix rounds 4-5 | one tier above the stuck implementer | |
| Final whole-branch review | most capable | |

Always name the model in the dispatch. An omitted model inherits the session's, usually the most expensive.

---

## 3. Dispatch the Implementer

Record `BASE=$(git rev-parse HEAD)` first. The dispatch contains exactly: one line on where the task fits; the brief path (`read this first; it is your requirements, exact values verbatim`); interfaces and rulings from earlier tasks the brief cannot know; your resolution of any ambiguity you saw; the report path and report contract. Nothing else: no prior-task summaries, no session history, never the whole plan.

Implementer contract (in the prompt):
- Ask questions before starting if anything is unclear; asking mid-task is fine.
- Run the focused test while iterating; the full suite once before committing.
- Never dispatch subagents, above all never a reviewer; review comes from the controller.
- A file growing beyond the plan's intent: stop and report `DONE_WITH_CONCERNS`; do not split on your own.
- Self-review before reporting: completeness, YAGNI, existing patterns, tests assert real behaviour, output pristine.
- Write the full report (what, tests, RED and GREEN evidence with commands and output, files, concerns) to the report file; return under 15 lines: `Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT`, commits, one-line test summary, concerns, report path.

Never run two implementers in parallel on one branch. Batch several small same-shape edits into one dispatch.

Handling the status: `DONE` -> package and review. `DONE_WITH_CONCERNS` -> read; correctness or scope concerns are fixed before review, observations are noted. `NEEDS_CONTEXT` -> supply it, re-dispatch. `BLOCKED` -> context problem: more context, same model; reasoning problem: more capable model; too large: split; plan wrong: rule, ledger, re-dispatch with the ruling. Never retry the same model unchanged.

---

## 4. Review the Task

Write the review package to a file (`git log --oneline BASE..HEAD; git diff --stat BASE..HEAD; git diff -U10 BASE..HEAD`); it never enters the controller's context. `BASE` is the recorded one, never `HEAD~1` (drops all but the last commit of a multi-commit task).

Reviewer gets three paths (brief, report, package) plus the plan's Global Constraints verbatim. Reviewer contract:
- Treat the report as unverified claims; rationales in it (`kept simple per YAGNI`) never downgrade a finding.
- Do not re-run the suite the implementer ran; run a focused test only on a specific doubt. Noise in reported test output is a finding.
- Read the package once; open a changed file only for a hunk cut mid-function, and say so. Look outside the diff only for a named risk (lock order, contract change, shared state), one check per risk.
- Read-only; never spawns subagents.
- Part 1 spec compliance: missing, extra, misunderstood; a batched brief is checked file by file; `cannot verify from diff` items listed separately. Part 2 quality: separation, error handling, DRY without premature abstraction, edge cases, tests assert behaviour not mocks, file responsibility and growth caused by this change.
- Severity: Critical; Important (cannot be trusted until fixed: wrong or fragile behaviour, missed requirement, verbatim duplicated logic, swallowed errors, assertion-free tests); Minor (polish, broader coverage). Something the plan mandates that the rubric calls a defect is still a finding, labelled plan-mandated.
- Output begins with the spec verdict; every line is a verdict, a `file:line` finding, or a check run.

Controller rules: never write `do not flag X` or `at most Minor` into a reviewer prompt (pre-judging); never add open-ended directives (`check all uses`) without a task-specific reason; resolve every `cannot verify` item yourself before marking the task complete.

---

## 5. Fix Loop

Triggers: spec not compliant, any Critical or Important, or a `cannot verify` item confirmed as a gap. Minor findings go straight to the ledger as deferred. A finding that conflicts with plan text gets a ruling (spec is the authority) before any fix.

| Round | Who | Carries |
| :-: | :--- | :--- |
| 1-3 | resume the original implementer | open findings verbatim |
| 4-5 | fresh implementer, one tier up | brief path, report path, open findings, `a prior implementer attempted this N times; you own it now; read the report for what was tried` |

Each round: implementer fixes, re-runs the covering tests (named in the fix message; a one-line fix does not need the suite), appends a fix report with command and output, returns the short contract. Controller confirms the fix report holds covering tests, command, and output, then dispatches a scoped re-review over `FIX_BASE..HEAD` (FIX_BASE = head the previous review saw): each finding `ADDRESSED` or `NOT ADDRESSED`; new Critical/Important breakage in the fix diff joins the list; out-of-scope observations go to the ledger. Ledger every round.

**Breaker at round 5**: adjudicate each open finding yourself. Reviewer wrong or contestable: park with ruling. Real but nothing downstream builds on it: park, marked deferred. Real and load-bearing: rule on the smallest unblocking change, ledger it, carry it into the next task's dispatch. Adjudicate only at the cap; earlier is pre-judging. Silent discard is forbidden.

---

## 6. Waiting and Narration

While children run, do local work (ledger, next package). Idle: wait in bounded stretches (5-10 minutes), then one line of status and a reconcile of live children; chase any that finished without reporting. Never poll with short timeouts; never one silent open-ended wait.

---

## 7. Rationalizations

| Excuse | Reality |
| :--- | :--- |
| `I will fix it myself, dispatching is overhead` | Controller fixes pollute coordination context and skip review. |
| `One more round will converge` | Past the cap, rounds do not converge; the failure is structural. Adjudicate. |
| `The fix was small, skip the re-review` | Unreviewed fixes are how regressions land. |
| `The implementer spawned its own reviewer; free assurance` | A duplicate seat on the same diff. Flag it as a defect. |
| `Ledger bookkeeping is overhead` | The ledger is what survives compaction. |

Adapted from obra/superpowers (MIT).
