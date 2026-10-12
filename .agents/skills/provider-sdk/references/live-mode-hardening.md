# Live Mode Hardening

Rules for the part of the package that talks to the real provider: mode selection, timeouts, retries and idempotency, webhooks, and secrets.

---

## 1. Mode Selection at Startup

| Environment | `mode=mock` | `mode=live` |
| :--- | :--- | :--- |
| Local, tests, CI | Default | Allowed with sandbox or test credentials |
| Shared non-production | Allowed | Allowed |
| Production | **Refused: the process does not start** | Required, with every credential present |

```typescript
export function selectProvider(config: Config): ProviderPort {
  if (config.PROVIDER_MODE === 'mock') {
    if (config.APP_ENV === 'production')
      throw new ProviderConfigError('the mock provider is refused in production; set PROVIDER_MODE=live');
    return new ProviderAdapter(createProvider({ mode: 'mock' }));
  }
  const missing = ['PROVIDER_URL', 'PROVIDER_API_KEY'].filter((key) => !config[key]);
  if (missing.length) throw new ProviderConfigError(`live provider needs ${missing.join(', ')}`);
  return new ProviderAdapter(createProvider({ mode: 'live', url: config.PROVIDER_URL, apiKey: config.PROVIDER_API_KEY, timeoutMs: config.PROVIDER_TIMEOUT_MS }));
}
```

- [ ] The mode is an explicit configuration key validated at startup; no inference from the presence of a key.
- [ ] A mock answer in production is a false statement about a real customer, so the refusal is a startup failure, not a log warning.
- [ ] Both refusals (mock in production, live with a credential missing) have a unit test.
- [ ] The readiness endpoint reports the mode, never the credentials.

---

## 2. Timeouts

| Rule | Value to start from | Reason |
| :--- | :--- | :--- |
| Every request has a total timeout | 5 to 10 s for interactive calls, 30 s for batch | A hung provider must not hold a request thread or a database transaction |
| Connect timeout shorter than total | 2 to 3 s | Fail fast on an unreachable host |
| Timeout is configuration, not a constant | One key per provider | Tuned per environment without a release |
| A timeout throws "unavailable" | Never a refusal | The provider may still have acted; the outcome is unknown |
| No provider call inside a database transaction | Use an outbox or call before opening it | A slow call otherwise holds locks |

---

## 3. Retries and Idempotency

The live transport never retries by itself: it cannot know whether a call is safe to repeat.

| Call kind | Examples | Retry policy |
| :--- | :--- | :--- |
| Read | Get status, list, lookup | Retry on unavailable: 3 attempts, exponential backoff with jitter |
| Write with a provider idempotency key | Charge, payout, send with a client reference | Retry with the **same** key, stored before the first attempt |
| Write naturally idempotent | Put by identifier, cancel | Retry |
| Write with no idempotency mechanism | Registration that triggers a side effect per call | Never retry automatically. Record "outcome unknown", reconcile by a later read |

- [ ] The idempotency key is derived from the business operation (order id plus attempt purpose), persisted, and reused; a fresh random key per attempt defeats it.
- [ ] Honour `Retry-After` on 429 and 503; stop on any other 4xx.
- [ ] After a timeout on a write, query the provider for the operation by its reference before deciding to repeat.
- [ ] A circuit breaker or a bounded queue keeps a provider outage from exhausting workers.
- [ ] Rate limits from the document are enforced on our side before the provider enforces them.

---

## 4. Webhooks

| Step | Rule |
| :--- | :--- |
| 1. Read | Capture the raw request bytes before any JSON parsing |
| 2. Verify | Compute the signature (usually HMAC-SHA256 with the webhook secret) over the raw bytes, exactly as the document specifies; compare in constant time |
| 3. Freshness | Reject a signed timestamp older than the tolerance (five minutes is common) to stop replays |
| 4. Deduplicate | Store the provider's event id with a unique constraint; a repeat answers 200 and does nothing |
| 5. Acknowledge fast | Persist the event, answer 2xx, process asynchronously; providers retry on slow answers |
| 6. Trust little | Treat the payload as a hint: fetch the object's current state from the provider before moving money or status |
| 7. Order | Events arrive out of order and more than once; handlers compare state, not sequence |

A failed signature answers 401 with no detail and is logged with the request id, never with the payload. The mock engine can emit signed webhooks with a test secret so the handler's verification path runs in every test.

```python
import hashlib, hmac

def verified(raw_body: bytes, header_signature: str, secret: bytes) -> bool:
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_signature)
```

---

## 5. Secrets and Logs

- [ ] Credentials enter through validated configuration from a secret store; none in the repository, the image, or the environment example (which holds names and placeholders only).
- [ ] The transport logs method, path template, status, duration, and request id. Never headers, never full bodies.
- [ ] Error messages built from provider replies are stripped of tokens, card numbers, and one-time codes before they leave the package.
- [ ] The mock's recorded requests and any test snapshot have authentication headers removed.
- [ ] Separate credentials per environment; a production key never reaches a developer machine.
- [ ] Rotation is possible without a code change: two valid webhook secrets are accepted during a rotation window.
- [ ] Personal data sent to the provider is the minimum the call needs (`data-privacy`).

---

## 6. Observability

| Signal | Why |
| :--- | :--- |
| Count and latency per call and outcome (ok, refused by code, unavailable) | Distinguishes a provider outage from customer refusals |
| The provider's own request or trace id, logged beside ours | Their support asks for it first |
| Alert on the unavailable rate, not on refusals | Refusals are business as usual |
| Mode exposed as a metric label | A mock answering where live was expected is visible at once |
