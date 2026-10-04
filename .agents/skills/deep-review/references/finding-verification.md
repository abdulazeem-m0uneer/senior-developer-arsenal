# Finding Verification & Reporting

How a candidate becomes a reported finding: proof standards, false-positive filters, severity scale, report layout, and the re-review loop.

---

## 1. Candidate Lifecycle

| State | Meaning | Reported as |
| :--- | :--- | :--- |
| Candidate | Suspicion logged during a pass | Not reported |
| Confirmed | Proven against the actual code | Finding with severity |
| Refuted | Shown to be wrong or guarded | Counted only |
| Unproven | Could not be proven or refuted with the access available | Open question, with what would settle it |

---

## 2. Proof Standards

| Proof type | Strength | Use for |
| :--- | :--- | :--- |
| Failing test or script that reproduces the fault | Strongest | Logic, boundary, concurrency, contract defects |
| Concrete input and the exact path it takes, line by line | Strong | Injection, authorization, null dereference |
| Measurement (query plan, timing, allocation count) | Strong | Performance claims |
| Trace through callers showing no guard exists | Adequate | Missing validation, missing transaction |
| "This looks risky" | None | Never reportable |

Verification steps for each candidate:
- [ ] Re-open the cited lines; confirm the path and line numbers at the reviewed commit.
- [ ] Read the whole enclosing function and every caller that can reach it.
- [ ] Check configuration and framework defaults that may already handle the case.
- [ ] Search the tests for an existing case that covers or contradicts the claim.
- [ ] State the trigger condition and the observable consequence in one sentence each.

---

## 3. False-Positive Filters

| Question | If yes |
| :--- | :--- |
| Is the input validated or constrained before it reaches this line? | Refute, or downgrade to hardening |
| Is the code path unreachable from any entry point? | Refute as a defect; report as dead code if in scope |
| Does a framework, middleware, or database constraint already enforce it? | Refute; cite where |
| Is the behaviour intended and documented? | Refute; note if the documentation is misleading |
| Is it pre-existing and outside the scope under review? | Move to a separate "pre-existing" list |
| Is it the same root cause as another finding? | Merge; list all locations under one finding |
| Is it a preference with no project rule behind it? | Drop |
| Would the proposed fix change behaviour that callers depend on? | Keep, and flag the compatibility cost |

---

## 4. Severity Scale

| Severity | Criteria | Merge decision |
| :--- | :--- | :--- |
| `[Blocker]` | Data loss or corruption, security breach, crash on a main path, wrong money, broken build | Must fix before merge |
| `[High]` | Wrong result on a realistic path, race under normal load, breaking contract change, missing test for critical logic | Fix before merge unless explicitly accepted |
| `[Medium]` | Edge-case defect, measurable inefficiency, missing error handling on a rare path, weak test | Fix in this change or track with an owner |
| `[Low]` | Maintainability, naming, minor duplication, documentation gap | Optional |

Rank by impact first, then likelihood. A finding without proof has no severity.

---

## 5. Report Layout

```text
Verdict: CLEAN | CHANGES REQUIRED   (iteration <n>)
Scope:   <base>...<head> or <path>, <files> files, <lines> changed lines
Baseline: build <ok|fail>, lint <ok|fail>, type-check <ok|fail>, tests <passed>/<failed>/<skipped>
Passes:  correctness, security, data integrity, concurrency, performance, tests, contracts, config, docs
Candidates: <raised> raised, <confirmed> confirmed, <refuted> refuted, <unproven> unproven
```

| # | Severity | Pass | Location | Finding | Proof | Fix |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | [Blocker] | Security | `api/invoices.ts:52` | Invoice loaded by ID without tenant filter | Request as tenant B with an ID owned by tenant A returns 200 | Add `tenantId` from the session to the query |

Followed by: open questions (unproven items), pre-existing issues outside scope, and files reviewed with no findings.

---

## 6. Re-Review Loop

1. For each fix: re-run its original proof and confirm it no longer reproduces.
2. Review the fix diff itself with every applicable pass; fixes introduce their own defects.
3. Re-run the baseline commands (build, lint, type-check, full test suite).
4. Re-run all passes over the lines changed since the last iteration and their callers.
5. Exit when one full iteration produces zero new confirmed findings, no open `[Blocker]` or `[High]`, and a green baseline. Otherwise increment the iteration number and repeat.

- [ ] A finding is closed only by evidence, never by the statement that it was fixed.
- [ ] Accepted risks are listed with who accepted them; they are not marked resolved.
