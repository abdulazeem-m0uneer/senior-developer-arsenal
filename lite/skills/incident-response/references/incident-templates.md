# Status Update & Postmortem Templates

Fill these in; do not invent formats during an incident. All times are UTC.

---

## 1. Declaration

```markdown
INCIDENT DECLARED: <short title, symptom not cause>
Severity: SEV<n> (<one line of impact that justifies it>)
Started: <time first seen> | Declared: <time>
Commander: <name> | Operations: <name> | Communications: <name>
Channel: <link> | Timeline: <link>
Next update: <time>
```

---

## 2. Status Update (same shape every time)

```markdown
UPDATE <n>, <time>, SEV<n>, status: investigating | mitigating | monitoring | resolved
Impact now: <who is affected, which function, how many or what share>
What we know: <verified facts only>
What we are doing: <current action and who holds it>
What users can do: <workaround, or "nothing needed">
Next update: <time>
```

Rules:
- [ ] Impact first, in the user's terms ("card payments fail for about one in five customers"), not in system terms.
- [ ] Only verified facts. No cause until it is proven; "cause not yet known" is a complete sentence.
- [ ] No fix-time promise; commit to the next update time instead, and keep it.
- [ ] "No change since the last update" is a valid update and is still sent on time.
- [ ] External updates drop internal names, host names, and people; they keep impact, workaround, and next update.

Worked example:

```markdown
UPDATE 3, 14:45, SEV2, status: monitoring
Impact now: checkout errors are back to normal levels since 14:38. Between 13:52 and 14:38 about 20% of checkouts failed.
What we know: errors began with the 13:50 release and stopped after it was rolled back.
What we are doing: watching error rate for 30 minutes; reconciling orders placed in the window (owner: operations).
What users can do: retry a failed checkout; no one was charged for a failed order.
Next update: 15:15
```

---

## 3. Timeline

| Time (UTC) | Who | Event | Source |
| :--- | :--- | :--- | :--- |
| 13:50 | pipeline | Release `3f9c2ab` deployed | deploy log |
| 13:52 | alerting | Checkout error-budget burn alert fired | alert link |
| 13:58 | commander | Declared SEV2; roles assigned | channel |
| 14:10 | operations | Captured previous container logs and events | evidence folder |
| 14:31 | operations | Rolled back to `a71e0d4` | command output |
| 14:38 | operations | Version endpoint returns `a71e0d4`; error rate under 0.1% | version check, dashboard |

Record decisions and the options rejected, not only actions. Derive four durations from it: time to detect, to declare, to mitigate, to resolve.

---

## 4. Postmortem

```markdown
# Postmortem: <title> (<date>, SEV<n>)

Status: draft | reviewed | actions complete        Author: <name>        Review date: <date>

## Summary
<Three sentences: what users experienced, for how long, what ended it.>

## Impact
- Users affected: <number or share, which segment>
- Duration: <start> to <end> (<minutes>)
- Data or money: <records lost, wrong, or to be reconciled; "none" if none>
- SLO: <error budget spent>

## Timeline
<The table from the incident, trimmed to decisive events.>

## Causal chain
1. Trigger: <the change or event that started it>
2. Why it caused harm: <the condition that turned the trigger into a failure>
3. Why it was not prevented: <the missing test, review step, or guard>
4. Why detection took <n> minutes: <alert gap, noisy signal, wrong threshold>
5. Why mitigation took <n> minutes: <missing runbook, slow rollback, unclear ownership>

## What went well
- <Things to keep: an alert that fired, a rollback that worked, a clear handover.>

## What went badly
- <Things that slowed detection, decision, or recovery.>

## Where we were lucky
- <What would have made this worse and was absent only by chance.>

## Actions
| # | Action | Type | Owner | Due | Tracking link |
| :- | :--- | :--- | :--- | :--- | :--- |
| 1 | <specific, verifiable change> | prevent / detect / mitigate | <one person> | <date> | <link> |

## The rule or check this incident leaves
<One sentence, plus where it is enforced: a pipeline check, a lint, an alert, a line in the runbook.>
```

---

## 5. Postmortem Review Checklist

- [ ] **Blameless**: no person is named as a cause; roles and decisions are described with the information available at the time.
- [ ] **No "human error"**: every "someone did X" is followed by why the system made X easy and its effect unguarded.
- [ ] **Chain is causal**: each step explains the next; removing any step would have prevented or shortened the impact.
- [ ] **Actions are verifiable**: "add an alert on queue depth above 1,000 for 5 minutes", not "improve monitoring".
- [ ] **One owner, one date** per action, tracked where other work is tracked.
- [ ] **At least one action is automated**: a check, a test, or an alert, not only a document or a reminder.
- [ ] **Shared**: published to the team; affected users get a plain-language summary for SEV1 and SEV2.
- [ ] **Followed up**: actions reviewed on their due dates; an overdue action is escalated, not silently moved.
