# Pipeline & Deployment Reference

GitHub Actions baseline, caching and secrets rules, deploy strategies, rollback, and 12-factor configuration.

---

## 1. GitHub Actions Baseline

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version-file: .nvmrc
          cache: npm
      - run: npm ci
      - run: npm run lint && npm test
  image:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-24.04
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

---

## 2. Pipeline Checklist

- [ ] **Least privilege**: top-level `permissions: contents: read`; add `packages: write`, `id-token: write`, `pull-requests: write` per job only.
- [ ] **Pinned actions**: third-party actions pinned to a full commit SHA (with the version in a comment); updates automated via Dependabot (`package-ecosystem: github-actions`).
- [ ] **Caching**: built-in `cache:` input of `actions/setup-node` (`npm`), `actions/setup-python` (`pip`), `actions/setup-dotnet` (`cache: true`, needs `packages.lock.json`); otherwise `actions/cache@v4` with `key: ${{ runner.os }}-deps-${{ hashFiles('**/package-lock.json') }}` and a `restore-keys` prefix.
- [ ] **Fail fast**: cheap jobs (lint, typecheck, unit) before expensive ones; `timeout-minutes` on every job; `needs:` to gate image build and deploy.
- [ ] **Build once, promote**: one image per commit SHA; environments differ by configuration only. Never rebuild per environment.
- [ ] **Deploy gating**: `environment: production` with required reviewers; deploy job has its own `concurrency` group with `cancel-in-progress: false`.
- [ ] **Debugging**: `gh run view <run-id> --log-failed`; `gh run rerun <run-id> --failed`; lint workflows locally with `actionlint`.

---

## 3. Secrets Handling

- [ ] Cloud access through OIDC: job `permissions: id-token: write` plus `aws-actions/configure-aws-credentials@v4` with `role-to-assume` and `aws-region` (or the Azure / GCP equivalent). No static cloud keys in secrets.
- [ ] Untrusted input (`github.event.pull_request.title`, branch names, issue bodies) is never expanded inside `run:`; assign it under `env:` and reference the shell variable.
- [ ] Avoid `pull_request_target` with a checkout of the pull request head; it runs fork code with access to secrets. Plain `pull_request` runs from forks receive no secrets, so design those jobs to need none.
- [ ] Runtime secrets come from the platform secret store (injected as environment variables or mounted files), not from the image or the repository.

---

## 4. Deploy Strategies

| Strategy | How it works | Rollback | Cost / caveat |
| :--- | :--- | :--- | :--- |
| Rolling | Replace instances in batches (`maxSurge`, `maxUnavailable`) | Roll back to previous revision; takes one rollout | Old and new versions serve together; both must be schema-compatible |
| Blue/green | Full new stack beside the old; switch the router at once | Switch the router back; near-instant | Double capacity during cutover; long-lived connections need draining |
| Canary | Route a small traffic share (1-5%) to the new version, widen on healthy metrics | Set canary weight to 0 | Needs traffic splitting and per-version metrics; define abort thresholds up front |

Rollback commands:

```bash
kubectl rollout status deployment/api --timeout=120s   # gate: fails if not ready in time
kubectl rollout undo deployment/api                    # previous revision
helm upgrade --install api ./chart --atomic --timeout 5m   # Helm 3: auto-rollback on failed upgrade
helm rollback api <revision>
```

- [ ] Database changes use expand/contract: add nullable column or new table, deploy code that writes both, backfill, switch reads, drop the old shape in a later release.
- [ ] Rollback trigger is numeric and automated where possible (5xx rate, p99 latency, readiness failures over a fixed window).

---

## 5. 12-Factor Configuration

- [ ] **Config in environment**: no per-environment files in the image; validate all variables at startup and exit non-zero on missing values.
- [ ] **Backing services as attached resources**: database, cache, and queue addressed by URL from config; swappable without code change.
- [ ] **Build, release, run separated**: immutable image plus config equals a release; releases are numbered and never mutated.
- [ ] **Stateless, disposable processes**: no local session or file state; self-contained server on a configured port, fast start, graceful stop.
- [ ] **Dev/prod parity**: same engine versions and the same image in every environment.
- [ ] **Logs as event streams**: structured JSON to stdout/stderr; the platform ships them. No log files inside the container.
- [ ] **Admin processes**: migrations and one-off tasks run as separate jobs from the same image and release.
