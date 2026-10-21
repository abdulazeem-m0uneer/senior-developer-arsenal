# Feedback Loop, Minimisation & Fix Discipline

## 1. Build the Loop First

A tight pass/fail signal that goes red on *this* bug is the investigation. Bisection, hypothesis tests, and instrumentation all consume it; without it, reading code produces theories, not findings. Spend disproportionate effort here.

Ways to build one, in rough order of preference:

| # | Loop | When |
| :-: | :--- | :--- |
| 1 | Failing test at the seam that reaches the bug (unit, integration, e2e) | Always try first |
| 2 | `curl` or HTTP script against a running dev server | API behaviour |
| 3 | CLI run with a fixture input, stdout diffed against a known-good snapshot | Command-line tools, scripts |
| 4 | Headless browser script asserting on DOM, console, or network | UI symptoms |
| 5 | Replay a captured trace (saved request, payload, event log) through the code path in isolation | Production-only input |
| 6 | Throwaway harness: one service, mocked dependencies, a single function call | Deep internal path |
| 7 | Property or fuzz loop: 1000 random inputs, look for the failure mode | `Sometimes wrong output` |
| 8 | Bisection harness: boot at state X, check, repeat; drive `git bisect run` | Regression between two known states |
| 9 | Differential loop: same input through old vs new version or two configs, diff output | Behaviour drift |
| 10 | Human-in-the-loop script that tells a person exactly what to click and captures the result | Last resort |

Loop completion criterion, all four: **red-capable** (asserts the user's exact symptom, not `did not crash`), **deterministic** (same verdict every run), **fast** (seconds), **agent-runnable** (unattended). Name the one command, show its invocation and output once, redacted.

Tighten it like a product: faster (cache setup, skip unrelated init, narrow scope), sharper (assert the symptom), more deterministic (pin time, seed RNG, isolate filesystem, freeze network). A 30-second flaky loop is barely better than none; a 2-second deterministic one is the whole investigation.

Non-deterministic bugs: raise the reproduction rate, not the cleanliness. Loop the trigger 100x, parallelise, add stress, narrow timing windows, inject sleeps. 50% is debuggable; 1% is not.

Cannot build one: say so, list what was tried, ask for (a) access to the reproducing environment, (b) a redacted artifact (HAR, log dump, core dump, timestamped recording), or (c) permission for temporary production instrumentation. Do not hypothesise without a loop.

Redact every secret in shown commands and output (`<REDACTED>`); build loops against environment variables so credentials stay out of what is shown.

---

## 2. Reproduce, Then Minimise

- Confirm the loop reproduces the failure the user described, not a nearby one. Wrong bug, wrong fix.
- Shrink to the smallest scenario that still goes red: cut inputs, callers, config, data, and steps one at a time, re-running after each cut. Done when every remaining element is load-bearing (removing any one makes it green).
- The minimal repro shrinks the hypothesis space and becomes the regression test.

---

## 3. Compare Against Working Examples

Before hypothesising: find similar code in the same codebase that works; if implementing a documented pattern, read the reference implementation completely, not skimmed. List every difference between working and broken, however small; do not assume `that cannot matter`. Note the dependencies, settings, and assumptions the broken path needs.

---

## 4. Instrument Against Predictions

- Each hypothesis states a falsifiable prediction: `if X is the cause, changing Y makes it disappear / Z makes it worse`. No prediction, no hypothesis.
- Show the ranked list to the user before testing when they are present (they often re-rank instantly); do not block on it.
- Each probe maps to one prediction; one variable at a time. Debugger or REPL first (one breakpoint beats ten logs); targeted logs at the boundaries that distinguish hypotheses second; never `log everything and grep`.
- Tag every debug line with a unique prefix (`[DEBUG-a4f2]`), capture the call stack before the dangerous operation (`new Error().stack`), use `console.error` in tests where loggers are suppressed. Cleanup is then one grep.
- Multi-component systems (CI -> build -> sign; API -> service -> DB): log what enters and leaves each boundary and verify config propagation once, to learn *where* it breaks before investigating *why*.
- Performance regressions: logs are the wrong tool. Baseline measurement (timing harness, profiler, query plan), then bisect. Measure first, fix second.
- Test pollution (state leaks between tests): run test files one by one against a check for the leaked artifact, stop at the first polluter.

---

## 5. Fix Discipline

1. Regression test before the fix, at a seam that exercises the real bug pattern as it occurs at the call site. A seam too shallow to replicate the triggering chain gives false confidence; if no correct seam exists, that is a finding (architecture prevents locking the bug down), record it.
2. Watch it fail. If the red was forced by mutating code or a fixture, diff against a pristine copy to prove the mutation landed.
3. One fix, addressing the root cause. No `while I am here` improvements, no bundled refactor.
4. Watch it pass; run the full suite; re-run the original un-minimised loop.
5. Fix did not work: stop and count. Fewer than three attempts: back to section 1 with the new evidence; never stack a second fix on the first. **Three failed fixes: stop and question the architecture.** Signs: each fix reveals new shared state or coupling elsewhere; fixes need a large refactor; each fix creates symptoms in a new place. That is not a failed hypothesis; it is a wrong structure. Discuss with the user before attempt four.
6. Defence in depth after the root-cause fix: validate at the entry point (reject obviously bad input), in the business logic (data makes sense for this operation), with an environment guard (refuse dangerous operations in test or dev contexts), and with a debug log that names the state before the dangerous operation. One check can be bypassed by another path, a refactor, or a mock; four layers make the bug structurally impossible.

`No root cause` (environmental, timing, external) is a valid end only after the whole process: document what was investigated, add handling (retry, timeout, clear error), add monitoring. Most `no root cause` verdicts are incomplete investigation.

---

## 6. Cleanup Before Done

- [ ] Original repro no longer reproduces (loop re-run).
- [ ] Regression test passes, or absence of a seam is documented.
- [ ] `grep` for the debug tag returns nothing.
- [ ] Throwaway harnesses deleted or moved to a marked debug location.
- [ ] The confirmed hypothesis is in the commit message so the next debugger learns.

---

## 7. Red Flags

`Quick fix now, investigate later` / `just try changing X` / `add several changes, run tests` / `it is probably X` / `one more attempt` after two failures / each fix reveals a new problem elsewhere. All mean: stop, back to section 1.

Adapted from obra/superpowers (MIT) and mattpocock/skills (MIT).
