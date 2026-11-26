# Dockerfile Hardening & Health Probes

Multi-stage patterns, hardening checklist, runtime flags, and health probes for Node.js, .NET, and Python images.

---

## 1. Multi-Stage Pattern (Node.js)

```dockerfile
# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:22-bookworm-slim AS runtime
ENV NODE_ENV=production
WORKDIR /app
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/dist ./dist
COPY --from=build --chown=node:node /app/package.json ./
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["node", "dist/server.js"]
```

---

## 2. Stack-Specific Notes

| Stack | Build stage | Runtime stage | Notes |
| :--- | :--- | :--- | :--- |
| Node.js | `node:22-bookworm-slim`, `npm ci` | Same slim image or `gcr.io/distroless/nodejs22-debian12:nonroot` | Start with `node`, not `npm start` (npm does not forward signals reliably) |
| .NET | `mcr.microsoft.com/dotnet/sdk:9.0`; `dotnet restore` on `*.csproj` first, then `dotnet publish -c Release -o /app/publish --no-restore` | `mcr.microsoft.com/dotnet/aspnet:9.0` or the `-noble-chiseled` variant | `USER $APP_UID` (non-root user shipped since .NET 8); default port is 8080 via `ASPNETCORE_HTTP_PORTS` |
| Python | `python:3.12-slim`; `python -m venv /opt/venv`, `pip install --no-cache-dir -r requirements.txt` | `python:3.12-slim` with `COPY --from=build /opt/venv /opt/venv` | Set `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`, `PATH=/opt/venv/bin:$PATH`; create a user with `useradd --system` |

Cache mounts for dependency stores: `/root/.npm` (npm), `/root/.nuget/packages` (NuGet), `/root/.cache/pip` (pip).

---

## 3. Hardening Checklist

- [ ] **Base image pinned**: explicit version tag, ideally plus digest (`FROM node:22-bookworm-slim@sha256:<digest>`). Never `latest`.
- [ ] **Minimal runtime**: slim, distroless, or chiseled; no compilers, package managers' caches, or SDK in the final stage.
- [ ] **Non-root**: `USER` set to a non-zero UID in the final stage; files owned via `COPY --chown`.
- [ ] **No secrets in layers**: no `ARG`/`ENV` credentials (visible in `docker history --no-trunc`). Use `RUN --mount=type=secret,id=npmrc,target=/root/.npmrc npm ci` with `docker build --secret id=npmrc,src=$HOME/.npmrc .`.
- [ ] **`.dockerignore` present**: excludes `.git`, `node_modules`, `bin/`, `obj/`, `.env*`, test output, local caches.
- [ ] **Layer order**: lockfiles copied and dependencies installed before `COPY . .` so source edits do not invalidate the dependency layer.
- [ ] **Exec-form `CMD` / `ENTRYPOINT`**: JSON array so the application is PID 1 and receives `SIGTERM`. Shell form wraps it in `/bin/sh -c`.
- [ ] **OS packages**: `apt-get update && apt-get install -y --no-install-recommends <pkgs> && rm -rf /var/lib/apt/lists/*` in a single `RUN`.
- [ ] **`COPY` not `ADD`**: `ADD` auto-extracts archives and fetches URLs.
- [ ] **Health check**: `HEALTHCHECK` for plain Docker/Compose; orchestrator probes for Kubernetes (which ignores `HEALTHCHECK`).
- [ ] **Scanned**: `trivy image --severity HIGH,CRITICAL --exit-code 1 --ignore-unfixed <image>` gates the pipeline; `hadolint Dockerfile` lints it.
- [ ] **Labelled**: OCI labels `org.opencontainers.image.source` and `org.opencontainers.image.revision` set to repository URL and commit SHA.

---

## 4. Runtime Flags

```bash
docker run --rm \
  --read-only --tmpfs /tmp \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --memory=512m --cpus=1 --pids-limit=200 \
  --init \
  -p 3000:3000 --env-file .env app:ci
```

Kubernetes equivalent (container `securityContext`):

```yaml
securityContext:
  runAsNonRoot: true
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
```

---

## 5. Common Failures

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| Dependencies reinstall on every build | Source copied before install | Copy lockfiles first; add a cache mount |
| Container takes 10 s to stop | Shell-form `CMD` or `npm start` swallows `SIGTERM` | Exec-form `CMD`; handle `SIGTERM`; `--init` for zombie reaping |
| Image is 1 GB+ | SDK or dev dependencies in final stage | Multi-stage; `npm prune --omit=dev`; publish output only |
| Secret found by scanner in image | Passed via `ARG` or copied `.env` | Secret mount; rotate the leaked credential; fix `.dockerignore` |
| Health check always failing | Probe tool (`curl`) missing in slim image, or app bound to a different port | Probe with the runtime itself; align port with `EXPOSE` |

---

## 6. Health Probes & Shutdown

| Probe | Question | Must check | Must not check |
| :--- | :--- | :--- | :--- |
| Liveness (`/healthz`) | Is the process stuck? | Event loop / thread responds | Downstream dependencies (causes restart storms) |
| Readiness (`/readyz`) | Can it take traffic now? | Database, cache, required config loaded | Optional or degradable dependencies |
| Startup | Has it finished booting? | Migrations applied, warm-up done | Anything checked by liveness |

- [ ] On `SIGTERM`: fail readiness, stop accepting connections, finish in-flight requests, close pools, exit before `terminationGracePeriodSeconds` (default 30 s).
