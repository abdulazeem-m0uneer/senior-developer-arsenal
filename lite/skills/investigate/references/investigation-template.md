# Root Cause Investigation Artifact Template

Use this format when documenting complex incident investigations, production bugs, or regression audits.

---

```markdown
# 🔬 Incident / Bug Investigation: [Issue Title]

**Date**: YYYY-MM-DD
**Investigator**: [Agent / Subagent]
**Status**: [Investigating | Root Cause Identified | Resolved | Blocked]

---

## 1. Ground Truth (Observable Facts)

| # | Verified Fact | Source Evidence (Log / Test / File Link) |
| :- | :--- | :--- |
| 1 | Exact error string / exit code | `stderr: ...` |
| 2 | Failing test or reproduction command | `npm test -- ...` or `dotnet test -- ...` |
| 3 | Observed divergence | Expected X, observed Y |

---

## 2. Competing Hypotheses Matrix

| ID | Hypothesis | Layer | Likelihood | Discriminative Test | Result |
| :--- | :--- | :--- | :---: | :--- | :---: |
| **H1** | [Logic / State bug] | Application | High | [Specific test / log point] | [Confirmed / Disproved] |
| **H2** | [Timing / Concurrency] | Runtime | Med | [Concurrency stress test] | [Disproved] |
| **H3** | [Environment / Config] | Infra | Low | [Config verification] | [Disproved] |
| **H4** | [Database / Invariant] | Data | Med | [Raw DB query check] | [Disproved] |
| **H5** | [Dependency / Tooling] | External | Low | [Version audit] | [Disproved] |

---

## 3. The 5-Whys Analysis

1. **Why did the failure occur?**
   - *Direct Cause*: [e.g., NullReferenceException thrown in OrderService.cs#L45]
2. **Why was that condition present?**
   - *Proximate Cause*: [e.g., Session state was null when background queue worker processed order]
3. **Why was that state allowed into the queue?**
   - *Validation Gap*: [e.g., DTO mapper did not validate session token presence before enqueue]
4. **Why didn't tests catch this?**
   - *Test Blindspot*: [e.g., Unit tests mocked the queue without testing full async lifecycle]
5. **Systemic Root Cause (Why was it breakable?):**
   - *Architectural Root*: [e.g., Missing compile-time non-nullable contract on QueueMessage payload]

---

## 4. Chesterton's Fence Audit

- **Why did the original code exist?**: [Explain original design rationale]
- **Risks of modification**: [Downstream consumers affected]
- **Verification of safety**: [Proven by reference search]

---

## 5. Surgical Fix & Verification

- **Code Fix**: [File links with 2-5 line surgical diff]
- **Automated Regression Test**: [Link to test demonstrating pass/fail]
- **Verification Command**: `[command]` $\to$ `PASS`
```
