# Manifest Authoring Checklist

Decision rules and required fields for production-grade Kubernetes workloads. Stable API versions: `apps/v1` (Deployment, StatefulSet), `batch/v1` (Job, CronJob), `policy/v1` (PodDisruptionBudget), `autoscaling/v2` (HPA). Confirm the cluster's served versions with `kubectl api-versions`.

---

## 1. Workload Kind

| Need | Kind | Notes |
| :--- | :--- | :--- |
| Stateless service, any replica interchangeable | Deployment | Default choice |
| Stable network identity or per-replica volume | StatefulSet | Set `serviceName`, `volumeClaimTemplates`; ordered rollout by default |
| Run to completion once | Job | Set `backoffLimit`, `activeDeadlineSeconds`, `ttlSecondsAfterFinished` |
| Recurring run | CronJob | Set `concurrencyPolicy` (Forbid for non-idempotent), `startingDeadlineSeconds`, history limits |
| One pod per node (agents) | DaemonSet | Needs tolerations deliberately chosen |

- Helper process tied to the main container's lifetime: declare it as a sidecar (an init container with `restartPolicy: Always`), stable since Kubernetes v1.33. On older clusters use a normal second container.
- Never run a bare Pod for anything that must survive node loss.

---

## 2. Resources

- Set `requests` on every container. The scheduler, HPA, and eviction order all depend on them.
- Memory: set `limits.memory` equal to `requests.memory`. Memory is not compressible; an exceeded limit is an OOM kill, and equal values give predictable QoS and eviction.
- CPU: requests always; limits are debatable. A CPU limit throttles the container even when the node is idle and inflates tail latency. Omit it unless the namespace requires it or noisy neighbours are proven. If set, watch `container_cpu_cfs_throttled_periods_total`.
- Derive values from observed usage (`kubectl top pod --containers`, metrics history), not guesses. Add a LimitRange and ResourceQuota per namespace.
- In-place pod resize (change CPU or memory without recreating the pod, via the `resize` subresource) is stable since Kubernetes v1.35. Do not rely on it for older clusters.

---

## 3. Probes

| Probe | Question it answers | Failure effect | Use for |
| :--- | :--- | :--- | :--- |
| startup | Has the app finished booting? | Container restarted after `failureThreshold * periodSeconds` | Slow boot; holds off the other two |
| readiness | Can it take traffic now? | Removed from Service endpoints | Warm-up, dependency down, overload shedding |
| liveness | Is the process wedged beyond recovery? | Container restarted | Deadlock detection only |

- Classic mistakes:
  - Liveness checks a database or downstream service: one outage restarts every replica and deepens it.
  - Slow app, no startup probe: liveness kills it during boot, producing CrashLoopBackOff.
  - Same endpoint and thresholds for liveness and readiness.
  - `timeoutSeconds: 1` on a path that does real work; probes under CPU throttling flap.
  - No readiness probe: traffic hits a pod that is still booting.
- Liveness: cheap local check, generous `failureThreshold`. Readiness: may check dependencies the pod cannot serve without.
- gRPC services: use the native `grpc` probe rather than an exec of a client binary.

---

## 4. Security Context and Pod Security

