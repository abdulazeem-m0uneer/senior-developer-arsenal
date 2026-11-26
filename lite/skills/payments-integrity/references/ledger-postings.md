# Ledger Postings & State Machine

A minimal append-only double-entry ledger, a worked posting example, rounding, the payment state machine, the gateway-call pattern, and webhook handling.

---

## 1. Ledger Tables

```sql
CREATE TABLE ledger_transactions (
  id          uuid PRIMARY KEY,
  reference   text NOT NULL UNIQUE,            -- '<event>:<id>'; doubles as the idempotency key
  kind        text NOT NULL,                   -- capture, refund, settlement, payout
  actor       text NOT NULL,                   -- user id, job name, or 'gateway-webhook'
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE ledger_entries (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  transaction_id uuid    NOT NULL REFERENCES ledger_transactions (id),
  account        text    NOT NULL,             -- from a fixed chart, e.g. 'supplier:42:payable'
  currency       char(3) NOT NULL,             -- ISO 4217
  amount_minor   bigint  NOT NULL CHECK (amount_minor <> 0)   -- positive = debit, negative = credit
);
REVOKE UPDATE, DELETE, TRUNCATE ON ledger_transactions, ledger_entries FROM app_role;
```

- A posting inserts the transaction and all its entries in one database transaction and checks the entries sum to zero per currency before commit.
- A repeated `reference` hits the unique constraint: return the stored transaction, do not post again.
- Account names come from one typed chart of accounts in code; no flow builds an account string by hand.
- Balance is a query: `SELECT SUM(amount_minor) FROM ledger_entries WHERE account = $1 AND currency = $2`. A cached balance is allowed if a job rebuilds it and alerts on any difference.

---

## 2. Worked Example

A customer pays 50.00 in a two-decimal currency (5000 minor units). The platform keeps 10% commission, the gateway takes a fee of 75 at settlement, and 20.00 is refunded later.

| Transaction (`reference`) | Account | `amount_minor` |
| :--- | :--- | ---: |
| Capture (`capture:pay_812`) | `gateway:clearing` (asset: what the gateway owes us) | +5000 |
| | `supplier:42:payable` (liability) | -4500 |
| | `platform:revenue:commission` | -500 |
| Settlement (`settlement:stl_3301`) | `bank:operating` | +4925 |
| | `platform:expense:gateway-fees` | +75 |
| | `gateway:clearing` | -5000 |
| Partial refund (`refund:ref_33`) | `supplier:42:payable` | +1800 |
| | `platform:revenue:commission` | +200 |
| | `gateway:clearing` | -2000 |

Each transaction sums to zero. After the refund `gateway:clearing` stands at -2000: the gateway deducts it from the next settlement, and reconciliation expects exactly that line. The supplier is owed 2700, commission earned is 300, and no entry was ever edited.

---

## 3. Rounding and Allocation

```typescript
// Commission in basis points, rounded half-up once; the supplier takes the remainder.
export function split(amountMinor: bigint, commissionBps: bigint) {
  const commission = (amountMinor * commissionBps + 5000n) / 10000n;
  return { commission, supplier: amountMinor - commission };
}
```

- Never round each part separately: `round(a) + round(b)` need not equal `round(a + b)`.
- Splitting among n parties: integer-divide, then hand the remaining minor units out one by one in a fixed order.
- A refund reverses the original split in proportion with the same remainder rule, so repeated partial refunds never reverse more than was posted.

---

## 4. Payment State Machine

| From | Event | To | Posts to ledger |
| :--- | :--- | :--- | :--- |
| `created` | Session opened at gateway | `pending` | no |
| `pending` | Gateway confirms authorisation | `authorised` | no (or a hold posting) |
| `pending` | Gateway reports failure or expiry | `failed` | no |
| `authorised` | Capture confirmed | `captured` | capture |
| `authorised` | Void confirmed | `voided` | hold release, if a hold was posted |
| `captured` | Refund confirmed, amount left > 0 | `partially_refunded` | refund |
| `captured`, `partially_refunded` | Refund confirmed, amount left = 0 | `refunded` | refund |

`failed`, `voided`, and `refunded` are terminal. Every pair not listed is refused.

```sql
UPDATE payments SET status = 'captured', captured_minor = $2, updated_at = now()
WHERE id = $1 AND status = 'authorised';      -- 0 rows updated = illegal or already done: re-read, do not force
```

---

## 5. Gateway Call Pattern

```python
def start_capture(payment_id: str, key: str) -> Attempt:
    with db.transaction():                                   # 1. record intent, commit
        attempt = attempts.insert_or_get(key=key, payment_id=payment_id, status="pending")
    if attempt.status != "pending":
        return attempt                                       # repeated request: stored outcome
    try:
        answer = gateway.capture(payment_id, idempotency_key=key, timeout=10)   # 2. one call, no open transaction
    except (Timeout, ServerError):
        answer = gateway.get_payment(reference=payment_id)   # unknown outcome: read, never re-charge
    with db.transaction():                                   # 3. store the answer and post
        return settle(attempt, answer)
```

- `settle` is the only function that changes payment status. The client's confirmation, the webhook, and the recovery job all call it, so a race posts once.
- If the read in step 2 is also inconclusive, leave the attempt `pending`, answer "outcome unknown" (HTTP 409 or 202), and let a recovery job settle it from a later gateway read.

---

## 6. Webhook Handler

```typescript
export async function handleWebhook(rawBody: Buffer, signature: string, timestamp: string) {
  const expected = createHmac("sha256", secret).update(`${timestamp}.`).update(rawBody).digest();
  const given = Buffer.from(signature, "hex");
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) throw new Unauthorized();
  if (Math.abs(Date.now() / 1000 - Number(timestamp)) > 300) throw new Unauthorized();

  const event = JSON.parse(rawBody.toString("utf8"));
  const fresh = await events.insertIfAbsent(event.id, event.type, rawBody);   // unique on event id
  if (fresh) await queue.enqueue("settle-from-gateway", { paymentReference: event.data.reference });
  return { status: 200 };                                                     // duplicates are acknowledged too
}
```

- Use the signing scheme the gateway documents; the shape above (timestamp, raw body, HMAC, constant-time compare, tolerance window) is the common one.
- The worker does not trust the event's payload for the amount or status: it reads the payment from the gateway and calls `settle`.
- Reconciliation is a `FULL OUTER JOIN` of the gateway's report lines and `ledger_transactions` on the reference: any row with one side missing is a difference a human closes.
