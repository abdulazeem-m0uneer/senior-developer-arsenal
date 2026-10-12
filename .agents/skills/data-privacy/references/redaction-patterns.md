# Redaction Pattern Sheet

Redaction at the logger, tracer, and error reporter for Node.js/TypeScript, .NET, and Python; masking formats and masked views; synthetic test data; and the test that proves it.

---

## 1. Principles

- **Allow-list over deny-list**: log named safe fields. A deny-list misses the field added next month.
- **Central, not per call**: configure redaction once in the logger, tracer, and error reporter; call sites cannot forget it.
- **Ids, not values**: `userId=8f3a` is enough to find the person with the right permission.
- **Remove, do not hash, by default**: an unsalted hash of an email or phone is reversible by enumeration. Use a keyed hash only where correlation is needed.
- **Never log**: passwords, tokens, one-time codes, session cookies, `Authorization` headers, card data, full request or response bodies.

---

## 2. Logger Configuration by Stack

```typescript
// Node.js / TypeScript (pino)
export const logger = pino({
  redact: {
    paths: ["req.headers.authorization", "req.headers.cookie", "*.password", "*.token", "*.otp",
            "*.email", "*.phone", "*.iban", "*.nationalId", "user.name", "body"],
    censor: "[REDACTED]",
  },
  serializers: {
    req: (req) => ({ id: req.id, method: req.method, route: req.routeOptions?.url }),   // route template, not the raw URL
    err: (err) => ({ type: err.name, code: err.code, stack: err.stack }),               // no message: it may quote input
  },
});
```

```csharp
// .NET (Serilog): a logged entity is reduced to its safe fields.
Log.Logger = new LoggerConfiguration()
    .Destructure.ByTransforming<User>(u => new { u.Id })
    .Destructure.ByTransforming<PaymentRequest>(p => new { p.OrderId, p.AmountMinor, p.Currency })
    .WriteTo.Console(new CompactJsonFormatter())
    .CreateLogger();
```

```python
# Python (structlog): one processor in front of the renderer.
SENSITIVE = {"password", "token", "otp", "email", "phone", "iban", "national_id", "authorization", "cookie"}

def redact(_, __, event: dict) -> dict:
    return {key: "[REDACTED]" if key.lower() in SENSITIVE else value for key, value in event.items()}

structlog.configure(processors=[structlog.contextvars.merge_contextvars, redact, structlog.processors.JSONRenderer()])
```

- Log the route template (`/users/:id`), never the raw URL with its query string.
- .NET: use message templates with named properties (`"Order {OrderId} paid"`), never string interpolation, which bypasses destructuring policies. Keep `EnableSensitiveDataLogging` off outside local development: it prints SQL parameter values.
- Scrubbing message text by pattern is a second net, not the control. The control is not passing the value in.

---

## 3. Traces, Metrics, and Error Reports

```typescript
// Error reporter (the `beforeSend` hook most SDKs offer): keep the id, drop the rest.
init({
  sendDefaultPii: false,
  beforeSend(event) {
    if (event.request) { delete event.request.data; delete event.request.cookies; delete event.request.headers; }
    if (event.user) event.user = { id: event.user.id };
    return event;
  },
});
```

- Add a last line of defence in the telemetry pipeline: an OpenTelemetry Collector `attributes` processor with `action: delete` on `http.request.header.authorization`, `user.email`, and `url.query`.
- Span attributes and metric labels carry ids and enumerations only. A label holding a person is a privacy leak and a cardinality explosion.
- Turn off capture of request bodies, SQL parameter values, and local variables in auto-instrumentation unless each is reviewed.
- Exception messages are data: throw `NotFound("user", userId)`, not a message that quotes the email looked up.

---

## 4. Masking Formats, Views, and Exports

| Item | Masked form | Rule |
| :--- | :--- | :--- |
| Email | `j***@example.com` | First character and domain |
| Phone | `*******42` | Last two digits |
| Bank account or IBAN | `****6789` | Last four |
| Government id | Absent | Show only on the screen that needs it, with an audited permission |
| Address or location | City, or coordinates rounded to two decimals | Never exact coordinates in logs |
| Free text | Length only (`noteLength=214`) | Content is whatever the user typed |
| Token or code | Absent; length at most | Never a prefix: prefixes get reassembled |

One shared masking function per item, used by logs, back-office views, and exports, so a value never appears in two formats.

```sql
CREATE VIEW support.customers AS
SELECT id, left(email, 1) || '***@' || split_part(email, '@', 2) AS email_masked, '*******' || right(phone, 2) AS phone_masked
FROM app.customers;   -- support_role is granted this view and nothing on app.customers
```

- Exports select named columns, never `SELECT *`, and apply the same tenant filter as the API.
- Analytics events carry a pseudonymous id; the mapping to the person stays in the primary store.

---

## 5. Synthetic Test Data

| Item | Use | Never |
| :--- | :--- | :--- |
| Email | `user1@example.com`, `@example.org`, `@example.net` (reserved domains) | A colleague's or customer's address |
| Phone | A range the national regulator reserves for fiction or testing | A number that could ring |
| IP address | `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` (documentation ranges) | Real client addresses |
| Whole datasets | Generated by a seeded factory | A production dump, even one "anonymised" by hand |

A staging refresh from production is a transfer of personal data: it needs masking in the pipeline and the same access rules, or it does not happen.

---

## 6. The Test That Proves It

```typescript
it("never writes the phone number to logs, spans, or error reports", async () => {
  const marker = "+10005550199";
  const sinks = captureSinks();                         // in-memory log stream, span exporter, error transport
  await request(app).post("/signup").send({ phone: marker, email: "user1@example.com" });
  await request(app).post("/signup").send({ phone: marker, email: "not-an-email" });     // the error path too
  expect(sinks.all()).not.toContain(marker);
  expect(sinks.all()).not.toContain(marker.slice(-7));
});   // the failure path matters most: leaks live in error handlers, not the happy path
```
