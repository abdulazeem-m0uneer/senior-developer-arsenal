# Severity Matrix & Mitigation Menu

Severity levels with update cadences, role duties, the mitigation order, evidence capture commands, and all-clear criteria.

---

## 1. Severity Matrix

Severity follows impact. When two rows apply, take the higher. Data loss, a security breach, or wrong money movement is never below SEV2.

| Level | Impact | Examples | Response | Internal update | External update | Postmortem |
| :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| SEV1 | Core function down for most users, or data or money at risk | Sign-in fails for everyone; payments double-charged; data exposed | Page now, all hands, 24x7 until mitigated | every 15 min | every 30 min | Required, within 5 working days |
| SEV2 | Core function degraded, or down for a large segment | Checkout error rate 20%; one region unreachable; queue backlog growing without bound | Page now, on-call plus one | every 30 min | every 60 min | Required, within 5 working days |
| SEV3 | Secondary function broken, workaround exists | Exports fail; notifications delayed; one integration down | Working hours, on-call owns | every 2 h | when resolved, if users noticed | Short written review |
| SEV4 | Cosmetic or internal only | Wrong label; internal dashboard stale | Ticket, normal priority | none | none | None |

Re-evaluate severity at every update. Upgrade immediately when impact grows; downgrade only after a full observation window at the lower impact.

---

## 2. Roles

| Role | Does | Does not |
| :--- | :--- | :--- |
| Commander | Sets severity, decides the next action, assigns work, calls all-clear, hands over explicitly at shift end | Type commands or debug |
| Operations | Is the only one changing production; announces each change before making it; reports the observed result | Decide alone to try a risky change |
| Communications | Sends updates on the clock, keeps the timeline, answers stakeholders | Speculate about cause or promise a fix time |
| Subject expert (as needed) | Investigates one named question and reports back | Change production directly |

A solo responder still switches hats aloud: write the decision in the timeline as commander, then execute as operations, then send the update.

---

## 3. Mitigation Menu (fastest reversible first)

| Order | Action | Use when | Check before | Verify after |
| :---: | :--- | :--- | :--- | :--- |
| 1 | Turn the feature flag off | The fault sits behind a flag | Flag default is the safe state | Error rate on the flagged route |
| 2 | Roll back the release | Symptom started with a deploy | Migrations in the bad release are backward compatible | Version endpoint returns the old commit |
| 3 | Revert a configuration or secret change | Symptom started with a config change | Previous value is known and still valid | Process restarted with the old value |
| 4 | Scale out or raise limits | Saturation: CPU, pool, queue depth | The bottleneck is not a shared database | Saturation gauges fall |
| 5 | Shed load or rate-limit | A caller or a retry storm is overwhelming the system | Critical callers are exempt | Latency recovers for the rest |
| 6 | Fail over | A zone, region, or primary is unhealthy | Replica lag is acceptable; the data-loss window is stated | Writes succeed on the new primary |
| 7 | Fix forward | Rollback is impossible (destructive migration, external state) | Change is minimal, reviewed by a second person | Same checks as a normal release |

```bash
kubectl rollout history deployment/<name>                    # find the last good revision
kubectl rollout undo deployment/<name> --to-revision=<n>
kubectl rollout status deployment/<name> --timeout=120s
curl -fsS https://<host>/version                             # the proof, not the exit code
```

---

## 4. Evidence Before Restart

| What a restart destroys | Capture |
| :--- | :--- |
| Crashed container output | `kubectl logs <pod> --previous --tail=500 > evidence/<pod>-previous.log` |
| Scheduling and kill reasons | `kubectl describe pod <pod> > evidence/<pod>-describe.txt`; `kubectl get events --sort-by=.lastTimestamp > evidence/events.txt` |
| Node.js stuck or leaking process | `kill -USR2 <pid>` writes a heap snapshot when the process was started with `--heapsnapshot-signal=SIGUSR2`, or a diagnostic report when started with `--report-on-signal` |
| .NET threads and heap | `dotnet-dump collect -p <pid>`; `dotnet-counters monitor -p <pid>` for a live read |
| Python stuck threads | `py-spy dump --pid <pid>` |
| Database state | Active queries and locks (`pg_stat_activity`, `pg_locks` or the engine equivalent), connection counts |
| Host state | `journalctl -u <unit> --since "30 min ago" --no-pager > evidence/unit.log`; `dmesg -T` (last 100 lines) for out-of-memory kills |

Evidence files may hold personal data and secrets: store them with the incident record under restricted access, never in a public ticket or repository.

---

## 5. All-Clear Criteria

- [ ] The user-facing symptom is gone, confirmed from the user side (synthetic check or a real request), not only from dashboards.
- [ ] Error rate and latency are inside the SLO for one full observation window (30 minutes for SEV1 and SEV2).
- [ ] Backlogs have drained: queues, retries, delayed jobs, replication lag.
- [ ] Data is reconciled or the reconciliation is a filed, owned action with a date.
- [ ] No mitigation is fragile: manual scale settings, disabled checks, and switched-off flags are recorded with an owner for their removal.
- [ ] The final update is sent, the timeline is complete, and the postmortem has an owner and a date.

---

## 6. From Incident to Rule

Each incident leaves one preventive rule or check. The pattern:

| What happened | The rule or check it leaves |
| :--- | :--- |
| A deploy step reported success while the old version kept serving | A release is done when the version endpoint returns the new commit; the pipeline asserts it |
| A release dropped a column the previous build still read, blocking rollback | Expand in one release, contract in a later one; a migration lint refuses destructive changes |
| An intermittent test failure was retried for a week and was a real hang | An intermittent failure is investigated to its cause; retries are not a fix |
| A certificate expired on a weekend | Expiry is monitored with an alert 30 days ahead |
| A retry loop multiplied a partial outage | Retries carry a budget, backoff, and jitter; load tests include a dependency failure |
