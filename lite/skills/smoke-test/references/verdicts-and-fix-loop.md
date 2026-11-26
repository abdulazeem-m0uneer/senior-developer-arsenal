# Verdicts, Failure Report & Fix Loop

What each verdict means and allows, the shape of the report, how to classify a failure, and the bounded loop that follows.

---

## 1. Verdicts

| Verdict | Exit | Condition | What may be said |
| :--- | :---: | :--- | :--- |
| `PASSED` | 0 | Every requested layer ran and every check in it passed | "Released and verified on `<commit>`." |
| `FAILED` | 1 | At least one check failed | "Released but NOT verified", with each failure. Enter the fix loop |
| `PARTIAL` | 3 | Nothing failed, but a layer or case was NOT RUN or could not be verified | "Not verified: `<what was not run and why>`." Never "it works" |
| Usage error | 2 | Bad arguments, target unreachable before layer 0 | Nothing about the release |

Causes of `PARTIAL`: the privileged account's credentials are absent, log access is absent, a case's precondition was missing, a subset of layers was requested, or the checkout is not the released commit. A release whose smoke run is always `PARTIAL` for the same reason has an open task, not a quirk.

Decision rule, in this order: any failure gives `FAILED`; otherwise any NOT RUN gives `PARTIAL`; otherwise `PASSED`.

---

## 2. Report Shape

```text
Target staging  commit 4f2a9c1  started 14:02:11Z  tag smoke-7k2d

| Layer                 | Passed | Failed | Not run |
| 0 release identity    |      1 |      0 |       0 |
| 1 every route         |    142 |      1 |       0 |
| 2 journeys            |     57 |      1 |       3 |
| 3 after the run       |      2 |      0 |       0 |

FAILED

1. layer 2  POST /v1/orders  request id 01J9...
   expected: 201 with a body matching the order schema
   got:      500 {"code":"internal_error","requestId":"01J9..."}
   logged:   error "null value in column tenant_id" orders.repository:88
NOT RUN: staff journeys (3 cases): no staff credentials on this machine
```

- Every failure carries the request id, the expectation, the actual answer, and the lines that request logged.
- Every value marked secret is replaced in the whole report, longest first so one secret inside another leaves nothing behind.
- A `--json` form of the same data lets the release script and the tracker consume the verdict.

---

## 3. Name the Kind of Failure

| Kind | Signs | Action |
| :--- | :--- | :--- |
| (a) Logic defect | Fails locally as well; the code does something the contract or the rule does not say | Fix loop, section 4 |
| (b) Configuration, secret, or infrastructure | Passes locally, fails deployed; missing variable, wrong URL, permission, migration not applied | Correct the environment through its normal change route; rerun |
| (c) Outside service or its mock | The failing call depends on a provider; the provider or mock answers unexpectedly | Fix the adapter or the mock (`provider-sdk`); a provider outage is reported, not masked |
| (d) The case is wrong | The API behaves as documented; the case expects something else | Correct the case in its own reviewed change that says why |
| (e) Made-up data missing | A precondition account or record does not exist | It should have been NOT RUN: change `check` to `need`, or create the data through the API |

Decide the kind from evidence (the request's log lines and trace, the endpoint's documented behaviour), not from which fix is quickest. Calling a logic defect "the case is wrong" is the commonest way a suite rots.

---

## 4. The Fix Loop

1. **Look.** Take the request id from the failure; fetch that request's log lines and trace. A refusal below 500 and a wrong success often log nothing: the trace and the response body are then the evidence.
2. **Reproduce locally** with the one case file against the `local` target.
3. **Failing test first**: a unit test for the rule, and a test through the real route. Both fail before the fix.
4. **Fix**, then rerun the case, then the local smoke suite, then the full gate (`quality-gate`).
5. **Review and CI** as for any change (`ci-wait`); the fix ships alone, with no feature riding on it.
6. **Release again and run the suite again** from the new commit. The verdict of the earlier run is void.
7. **Stop after two rounds.** If a failure is still open after the second fix was released and smoked, stop, and report: the failures, what was tried, the evidence, and the state the environment is in.

| Never | Because |
| :--- | :--- |
| Delete, skip, or loosen a case to get green | The suite then certifies the defect |
| Call a release working with a failure or a NOT RUN open | Only `PASSED` carries that meaning |
| Patch data in the database to make a case pass | The next user hits the same defect |
| Quote one-time codes, tokens, or personal data from logs into a pull request or a ticket | Logs of a test environment still hold secrets |
| Start a third round silently | Two failed rounds mean the diagnosis is wrong; a person must decide |

---

## 5. Stop Report Template

```text
Smoke verdict: FAILED after 2 fix rounds. Release <commit> is NOT verified.
Open failure: <METHOD path>, request id <id>, expected <x>, got <y>.
Round 1: <diagnosis> -> <fix commit> -> still failing because <evidence>.
Round 2: <diagnosis> -> <fix commit> -> still failing because <evidence>.
Environment now: <commit deployed>, <data left behind, tagged smoke-...>.
Options: roll back to <previous commit> | keep and investigate | <other>.
```