Pod level: `runAsNonRoot: true`, `runAsUser` set to a fixed non-zero id, `seccompProfile.type: RuntimeDefault`, `fsGroup` only if a volume needs it.
Container level: `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, `capabilities.drop: ["ALL"]` (add back one named capability only with a written reason), no `privileged`.

- Read-only root filesystem: mount `emptyDir` at `/tmp` and any other path the app writes.
- Pod Security Standards levels: `privileged` (unrestricted), `baseline` (blocks known privilege escalations), `restricted` (current hardening best practice). Pod Security Admission enforces them per namespace through labels `pod-security.kubernetes.io/enforce`, `/audit`, `/warn` (GA since v1.25).
- Roll out a stricter level with `warn` and `audit` first, read the warnings, then set `enforce`.
- Target `restricted` for application namespaces. Anything needing `baseline` or `privileged` is an exception with an owner and a reason in the manifest comment.
- Set `hostNetwork`, `hostPID`, `hostPath` only with a recorded reason.

---

## 5. Availability

- PodDisruptionBudget (`policy/v1`): one per multi-replica workload. `maxUnavailable: 1` or `minAvailable` below the replica count. `minAvailable` equal to replicas blocks node drains forever. A PDB does not protect against involuntary loss.
- Spread: use `topologySpreadConstraints` (`topologyKey: topology.kubernetes.io/zone` and `kubernetes.io/hostname`, `whenUnsatisfiable: ScheduleAnyway` unless hard isolation is required) with a `labelSelector` matching the pods. Pod anti-affinity is the older alternative; `required` anti-affinity makes pods unschedulable when nodes run out.
- At least 2 replicas for anything user-facing.
- HPA (`autoscaling/v2`): scaling on CPU or memory utilization is a percentage of the request, so requests must be set or the HPA reports unknown. Set `minReplicas` at the PDB-safe floor, tune `behavior.scaleDown.stabilizationWindowSeconds`. Do not set `spec.replicas` in a manifest that an HPA manages; it resets on every apply.

---

## 6. Rollout and Graceful Shutdown

| Field | Guidance |
| :--- | :--- |
| `strategy.rollingUpdate.maxSurge` | 25% default; raise for faster rollouts if quota allows |
| `maxUnavailable` | 0 for strict capacity during rollout (needs surge headroom) |
| `minReadySeconds` | 5-30; a new pod must stay Ready this long before it counts |
| `progressDeadlineSeconds` | Raise above worst-case boot time so a slow rollout is not marked failed |
| `terminationGracePeriodSeconds` | Longer than the app's drain time plus preStop sleep (default 30) |
| `lifecycle.preStop` | `sleep 5-10` so endpoint removal propagates before SIGTERM stops accepting connections |

- The app must handle SIGTERM: stop accepting, finish in-flight requests, exit. Run as PID 1 in exec form so the signal arrives.
- Distroless images have no `sleep` binary; use the native `lifecycle.preStop.sleep` action (check it is available on the cluster's version) or sleep inside the app.
- `revisionHistoryLimit` of 3-10 keeps `rollout undo` possible without clutter.

---

## 7. Config, Secrets, Identity

- ConfigMap for non-secret config; changes to env-injected values need a rollout. Roll on config change by hashing the ConfigMap into a pod annotation.
- Secrets: never in manifests, Helm values committed to git, or images. Use an external secret manager (External Secrets Operator, a CSI secrets driver, or sealed/encrypted-at-rest in git) and enable etcd encryption at rest. Prefer mounted files over env vars (env leaks into dumps and child processes).
- ServiceAccount: one per workload; `automountServiceAccountToken: false` unless the pod calls the API.
- RBAC: Roles in the namespace, not ClusterRoles; list exact resources and verbs; no wildcards; no `cluster-admin` bindings for workloads. Check with `kubectl auth can-i --list --as=system:serviceaccount:<ns>:<sa>`.
- NetworkPolicy: start each namespace with a default-deny ingress and egress policy, then allow DNS egress and each named flow. Requires a CNI that enforces policies; verify, because unenforced policies silently do nothing.

---

## 8. Names, Labels, Images

- `spec.selector` of Deployment, StatefulSet, and DaemonSet is immutable. Changing it needs delete and recreate. Never put a version or chart label in the selector; use only stable labels (`app.kubernetes.io/name`, `app.kubernetes.io/instance`).
- A Service selector that overlaps another workload's labels sends traffic to the wrong pods.
- Use the `app.kubernetes.io/*` recommended labels on everything.
- Images: no `latest`, no untagged. Immutable version tag at minimum; digest (`image@sha256:...`) for production. `imagePullPolicy: IfNotPresent` with immutable tags.
- One namespace per team or environment boundary; never deploy into `default` or `kube-system`.
