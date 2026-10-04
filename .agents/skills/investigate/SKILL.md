---
name: investigate
description: 'Autonomous root-cause investigation procedure using defensive epistemology, 5+ competing hypotheses, and 5-Whys causal analysis. Use when the user reports an elusive bug, intermittent test failure, unexplained crash, production outage, or runs /investigate. Triggers on: "investigate bug", "debug crash", "find root cause", "/investigate". Do not use for standard PR review (use code-review) or general performance profiling (use perf-audit).'
---

# Epistemic Root-Cause Investigation Procedure

Use this skill when diagnosing elusive bugs, intermittent test failures, system crashes, or confusing regressions.

---

## 1. When to Use This Skill

Activate this skill when:
- Investigating non-deterministic failures, concurrency deadlocks, or silent data corruption.
- Diagnosing unexplained regressions after a release or dependency upgrade.
- The user runs the `/investigate` slash command or asks to find the root cause of an issue.

*Boundary*: For standard code change auditing, use `code-review`. For database/event loop performance bottlenecks, use `perf-audit`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Ground-Truth Data Collection
1. Capture raw error output, stack traces, and failing test assertions without model editorializing.
2. Separate verified facts (`"I verified X via log/test"`) from assumptions (`"I assume Y"`).
3. If a tool fails, enforce **Rule 0**: STOP immediately. Do not speculate or blindly retry.

### Step 2: Formulate 5+ Competing Hypotheses
Consult: [Investigation Template](./references/investigation-template.md)
Generate at least 5 distinct, competing hypotheses covering:
- Invariant & Domain Logic
- Concurrency, Timing & Race Conditions
- State & Environmental Drift
- Data Integrity & Schema Constraints
- Tooling, Transpilation & Dependencies

### Step 3: Execute Discriminative Tests
1. For each test, declare expected outcome before execution (`EXPECT`).
2. Run minimal isolating command or test script.
3. Compare reality with expectation (`MATCHES: yes/no`). If reality diverges, debug mental model, not reality.

### Step 4: 5-Whys Causal Tree & Chesterton's Fence
Consult: [Epistemic Checklist](./references/epistemic-checklist.md)
1. Trace from symptom $\to$ proximate failure $\to$ missing check $\to$ test blindspot $\to$ systemic cause.
2. Verify Chesterton's Fence: Understand why the existing code was originally written before changing it.

### Step 5: Deliver Structured Investigation Report
Format output using the standardized template:
- **Verified Facts vs Assumptions**
- **Ruled-Out Hypotheses (with falsifying evidence)**
- **Root Cause (5-Whys Causal Chain)**
- **Surgical Fix (< 10 lines)**
- **Reproduction Test Proving Permanence**

---

## 3. Verification Protocol

1. Run the reproduction test before fix $\to$ assert failure.
2. Apply surgical fix.
3. Run the reproduction test after fix $\to$ assert pass.
4. Run full test suite to guarantee zero regression blast radius.

---

## 4. ⚡ Token-Saving Execution Rule

- **Zero Guessing**: Do not chain speculative edits.
- **Compact Causal Tables**: Output findings in structured Markdown tables.
- **Surgical Diff Only**: Show only the exact minimal fix lines.
