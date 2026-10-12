---
name: smoke-test
description: 'Builds and runs an API smoke suite that creates its own accounts and data through the API, runs the same cases locally before a pull request and against the deployed environment after every release from the exact commit, and ends in a PASSED, FAILED, or PARTIAL verdict with a bounded fix loop. Use when the user asks to smoke test an API, verify a release, add a smoke case, or runs /smoke-test. Triggers on: "smoke test", "verify the release", "works on staging", "post-deploy check", "/smoke-test". Do not use for browser journeys (use e2e-feature) or the test plan (use test-strategy).'
---

# API Smoke Test Procedure

This skill guides the agent through designing a layered API smoke suite that needs no database access, running it from the released commit against a local and a deployed target, and turning its verdict into either a verified release or a disciplined fix loop.

---

## 1. When to Use This Skill

Activate this skill when:
- A release reached an environment and someone is about to say "it is deployed and works".
- A change adds or alters an endpoint and must be proven through the real HTTP surface before a pull request.
- A smoke run failed and the failure must be classified and fixed without weakening the suite.
- The user runs the `/smoke-test` slash command.

*Boundary*: For journeys through a browser or mobile interface, use `e2e-feature`. For the overall test pyramid, use `test-strategy`. For request and response contract design, use `api-design`. For root-causing a hard failure, use `investigate`; for a production outage, use `incident-response`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Fix the Target and the Commit
1. Define the targets: `local` (the application started from this checkout against a throwaway database) and each deployed environment by base URL.
2. Run the suite from a checkout of exactly the commit the target was built from (a worktree is enough). A suite newer or older than the server judges it by the wrong routes and schemas.

### Step 2: Build the Four Layers
Consult: [Smoke Suite Design](./references/smoke-suite-design.md)
1. Layer 0, release identity: the health route answers 200 and names the commit it was built from, which must be the expected one.
2. Layer 1, every route unauthenticated: public routes answer, protected routes answer 401 or 403, nothing answers 5xx.
3. Layer 2, journeys: valid requests as made-up users, every answer validated against the endpoint's response schema.
4. Layer 3, after the run: no error-level log line and no new error-tracker issue caused by the run.

### Step 3: Write Cases That Own Their Data
1. A case creates its accounts and records through the API itself: sign up, sign in, create, read, change, remove. No SQL, no seed script, no fixture loaded into the database.
2. Tag everything created with the run's unique tag; remove or disable it in cleanup where an endpoint allows. A case must be safe to run twice and in parallel with another run.
3. A case never asks which target it runs on; differences live in the target definition.
4. Separate assertion from precondition: a wrong answer is a failure, a missing precondition is NOT RUN.

### Step 4: Enforce One Case per Endpoint
1. Each case declares the routes it covers; a static check compares that with the routes the API serves.
2. A route without a case needs a written excuse naming a real blocker ("charges a real card"). "Not written yet" is refused.
3. The check also refuses stale excuses, routes both covered and excused, and routes claimed by two cases.

### Step 5: Run and Read the Verdict
Consult: [Verdicts, Failure Report & Fix Loop](./references/verdicts-and-fix-loop.md)
1. Before a pull request that touches an endpoint, and again before a release from the release commit: run against `local`. Release nothing unless it PASSED; no flag skips it.
2. After every release: run against the deployed environment from the same commit.
3. Only `PASSED` means "it works". `PARTIAL` means something was not run: say what. `FAILED` enters the fix loop.

### Step 6: Run the Fix Loop
1. Find the failure by its request id in logs and traces; read what the endpoint is documented to do.
2. Name the kind: logic defect, configuration or secret, outside service or its mock, wrong case, missing data.
3. A logic defect gets a failing test first, then the fix, the gate, review, release, and the smoke run again.
4. After two fix rounds with a failure still open: stop and report with the evidence. Never weaken or delete a case to get green.

---

## 3. Verification Protocol

```bash
curl -fsS "$BASE_URL/health" | grep "$(git rev-parse HEAD)"        # layer 0: the server is this commit
git worktree add ../smoke-$SHA $SHA && cd ../smoke-$SHA            # run from the released commit
npm run smoke -- --target local;   echo "exit $?"                # or the project smoke entry point; before the pull request and the release
npm run smoke -- --target staging; echo "exit $?"                # 0 PASSED, 1 FAILED, 3 PARTIAL
npm run check:smoke-coverage                                       # every served route has a case or an excuse
```

| Layer | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| 0 | Health names an older commit | Release did not roll out; later layers test the wrong build | `[Blocker]` | Fix the rollout, rerun |
| 1 | Protected route answers 200 without credentials | Data exposed | `[Security]` | Add the guard and a test through the real route |
| 2 | Response has a field the schema forbids | Clients break or data leaks | `[Blocker]` | Fix the handler or the contract, test first |
| 2 | Staff journey NOT RUN: no credentials on this machine | Release unverified | `[Suggestion]` | Report PARTIAL; provide the account, rerun |

---

## 4. ⚡ Token-Saving Execution Rule

- **Verdict First**: Lead with `PASSED`, `FAILED`, or `PARTIAL` and the layer table; details only for failures and NOT RUN rows.
- **One Request Id per Failure**: Fetch the log lines of the failing request, never the environment's whole log.
- **Changed Module Only**: While fixing, rerun the one case file; run all layers once at the end.
