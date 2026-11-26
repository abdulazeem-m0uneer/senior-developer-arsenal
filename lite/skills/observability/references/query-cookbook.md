# Telemetry Query Cookbook

Bounded, read-only queries for common backends. Replace `REQ` with the request id and `api` with the service.

---

## 1. Rules for Every Query

- [ ] **Id first**: with a request id or trace id, query by it and nothing else.
- [ ] **Time window**: explicit on every query; start at 15 minutes and widen once, deliberately.
- [ ] **Line limit**: explicit on every query; 20 to 100 lines. A truncated answer is a prompt to narrow, not to raise the limit.
- [ ] **Filter on the server**: label and field filters in the query; `grep` after the fact means the limit applied to the wrong lines.
- [ ] **One question per command**: "what did this request log", "how many errors per service", "is the pool saturated".
- [ ] **Read-only**: no `delete`, `restart`, `scale`, `exec` into a data store, or port-forward left open.
- [ ] **Trim the output**: project the fields needed (time, service, level, message, error type); never paste raw JSON.

---

## 2. Which Signal Answers the Question

| Question | Signal | First query |
| :--- | :--- | :--- |
| What happened to this one request? | Logs by `request_id`, then its trace | Section 3 or 4 |
| Is it failing now, and how much? | Metrics (RED) | Section 7, error ratio |
| Which hop is slow or failing? | Trace by `trace_id` | Section 8 |
| Is a resource exhausted? | Metrics (USE) | Section 7, pool and queue gauges |
| Did the new version actually deploy? | Version endpoint | `curl -fsS https://<host>/version` |
| Why did the container restart? | Previous container log, events | Section 5 |

---

## 3. LogQL (Loki, via `logcli`)

```bash
# Everything one request logged, oldest first
logcli query --since=24h --limit=100 --forward -o raw '{service_name=~".+"} | json | request_id="REQ"' \
  | jq -r '[.timestamp, .["service.name"], .level, .message] | @tsv'
# Newest error lines of one service
logcli query --since=15m --limit=20 '{service_name="api"} | json | level=~"error|fatal"'
# Error count per service: one number per series instead of lines
logcli instant-query 'sum by (service_name) (count_over_time({service_name=~".+"} | json | level=~"error|fatal" [15m]))'
```

Put the label matcher (`service_name`) first: it selects streams from the index; `| json | field=...` scans what remains.

---

## 4. SQL-Like Log Store

```sql
-- One request, in order
SELECT timestamp, service, level, message, error_type
FROM logs
WHERE timestamp >= now() - INTERVAL '24 hours'
  AND request_id = 'REQ'
ORDER BY timestamp ASC
LIMIT 100;
-- Top error types in the last hour
SELECT service, error_type, count(*) AS occurrences
FROM logs
WHERE timestamp >= now() - INTERVAL '1 hour' AND level IN ('error', 'fatal')
GROUP BY service, error_type
ORDER BY occurrences DESC
LIMIT 20;
```

Interval syntax differs per engine; the rule does not: a predicate on the time column (usually the partition key) and a `LIMIT` on every statement. Never `SELECT *` on a log table.

---

## 5. `kubectl logs`

```bash
kubectl logs deploy/api --since=15m --tail=500 | grep -F '"request_id":"REQ"' | head -n 50
kubectl logs -l app=api --since=15m --tail=200 --prefix --max-log-requests=5 | grep -F '"level":"error"' | tail -n 20
kubectl logs pod/api-7c9f-abcde --previous --tail=50          # the container that crashed
kubectl get events --field-selector involvedObject.name=api-7c9f-abcde --sort-by=.lastTimestamp | tail -n 15
```

`kubectl logs` reads from the node and only as far back as log rotation allows; use it when no log store exists. Always pass both `--since` and `--tail`; never `-f` in an unattended session.

---

## 6. `journalctl`

```bash
journalctl -u api.service --since "15 min ago" --grep 'REQ' -n 50 --no-pager -o cat
journalctl -u api.service --since "1 hour ago" -p err -n 20 --no-pager -o short-iso
```

`--no-pager` is mandatory in a non-interactive shell. `-o cat` prints the application's own JSON line without the journal prefix, ready for `jq`.

---

## 7. PromQL (one number per series)

```bash
q() { curl -fsS --get http://prometheus:9090/api/v1/query --data-urlencode "query=$1" \
  | jq -r '.data.result[] | "\(.metric | to_entries | map(.value) | join(" ")) \(.value[1])"' | head -n 20; }

q 'sum(rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[5m])) / sum(rate(http_server_request_duration_seconds_count[5m]))'
q 'histogram_quantile(0.99, sum by (le, http_route) (rate(http_server_request_duration_seconds_bucket[5m])))'
q 'topk(5, sum by (http_route) (rate(http_server_request_duration_seconds_count[5m])))'
q 'max(db_client_connection_count{state="used"})'
```

Always aggregate (`sum by`, `topk`) before printing; a raw selector returns every series.

---

## 8. Traces

```bash
curl -fsS "http://tempo:3200/api/traces/<trace_id>" \
  | jq -r '.batches[].scopeSpans[].spans[] | "\(.name) \((.endTimeUnixNano|tonumber) - (.startTimeUnixNano|tonumber) | . / 1e6 | floor)ms \(.status.code // "")"' | head -n 40
```

No trace for the id usually means it was sampled out, not that the request never arrived: check the sampling policy, then fall back to logs and metrics. Response shapes differ between trace stores; project span name, duration, and status, and stop there.

---

## 9. When a Query Returns Nothing

| Cause | Check |
| :--- | :--- |
| Window too narrow or wrong time zone | Convert the reported time to UTC, widen once |
| Request succeeded quietly | Successful requests may log nothing; use the trace or metrics |
| Wrong environment or service label | List label values before guessing |
| The id was never propagated | A real gap: record it and fix it with step 2 of the skill |
