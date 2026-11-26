# Bug Report & Sign-Off Templates

Defect report format, severity and priority scales, triage rules, and the release sign-off checklist.

---

## 1. Bug Report Template

```text
Title:        <component>: <what fails> when <condition>
ID:           BUG-<n>          Found in: <build / commit / version>
Environment:  <env, OS, browser or client, account role, feature flags>
Severity:     S1 | S2 | S3 | S4        Priority: P0 | P1 | P2 | P3
Reproduction rate: <n of m attempts>

Preconditions:
  - <state and data required before step 1>
Steps to reproduce:
  1. <single action>
  2. <single action>
Expected result: <what the criterion or spec says must happen>
Actual result:   <what happened, exact message or value>
Evidence:        <screenshot, request and response, log line with correlation ID>
Traces to:       <acceptance criterion or test case ID>
Workaround:      <none | steps>
Regression:      <yes, last good build | no | unknown>
```

- [ ] Title is searchable and states the failure, not the feature name alone.
- [ ] Steps start from a clean, stated precondition and are the minimum needed.
- [ ] Expected and actual are facts; hypotheses about the cause go in a separate note.
- [ ] One defect per report; related defects are linked, not merged.
- [ ] Secrets, tokens, and personal data are redacted from evidence.

---

## 2. Severity (Impact) and Priority (Urgency)

| Severity | Meaning | Example |
| :--- | :--- | :--- |
| S1 Critical | Data loss, security breach, outage, money wrong, no workaround | Double charge on retry |
| S2 Major | Core function broken or wrong for many users; workaround is costly | Export omits rows over 1 000 |
| S3 Minor | Non-core function wrong; easy workaround | Sort order resets after edit |
| S4 Trivial | Cosmetic, wording, alignment | Label truncated at 320 px |

| Priority | Meaning | Action |
| :--- | :--- | :--- |
| P0 | Stop the release or hotfix now | Fix before anything else |
| P1 | Must fix in this release | Blocks sign-off |
| P2 | Fix in the next planned release | Listed as known issue |
| P3 | Fix when convenient | Backlog |

Severity and priority are independent: a typo in the company name on the landing page is S4 / P1; a crash in a rarely used admin export may be S2 / P2.

---

## 3. Triage and Lifecycle

| State | Meaning | Exit condition |
| :--- | :--- | :--- |
| New | Filed, not yet reviewed | Reproduced by a second person or rejected with a reason |
| Confirmed | Reproduced, severity and priority agreed | Assigned |
| In progress | Fix under way | Fix merged with a regression test |
| Ready for retest | Fix deployed to the test environment | Original steps re-run |
| Closed | Retest passed and neighbouring cases re-run | none |
| Reopened | Retest failed | Returns to In progress with new evidence |

- [ ] A fix is retested with the original steps and with the adjacent boundary and negative cases.
- [ ] `Cannot reproduce` requires the exact build, data, and steps that were tried.
- [ ] Duplicates link to the original and add any new evidence there.

---

## 4. Release Sign-Off Checklist

- [ ] Every acceptance criterion in scope has executed cases with recorded results.
- [ ] No open S1 or S2 defects; every open P0 / P1 is fixed and retested.
- [ ] Regression suite executed on the release candidate build, not on an earlier build.
- [ ] Automated suites (unit, integration, end-to-end) are green on the same commit.
- [ ] Data migrations verified forward on a production-like copy; rollback path rehearsed.
- [ ] Non-functional checks done where in scope: performance against stated targets, accessibility, supported browsers and devices, localization.
- [ ] Security-sensitive changes (auth, permissions, payments, personal data) had negative and permission cases executed.
- [ ] Feature flags, configuration, and secrets for the target environment are confirmed.
- [ ] Monitoring, alerts, and a post-release smoke check are in place.
- [ ] Known issues are listed with severity, owner, workaround, and target release.

Verdict table:

| Area | Result | Evidence | Blocking defects |
| :--- | :--- | :--- | :--- |
| Functional (AC-1 to AC-9) | Pass | Run 214: 87 / 87 | none |
| Regression | Pass with known issue | Run 215: 143 / 144 | BUG-22 (S3, P2) |
| Performance | Not run | Target environment unavailable | Decision required |

**Verdict**: `GO` | `GO WITH KNOWN ISSUES` | `NO-GO`. Any `Not run` area in scope means the verdict cannot be `GO` without an explicit, recorded risk acceptance by the release owner.
