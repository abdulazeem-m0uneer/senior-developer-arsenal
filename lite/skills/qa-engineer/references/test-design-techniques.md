# Test Design Techniques & Templates

Technique selection table, acceptance-criteria rules, test plan and test case templates, exploratory charters, and regression selection.

---

## 1. Acceptance Criteria Quality Gate

| Check | Bad | Good |
| :--- | :--- | :--- |
| Observable | "Refund works" | "Then the order status is `Refunded` and the customer receives email `refund-confirmed`" |
| Measurable | "Search is fast" | "Then results render within 500 ms at p95 for 10 000 products" |
| Single outcome | "User can edit and delete" | Two criteria, one per behaviour |
| States the negative | (missing) | "Given an order older than 30 days, then the refund is rejected with `REFUND_WINDOW_EXPIRED`" |
| Free of implementation | "Calls `RefundService`" | Describes behaviour visible to the actor |

- [ ] Each criterion has an ID, an actor, a precondition, a trigger, and an expected result.
- [ ] Roles, limits, and error messages are named explicitly; unknowns are listed as open questions.

---

## 2. Technique Selection

| Technique | Use when | How to derive cases |
| :--- | :--- | :--- |
| Equivalence partitioning | Input has ranges or categories | One case per valid class and per invalid class |
| Boundary value analysis | Numeric, length, date, or count limits | min - 1, min, min + 1, max - 1, max, max + 1, empty, one |
| Decision table | Outcome depends on combinations of conditions | One column per rule; cover every rule, collapse impossible ones |
| State-transition | Entity has a lifecycle (order, subscription, ticket) | Every valid transition once; every invalid transition from each state |
| Pairwise | Many independent options (browser, role, locale, plan) | Cover every pair of values, not every combination |
| Error guessing | Experience suggests weak spots | Double submit, back button, session expiry mid-flow, paste, emoji, very long text |
| Use-case / journey | End-to-end value | Main flow, each alternate flow, each exception flow |

State-transition matrix example (`-` means the transition must be rejected and tested as a negative case):

| From \ Event | pay | ship | cancel | refund |
| :--- | :---: | :---: | :---: | :---: |
| Draft | Paid | - | Cancelled | - |
| Paid | - | Shipped | Cancelled | Refunded |
| Shipped | - | - | - | Refunded |
| Cancelled | - | - | - | - |

---

## 3. Test Plan Skeleton

| Section | Content |
| :--- | :--- |
| Scope | Features and criteria covered |
| Out of scope | What is not tested and why |
| Risks | Area, likelihood, impact, mitigation |
| Environments & data | URLs, builds, accounts per role, seeded data, feature flags |
| Approach | Techniques per area, automated versus manual split |
| Entry criteria | Build deployed, smoke suite green, test data ready |
| Exit criteria | All high-priority cases run, no open S1 / S2 defects, sign-off recorded |
| Schedule & owners | Who executes, who decides go / no-go |

---

## 4. Test Case Template

| Field | Example |
| :--- | :--- |
| ID / Title | `TC-031` Refund rejected after the 30-day window |
| Traces to | `AC-2` |
| Type | Negative, boundary |
| Preconditions | Customer `qa-buyer-01`; order paid 31 days ago |
| Test data | Order total 49.99, card ending 4242 |
| Steps | 1. Open the order. 2. Select "Request refund". 3. Confirm. |
| Expected | Step 3: error `REFUND_WINDOW_EXPIRED`; order status stays `Paid`; no payment call made |
| Result / Evidence | Pass, Fail, Blocked, Not run; screenshot, response body, log line |

- [ ] One behaviour per case; steps are atomic and repeatable by someone new to the product.
- [ ] Expected results state both the visible response and the persisted state.
- [ ] The case cleans up or uses unique data so it can run again.

---

## 5. Exploratory Charter

```text
Charter:   Explore <area> with <tools, data, persona> to discover <risk or information>
Time box:  45-90 minutes
Notes:     what was tried, what was observed, questions raised
Coverage:  areas touched / areas not reached
Findings:  defects filed (IDs), anomalies to follow up
```

Heuristics to rotate: interrupt (refresh, back, lose network), concurrency (two tabs, two users), extremes (zero, huge, unicode), permissions (wrong role, expired session), time (time zone, month end), configuration (flags off, empty tenant).

---

## 6. Regression Selection

| Source | Include |
| :--- | :--- |
| Changed code | Cases for every touched module and its direct callers |
| Shared components | Auth, navigation, shared forms, shared libraries the change touches |
| Data changes | Migration forward, existing records still readable, rollback |
| Defect history | Cases for areas with recent or recurring defects |
| Permanent smoke set | Sign-in, core journey, money path, critical integrations |

- [ ] Cases are ordered by risk so a cut-short run still covers the highest risk.
- [ ] Excluded areas are listed with the reason, never silently dropped.
