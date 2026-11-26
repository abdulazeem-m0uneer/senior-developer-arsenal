# Log Field & Metric Naming Sheet

Field names, propagation rules, logger setup per stack, metric naming, label budget, sampling, and an SLO alert rule.

---

## 1. Log Fields

One JSON object per line. Names follow OpenTelemetry semantic conventions where one exists.

| Field | Required | Example | Rule |
| :--- | :---: | :--- | :--- |
| `timestamp` | yes | `2026-03-04T09:15:02.481Z` | RFC 3339, UTC, millisecond precision |
| `level` | yes | `info` | One of `debug`, `info`, `warn`, `error`, `fatal` |
| `message` | yes | `payment captured` | Constant text; variables go in fields so lines group |
| `service.name` / `service.version` | yes | `api` / `3f9c2ab` | Version is the commit SHA of the running build |
| `deployment.environment` | yes | `staging` | Never inferred from the host name |
| `request_id` | yes, in a request or job | `01HV3K9Q2M` | Same value in the response header and the error body |
| `trace_id` / `span_id` | yes, when tracing is on | 32 / 16 hex characters | Injected by the tracer, never hand-built |
| `http.route` | on request lines | `/orders/:id` | Template, not the raw path |
| `http.response.status_code`, `duration_ms` | on request lines | `502`, `183` | Numbers, not strings |
| `error.type`, `error.message`, `error.stack` | on error lines | `TimeoutError` | Logged once, at the handling boundary |
| `actor_id`, `tenant_id` | where known | opaque internal ids | Never an email, phone number, or name |
| `job.name`, `job.id`, `job.attempt` | on job lines | `send-receipt`, `8841`, `2` | Lets a retry be told from a first run |

Levels: `error` means someone may have to act; `warn` is a handled anomaly; a refused request (4xx) is `info`. `debug` is off in production and switchable without a deploy.

---

## 2. Propagation

| Hop | Carry | How |
| :--- | :--- | :--- |
| Inbound HTTP | `traceparent`, `x-request-id` | Accept a well-formed id (for example `^[A-Za-z0-9_-]{8,64}$`), else generate; echo it on the response |
| Outbound HTTP / gRPC | `traceparent`, `x-request-id` | Auto-instrumentation injects the first; an HTTP client interceptor adds the second |
| Queue message | both, as message headers | Producer injects; consumer extracts and starts a linked span |
| Background job | both, in job metadata | Store at enqueue time; restore into the logging context before the handler runs |
| Scheduled job | new ids per run | Generate at start; log `job.name` and the schedule tick |

---

## 3. Logger Setup

```ts
// Node.js: pino + AsyncLocalStorage (@opentelemetry/instrumentation-pino adds trace_id and span_id)
export const context = new AsyncLocalStorage<{ requestId: string }>();
export const logger = pino({
  redact: { paths: ['req.headers.authorization', 'req.headers.cookie', '*.password', '*.token', '*.otp'], censor: '[redacted]' },
  mixin: () => ({ request_id: context.getStore()?.requestId }),
});
```

```csharp
// .NET: built-in JSON console, trace ids from Activity, request id as a scope
builder.Logging.AddJsonConsole(o => o.IncludeScopes = true);
builder.Logging.Configure(o => o.ActivityTrackingOptions = ActivityTrackingOptions.TraceId | ActivityTrackingOptions.SpanId);
using (logger.BeginScope(new Dictionary<string, object> { ["request_id"] = requestId })) { await next(context); }
```

```python
# Python: structlog with contextvars; redact() is a processor that masks the listed keys
structlog.configure(processors=[
    structlog.contextvars.merge_contextvars, structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True), redact, structlog.processors.JSONRenderer(),
])
structlog.contextvars.bind_contextvars(request_id=request_id)  # in middleware, cleared after the response
```

Always redacted: `authorization` and `cookie` headers, tokens, API keys, passwords, one-time codes, card numbers, national ids, full request bodies of sign-in and payment routes. Redaction is an allowlist where possible: log named fields, not whole objects.

---

## 4. Metric Naming

- Shape: `<domain>_<thing>_<unit>`; base units only (`seconds`, `bytes`); counters end in `_total`; no unit in a label.
- OpenTelemetry names map to Prometheus by replacing dots: `http.server.request.duration` becomes `http_server_request_duration_seconds`.

| Method | Signal | Metric | Type |
| :--- | :--- | :--- | :--- |
| RED | Rate, Duration | `http_server_request_duration_seconds` (`_count`, `_bucket`) | Histogram |
| RED | Errors | same histogram filtered on `http_response_status_code=~"5.."` | Histogram |
| RED (jobs) | Rate, Errors, Duration | `job_duration_seconds` with `job_name`, `outcome` | Histogram |
| USE | Utilisation | `db_client_connection_count{state="used"}` over the pool maximum | Gauge |
| USE | Saturation | `db_client_connection_pending_requests`, `queue_depth`, event loop lag | Gauge |
| USE | Errors | `db_client_connection_timeouts_total` | Counter |

Label budget: series per metric equals the product of the distinct values of its labels. Keep each label under roughly 100 values and each metric under roughly 10,000 series.

| Allowed label | Forbidden label | Put it instead in |
| :--- | :--- | :--- |
| `http_route` (template) | raw URL, query string | span attribute `url.path` |
| `http_request_method`, `http_response_status_code` | error message text | log field `error.message` |
| `service_name`, `job_name`, `outcome` | user id, tenant id, request id, email | log fields and span attributes |

---

## 5. Sampling

| Policy | Keeps | Hides |
| :--- | :--- | :--- |
| Head sampling at N% | A random share, decided at the first span | Most errors and slow requests at low N |
| Tail sampling: errors + slow + N% of the rest | Every failure and outlier | The ordinary fast request; rates computed from traces are biased |
| Always on | Everything | Nothing; cost grows with traffic |

Compute rates and percentiles from metrics, never from sampled traces. A request that succeeded quickly may have neither an error line nor a kept trace; its metrics still count it.

---

## 6. SLO Burn-Rate Alert (Prometheus)

```yaml
groups:
  - name: api-slo
    rules:
      - alert: ApiErrorBudgetFastBurn
        expr: |
          ( sum(rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[5m]))
            / sum(rate(http_server_request_duration_seconds_count[5m])) ) > (14.4 * 0.001)
          and
          ( sum(rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[1h]))
            / sum(rate(http_server_request_duration_seconds_count[1h])) ) > (14.4 * 0.001)
        for: 2m
        labels: { severity: page }
        annotations:
          summary: API is spending its 99.9% availability budget 14.4 times too fast
          runbook_url: https://runbooks.example.com/api/error-budget-burn
```

`0.001` is the error budget of a 99.9% SLO; `14.4` spends 2% of a 30-day budget in one hour. Add a slow-burn pair (`6h` and `30m`, factor `6`) as a ticket, not a page.
