---
name: devops-ci
description: 'CI/CD and containerisation runbook: Dockerfile hardening and multi-stage builds, GitHub Actions pipelines, caching, secrets handling, deploy strategies (blue/green, canary), rollback, health checks, and 12-factor configuration. Use when the user asks to write or harden a Dockerfile, build or speed up a CI pipeline, plan a deployment or rollback, or fix a failing workflow. Triggers on: "Dockerfile", "GitHub Actions", "CI pipeline", "deploy strategy", "rollback", "/devops-ci". Do not use for version bumps and release notes (use git-release) or application latency profiling (use perf-audit).'
---

# DevOps, CI/CD & Containerisation Procedure

This skill guides the agent through building hardened container images, fast and least-privilege CI pipelines, and deployments that can be verified and rolled back.

---

## 1. When to Use This Skill

Activate this skill when:
- Writing or hardening a Dockerfile, or shrinking and securing an existing image.
- Creating, speeding up, or debugging a GitHub Actions workflow.
- Choosing a deploy strategy (rolling, blue/green, canary) or writing a rollback plan.
- Adding health checks, graceful shutdown, or environment-driven configuration.
- The user runs the `/devops-ci` slash command.

*Boundary*: For semantic version bumps, tags, and changelogs, use `git-release`. For slow queries or runtime latency inside the application, use `perf-audit`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Inventory the Delivery Path
1. Read the existing Dockerfile, `.dockerignore`, workflow files, and deployment manifests before proposing changes.
2. Record: runtime and version, build command, test command, exposed port, required environment variables, deploy target.
3. Identify what currently breaks the build/release/run separation (secrets baked into images, config files per environment in the image).

### Step 2: Build a Hardened Image
Consult: [Dockerfile Hardening & Health Probes](./references/dockerfile-hardening.md)
1. Multi-stage build: SDK/toolchain stage, minimal runtime stage containing only the published output.
2. Order layers for cache reuse: copy lockfiles, install dependencies, then copy source.
3. Run as a non-root user, use exec-form `CMD`, add a health check, pin the base image.
4. Pass build-time credentials with BuildKit secret mounts; never with `ARG` or `ENV`.

### Step 3: Design the Pipeline
Consult: [Pipeline & Deployment Reference](./references/pipeline-and-deploy.md)
1. Stages in order: lint and typecheck, unit tests, integration tests, build image, scan image, push, deploy.
2. Set top-level `permissions: contents: read` and widen per job only where needed.
3. Cache dependencies keyed on the lockfile hash; cache image layers with the `gha` cache backend.
4. Add `concurrency` to cancel superseded pull request runs and `timeout-minutes` on every job.
5. Build the image once, tag it with the commit SHA, and promote that same artifact through environments.

### Step 4: Secrets & Configuration
1. Prefer OIDC federation to the cloud provider over long-lived keys; scope remaining secrets to environments with required reviewers.
2. Never interpolate untrusted event fields into `run:` scripts; pass them through `env:`.
3. All configuration comes from environment variables validated at startup; the process fails fast on a missing value.

### Step 5: Deploy, Verify, Roll Back
1. Choose the strategy by blast radius and cost; define the automated promotion gate (error rate, latency, readiness).
2. Require readiness and liveness endpoints plus graceful `SIGTERM` handling before any zero-downtime strategy.
3. Schema changes follow expand/contract so the previous application version still runs after a rollback.
4. Write the rollback command and its trigger condition into the plan before the first deploy.

---

## 3. Verification Protocol

```bash
hadolint Dockerfile                                    # Dockerfile lint
docker build -t app:ci .                               # image builds from a clean context
docker run --rm app:ci id -u                           # must not print 0 (skip for shell-less images)
trivy image --severity HIGH,CRITICAL --exit-code 1 --ignore-unfixed app:ci
actionlint                                             # workflow syntax and expression check
```

Report findings in a compact table:

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Dockerfile | Runs as root, single stage with SDK | Larger attack surface, 1.2 GB image | `[Blocker]` | Multi-stage build, `USER` non-root |
| Workflow | `permissions` unset, actions on mutable tags | Token over-privilege, supply-chain risk | `[Security]` | `contents: read`, pin to commit SHA |

---

## 4. ⚡ Token-Saving Execution Rule

- **Surgical Diffs**: Output only the changed Dockerfile instructions or workflow keys, never whole unchanged files.
- **Logs**: When debugging a failed run, quote only the failing step and its first error lines.
- **Ranked Output**: Order recommendations by risk removed and minutes saved per pipeline run.
