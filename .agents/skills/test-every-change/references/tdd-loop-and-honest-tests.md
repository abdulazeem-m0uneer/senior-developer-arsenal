# TDD Loop Enforcement & Honest Tests

## 1. The Loop

```text
RED      write one minimal test for one behaviour
         run it; confirm it FAILS (not errors) for the expected reason
GREEN    write the simplest code that passes; nothing beyond the test
         run it; confirm it passes and the project suite is green with pristine output
REFACTOR after green only: duplication, names, helpers; no new behaviour
NEXT     the next failing test
```

Verify RED is mandatory. Test passes immediately: it tests existing behaviour; fix the test. Test errors (typo, import): fix until it fails correctly. Cannot explain why it failed: you do not know what it tests.

Verify GREEN means the project's suite, not your file. A scope statement in the task bounds the deliverable, not the verification. Every failure that run shows, including one you did not cause, goes in the report by name.

One vertical slice at a time: one seam, one test, one implementation, repeat. Writing all tests first and all code after tests the imagined shape of things and commits to test structure before the implementation teaches anything.

---

## 2. Code Before Test

Production code written before its failing test is deleted and rewritten from the test. Not kept as reference, not adapted while writing tests, not looked at. Exploration spikes are thrown away; TDD starts fresh. Exceptions, each with the user's say-so: throwaway prototypes, generated code, configuration files.

| Excuse | Reality |
| :--- | :--- |
| `Too simple to test` | Simple code breaks; the test costs 30 seconds. |
| `I will test after` | A test written after passes immediately and proves nothing; it checks the cases you remembered, not the ones you would have discovered. |
| `Already manually tested` | No record, no re-run, no edge cases. |
| `Deleting X hours is wasteful` | Sunk cost. Code you cannot trust is the waste. |
| `Keep as reference` | You will adapt it. That is testing after. |
| `Test is hard to write` | Design is hard to use. Listen to the test; simplify the interface. |

---

## 3. Name the Break

Before writing a test body: what production change makes this test fail, and is that change a bug or a decision?

| Answer | Action |
| :--- | :--- |
| Cannot name one | Redesign around an observable behaviour |
| `The source text changed` | Run the artifact and assert its effects; never grep source |
| Only intentional decisions (a constant's value, exact wording, private structure) | Change detector: fires on redesign, sleeps through bugs. Test the behaviour that depends on the decision: not `MAX_RETRIES == 5` but `a failing call is retried 5 times and a 6th never happens` |
| A wrong branch, missing side effect, wrong argument, boundary, broken contract | Write it |

Expected values come from an independent source: a literal, a hand-checked fixture, the spec. An expectation computed by the code under test or its helpers passes whatever the code does:

```ts
// mirror assertion: always true
expect(buildQuery({ tag: 'urgent' })).toBe(buildQuery({ tag: 'urgent' }));
// hand-derived literal
expect(buildQuery({ tag: 'urgent' })).toBe('tag:"urgent"');
```

Test your contract at the boundary (the route you register, the query you emit, the payload you produce), not the framework's mechanics. Constructors, getters, constants, and trivial forwarding earn a test only when they validate, normalise, default, derive, enforce, or cause side effects.

---

## 4. Exercise the Real Thing

- A mock earns no assertions. An assertion on the mock passes when the mock is present and fails when it is absent; it says nothing about the component. Assert the real behaviour; if the mock is what you check, unmock it or delete the assertion.
- Mock at the right level: learn every side effect of the real method first; mock the slow or external operation below the side effects the test depends on. The classic failure: the mock swallows the config write the next step reads.
- Doubles are specific: when arguments, counts, or order are part of the contract, assert them; a fake that accepts anything verifies nothing. Separate fixtures per branch (success, error, malformed).
- Mock responses mirror the complete real structure, all documented fields. A partial mock passes while integration breaks on the omitted field.
- Production classes carry production methods only. Cleanup only tests need lives in test utilities, never as `destroy()` on the class.
- Mock setup larger than the test logic, mocks missing methods the real thing has, tests breaking when the mock changes: switch to an integration test with real components.

---

## 5. Mutation Check Before Finishing

Mentally mutate the production code; at least one test must fail for each:

- wrong constant or argument
- wrong branch handler
- missing state change or side effect
- empty or default return
- missing validation for zero, empty, nil, unauthorised, malformed

A mutation nothing catches marks the behaviour unprotected, or the test tautological.

---

## 6. Warning Signs

Setup and assertion share one object, so equality is guaranteed / the test can fail only via crash or missing selector / it fails on every intentional change, never on accidental breakage / expected values hidden behind loops, builders, helpers / it asserts a `*-mock` test id / a method called only from tests / mock setup over half the test / `mocking just to be safe`.

Adapted from obra/superpowers (MIT) and mattpocock/skills (MIT).
