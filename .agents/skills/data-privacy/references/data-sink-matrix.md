# Data-to-Sink Matrix

The inventory table, the matrix template, what to look for in each sink, the access checks, retention notes, and when the decision belongs to a lawyer or the data protection officer.

---

## 1. Inventory Table

One row per personal data item the change touches.

| Item | Class | Tier | Enters at | Stored in | Purpose |
| :--- | :--- | :---: | :--- | :--- | :--- |
| Email | Direct identifier | 2 | `POST /signup` body | `users.email` | Sign-in, receipts |
| Phone | Direct identifier | 2 | `POST /signup` body | `users.phone` | One-time codes |
| One-time code | Credential | 3 | Generated server-side | `otp_codes.hash` | Verification |
| Pickup location | Indirect identifier | 2 | `POST /orders` body | `orders.pickup_point` | Fulfilment |
| Support note | Free text | 2 | Admin form | `tickets.body` | Support |

| Tier | Meaning | Default handling |
| :---: | :--- | :--- |
| 1 | Internal id, pseudonym | May appear in logs and spans |
| 2 | Identifies or locates a person | Never in logs, spans, labels, or error reports; masked in back-office views by default |
| 3 | Credential, special category, government id, payment data, data about a child | Never leaves its store in the clear; encrypted or hashed at rest; access audited |

---

## 2. Matrix Template

Fill one cell per item and sink: `clean` (traced, does not land), `masked` (lands redacted), `allowed` (lands by design, with the reason), `LEAK` (finding), or `n/c` (not checked, with why).

| Item | Logs | Traces and error reports | Stored copies and caches | API responses | Outside services | Exports and analytics | Backups |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Email | clean | LEAK: request body captured | allowed: `users` only | masked to other users | allowed: mail sender, address only | LEAK: raw in events | allowed: 35-day expiry |
| Phone | masked (last 2) | clean | LEAK: in idempotency record | clean | allowed: SMS sender | clean | allowed: 35-day expiry |
| One-time code | clean | clean | allowed: hash only | clean | allowed: SMS body | clean | n/c: backup of code table |

Every `LEAK` becomes a findings row with `file:line`, who can see it, and the request that shows it. Every `allowed` names why the sink needs the value.

---

## 3. What to Look for in Each Sink

| Sink | Typical leak | Where to look |
| :--- | :--- | :--- |
| Logs | Whole request or entity logged; exception text quoting input; SQL with bound values; access logs with query strings | Logger calls in the diff, global request logging, ORM query logging, reverse-proxy log format |
| Traces and error reports | Span attribute or metric label holding an email; captured request body, headers, cookies, local variables; breadcrumbs | Tracing instrumentation, error-reporter options, metric label sets (a label with a person in it is also a cardinality fault) |
| Stored copies and caches | Idempotency record holding the full response; queue or outbox payload carrying the person, not the id; audit `details` blob; job arguments; cache key or object name containing a name or email | Any `save`, `publish`, `enqueue`, `set` added by the diff; file naming code |
| API responses | Entity serialised whole; another user's data in a list, search, or autocomplete; error body echoing the looked-up value; existence leak ("email already registered") | Response mappers, list endpoints, error handlers, GraphQL field resolvers |
| Outside services | Full profile sent where an id would do; client headers and cookies forwarded; personal data in a URL (it lands in the other side's logs) | Outbound HTTP clients, SDK calls, webhook senders, push and mail templates |
| Exports and analytics | Raw identifiers in event properties; free text in events; exports without row filter; files left in shared storage | Analytics calls, report queries, export jobs, warehouse load definitions |
| Backups and replicas | Deleted person still in backups past the stated period; production copy restored to staging; read replica open to wider roles | Backup retention settings, refresh scripts, replica grants |

---

## 4. Access Checks per Read Path

| Check | Fails when | Proof |
| :--- | :--- | :--- |
| Actor from session | Handler reads `userId`, `tenantId`, or `role` from body, query, or header | Call with another id: 403 or 404, never data |
| Owner or tenant filter | Lookup by id alone | Test: user A requests B's row |
| List and search | Filter applied on detail route only | Test: list as A never returns B's rows |
| Field-level masking | Sensitive field returned to every role | Response for a low-privilege role shows the masked form |
| Unmask audited | Privileged read leaves no trace | Audit row with actor, subject id, reason |
| Bulk limits | Export or page size unbounded | Oversized page refused; export needs its own permission |
| Back-office paths | Admin screen bypasses service-layer checks | Same isolation tests against admin routes |

---

## 5. Minimisation, Retention, Deletion

| Question | Acceptable answer |
| :--- | :--- |
| Does the feature need this item at all? | Named use in this feature; otherwise do not collect |
| Could an id or a derived value do? | Pass the id; compute age band, not birth date; store city, not coordinates |
| How long is it kept? | A stated period per store, enforced by a named job or a store-level expiry |
| What does deletion do? | Delete or anonymise in the primary store, then every copy from the matrix; copies that cannot be reached have an expiry |
| What must be kept despite a deletion request? | Named records with the obligation that requires them (for example financial records), restricted and separated |
| Is the purpose the one it was collected for? | Yes, or flagged for decision |

---

## 6. When a Lawyer or the Data Protection Officer Decides

This review reports facts about where data goes. It does not say whether processing is lawful. Flag, do not decide:

| Trigger in the change | What to hand over |
| :--- | :--- |
| A new purpose for existing data | Item, old purpose, new purpose |
| A special category, a government id, or data about children | Item, why needed, where stored, who reads it |
| A new outside recipient or sub-processor | Recipient, items sent, country, contract status if known |
| A transfer to another country or region | Source and destination, items |
| Profiling or an automated decision about a person | Inputs, the decision, whether a human reviews it |
| Consent wording, cookie or tracking behaviour | Current text and behaviour, proposed change |
| Retention longer than the stated period, or a deletion that cannot reach a copy | Store, period, obstacle |
| A suspected leak that already reached production | What, since when, who could see it; use `incident-response` at once |

Write in the report: "Needs a decision by the data protection officer or legal counsel", with the row above. Do not quote a regulation as the reason a design is acceptable.
