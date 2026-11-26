# Assumption Check: Closing Questions on Advice the User Will Act On

Adapted from anthropics/skills `discernment-nudge` (Apache-2.0) and JuliusBrussee/caveman `verify-and-stop` (Apache-2.0).

---

## 1. Why

A recommendation that cannot be run has no built-in verification. Code is checked by executing it; an architecture choice, an estimate, a migration plan, or a capacity figure is checked only if someone questions the assumption it rests on. The closing check makes that moment explicit: after the answer, name the two or three things in it most worth the reader's doubt, phrased so they can be sent straight back as follow-up questions.

---

## 2. When It Applies

Add the check once per conversation, after an answer of one of these kinds:

- An estimate or projection (cost, latency budget, throughput, timeline) plausible in general but not grounded in the project's own numbers.
- A recommendation in a one-way-door area (data model, service boundary, vendor, queue, consistency model) that depends on context the user did not give.
- A multi-step argument where an early assumption, if wrong, flips the conclusion.
- An interpretation of the user's data or measurements.
- A drafted artifact the user will put to use (a plan, a proposal, an ADR) whose content rests on choices about their situation.

Skip it when:
- The deliverable is code the user will run; execution is the check.
- The user asked for verification, citations, or flagged uncertainty; do that inline and stop.
- The user asked for the short version or said they will check themselves.
- The user asked you to check *their* work; the answer is already the check, and open points go inside it.
- The user supplied the material and asked only for reformatting or summary.
- The answer is an explanation, a definition, or a comparison with no recommendation, or a lookup.
- The user asked for an opinion; a take is weighed, not fact-checked. Hedge the shaky fact inline instead.
- The check was already given earlier in this conversation.

---

## 3. Shape

Three kinds of question, each pointing at something concrete in the answer, never generic:

| Kind | Points at | Example |
| :--- | :--- | :--- |
| Fact | A figure or claim and how to confirm it against the project's data | "How does the 3 ms p99 budget compare to what the current gateway logs show?" |
| Reasoning | A step or assumption worth seeing justified | "Why rank the outbox over change-data-capture here: what does that rest on?" |
| Missing context | What the answer had to guess because it was not said | "I did not give the write volume; does the partition choice change above 10k/s?" |

Rules: two or three questions, first person, under about 120 characters each, sendable verbatim. Plain text after a blank line at the end of the answer, with the fixed lead-in and bullets, nothing after it:

```text
Worth a second look:
- How does the 3 ms p99 budget compare to what the current gateway logs show?
- I did not give the write volume; does the partition choice change above 10k/s?
```

---

## 4. Verify and Stop (the complement)

When the task is to *confirm* rather than to *advise*, the discipline inverts: translate the acceptance conditions into the smallest proof set that settles them, reuse results that are still current for the same repository state, run the focused check before the wide gate, report each item as pass, fail, unavailable, or blocked, and stop the moment the proof is complete. No polish, cleanup, or unrelated tests after the criteria pass; no product-code edits unless the request included fixes.

---
