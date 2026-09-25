---
name: root-cause-investigator
description: Autonomous root-cause investigation skill using applied rationality, 5+ competing hypotheses, and 5-Whys causal analysis. Use when diagnosing elusive bugs, intermittent test failures, unexplained crashes, production outages, or confusing regressions.
---

# 🔍 Root Cause Investigator

A disciplined investigation procedure applying defensive epistemology to eliminate confirmation bias, stop speculative flailing, and isolate the systemic root cause of complex failures.

---

## 🛑 Operating Constraints & Token Conservation

1. **No Speculative Tool Chaining**: Do not run commands without an explicit hypothesis.
2. **Rule 0**: If an experiment or test fails unexpectedly, STOP immediately. Report raw error and theory.
3. **Progressive Retrieval**: Read reference templates only when writing or structuring formal investigations:
   - [Investigation Template](references/investigation-template.md)
   - [Epistemic Checklist](references/epistemic-checklist.md)

---

## 📋 The 5-Step Investigation Procedure

### Step 1: Establish Ground-Truth Facts
- Isolate observable reality from human or model interpretation.
- Collect raw logs, stack traces, exact command exit codes, and timestamps.
- Explicitly partition into **Verified Facts** (observed) vs. **Assumptions** (unverified).

### Step 2: Formulate 5+ Competing Hypotheses
Never chase a single theory—confirmation bias will cause you to hallucinate evidence to fit it. Formulate at least 5 distinct possibilities across layers:
1. *Code Logic / State Machine Error*
2. *Environment / Configuration Divergence*
3. *Timing / Concurrency / Race Condition*
4. *Data Invariant Violation / Schema Mismatch*
5. *Dependency / Infrastructure / Network Fault*

### Step 3: Design Discriminative Tests
- For each test, write:
  - `HYPOTHESIS`: Which theory is being tested.
  - `TEST`: The minimal isolating command or assertion.
  - `EXPECTATION`: What must happen if theory is TRUE vs. FALSE.
- Run one test at a time. Record result.

### Step 4: The 5-Whys Causal Tree
When the proximate fault is found, do not stop at the surface. Ask:
- *Immediate Cause*: What code directly broke?
- *Systemic Cause*: Why did the test suite or type checker permit this?
- *Architectural Root Cause*: Why was the system designed to be breakable this way?

### Step 5: Surgical Fix & Verification
- Apply Chesterton's Fence: verify why the previous code existed before altering it.
- Produce a surgical fix ($<10$ lines where possible).
- Add a regression test that fails without the fix and passes with it.
- Report findings using the [Investigation Template](references/investigation-template.md).
