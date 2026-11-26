# Ecosystem Command Sheet

Inventory, upgrade, reproducible install, audit, licence, and provenance commands per ecosystem, plus update-bot configuration.

---

## 1. npm / pnpm (Node.js)

| Task | npm | pnpm |
| :--- | :--- | :--- |
| Outdated | `npm outdated` | `pnpm outdated -r` |
| Vulnerable | `npm audit --omit=dev` | `pnpm audit --prod` |
| Why is it installed | `npm explain <pkg>` | `pnpm why -r <pkg>` |
| Upgrade one | `npm install <pkg>@<version>` | `pnpm up <pkg>@<version>` (add `-r` for all workspaces) |
| Reproducible install | `npm ci` | `pnpm install --frozen-lockfile` |
| Licences | `npx license-checker --production --summary` | `pnpm licenses list --prod --json` |
| Registry signatures and provenance | `npm audit signatures` | `npm audit signatures` after an npm install of the same lockfile, or check the package page |
| Scripts a version would run | `npm view <pkg>@<version> scripts` | same |
| Unmaintained signal | `npm view <pkg> time.modified deprecated` | same |

- Install without lifecycle scripts when evaluating an unknown package: `npm ci --ignore-scripts`. pnpm 10 and later runs dependency build scripts only for packages allowlisted in `onlyBuiltDependencies`.
- Runtime: keep `.nvmrc` or `.node-version`, `engines.node` in `package.json`, the Dockerfile `FROM` line, and the CI `node-version` on one line. Set the `engines` floor to the oldest patch that has every API in use.
- Peer warnings after a major are findings, not noise: resolve them or record why not.

---

## 2. NuGet (.NET)

```bash
dotnet list package --outdated                         # add --include-transitive for the full tree
dotnet list package --vulnerable --include-transitive
dotnet list package --deprecated
dotnet nuget why <project.csproj> <package>            # which dependency pulls it in (recent SDKs)
dotnet add <project.csproj> package <package> --version <version>
dotnet restore --locked-mode                           # CI: fails if packages.lock.json would change
dotnet tool install --global nuget-license && nuget-license -i <solution.sln>
```

- Enable lockfiles once: `<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>` in `Directory.Build.props`; commit every `packages.lock.json`.
- Prefer central package management (`Directory.Packages.props`) so one line sets a version for all projects.
- Framework moves (`<TargetFramework>`) go one release at a time; pin the SDK in `global.json` and move it in the same change as the base image tag.
- Verify signatures on restore where policy requires: `dotnet nuget verify <package.nupkg>`.

---

## 3. pip / uv / Poetry (Python)

| Task | pip | uv | Poetry |
| :--- | :--- | :--- | :--- |
| Outdated | `pip list --outdated` | `uv tree --outdated --depth 1` | `poetry show --outdated` |
| Vulnerable | `pip-audit -r requirements.txt` | `uv run pip-audit` | `pip-audit` inside the environment |
| Upgrade one | edit the pin, `pip-compile --upgrade-package <pkg>` | `uv lock --upgrade-package <pkg>` | `poetry update <pkg>` or `poetry add <pkg>@^<major>` |
| Reproducible install | `pip install --require-hashes -r requirements.txt` | `uv sync --locked` | `poetry check --lock && poetry install` |
| Licences | `pip-licenses --format=json` | `uv run pip-licenses` | `pip-licenses` inside the environment |
| Why is it installed | `pipdeptree -r -p <pkg>` | `uv tree --invert --package <pkg>` | `poetry show --tree --why <pkg>` |

- Hash-pinned requirements (`pip-compile --generate-hashes`) turn a tampered artefact into an install failure.
- Interpreter: keep `requires-python`, `.python-version`, the image tag, and the CI matrix aligned; move one minor at a time and read the release notes of each minor for removals.
- Run the suite with deprecations as errors once after the upgrade: `python -W error::DeprecationWarning -m pytest`.

---

## 4. Docker Base Images

```bash
docker buildx imagetools inspect node:22-bookworm-slim --format '{{.Manifest.Digest}}'   # digest to pin
trivy image --severity HIGH,CRITICAL --ignore-unfixed <image>                            # before and after
docker history --no-trunc <image> | head -n 20                                           # what the new base adds
```

- Pin as `FROM <image>:<version>@sha256:<digest>`; the tag documents, the digest decides.
- Move the distribution and the runtime separately (`bookworm` to the next release is its own change): native modules and system libraries shift with it.
- Where a tag elsewhere names the version an image is built from (a compose file, a chart value), change it in the same commit; a stale tag runs the old image under a new name.

---

## 5. GitHub Actions

```bash
gh api repos/<owner>/<action>/git/ref/tags/<tag> --jq '.object.sha'      # SHA for a tag (annotated tags need one more hop)
grep -rnE 'uses: [^@]+@(v?[0-9]+|main|master)\s*$' .github/workflows     # actions still on mutable refs
actionlint                                                               # after editing
```

- Pin third-party actions as `uses: <owner>/<action>@<full-sha> # v4.2.2`; a tag can be moved, a SHA cannot.
- Read the release notes of an action major: the runner runtime and default inputs change between majors.

---

## 6. Update Bot (grouped and scheduled)

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: npm            # also: nuget, pip, uv, docker, github-actions
    directory: /
    schedule: { interval: weekly, day: monday }
    open-pull-requests-limit: 5
    cooldown: { default-days: 7 }     # skip releases younger than a week
    groups:
      dev-minor-patch:
        dependency-type: development
        update-types: [minor, patch]
      prod-patch:
        dependency-type: production
        update-types: [patch]
  - package-ecosystem: github-actions
    directory: /
    schedule: { interval: weekly }
    groups:
      actions: { patterns: ['*'] }
```

- Majors are never grouped: one pull request each, with the migration notes read.
- Security updates bypass the schedule and the release-age delay; everything else waits for the weekly batch.
- Auto-merge at most development-only patch groups with green CI; production dependencies get a human or reviewer pass.
