# Helm Conventions & Validation

Chart layout, values design, offline validation, and safe upgrade flags. Live `upgrade`, `rollback`, and `apply` run only through `shared-infra-changes`.

---

## 1. Chart Layout

```text
chart/
  Chart.yaml            # name, version (chart), appVersion (app)
  values.yaml           # every knob, each with a comment
  values.schema.json    # types and required keys; helm validates it
  templates/
    _helpers.tpl        # names and labels only
    deployment.yaml
    service.yaml
    NOTES.txt
  README.md             # how to set the important values
```

- `Chart.yaml` `version` changes whenever the chart changes; `appVersion` tracks the application release. Bump them independently, following semver.
- One template per resource kind. Name templates with a helper (`{{ include "chart.fullname" . }}`) so two releases never collide.
- Pin chart dependencies in `Chart.lock`; commit it.

---

## 2. values.yaml Design

- Few knobs, each documented in a comment. Expose what operators actually vary: image tag, replicas, resources, ingress host, env, existing secret name.
- Defaults must be safe: restricted securityContext on, requests set, PDB on, no `latest`.
- No logic-heavy templates: avoid nested `if`, `range`, and `tpl` chains that no reader can predict. If a template needs a paragraph of explanation, split the chart or use kustomize.
- Do not make every field a value; a chart with 200 values is a templating layer over YAML.
- Reference secrets by name (`existingSecret`); never carry secret values in `values.yaml` committed to git.
- Add `values.schema.json` with `required` and types so a bad value fails at lint time.
- Per-environment differences live in `values-<env>.yaml` files, not in template conditionals.

---

## 3. kustomize as an Alternative

| Prefer | When |
| :--- | :--- |
| Helm | Distributing a reusable package; many installs with different values; lifecycle hooks and release history needed |
| kustomize | One app, a few environments differing by patches; you want plain readable YAML with no template language |

- Layout: `base/` plus `overlays/<env>/kustomization.yaml` with `patches`, `images`, `replicas`, `configMapGenerator`.
- Use `images:` to set the tag per overlay instead of editing the base.
- Both can combine: `helm template` output as a kustomize base, patched per environment.

---

## 4. Offline Validation (no cluster)

```bash
helm lint ./chart --strict -f values-prod.yaml
helm template rel ./chart -f values-prod.yaml --namespace app > out.yaml
kubeconform -strict -summary -ignore-missing-schemas out.yaml
kustomize build overlays/prod | kubeconform -strict -summary -
```

- kubeconform (maintained successor to kubeval) checks manifests against the schemas for a Kubernetes version: pass `-kubernetes-version <x.y.z>` to match the target cluster. For CRDs, point `-schema-location` at a CRD schema catalog or generated schemas, or use `-ignore-missing-schemas` and say so in the report.
- Schema checks do not catch: wrong selector/label match, missing ConfigMap, bad port numbers, resource quota breach. Review those by reading.
- Render with the same `--namespace`, `--kube-version`, and `--api-versions` flags the real release uses, otherwise conditional templates take a different path.

---

## 5. Server-Side Validation (needs cluster access)

Use only against a cluster the user owns or has approved for read access; these still contact the API server.

```bash
kubectl apply --dry-run=server -f out.yaml     # runs admission and schema validation, persists nothing
kubectl diff -f out.yaml                       # server-side diff against live; exit 1 = differences
helm diff upgrade rel ./chart -f values-prod.yaml   # helm-diff plugin: rendered change vs release
```

- `--dry-run=client` only checks syntax locally; it misses admission webhooks, quota, and immutable-field errors. Prefer `server`.
- Read the diff for: selector changes, `replicas` reset against an HPA, removed resources (prune), changed PVC specs, and image changes you did not intend.
- A diff that touches resources the change does not own is a stop sign: report it, do not apply.

---

## 6. Install, Upgrade, Rollback (executed via shared-infra-changes)

| Command | Purpose |
| :--- | :--- |
| `helm upgrade --install rel ./chart --atomic --wait --timeout 5m` | Wait for readiness; roll back automatically on failure |
| `helm history rel` | List revisions and statuses |
| `helm rollback rel <revision> --wait` | Return to a prior revision; hooks and PVCs are not reverted |
| `helm get values rel` / `helm get manifest rel` | Read what is deployed (read-only) |

- `--atomic` implies `--wait`; the timeout must exceed the slowest pod's startup plus `minReadySeconds`.
- Helm does not roll back data, CRDs it did not own, or one-shot hook side effects. Write the rollback with that in mind.
- CRDs in a chart's `crds/` directory are installed once and never upgraded or deleted by Helm; manage CRD upgrades separately.
- Never `helm upgrade` a release you did not install; list ownership first with `helm list -A`.

---

## 7. Policy as Code (optional)

- Kyverno and OPA Gatekeeper enforce rules at admission (no `latest`, required labels, restricted securityContext). They are an extra gate; the checklist and offline validation stand on their own.
- Where the cluster already runs one, test manifests against its policies in CI (`kyverno apply`, `conftest`), and add new policies in audit mode before enforce.
- Do not add a policy engine to a shared cluster from this skill; that is a `shared-infra-changes` request.
