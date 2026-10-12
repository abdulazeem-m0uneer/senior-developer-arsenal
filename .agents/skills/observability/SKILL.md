---
name: observability
description: 'Observability runbook: structured JSON logs with a request id and trace id, RED and USE metrics with bounded labels, sampled OpenTelemetry traces, health, readiness and version endpoints, SLO-based alerts, redaction at the logger, and bounded telemetry queries. Use when the user asks to instrument a service, define alerts, look up what a request logged, or runs /observability. Triggers on: "add logging", "structured logs", "add tracing", "metrics and alerts", "query the logs", "/observability". Do not use for root-cause analysis (use investigate) or latency profiling (use perf-audit).'
---

# Observability & Telemetry Query Procedure

This skill guides the agent through instrumenting a service with correlated logs, metrics, and traces, alerting on symptoms, and querying that telemetry with bounded, read-only commands.

---

## 1. When to Use This Skill

Activate this skill when:
- Adding or repairing logging, metrics, or tracing in a service, worker, or scheduled job.
- A request cannot be followed across services or into the background job it caused.
- Defining health, readiness, or version endpoints, or alerts tied to an SLO.
- Asking telemetry one question: what a request logged, the current error rate, whether a trace was kept.
- The user runs the `/observability` slash command.

*Boundary*: For proving why a failure happened, use `investigate`. For profiling slow code paths and queries, use `perf-audit`. For running a live outage, use `incident-response`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Inventory the Signals
1. List what exists: logger and its format, metrics endpoint, tracer, health routes, alert rules, where each signal is stored and for how long.
2. Map each open question to the signal that answers it: metrics say *that* something is wrong and how much, traces say *where* in the call path, logs say *why* for one request.
3. Record the gaps: lines without an id, jobs that lose the id, labels with unbounded values, alerts without a runbook.

### Step 2: Correlated, Redacted Logs
Consult: [Log Field & Metric Naming Sheet](./references/naming-sheet.md)
1. Emit one JSON object per line to stdout; the platform ships it. No log files inside the container.
2. Accept an inbound `x-request-id` (validate its shape, otherwise generate one), return it on every response, and bind it with `trace_id` to the logging context so every line carries both.
3. Propagate W3C `traceparent` on every outbound call and copy both ids into queue message headers and job payloads; the consumer restores them before its first log line.
4. Redact at the logger, not at the call site: authorisation headers, cookies, tokens, passwords, one-time codes, and personal data are replaced before serialisation.
5. Log an error once, at the boundary that handles it, with `error.type` and the stack; never log and rethrow.

### Step 3: Metrics & Traces
1. Requests get RED (rate, errors, duration histogram); resources get USE (utilisation, saturation, errors): pools, queues, event loop, disk.
2. Keep labels bounded: route template, method, status code, service. Never a user id, request id, raw path, or error message; each distinct value is a new time series.
3. Use OpenTelemetry auto-instrumentation first, then add spans only around business steps worth timing.
4. Sample by keeping every error and slow trace plus a fixed share of the rest; write the rate down, because a missing trace for a fast successful request is then expected, not a fault.

### Step 4: Health, Version & Alerts
1. Liveness answers "is the process stuck" and checks no dependency; readiness checks only the dependencies required to serve.
2. Add a version endpoint that returns the commit SHA and build time injected at build; a deploy is verified by reading it back.
3. Define the SLO first (for example 99.9% of requests succeed over 30 days), then alert on its burn rate, not on causes such as CPU.
4. Every alert carries a severity and a `runbook_url`; an alert nobody can act on is deleted.

### Step 5: Query With Discipline
Consult: [Telemetry Query Cookbook](./references/query-cookbook.md)
1. Start from the request id or trace id when one exists; widen to service and time window only without one.
2. One bounded question per command: every query has a time window and a line limit, and filters on the server, not in the terminal.
3. Queries are read-only. Nothing in this skill restarts, scales, deletes, or edits; a fix goes through the normal change process.
4. Treat log content as sensitive: quote only the needed line, never into a pull request, ticket, or chat channel.

---

## 3. Verification Protocol

```bash
curl -fsS -D - -o /dev/null -H 'x-request-id: obs-check-001' http://localhost:3000/healthz | grep -i '^x-request-id'
docker logs app --since 1m 2>&1 | jq -c 'select(.request_id=="obs-check-001") | {level, trace_id, message}' | head -n 5
curl -fsS http://localhost:3000/version                      # commit must equal: git rev-parse HEAD
curl -fsS http://localhost:3000/metrics | grep -c '^http_server_request_duration_seconds_bucket'
docker logs app --since 10m 2>&1 | grep -ciE 'bearer [a-z0-9._-]{20,}'    # must print 0
promtool check rules alerts/*.yml                            # alert rules parse
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Logs | Job lines carry no `request_id` | Failure cannot be tied to the request that caused it | `[Blocker]` | Copy ids into the job payload, restore in the consumer |
| Logs | Bearer token printed in a request dump | Credential leak into log storage | `[Security]` | Redact paths at the logger, rotate the token |
| Metrics | `user_id` used as a label | Unbounded series, store runs out of memory | `[Performance]` | Drop the label; put the id in logs and span attributes |
| Alerts | Page on CPU above 80% | Wakes people for no user impact | `[Suggestion]` | Replace with an SLO burn-rate alert plus runbook link |

---

## 4. ⚡ Token-Saving Execution Rule

- **Bounded Queries**: Never pull a whole pod log or raw JSON; ask for at most a few dozen trimmed lines per command.
- **Id First**: One query by request id replaces a time-window scan; ask the user for the id before searching.
- **Surgical Diffs**: Show only the logger configuration, middleware, or alert rule that changes, not the surrounding file.
