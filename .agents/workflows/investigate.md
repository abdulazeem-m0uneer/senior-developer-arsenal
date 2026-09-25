---
name: investigate
description: Run a structured root-cause investigation using defensive epistemology, competing hypotheses, and 5-Whys causal analysis.
---

# 🔎 Workflow: /investigate

Use this workflow when diagnosing intermittent test failures, system crashes, data corruption, or confusing regressions.

---

## Steps

1. **Ground-Truth Data Collection**:
   - Capture exact error output, failing test assertions, or stack traces without model editorializing.
   - Separate verified facts from unverified assumptions.

2. **Generate Competing Hypotheses**:
   - Formulate 5+ competing theories across:
     - Application Logic / Invariants
     - Timing / Concurrency / Race Conditions
     - Environment / Configuration State
     - Database Constraints / Data Drift
     - External Dependencies / Tooling

3. **Execute Discriminative Tests**:
   - For each test: declare `EXPECT`, run minimal isolating test, compare `RESULT`.
   - Batch size $\le 3$. Stop if any test produces unexpected outcome (Notice Confusion).

4. **5-Whys Causal Tree**:
   - Traverse from immediate failure $\to$ proximate state $\to$ validation gap $\to$ test blindspot $\to$ systemic root cause ("Why was this breakable?").

5. **Surgical Fix & Regression Proof**:
   - Verify Chesterton's Fence.
   - Implement surgical fix ($<10$ lines).
   - Write and run reproduction test to guarantee permanence.
   - Output structured investigation table.
