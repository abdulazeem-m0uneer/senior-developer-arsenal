# Skill Eval Loop: Trigger Accuracy and Output Quality

Adapted from agentskills/agentskills docs (Apache-2.0), anthropics/skills `skill-creator` (Apache-2.0), and JuliusBrussee/caveman `evals/` design (Apache-2.0).

---

## 1. Two Questions, Two Evals

A skill fails in two independent ways: it does not fire when it should (or fires when it should not), and it fires but the output is no better than without it. Test each separately. Trigger evals exercise the description; output evals exercise the body.

---

## 2. Trigger Eval

**Query set.** About 20 realistic prompts, labelled `should_trigger: true | false`, 8–10 each way.

- Positive queries vary along phrasing (formal, casual, typos), explicitness (names the domain vs describes the need without naming it), detail (terse vs file paths, column names, backstory), and complexity (single step vs the task buried in a longer chain). The most useful ones are where the skill helps but the link is not obvious.
- Negative queries are **near-misses**: same keywords, different job ("update the formulas in my Excel budget" against a CSV-analysis skill). "Write a fibonacci function" tests nothing.
- Include realism: paths (`~/Downloads/report_final_v2.xlsx`), personal context, specific values.

**Run.** Each query three times with the skill installed in a clean session; record whether the skill was loaded. Trigger rate = loads / runs. Positive passes above 0.5; negative passes below 0.5. Stop a run early once the agent has either loaded the skill or started working without it.

**Split.** Train 60 %, validation 40 %, proportional positives and negatives, fixed across iterations. Only train failures guide edits; validation measures whether the edit generalised.

**Loop.** Evaluate both sets; revise on train failures; repeat up to about five times; select the iteration with the best *validation* pass rate (often not the last one).

- Positives failing: scope too narrow. Add the contexts where the skill applies, including ones that do not name the domain.
- Negatives firing: scope too broad. State what the skill does not do and name the neighbour that does.
- Never paste a failed query's keywords into the description; address the category they represent. Stuck after several rounds: restructure the sentence rather than tweak it.
- Watch the 1024-character limit; descriptions grow under optimisation.

**Description shape that triggers.** Imperative ("use when…"), user intent not mechanics, slightly pushy (agents under-trigger: list the situations, "even if they do not say X"), concise.

---

## 3. Output Eval

**Test cases** in `evals/evals.json` beside the skill: `id`, `prompt` (realistic, as a user would type it), `expected_output` (one human-readable sentence), optional `files`. Start with 2–3; cover one boundary case (malformed input, ambiguous request). Assertions come later.

**Runs.** Each case twice from a clean context: with the skill and without it (or against a snapshot of the previous version when improving). Isolation is mandatory; a run that inherits the authoring conversation measures the conversation, not the skill. Record `total_tokens` and `duration_ms` per run as soon as the run ends.

**Honest baseline.** A terse system prompt ("answer concisely") is the control for a skill that compresses output; comparing against no prompt at all conflates the skill with generic brevity. Pick the control that isolates what the skill claims to add.

**Workspace** (outside the skill folder):
```text
<skill>-workspace/iteration-N/
  eval-<slug>/with_skill/{outputs/, timing.json, grading.json}
  eval-<slug>/without_skill/{outputs/, timing.json, grading.json}
  benchmark.json
  feedback.json
```

**Assertions**, written after the first outputs are seen: verifiable and specific ("the output file is valid JSON", "both axes are labelled", "at least three recommendations"), not vague ("output is good") or brittle (an exact phrase). Style and feel stay with human review.

**Grading.** Each assertion `PASS` or `FAIL` with quoted evidence. No benefit of the doubt: a "Summary" heading over one vague sentence fails "includes a summary". Mechanical checks go to a script, not a judge. For two versions, a blind comparison (judge sees both outputs, not which is which) complements assertion grading.

**Aggregate** into `benchmark.json`: pass rate, time, tokens per configuration, and the delta. A skill that costs 13 s and lifts pass rate by 50 points is worth it; one that doubles tokens for 2 points is not. Standard deviation means something only with several runs per case.

---

## 4. Reading the Patterns

- Assertions passing in both configurations measure nothing; replace them.
- Assertions failing in both are broken, too hard, or wrong; fix before the next round.
- Assertions passing only with the skill show where it earns its place; find which instruction did it.
- Inconsistent results across runs mean an ambiguous instruction; add an example or sharpen the bound.
- A case 3× slower than the rest: read its transcript for the bottleneck.
- Every run rewrote the same helper: bundle it under `scripts/`.

**Human review** records one specific complaint per case in `feedback.json` ("months are alphabetical, not chronological"); empty means fine. Improve on the cases with complaints.

**Revise** by giving failed assertions, feedback, transcripts, and the current `SKILL.md` to a model with four rules: generalise from the examples (the skill runs on prompts nobody tested), keep it lean (remove instructions the transcripts show wasting work; if pass rate plateaus with more rules, try removing some), explain the why, bundle repeated work. Re-run everything into `iteration-N+1/`. Stop when feedback is empty, the user is satisfied, or improvement stalls.

---
