---
name: dependency-upgrade
description: 'Dependency and runtime upgrade runbook: inventory outdated and vulnerable packages, read the official migration guide at the exact versions, upgrade one dependency and one major at a time, keep installs reproducible, run the full suite plus a real start, and check licences and supply chain. Use when the user asks to upgrade a package, runtime or base image, or runs /dependency-upgrade. Triggers on: "upgrade dependency", "bump version", "update packages", "major upgrade", "/dependency-upgrade". Do not use for flaws in own code (use security-audit) or schema changes (use database-migration).'
---

# Safe Dependency Upgrade Procedure

This skill guides the agent through upgrading a dependency, runtime, or framework in small verified steps, with the official migration notes read at the exact versions and a rollback ready.

---

## 1. When to Use This Skill

Activate this skill when:
- Bumping a library, framework, language runtime, container base image, or CI action.
- Clearing a vulnerability advisory or a deprecation warning that comes from a dependency.
- Replacing an unmaintained or badly licensed package.
- Setting up or tuning an automated update bot.
- The user runs the `/dependency-upgrade` slash command.

*Boundary*: For vulnerabilities in the project's own code, use `security-audit`. For a regression found after an upgrade, use `investigate`. For pipeline and image design, use `devops-ci`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Inventory & Triage
Consult: [Upgrade Risk Triage](./references/risk-triage.md)
1. List what is outdated, vulnerable, deprecated, or unmaintained, and the licence of each candidate at its target version.
2. Record current and target version, direct or transitive, runtime or development only, and where the project touches its API.
3. Order the work: exploitable vulnerabilities in production paths first, then end-of-life runtimes, then majors, then the routine minor and patch groups.

### Step 2: Read the Official Notes at the Exact Versions
1. Read the changelog, release notes, and migration guide for every version between current and target, from the official source. Do not answer from memory: APIs differ between versions and recall is of an unknown one.
2. Extract breaking changes, new peer or runtime requirements, changed defaults, and deprecations; map each to the call sites it touches.
3. Check the runtime floor: the oldest runtime patch that has every API the code and the new version call. Update it in every file that names the runtime.

### Step 3: Change One Thing
Consult: [Ecosystem Command Sheet](./references/ecosystem-commands.md)
1. One dependency, or one coherent group that must move together (a framework and its plugins), per change. A bisect must be able to blame a single upgrade.
2. Step through majors one at a time, 2 to 3 to 4, getting green at each; skipping hides which major broke what.
3. Update through the package manager so manifest and lockfile change together; commit the lockfile; installs in CI use the frozen or locked mode.
4. Fix deprecation warnings introduced or surfaced by the upgrade in the same change; a warning left today is the breaking change of the next major.
5. Keep versions that are written twice in step: runtime version files, the image `FROM` line, CI setup, and any image tag that names what it is built from.

### Step 4: Check Licence & Supply Chain
1. Run the licence check against an allowlist; an unknown or missing licence is refused, and an exception is recorded per package with its reason.
2. Diff the lockfile for new transitive packages; question a large new tree for a small bump.
3. Inspect new or changed install scripts, the publisher, provenance or signature, and release age; reject look-alike names (typosquats).
4. Pin container images and CI actions to a digest or full commit SHA, with the readable version in a comment.

### Step 5: Prove It, Then Plan the Way Back
1. Clean install from the lockfile, then lint, typecheck, build, and the full test suite; never a partial run.
2. Start the application for real and exercise a request path: type checks and unit tests miss wiring and start-up failures.
3. State the rollback: revert the single commit and reinstall. If the upgrade migrated data or stored formats, say whether the old version still reads them.
4. Group and schedule bot updates (weekly minor and patch groups, majors individually, a release-age delay) so they are reviewed, not rubber-stamped.

---

## 3. Verification Protocol

```bash
git diff --stat HEAD                                         # only the intended manifest and lockfile moved
npm ci && npm audit --omit=dev && npm test                   # Node.js (pnpm: install --frozen-lockfile)
dotnet restore --locked-mode && dotnet list package --vulnerable --include-transitive && dotnet test
uv sync --locked && uv run pip-audit && uv run pytest        # Python (pip: --require-hashes -r requirements.txt)
<start command> & sleep 10 && curl -fsS http://localhost:<port>/healthz   # real start answers
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Lockfile | Manifest changed, lockfile not committed | Every install resolves different versions | `[Blocker]` | Regenerate with the package manager, commit both |
| Scope | Five unrelated majors in one change | Regression cannot be bisected or reverted alone | `[Architecture]` | Split into one change per dependency or group |
| Supply chain | New transitive package with a `postinstall` script | Arbitrary code at install time | `[Security]` | Read the script; allowlist or block it explicitly |
| Licence | Target version switched to a copyleft licence | Obligation on distributed code | `[Blocker]` | Stay on the last permissive version or replace |
| Hygiene | New deprecation warnings left in the output | Next major breaks | `[Suggestion]` | Migrate the call sites in this change |

---

## 4. ⚡ Token-Saving Execution Rule

- **Targeted Reading**: Read only the changelog sections between the two versions and search them for the APIs the project calls.
- **Diff, Not Dump**: Report the lockfile as a list of added, removed, and changed packages; never paste it.
- **First Failure Only**: After a failed run, quote the first failing test or error and fix that before reading further.
