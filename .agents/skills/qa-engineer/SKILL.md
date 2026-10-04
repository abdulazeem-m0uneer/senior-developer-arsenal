---
name: qa-engineer
description: 'QA engineering runbook: derive testable acceptance criteria, write test plans and test cases (positive, negative, boundary, state-transition), run exploratory charters, select the regression suite, file reproducible bug reports with severity and priority, and run the release sign-off checklist. Use when the user asks for a test plan, test cases, a bug report, or QA sign-off. Triggers on: "test plan", "test cases", "acceptance criteria", "bug report", "/qa-engineer". Do not use for automated test code design (use test-strategy) or tests for a code change (use test-every-change).'
---

# QA Engineering Procedure

This skill guides the agent through quality assurance of a feature or release from the outside in: what must be true, how to prove it, how to report what is broken, and when the release may ship.

---

## 1. When to Use This Skill

Activate this skill when:
- A requirement, ticket, or user story needs testable acceptance criteria.
- A feature or release needs a test plan, test cases, or an exploratory testing session.
- A defect must be written up so that another engineer can reproduce it on the first attempt.
- A release candidate needs a regression scope and a go / no-go sign-off.
- The user runs the `/qa-engineer` slash command.

*Boundary*: For the design of automated test code (layers, doubles, flaky tests), use `test-strategy`. For writing the tests that a specific code change requires, use `test-every-change`. For the engineering completion gate of a feature, use `definition-of-done`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Derive Acceptance Criteria
1. Read the requirement source (ticket, spec, user story, API contract) and the code or UI that implements it. List every actor, input, output, and business rule.
2. Write each criterion as `Given / When / Then` with a measurable outcome. Reject wording such as "works correctly" or "fast"; replace it with an observable result or a number.
3. Give each criterion a stable ID (`AC-1`, `AC-2`) and record open questions instead of guessing the intended behaviour.

### Step 2: Plan by Risk
1. Rate each area by likelihood of failure and impact (money, data loss, authorization, legal, core journey).
2. Write the plan: scope, out of scope, environments and test data, entry criteria, exit criteria, and who decides.
3. Spend depth where the risk is: high-risk areas get every technique in Step 3; low-risk areas get a smoke case.

### Step 3: Design Test Cases
Consult: [Test Design Techniques & Templates](./references/test-design-techniques.md)
- **Positive**: the documented happy path for each criterion.
- **Negative**: invalid, missing, malformed, unauthorized, and out-of-order input; assert the exact error and that no state changed.
- **Boundary**: each limit at minimum, minimum - 1, maximum, maximum + 1, plus empty and one.
- **State-transition**: every valid transition, and every invalid one attempted from each state.
- Every case has an ID, preconditions, numbered steps, test data, one expected result per step, and the criterion it traces to.

### Step 4: Explore
Run time-boxed exploratory charters ("explore <area> with <resource> to discover <information>") on the high-risk areas. Log what was covered, what was not, and every anomaly, even if unconfirmed.

### Step 5: Select the Regression Suite
Start from the change set: touched modules, their callers, shared components, data migrations, and configuration. Add the permanent smoke set (sign-in, core create / read / update / delete, payment or other money path). State what was deliberately left out and why.

### Step 6: Report Defects
Write each bug with the [Bug Report & Sign-Off Templates](./references/bug-report-and-signoff.md): one defect per report, minimal reproduction steps, expected versus actual, environment, evidence, severity (impact) and priority (urgency) set independently. Reproduce it twice before filing; state the reproduction rate when it is intermittent.

### Step 7: Sign Off
Walk the release sign-off checklist and issue a verdict: `GO`, `GO WITH KNOWN ISSUES` (each listed with owner and workaround), or `NO-GO`.

---

## 3. Verification Protocol

1. Traceability is complete: every acceptance criterion maps to at least one positive and one negative case, and every case maps back to a criterion or a named risk.
2. Every executed case has a recorded result (`Pass`, `Fail`, `Blocked`, `Not run`) with evidence; `Blocked` and `Not run` carry a reason.
3. Every open defect has severity, priority, and reproduction steps verified from a clean state.
4. Output the summary table:

| Criterion | Cases (pos / neg / boundary / state) | Passed | Failed | Blocked | Open defects |
| :--- | :---: | :---: | :---: | :---: | :--- |
| AC-1 Refund within 30 days | 2 / 3 / 4 / 2 | 10 | 1 | 0 | BUG-14 (S2, P1) |
| AC-2 Refund denied after 30 days | 1 / 2 / 2 / 1 | 6 | 0 | 0 | none |

---

## 4. ⚡ Token-Saving Execution Rule

- **Tables Over Prose**: Deliver criteria, cases, and results as compact tables; no testing theory.
- **Failures First**: Report failed and blocked cases in full; summarize passes as counts.
- **One Defect, One Report**: Never restate the test case inside the bug report; link it by ID.
