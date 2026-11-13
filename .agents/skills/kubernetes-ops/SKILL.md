---
name: kubernetes-ops
description: 'Kubernetes workload runbook: manifest checklist (requests and limits, probes, securityContext, PDB, HPA, rollout, secrets, NetworkPolicy, RBAC), Helm and kustomize conventions, validation before apply, and a symptom-driven debugging runbook, read-only kubectl first. Use to write, review, or debug manifests, a Helm chart, or a failing pod or rollout, or /kubernetes-ops. Triggers on: "Kubernetes manifest", "Helm chart", "CrashLoopBackOff", "Pending pod", "kubectl". Not for applying to a live shared cluster (use shared-infra-changes) or Dockerfiles and pipelines (use devops-ci).'
---

# Kubernetes Operations Procedure

This skill guides the agent through writing safe Kubernetes manifests and charts, validating them before they reach a cluster, and finding the cause of a failing workload with read-only commands first.

---

## 1. When to Use This Skill

Activate this skill when:
- Writing or reviewing a Deployment, StatefulSet, Job, CronJob, Service, Ingress, HPA, PDB, or NetworkPolicy.
- Creating or changing a Helm chart or kustomize overlay.
- A pod is Pending, crashing, not Ready, or a rollout is stuck; a Service has no endpoints.
- Checking a manifest for security context, resource, probe, or shutdown mistakes before merge.
- The user runs the `/kubernetes-ops` slash command.

*Boundary*: Any change to a live shared cluster (apply, patch, scale, delete, rollout undo) goes through `shared-infra-changes` and the `infra-reviewer` subagent. Images, Dockerfiles, and pipelines belong to `devops-ci`. This skill supplies the Kubernetes-specific knowledge only.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Inventory Before Writing
1. Read the existing manifests or chart, the target cluster version, and the namespace's Pod Security level. Never assume the cluster version; read it from the project or ask.
2. Note the app's startup time, shutdown behavior, ports, memory profile, and dependencies.

### Step 2: Author or Review the Manifest
Consult: [Manifest Authoring Checklist](./references/manifest-checklist.md)
1. Pick the workload kind by the app's identity and lifetime, not by habit.
2. Set requests on every container; make memory limit equal to request.
3. Give probes distinct jobs: startup for slow boot, readiness for traffic, liveness for deadlock only.
4. Apply the restricted securityContext, a PDB, spread constraints, graceful shutdown, and a default-deny NetworkPolicy.
5. Pin images by tag or digest, never `latest`; keep secrets out of manifests and images.

### Step 3: Package with Helm or kustomize
Consult: [Helm Conventions & Validation](./references/helm-and-validation.md)
1. Keep values few and documented; keep logic out of templates.
2. Version the chart and the app separately.
3. Prefer kustomize overlays when only per-environment patches differ.

### Step 4: Validate Before Anything Touches a Cluster
Consult: [Helm Conventions & Validation](./references/helm-and-validation.md)
1. Render offline, lint, and schema-check with kubeconform.
2. Use `kubectl apply --dry-run=server` and `kubectl diff` only against a cluster the user owns or has approved reading.
3. Treat policy-as-code (Kyverno, OPA Gatekeeper) as an optional extra gate; never require it.

### Step 5: Debug with Read-Only Commands First
Consult: [Debugging Runbook](./references/debugging-runbook.md)
1. Match the symptom in the table, then run the listed read-only commands in order: `get`, `describe`, events, `logs`, `top`.
2. Form one hypothesis from evidence and name the single command that would confirm it.
3. Ephemeral debug containers and `exec` are still access to a live workload: ask first on shared clusters.

### Step 6: Hand Off Live Changes
1. Never run `apply`, `patch`, `scale`, `delete`, `rollout undo`, `helm upgrade`, or `helm rollback` against a live shared cluster from this skill.
2. Produce the exact command, the expected effect, and the rollback command; route them through `shared-infra-changes`.

---

## 3. Verification Protocol

```bash
helm lint ./chart --strict && helm template rel ./chart -f values.yaml | kubeconform -strict -summary -
kustomize build overlays/prod | kubeconform -strict -summary -
grep -rnE 'image:.*(:latest|[^:@]+$)' manifests/        # untagged or latest images: must print nothing
kubectl apply --dry-run=server -f out.yaml              # only against an approved cluster
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Probe | Liveness checks the database | Database blip restarts every pod at once | `[Blocker]` | Liveness checks the process only; dependency in readiness |
| Security | No `runAsNonRoot`, writable root filesystem | Root path to node escape | `[Security]` | Restricted securityContext |
| Resources | No requests set | HPA cannot compute; pod evicted first | `[Architecture]` | Set requests from observed usage |

---

## 4. Negative Triggers

- Applying, scaling, or deleting on a live shared cluster: use `shared-infra-changes`.
- Dockerfile hardening, image scanning, CI workflows, deploy strategy: use `devops-ci`.
- Reviewing an infrastructure diff before merge: the `infra-reviewer` subagent.
- An outage already in progress: use `incident-response`.

---

## 5. ⚡ Token Conservation Directive

- **Filtered Output**: Pipe `kubectl` output through `grep`, `-o jsonpath`, or `tail`; never paste whole `describe` or YAML dumps.
- **Events Only**: Quote the failing event line and the last 20 log lines, not the full log.
- **Table, Not Prose**: Report the symptom, evidence, cause, and next command in one row.
