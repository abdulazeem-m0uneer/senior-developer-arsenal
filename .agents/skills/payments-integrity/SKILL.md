---
name: payments-integrity
description: 'Runbook for code that moves money (charges, refunds, payouts, wallet balances, gateway webhooks): integer minor units, an append-only double-entry ledger, idempotency keys, gateway calls outside transactions, signed deduplicated webhooks, state machines and reconciliation. Use when the user asks to add or review a payment flow, refund or webhook handler, or runs /payments-integrity. Triggers on: "payment flow", "refund", "gateway webhook", "double charge", "/payments-integrity". Do not use for wrapping a provider API (use provider-sdk) or vulnerability hunting (use security-audit).'
---

# Payments Integrity Procedure

This skill guides the agent through building and reviewing money movement so that every amount is exact, every operation is safe to repeat, every balance can be re-derived, and the books agree with the gateway.

---

## 1. When to Use This Skill

Activate this skill when:
- Adding or changing a charge, authorisation, capture, void, refund, payout, or wallet top-up.
- Writing or reviewing a gateway webhook handler or a payment-result callback.
- Designing ledger accounts, postings, or a balance read.
- Investigating a double charge, a lost payment, a negative balance, or a mismatch with the gateway report.
- The user runs the `/payments-integrity` slash command.

*Boundary*: For the client wrapper around a gateway API and its mock and live modes, use `provider-sdk`. For the schema change itself, use `database-migration`. For injection, broken authentication, and other vulnerabilities, use `security-audit`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Map the Flow and Its States
1. Write the flow as steps: who starts it, which gateway calls it makes, which records it writes, which events it emits.
2. Define the payment status as an explicit state machine with a transition table. A transition not in the table is refused, not logged and allowed.
3. Mark every step that can be repeated (client retry, webhook redelivery, job rerun) and every step that can fail after money moved.
4. Keep card data out: use the gateway's hosted fields or redirect and store only its token, the last four digits, and the brand. Storing a card number or security code brings the whole system into PCI scope.

### Step 2: Model Amounts and the Ledger
Consult: [Ledger Postings & State Machine](./references/ledger-postings.md)
1. Store every amount as an integer in the currency's minor unit, next to its currency code. Never floating point, never an amount without a currency.
2. Round once, at one named place, with one named mode; allocate the remainder so the parts sum to the whole.
3. Record money in an append-only double-entry ledger: each transaction's entries sum to zero per currency. Corrections are new reversing transactions, never updates.
4. Derive balances from entries. A stored balance is a cache that a query can rebuild and a job compares.

### Step 3: Make Every Operation Idempotent
1. Every money operation carries an idempotency key, stored under a unique constraint with the request fingerprint and the outcome.
2. Use the business reference (`<event>:<id>`, or the gateway reference) as the ledger transaction reference so it doubles as the key.
3. Never call the gateway inside a database transaction: store the attempt and commit, call the gateway once, then store the answer in a second transaction.
4. On an unknown answer (time-out, 5xx), read the payment from the gateway before anything else. Never retry a charge blindly.

### Step 4: Confirm Server-Side and Harden Webhooks
1. Never trust the client's report of a payment result. Fetch the payment from the gateway and compare amount, currency, status, and your own reference.
2. Verify each webhook's signature over the raw body with a constant-time comparison; reject stale timestamps.
3. Deduplicate by event id under a unique constraint, acknowledge fast, and process asynchronously.
4. Tolerate repeats and out-of-order delivery: apply an event only if the state machine allows the transition; otherwise re-read the gateway's current state.
5. An unknown event type with a valid signature is stored and alerted on, never posted to the ledger.

### Step 5: Refunds, Concurrency, and Reconciliation
Consult: [Money Traps](./references/money-traps.md)
1. Refuse a refund above what is left (captured minus already refunded and pending), checked under a row lock or a guarded update.
2. Allow one capture or void per authorisation and make it final.
3. Write concurrency tests: parallel identical requests, parallel different refunds, a webhook racing the client's confirmation.
4. Run a reconciliation job against the gateway's settlement report: every gateway line has one ledger transaction and the reverse; differences alert a human.
5. Record who or what caused each money movement, when, and under which permission, in an audit trail that is never edited.

---

## 3. Verification Protocol

```bash
npm test -- payments ledger webhooks                   # or: dotnet test --filter Category=Money, pytest -m money
psql "$DATABASE_URL" -c "SELECT transaction_id, currency FROM ledger_entries GROUP BY 1, 2 HAVING SUM(amount_minor) <> 0;"   # 0 rows
psql "$DATABASE_URL" -c "SELECT p.id FROM payments p JOIN refunds r ON r.payment_id = p.id AND r.status <> 'failed' GROUP BY p.id, p.captured_minor HAVING SUM(r.amount_minor) > p.captured_minor;"   # 0 rows
rg -n "float|double|parseFloat|toFixed|Math\.round" src/payments src/ledger   # each hit is a candidate rounding bug
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Checkout | Gateway call inside an open transaction | Charge succeeds, rollback loses the record | `[Blocker]` | Store attempt, commit, call, store answer |
| Webhook | Signature computed on re-serialised JSON | Forged or rejected events | `[Security]` | Verify over the raw request body |
| Refund | Remaining amount read without a lock | Two refunds exceed the capture | `[Blocker]` | Guarded update or `SELECT ... FOR UPDATE` |

---

## 4. ⚡ Token-Saving Execution Rule

- **Flow First**: Read the one flow being changed (its handler, state table, and postings), not the whole payments module.
- **Trap Table as Checklist**: Walk the trap table and report only the rows the change violates, each with `file:line` and the proving test.
- **Surgical Fixes**: Output the changed function or constraint and its test, never the unchanged surroundings.
