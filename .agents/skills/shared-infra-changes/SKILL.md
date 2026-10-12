---
name: shared-infra-changes
description: 'Runbook for changing live shared infrastructure (DNS zones, cloud accounts, clusters, identity providers): inventory first, additions only, each marked with its owner, one reviewed data file, a human-approved plan, a no-changes re-plan and a rollback written first. Use when the user asks to add to a shared account, review an infrastructure plan, or runs /shared-infra-changes. Triggers on: "add a DNS record", "shared account", "live zone", "infrastructure plan", "/shared-infra-changes". Do not use for pipelines and Dockerfiles (use devops-ci) or schema changes (use database-migration).'
---

# Shared Infrastructure Change Procedure

This skill guides the agent through changing live shared infrastructure by additions only, through one reviewed data file, with a plan a human approved, an apply of exactly that plan, and proof afterwards that nothing else moved.

---

## 1. When to Use This Skill

Activate this skill when:
- Adding a DNS record, access rule, bucket, queue, namespace, or identity-provider client to a zone, account, cluster, or tenant that already serves other systems.
- Setting up infrastructure-as-code for one slice of a shared account without adopting what is already there.
- Reviewing an infrastructure pull request or a plan output before it is applied.
- A plan shows a change or a destroy nobody asked for, or an apply went wrong.
- The user runs the `/shared-infra-changes` slash command.

*Boundary*: For Dockerfiles, CI pipelines, and application deploy strategy, use `devops-ci`. For database schema changes, use `database-migration`. For an outage already in progress, use `incident-response`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Inventory Before Touching Anything
Consult: [Additions-Only Guardrails](./references/additions-only-guardrails.md)
1. Name the owner of the shared resource and find their written rule for it. No written rule means the default: nothing that exists is edited or deleted.
2. Take a read-only export of what exists (every record or resource: name, type, value, who depends on it) and commit it as the baseline. Strip secret values first.
3. Classify each item as theirs, ours (carries our marker), or unknown. Unknown is treated as theirs.
4. Never import or adopt an existing resource into state: once it is managed, a one-line mistake destroys it.

### Step 2: Confine the Change to One Data File
1. Every addition is one entry in a single data file (JSON or YAML): name, environment, target, added-by. Reviewers read data, not provisioning logic.
2. Freeze every other file of the configuration by checksum or policy check. Changing a frozen file means changing its checksum in the same pull request, in front of the reviewer.
3. Mark each addition with who added it and for which environment, in the comment, tag, or label field; in the name itself where the resource has no such field.
4. The check refuses a name the baseline already holds, the apex, wildcards, and any malformed spelling. Keep each bypass ever found as a planted case that must stay refused.

### Step 3: Review, Plan, and Write the Rollback
Consult: [Plan, Apply & Rollback Reference](./references/plan-apply-and-rollback.md)
1. Open a pull request; the reviewer tries to defeat the guard, not only to read it.
2. Write the plan to a file and read it by machine: refuse any action that is not a create, any resource kind outside the allow-list, and any name the live system already holds for someone else.
3. Write the rollback step and its trigger before anyone approves: the exact command that removes only what this change adds.
4. Show a human owner the table of what is added, changed, and removed, and wait for their written go-ahead. Every time, with no standing approval.

### Step 4: Apply Exactly the Reviewed Plan
1. Apply the saved plan file, never a fresh plan. Refuse a plan older than 30 minutes or one made against a different state.
2. One writer at a time: state locking on, and no console or direct API write outside the reviewed path.
3. Read credentials from the environment or a secret store. Never put them in arguments, logs, state, or the conversation; show a length at most.
4. A change or removal of our own items needs an explicit flag on both plan and apply, and its own go-ahead.

### Step 5: Prove Nothing Else Moved
1. Plan again: it must report no changes. Anything else is drift; stop and investigate before a second apply.
2. Export the inventory again and compare it with the baseline minus our marked items: the difference must be empty.
3. Check from outside what the change was for (resolve the name, call the endpoint, sign in through the provider).
4. Record what was added, who approved, the plan summary, and the rollback step in the runbook.

---

## 3. Verification Protocol

```bash
tofu fmt -check -recursive && tofu validate            # terraform takes the same subcommands
sha256sum --check frozen.sha256                        # every file but the data file is unchanged
tofu plan -out=change.tfplan -lock-timeout=60s
tofu show -json change.tfplan | jq -e \
  '[.resource_changes[] | select((.change.actions - ["create","no-op","read"]) | length > 0)] | length == 0'
tofu apply change.tfplan                               # only after the written go-ahead
tofu plan -detailed-exitcode                           # 0 = no changes; 2 = drift, stop
dig +short app-staging.example.com                     # the outside check for a DNS addition
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Plan | One `update` on a record the baseline holds | Breaks another team in production | `[Blocker]` | Remove it from the configuration; never import existing items |
| Wrapper | Token passed as a command-line argument | Visible in process list and shell history | `[Security]` | Read it from the environment; print its length only |

---

## 4. ⚡ Token-Saving Execution Rule

- **Filtered Plans**: Never paste a whole plan; filter to the action lines and the summary, and give the owner the added/changed/removed table.
- **One Section**: Read only the runbook section and the data file the change touches, not the whole configuration.
- **Facts Once**: A fact learned about the shared resource goes into the baseline or the runbook, not into a new file or a repeated explanation.
