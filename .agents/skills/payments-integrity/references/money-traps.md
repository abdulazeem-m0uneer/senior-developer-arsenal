# Money Traps

The traps that recur in every payment system: what goes wrong, the rule that prevents it, and the test that proves the rule holds.

---

## 1. Amounts and Rounding

| Trap | What goes wrong | Rule | Test that proves it |
| :--- | :--- | :--- | :--- |
| Floating-point amounts | `0.1 + 0.2` drifts; totals differ by one minor unit | Integer minor units end to end, including JSON (integer or string, never a decimal number) | Property test: sum of 10,000 random amounts equals the integer sum |
| Amount without currency | Two currencies added together | Amount and currency travel as one value; arithmetic across currencies throws | Adding two different currencies raises |
| Wrong exponent | A zero-decimal or three-decimal currency charged 100 times off | Exponent comes from a currency table, never a hard-coded `* 100` | Convert a major amount for a 0, 2 and 3 decimal currency |
| Rounding in several places | Parts do not sum to the total | Round once, named mode; give the remainder to one named party | Split of an odd amount: parts sum to the whole |
| Percentages on display values | Fee computed from a rounded figure | Compute from minor units with basis points | Fee on 1 minor unit and on the maximum amount |

---

## 2. Idempotency and Gateway Calls

| Trap | What goes wrong | Rule | Test that proves it |
| :--- | :--- | :--- | :--- |
| No idempotency key | A client retry charges twice | Key required on every money operation; unique constraint stores outcome | Same request twice returns the same payment; one gateway call recorded |
| Same key, different body | A reused key silently returns an unrelated result | Store a request fingerprint; mismatch is a 422 | Same key with another amount is refused |
| Gateway call inside a transaction | Charge succeeds, rollback loses the row; or a slow gateway holds locks | Attempt row committed first, one call, answer stored after | Fail the second write: the attempt row still exists and is recoverable |
| Blind retry on time-out | The first call succeeded; the retry is a second charge | Outcome unknown means read the payment by your reference, then decide | Stub a time-out after success: exactly one charge |
| Automatic retries in the HTTP client | Hidden duplicate charges | Retries off for money calls unless the gateway honours an idempotency key you send | Assert the client's retry count for the money client is 0 |
| Trusting the client's result | A forged "success" redirect grants the goods | Confirm with the gateway: amount, currency, status, your reference | Forged success with no gateway payment changes nothing |
| Amount taken from the client | Customer pays 1 for an order of 100 | Amount computed server-side from the order; compared again on confirmation | Tampered amount is refused |

---

## 3. Webhooks

| Trap | What goes wrong | Rule | Test that proves it |
| :--- | :--- | :--- | :--- |
| Unsigned or wrongly verified webhook | Anyone can mark a payment paid | Signature over the raw body, constant-time compare, timestamp tolerance | Wrong signature and old timestamp both get 401 and no state change |
| Duplicate delivery | Paid twice in the ledger | Event id under a unique constraint; the duplicate is acknowledged and ignored | Same event delivered three times: one ledger transaction |
| Out-of-order delivery | "refunded" arrives before "captured" and is dropped or mis-applied | Apply only legal transitions; otherwise re-read the gateway state | Deliver in reverse order: final state is correct |
| Slow handler | Gateway times out and redelivers in a storm | Store, acknowledge with 2xx, process from a queue | Handler returns before processing completes |
| Unknown event type | Silently dropped, or posted by a default branch | Store and alert; never post | Unknown type: stored, alert raised, no ledger entry |
| Webhook races the client's confirmation | Both paths post the same capture | Both go through one settle function keyed on the payment reference | Run both concurrently: one posting |

---

## 4. State, Refunds, and Balances

| Trap | What goes wrong | Rule | Test that proves it |
| :--- | :--- | :--- | :--- |
| Status set freely | `refunded` back to `captured`; `failed` to `captured` | Transition table; guarded update `WHERE status = <expected>` | Every illegal pair in the table is refused |
| Capture twice | Double capture or capture after void | One terminal outcome per authorisation | Parallel capture and void: exactly one wins |
| Refund above the capture | Money paid out that was never received | Refundable = captured minus refunded minus pending, checked under a lock | Two parallel refunds whose sum exceeds the capture: one refused |
| Refund counted only when settled | Pending refunds overlap | Pending refunds reduce the refundable amount at once | Second refund while the first is pending is limited |
| Balance column updated in place | Lost update under concurrency; no history | Balance derived from entries; a cached balance is rebuilt and compared | 50 parallel debits never take the balance below zero |
| Spend check and debit in separate steps | Double spend from a wallet | One atomic step: lock the account row, check, post | Parallel spends of the full balance: one succeeds |
| Editing a ledger entry | History cannot be audited | Append only; correct with a reversing transaction | Application role has no UPDATE or DELETE on ledger tables |

---

## 5. Reconciliation, Audit, and Exposure

| Trap | What goes wrong | Rule | Test that proves it |
| :--- | :--- | :--- | :--- |
| No reconciliation | A lost webhook is never noticed | Daily job matches the gateway report to the ledger in both directions | Seed a gateway line with no ledger match: alert raised |
| Reconciling totals only | Two opposite errors cancel | Match line by line on the gateway reference | Two offsetting errors are both reported |
| Fees ignored | Bank deposit never equals captures | Gateway fees are posted to their own account from the settlement report | Settlement with a fee balances to zero |
| Card data stored or logged | PCI scope and breach liability | Hosted fields or redirect; store token, last four, brand only | Scan logs and tables for card-number patterns |
| No audit trail | Nobody can say who refunded | Actor, permission, reason, and time recorded with each movement | Refund without an actor is refused |
| Internal figures in customer answers | Commission or supplier payout leaks | Separate response shapes per audience | Customer response contains no fee or payout field |
| Manual database fix | Books no longer explainable | Corrections are posted through the same ledger path with a reason | No write path to money tables outside the ledger module |

---

## 6. Review Order

1. Amount type and currency on every new field and parameter.
2. Idempotency key and unique constraint on every new operation.
3. Position of each gateway call relative to transaction boundaries.
4. Source of truth for each status change (gateway read, not client).
5. Webhook signature, deduplication, ordering.
6. Refund and balance checks under a lock.
7. Ledger postings sum to zero; no update or delete.
8. Reconciliation covers the new flow; audit record written.
