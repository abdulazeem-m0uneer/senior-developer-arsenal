# Debugging Runbook

Symptom to cause to command. Run read-only commands first, in the order shown. Nothing here changes live state unless marked CHANGE; every CHANGE command on a shared cluster goes through `shared-infra-changes`.

---

## 1. First Pass (read-only)

```bash
kubectl get pods -n NS -o wide                                  # state, restarts, node
kubectl describe pod POD -n NS | sed -n '/Events:/,$p'          # events at the bottom
kubectl get events -n NS --sort-by=.lastTimestamp | tail -30    # namespace timeline
kubectl logs POD -n NS -c CONTAINER --tail=50                   # current container
kubectl logs POD -n NS -c CONTAINER --previous --tail=50        # the container that crashed
kubectl top pod POD -n NS --containers                          # needs metrics-server
kubectl get deploy,rs,svc,endpointslices -n NS                  # the chain around the pod
```

- Always state namespace and context: `kubectl config current-context` before anything else, so a command never lands on the wrong cluster.
- Read events oldest to newest; the first warning is usually the cause, later ones are consequences.

---

## 2. Symptom Table

| Symptom | Likely causes | Evidence command | Notes |
| :--- | :--- | :--- | :--- |
| `Pending` | Insufficient CPU/memory; untolerated taint; unmatched nodeSelector/affinity; PVC unbound; quota | `describe pod` events (`FailedScheduling` states which); `kubectl get pvc`; `kubectl describe node NODE` (Allocatable vs Allocated) | Message lists counts per reason, e.g. "0/5 nodes: 3 Insufficient memory, 2 had untolerated taint" |
| `ImagePullBackOff` / `ErrImagePull` | Wrong tag or name; private registry without pull secret; rate limit; node cannot reach registry | `describe pod` events show the registry error text | Check `imagePullSecrets` exists in the same namespace |
| `CrashLoopBackOff` | App exits on start; bad config or missing env; failing liveness probe; OOM | `logs --previous`; `describe pod` -> Last State, Exit Code, Reason | See exit codes below |
| `Running` but not Ready | Readiness probe failing; wrong port or path; dependency down | `describe pod` -> "Readiness probe failed: ..." line; `logs` | Probe runs from the kubelet, not from inside the app network namespace of other pods |
| `ContainerCreating` long | Volume mount/attach failure; missing ConfigMap or Secret; CNI problem | `describe pod` events (`FailedMount`, `FailedCreatePodSandBox`) | |
| `CreateContainerConfigError` | Referenced Secret/ConfigMap/key missing | `describe pod` | |
| Rollout stuck | New pods not Ready; quota; PDB or surge limits; `progressDeadlineSeconds` exceeded | `kubectl rollout status deploy/D -n NS`; `kubectl get rs -n NS`; `describe` the new pod | Old pods keep serving; no outage yet |
| Service has no endpoints | Selector does not match pod labels; pods not Ready; wrong `targetPort` | `kubectl get endpointslices -l kubernetes.io/service-name=SVC`; `kubectl get svc SVC -o jsonpath='{.spec.selector}'`; `kubectl get pods --show-labels` | Not-Ready pods are excluded from endpoints |
| DNS failures | CoreDNS down; NetworkPolicy blocks UDP/TCP 53; wrong service name or namespace; `ndots` search path latency | `kubectl get pods -n kube-system -l k8s-app=kube-dns`; debug container: `nslookup SVC.NS.svc.cluster.local` | Name form: `svc.ns.svc.cluster.local` |
| Ingress 502 / 503 | 503: no ready endpoints behind the Service. 502: backend closed connection or wrong port/protocol; backend restarts mid-request | `describe ingress`; endpoints (above); ingress controller logs | Check `targetPort`, backend protocol annotation, and preStop/shutdown behavior during rollouts |
| `Evicted` pods | Node pressure (memory, disk, PID); ephemeral storage over limit | `describe pod` -> Reason/Message; `describe node` -> Conditions, Taints | Pods with no requests (BestEffort) go first |
| Node `NotReady` / pressure | Kubelet down; `MemoryPressure`, `DiskPressure`, `PIDPressure` | `kubectl describe node NODE` Conditions; `kubectl get events --field-selector involvedObject.kind=Node` | Cordon/drain are CHANGE commands |
| `Terminating` forever | Finalizer; stuck volume detach; process ignoring SIGTERM | `kubectl get pod POD -o jsonpath='{.metadata.finalizers}'` | Force delete is CHANGE and risks duplicate StatefulSet pods |
| HPA shows `<unknown>` | No requests set; metrics-server missing | `kubectl describe hpa HPA`; `kubectl top pod` | |
| Job never completes | `backoffLimit` hit; pod fails; deadline reached | `kubectl describe job J`; `logs` of the failed pods | |

---

## 3. Exit Codes and Last State

| Code / Reason | Meaning | Next |
| :--- | :--- | :--- |
| `OOMKilled`, exit 137 | Exceeded memory limit (137 = SIGKILL, also a probe/grace-period kill) | Compare `kubectl top` to the limit; check Reason field to tell OOM from kill |
| 143 | SIGTERM handled and exited | Normal during shutdown |
| 1, 2 | Application error | `logs --previous` |
| 126 / 127 | Command not executable / not found | Check `command`, `args`, image entrypoint |
| 139 | Segfault | Image/architecture mismatch or native crash |
| 255 | Exit status out of range, often runtime error | Logs |

- Restart count rising on a pod that runs for a fixed period before dying points at a liveness probe: look for "Liveness probe failed" and "Container ... failed liveness probe, will be restarted".
- Crash in under a second: config or entrypoint. Crash after minutes: leak, probe, or dependency.

---

## 4. Looking Inside a Running Pod (still live access)

On a shared cluster, ask the owner before using these.

```bash
kubectl exec POD -n NS -c C -- env | grep -v -i -E 'secret|token|key|pass'   # never print secrets
kubectl exec POD -n NS -c C -- cat /etc/resolv.conf
kubectl debug -it POD -n NS --image=busybox:1.36 --target=C -- sh              # ephemeral container, shares process namespace
kubectl debug POD -n NS --copy-to=POD-debug --container=C -- sh                # CHANGE: creates a copy pod
kubectl debug node/NODE -it --image=busybox:1.36                               # node-level; high privilege, ask first
```

- Ephemeral containers are the way to debug distroless and read-only images: they add a shell without altering the original container. They cannot be removed afterwards; the pod must be recreated.
- Never print Secret values into the conversation: show a key name or a length.
- `kubectl port-forward` is read-style access to a service; still state the target.

---

## 5. Rollout Commands

```bash
kubectl rollout status deploy/D -n NS --timeout=120s     # read-only
kubectl rollout history deploy/D -n NS                   # read-only
kubectl rollout history deploy/D -n NS --revision=N      # read-only
kubectl rollout undo deploy/D -n NS --to-revision=N      # CHANGE: roll back
kubectl rollout restart deploy/D -n NS                   # CHANGE
kubectl scale deploy/D -n NS --replicas=N                # CHANGE
```

- `rollout undo` reverts the pod template only, not ConfigMaps, Secrets, or data. If config changed in the same release, the undo may not restore a working state.
- Before proposing an undo, state what revision N contains and why it is safe.

---

## 6. Reporting Format

| Symptom | Evidence (one line) | Cause | Next command (read-only or CHANGE via gate) |
| :--- | :--- | :--- | :--- |

- Give one cause per row. Mark confirmed versus hypothesis.
- If a fix needs a CHANGE command, write it with its rollback and hand it to `shared-infra-changes`; do not run it.
