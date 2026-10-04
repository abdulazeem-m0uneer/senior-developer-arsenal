---
name: perf-audit
description: 'Performance auditing workflow to detect database query bottlenecks, event loop lag, memory leaks, and thread pool starvation. Use when the user asks to audit backend performance, profile slow queries, detect event loop lag, or runs /perf-audit. Triggers on: "performance audit", "slow queries", "event loop lag", "memory leak", "thread starvation", "/perf-audit". Do not use for frontend client-side re-render profiling (use frontend-audit).'
---

# Systems Performance & Latency Audit Skill

Follow this procedure when conducting systematic performance audits across database query execution, runtime thread pools, and event loops.

---

## 1. When to Use This Skill

Activate this skill when:
- Investigating high p99 latency, slow API endpoints, or database lock contention.
- Detecting thread pool starvation in .NET or event loop blocking in Node.js/Python.
- Auditing memory consumption and connection pool sizing.
- The user runs the `/perf-audit` slash command.

*Boundary*: For React/Angular component re-render churn and DOM virtualizing, use `frontend-audit`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Database Query & Index Profiling
Consult: [Backend Performance Reference](./references/perf-profiling.md)
1. Inspect slow repository queries and ORM mappings.
2. Check for missing indexes on filter/join columns, unindexed foreign keys, and large `OFFSET` clauses.
3. In C#: Verify read queries use `.AsNoTracking()` and split queries (`AsSplitQuery`).
4. In PostgreSQL: Profile queries with `EXPLAIN (ANALYZE, BUFFERS)`.

### Step 2: Concurrency & Runtime Inspection
1. **.NET / C#**: Search for sync-over-async (`.Result`, `.Wait()`) and verify `IHttpClientFactory` usage.
2. **Node.js**: Search for synchronous filesystem or crypto calls in request loops.
3. **Python**: Search for synchronous blocking calls inside `async def` functions.

### Step 3: Resource & Memory Leak Inspection
1. Verify disposal of all database connections, streams, and HTTP clients.
2. Verify that in-memory caches have explicit size bounds and TTL eviction policies.

---

## 3. Verification Protocol

Output findings in a compact Markdown table:

| Subsystem | Bottleneck | Metric / Risk | Severity | Recommendation |
| :--- | :--- | :--- | :---: | :--- |
| Database | Sequential scan on `orders.customer_id` | Scans 2M rows per lookup | `⚡ [Perf]` | `CREATE INDEX CONCURRENTLY idx_orders_customer` |
| .NET API | `.Result` call in payment handler | Thread pool starvation | `🚨 [Blocker]` | Convert to `await` pipeline |

---

## 4. ⚡ Token-Saving Execution Rule

- Present recommendations ranked by ROI (highest latency reduction per line of code).
- Show only 2–5 line surgical fixes.
