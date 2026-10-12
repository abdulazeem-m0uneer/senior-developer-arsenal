# Plan, Apply & Rollback Reference

Plan guard rules, tool equivalents, the approval table, the rollback template, secrets handling, and the reviewer's attack list.

---

## 1. Plan Guard

The wrapper reads the machine-readable plan and refuses on its own reading, at plan time and again at apply time. A refused plan file is deleted.

| Guard | Refuses | Reason |
| :--- | :--- | :--- |
| Actions | Anything but `create` (update, delete, replace) | A replace is a delete of something live |
| Kinds | A resource kind outside the allow-list | A plan may not grow a ruleset or account setting unnoticed |
| Names | A name the live system already holds for someone else | Many providers accept it as an addition and share the traffic |
| Marker | An addition without the owner and environment marker | Unmarked items cannot be told from theirs later |
| Source | An addition whose name is not in the data file | The plan must equal the reviewed data |
| Age | A plan older than 30 minutes | The live system has moved since review |
| Override | Changes to our own items without the flag on both plan and apply | One flag is a slip; two are a decision |

```typescript
type Change = { address: string; type: string; change: { actions: string[] } };

export function planProblems(changes: Change[], allowed: Set<string>): string[] {
  return changes
    .filter((c) => !["no-op", "read"].includes(c.change.actions.join(",")))
    .flatMap((c) => [
      ...(c.change.actions.join(",") === "create" ? [] : [`${c.address}: ${c.change.actions} is not an addition`]),
      ...(allowed.has(c.type) ? [] : [`${c.address}: kind ${c.type} may not be added`]),
    ]);
}
```

---

## 2. Tool Equivalents

| Step | OpenTofu / Terraform | Pulumi | Provider CLI only |
| :--- | :--- | :--- | :--- |
| Save a plan | `plan -out=change.tfplan` | `pulumi preview --save-plan=plan.json` (update plans, experimental) | Write the exact commands to a script file |
| Read it by machine | `show -json change.tfplan` | `pulumi preview --json` | Review the script; dry-run flag where one exists |
| Apply that plan | `apply change.tfplan` | `pulumi up --plan=plan.json` | Run the reviewed script, unchanged |
| Prove no drift | `plan -detailed-exitcode` (0 clean, 2 drift) | `pulumi preview --expect-no-changes` | Re-export and diff against the expected inventory |
| Lock | Backend state locking | Backend stack lock | One named operator at a time |

Without infrastructure-as-code the same rules hold: the reviewed artefact is the script, the plan is its dry run, and the proof is the inventory diff.

---

## 3. What the Human Approves

Never the raw plan. One table, plus the rollback:

| Action | Item | Value | Environment | Affects existing? |
| :--- | :--- | :--- | :--- | :--- |
| Add | `A api-staging` | `203.0.113.10` | staging | No |
| Add | Access policy `docs-staging-readers` | Group `engineering` | staging | No |
| Change | none | | | |
| Remove | none | | | |

- Approval is written (pull request comment, ticket, chat message that is kept) and names the plan it approves.
- Silence, an earlier approval, or "same as last time" is not a go-ahead.
- If the plan is regenerated for any reason, the approval is void.

---

## 4. Rollback, Written First

```text
Change:    add A api-staging -> 203.0.113.10 (staging)
Trigger:   the outside check fails 10 minutes after apply, or any existing name resolves differently
Rollback:  remove the api-staging entry from records.json; plan (override flag: removal of our own item);
           show the plan (one delete, zero others); apply; re-plan reports no changes
Not undone by rollback: resolver caches until the record TTL (300 s) expires
Who runs it: the operator who applied; the owner is told in the same hour
```

- Rollback removes only what this change added. It never restores somebody else's item from memory: if one of theirs was touched, stop and call the owner with the baseline row.
- Lower a TTL in a separate, earlier change if a fast rollback matters; lowering it in the same change does not help.
- Things that cannot be rolled back (a deleted bucket with data, a rotated signing key, an issued certificate) are named in the plan review, not discovered afterwards.

---

## 5. Secrets

- Credentials come from the environment or a secret store, loaded in the same command that uses them. Never an argument, never a committed file, never echoed.
- Scope the token to the one zone, project, or namespace and to the actions the change needs. A read-only token for inventory, a separate one for apply.
- State can contain secrets: encrypt it at rest, restrict who can read the backend, and never paste state or `show` output into a ticket or conversation.
- To prove a secret is loaded, print its length, not its value.
- A secret that reached a log or a terminal recording is rotated, not just deleted.

---

## 6. Reviewer Attack List

Review in this order; prefer proving a finding (render, validate, mutate a copy) to arguing it.

1. **Breaks the first apply**: wrong argument for the pinned provider version, a thing used before it exists, a job with no deadline.
2. **Touches what is not ours**: an import, a data source turned into a resource, a name collision, a missing marker. Try to defeat the guard.
3. **Opens a hole**: a path to administrator rights, a secret in arguments or state, something public that should not be, a header or address trusted from anyone.
4. **Locks people out or loses data**: remote access, firewall, a volume, a regenerated secret for a store that keeps the old one.
5. **Passes the gate while wrong**: a check that counts a string, a pattern that matches nothing, a planted case that changes nothing.
6. **Says what the files do not**: a runbook line or comment the configuration contradicts.

Report: verdict, findings most severe first with `file:line`, the concrete failing case and the smallest fix; then what was checked and found sound, and what only the live provider can show.

---

## 7. Common Failures

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| Re-plan shows changes right after apply | Provider normalises a value (case, trailing dot, default) | Write the normalised form in the module; do not ignore the diff |
| Plan wants to destroy something of theirs | It was imported or declared earlier | Remove it from state without destroying (`state rm`), with the owner told |
| Addition accepted but traffic is split | Name already existed outside state | The live-name guard was skipped; remove ours, re-check |
| Apply fails halfway | Partial create | Re-plan; apply the remainder only after a new go-ahead |
