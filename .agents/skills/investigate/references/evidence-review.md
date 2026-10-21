# Evidence Review: Claims From Data, Not From Guesses

Adapted from JuliusBrussee/caveman, skills `caveman-evidence-review` and `caveman-manage` (Apache-2.0).

---

## 1. Scope of the Method

Use this when the answer must come from recorded data (logs, traces, metrics, cost ledgers, test results, benchmark runs) rather than from reading code: "why did spend double", "which job causes the timeouts", "did the change make it faster". The code tells you what *should* happen; the records tell you what *did*. Build every conclusion from the records and cite them so that someone else can re-run the same query and get the same rows.

---

## 2. Keep the Buckets Separate

Numbers of different provenance never get added together or relabelled. Name the bucket next to every figure:

| Bucket | Meaning | May be called |
| :--- | :--- | :--- |
| Measured | Read from a complete record at list price or actual value | "cost", "latency", "count" |
| Inferred | Modelled or extrapolated from a sample | "estimate", "headroom", "projected" |
| Verified | Confirmed by an independent record (a ledger, a second system) | "saving", "confirmed" |
| Cost of evidence | What the measurement itself consumed | reported separately, never netted |

A catalogue subtotal is not an invoice. An experiment's lift is not a verified saving until real traffic and an independent record say so. Mixing buckets is the fastest way to a confident wrong number.

---

## 3. The Procedure

1. **Load the context and stop if it is missing.** Which project, which environment, which identity. If login, project selection, or the data source is absent, ask for it; do not guess, and never supply a scope id the user did not give.
2. **Establish the baseline from aggregates.** Read the shortest set of summary views that can answer the question (overview, cost by group, error rate by group). State the time window and the basis of each figure before interpreting any direction.
3. **Test the leading explanation against individual records.** Choose a bounded window and closed filters (one group, one model, one error code, one session). Compare the suspect cohort with a control: the same filter over an earlier window, or a neighbouring group over the same window. One expensive record proves nothing; a cohort against a control does.
4. **Inspect a few representative records in full.** Pick a small number of high-signal ids and read their metadata: spans, timing, status, counts, route, cache state. Leave payload bodies (prompts, request bodies, file contents) unread unless the user explicitly asks for payload review; metadata answers the default question and payloads are where the private data lives.
5. **Report, then stop at the strongest supported statement.** If a signal is missing, name the missing signal rather than filling the gap with a plausible story.

Useful groupings when searching records: by job or workflow (what drives cost or failures), by model or version (mix comparison), by session (retry and loop behaviour), ungrouped (to name exact ids).

---

## 4. Rules

- Cite record ids and the exact window for every finding. "Traces 7f3…, 7f4…, window 2026-10-20T08:00Z to 10:00Z" is a finding; "the nightly job seems expensive" is not.
- Never claim a cause from an aggregate alone. Aggregates locate; records prove.
- An empty result is evidence of no signal in that window, not evidence of zero cost or zero risk.
- Absence is not a pass. A missing guardrail, a pending result, or a field that is not populated is reported as `evidence incomplete`, and nothing is approved on it.
- A request to review, inspect, explain, or recommend authorises reads only. A lifecycle action (start, approve, cancel, roll back, promote) is proposed as one line and executed only on an explicit, specific instruction naming that action and that id; generic earlier words ("do what is best") do not count.
- Unknown states and server errors fail closed: report the exact code and stop.
- After an operator says they ran an action, re-read the state and report what the system shows, not what the operator intended.

---

## 5. Report Shape

```text
## Evidence review

Scope: <project> · <from> to <to>
Measured: <value and basis>
Verified: <value from the independent record, kept separate>
Inferred: <band, kept separate>

Findings:
1. <finding> — <aggregate evidence> — records <ids>
2. <finding> — <aggregate evidence> — records <ids>

Unproven:
- <plausible explanation lacking a control, a record, or a test>

Next read-only check:
- <one bounded query>

Possible action:
- <proposal only; not executed>
```

---
