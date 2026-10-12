---
name: incident-response
description: 'Production incident runbook: set severity by user impact, assign incident roles, mitigate before diagnosing, keep a live timeline, send status updates on a fixed interval, preserve evidence before restart, and close with a blameless postmortem with owned, dated actions. Use when the user asks to handle an outage, write a status update or postmortem, or runs /incident-response. Triggers on: "production is down", "we have an incident", "status update", "write a postmortem", "/incident-response". Do not use for root-cause method (use investigate) or deploy pipeline design (use devops-ci).'
---

# Production Incident Response Procedure

This skill guides the agent through running a production incident from declaration to all-clear, and through the blameless postmortem that turns it into a permanent rule or automated check.

---

## 1. When to Use This Skill

Activate this skill when:
- Users are affected now: an outage, elevated errors, data at risk, or a failed release.
- An alert needs a severity and an owner, or an incident needs a status update.
- An incident has ended and needs a postmortem with tracked actions.
- Preparing: writing the severity matrix, on-call roles, or update templates before they are needed.
- The user runs the `/incident-response` slash command.

*Boundary*: For the hypothesis-driven search for the root cause after mitigation, use `investigate`. For reading logs, metrics, and traces, use `observability`. For designing rollback into the pipeline, use `devops-ci`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Declare, Size, Assign
Consult: [Severity Matrix & Mitigation Menu](./references/severity-matrix.md)
1. Declare early: a suspected incident is declared and downgraded later; an undeclared one has no owner.
2. Set severity from user impact (who, how many, which function, is data or money at risk), never from the suspected cause.
3. Assign three roles, even when one person holds several: commander (decides, owns severity), operations (the only hands changing production), communications (updates, stakeholders).
4. Open one channel and one timeline document; record the start time and the first known-bad observation.

### Step 2: Mitigate First
1. Ask "what changed" before "why": the last deploy, configuration change, flag flip, migration, dependency or certificate expiry.
2. Choose the fastest reversible action: roll back the release, turn the feature flag off, scale out, fail over, shed load.
3. Before rolling back across a schema change, read the migrations the bad release added; a dropped column the older build still reads means fix forward.
4. One change at a time, announced in the channel before it is made, by operations only.
5. Verify the mitigation on the system itself: the version endpoint returns the expected commit and the error rate falls. A command that exited zero proves nothing.

### Step 3: Preserve Evidence
1. Before any restart or redeploy, capture what the restart destroys: the previous container log, a thread or heap dump, pool and queue state, the failing request ids.
2. Snapshot dashboards with their time range; note the retention period of logs and traces and export what will expire.
3. Never let evidence collection delay mitigation of a critical incident beyond a few minutes; take what is cheap and move on.

### Step 4: Communicate on a Clock
Consult: [Status Update & Postmortem Templates](./references/incident-templates.md)
1. Send updates at the interval the severity sets, even when the update is "no change"; silence reads as loss of control.
2. Fixed shape every time: impact now, what is known, what is being done, next update time. No guesses about cause.
3. Append to the timeline as events happen, with UTC times and who did what; it is not reconstructed from memory afterwards.

### Step 5: All-Clear & Postmortem
1. Close only when all hold: the user-facing symptom is gone, SLO signals are back in range for a full observation window, no mitigation is still fragile, and follow-ups are filed.
2. Hold the postmortem within five working days while memory is fresh; it is blameless: it names decisions and conditions, not culprits.
3. Write the causal chain from trigger to impact, including why detection and mitigation took as long as they did, and what went well.
4. Every action has one owner and a date. Every incident leaves at least one rule or automated check that would have prevented or caught it.

---

## 3. Verification Protocol

```bash
curl -fsS https://<host>/version                              # running commit equals the rollback target
kubectl rollout status deployment/<name> --timeout=120s       # replicas ready on that revision
kubectl logs deployment/<name> --since=10m --tail=500 | grep -c '"level":"error"'   # falling, compare with the peak
git log --oneline -5 <rollback-target>..<bad-release>         # what the rollback removed
```

Review the incident record before closing:

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Mitigation | "Rolled back" reported, version endpoint still shows the bad commit | Incident continues unowned | `[Blocker]` | Read the running version back; redo the rollback |
| Evidence | Pods restarted before logs or dumps were taken | Cause unprovable, likely repeat | `[Architecture]` | Add capture commands to the runbook ahead of restart |
| Postmortem | Actions without owner or date | Nothing changes | `[Blocker]` | One named owner and a date per action |
| Postmortem | Cause recorded as "human error" | Systemic gap stays open | `[Suggestion]` | Ask why the system allowed it; add a guard or check |

---

## 4. ⚡ Token-Saving Execution Rule

- **Template Fill**: Produce status updates and the postmortem by filling the templates; do not compose new formats mid-incident.
- **Bounded Evidence**: Quote only the first failing lines and the numbers that set severity; link to dashboards instead of pasting them.
- **Mitigation Before Theory**: Do not spend output on causal speculation while users are affected; list the reversible actions and their order.
