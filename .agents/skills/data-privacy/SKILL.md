---
name: data-privacy
description: 'Privacy review runbook for a code change: inventory the personal data it touches, trace each item to seven sinks (logs, traces and error reports, stored copies, API responses, outside services, exports, backups), then check access control, minimisation, retention, deletion, redaction and test data. Use when the user asks for a privacy review, a personal-data leak check, or runs /data-privacy. Triggers on: "privacy review", "PII in logs", "personal data leak", "redact", "/data-privacy". Do not use for injection or broken authentication (use security-audit) or diff quality (use code-review).'
---

# Data Privacy Review Procedure

This skill guides the agent through reviewing a change for personal-data leaks by tracing every personal data item it touches to every place the value can land, and reporting each leak with the request that shows it.

---

## 1. When to Use This Skill

Activate this skill when:
- A change touches logs, traces, metrics, error reports, caches, exports, analytics, or a call to an outside service.
- A change adds a table, column, event payload, or response field that holds data about a person.
- Adding or reviewing log redaction, data masking, retention, or deletion.
- Preparing fixtures, seeds, or a staging copy that might contain real people.
- The user runs the `/data-privacy` slash command.

*Boundary*: For injection, broken authentication, secrets, and other exploitable vulnerabilities, use `security-audit`. For logging, tracing, and alerting design as such, use `observability`. Whether processing is lawful is decided by a lawyer or the data protection officer, not by this review.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Inventory the Personal Data in the Change
1. Start from the diff, not the codebase: list every field, parameter, column, and payload key the change reads, writes, or forwards.
2. Mark each as direct identifier (name, email, phone, government id, account number), indirect identifier (device id, IP address, precise location, plate), special category (health, biometrics, beliefs, data about a child), or credential (password, token, one-time code).
3. Include free-text fields and uploaded files: they hold whatever the user typed or photographed.
4. Give each item a sensitivity tier; the tier decides masking and who may read it.

### Step 2: Trace Each Item to the Seven Sinks
Consult: [Data-to-Sink Matrix](./references/data-sink-matrix.md)
1. Logs: messages, structured fields, request and response dumps, SQL text, exception messages that quote a value.
2. Traces and error reports: span attributes, metric labels, breadcrumbs, captured request bodies and local variables.
3. Stored copies and caches: idempotency records, outbox and queue payloads, audit details, job arguments, cache keys, object names.
4. API responses: fields one actor must not see about another, list endpoints, error bodies, pagination and search.
5. Outside services: what is sent beyond what the call needs, forwarded headers, webhooks out.
6. Exports and analytics: files, reports, event streams, data warehouse loads, product analytics.
7. Backups and replicas: copies that outlive deletion, staging refreshes from production.

### Step 3: Check Access on Every Read Path
1. The actor comes from the verified session, never from an id in the request.
2. Every read by id also filters on the owner or tenant; list, search, and back-office endpoints apply the same filter.
3. Sensitive fields are masked by default and unmasked by an explicit permission, with the unmasking audited.

### Step 4: Minimise, Retain, Delete
1. Collect and store only what the feature needs; pass ids between components and resolve the person at the edge.
2. Every new store of personal data names its retention period and the job that enforces it.
3. Deletion and anonymisation reach every copy from Step 2, or the copy has a stated expiry.
4. Note the purpose and whether consent or another lawful basis is recorded for it. Flag for the data protection officer or a lawyer: a new purpose, a special category, data about children, a new outside recipient, a transfer to another country.

### Step 5: Redact at the Source and Clean Test Data
Consult: [Redaction Pattern Sheet](./references/redaction-patterns.md)
1. Redact in the logger, tracer, and error-reporter configuration, not at each call site: one allow-list beats a thousand careful developers.
2. Log ids, not values. Where a value is needed for support, log a masked form.
3. Fixtures, seeds, and snapshots hold synthetic people only: reserved example domains and documented test number ranges.
4. Add a test that sends a marked value through the changed path and asserts it appears in no log, span, or error report.

---

## 3. Verification Protocol

```bash
git diff --name-only origin/main...HEAD                                    # the review starts from the diff
rg -n -i "(log|logger|console|print)\w*[.(].*(email|phone|password|token|iban|ssn|address|birth)" src
rg -n -i "[a-z0-9._%+-]+@(?!example\.(com|org|net))[a-z0-9.-]+\.[a-z]{2,}" --pcre2 tests fixtures seeds   # real-looking emails in test data
npm test -- redaction                                                      # or: dotnet test --filter Category=Privacy, pytest -m privacy
```

Report findings most serious first, then what was traced and found clean, then what was not checked:

| Data item | Sink | Location | Who can see it | Severity | Fix |
| :--- | :--- | :--- | :--- | :---: | :--- |
| Phone number | Error report | `src/auth/otp.service.ts:57` | Everyone with error-tracker access | `[Blocker]` | Throw with the user id; scrub request body in the reporter |
| Email of another tenant | API response | `src/invoices/list.handler.ts:31` | Any signed-in user via `GET /invoices?customer=` | `[Security]` | Filter on session tenant; add an isolation test |

---

## 4. ⚡ Token-Saving Execution Rule

- **Diff First**: Trace only the data items the diff touches; open a whole file only where the diff is not enough.
- **Matrix, Not Prose**: Report the filled matrix and the findings table; no file contents and no privacy primer.
- **Clean Cells Once**: List sinks traced and found clean in one line each, and say plainly what was not checked.
