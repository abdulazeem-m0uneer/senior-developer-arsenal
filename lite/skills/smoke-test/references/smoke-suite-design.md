# Smoke Suite Design

The four layers, the anatomy of a case, the rules for made-up data, and the static coverage check that makes "one case per endpoint" enforceable.

---

## 1. The Four Layers

| Layer | Question | Needs | Passes when |
| :---: | :--- | :--- | :--- |
| 0 Release identity | Is the server the commit we think it is? | Base URL | Health answers 200 and names the expected commit |
| 1 Every route, no credentials | Does routing, the auth guard, and the error shape hold everywhere? | The list of served routes | Public routes give their documented answer; every other route answers exactly 401 (or 403); nothing answers 5xx; every answer carries a request id; every refusal uses the one error body |
| 2 Journeys | Does each endpoint do what its contract says with valid input? | Accounts the suite creates itself, plus any pre-provisioned privileged account | Every call returns the expected status and a body that validates against the endpoint's response schema |
| 3 After the run | Did anything fail quietly? | Read access to logs and the error tracker | No error-level line since the run began, no new error-tracker issue; the log lines of each failed request are attached to its failure |

Layers 0 and 1 change nothing on the server and need no account, so they can always run. A layer that cannot run (no log access, no privileged account) is reported NOT RUN and makes the verdict PARTIAL; it never counts as passed.

Layer 1 details: replace path parameters with a value no record can have (a nil identifier), so nothing is read or changed; send the origin header a real client would; wait for the log pipeline to settle before layer 3 reads it.

---

## 2. Anatomy of a Case

One file per module. The engine sends the call and validates the answer; the case only says what to call and with what.

```javascript
export const module = 'orders';
export const covers = ['POST /v1/orders', 'GET /v1/orders/:id', 'DELETE /v1/orders/:id'];

export async function run(t) {
  const customer = t.state.customer;                       // created through the API by the auth case
  const order = await t.call('POST /v1/orders', {
    as: customer,
    body: { item: `smoke ${t.tag}`, quantity: 1 },         // VALID input, tagged with the run
  });
  const read = await t.call('GET /v1/orders/:id', { as: customer, params: { id: order.id } });
  t.check(read.quantity === 1, 'the order keeps its quantity');
  t.state.order = order;
}

export async function cleanup(t) {
  if (t.state.order) await t.call('DELETE /v1/orders/:id', { as: t.state.customer, params: { id: t.state.order.id } });
}
```

| Engine facility | Purpose |
| :--- | :--- |
| `t.call('<METHOD> <path>', { as, params, query, body })` | Sends the request, records the request id, validates status and body against the route's response schema |
| `t.tag` | Unique per run; goes into every name, email, and reference the case creates |
| `t.state` | Hands sessions and created records to later cases |
| `t.check(condition, message)` | An assertion about what the API answered: false is a failure |
| `t.need(condition, reason)` | A precondition: false marks the case NOT RUN with the reason |
| `t.secret(value)` | Marks a token, password, or one-time code so the report replaces it everywhere |
| `cleanup(t)` | Runs even after a failure; removes or disables what the case created |

The engine fails the run when a case calls a route it does not list in `covers`, or lists one it never calls, so the coverage check counts only routes really exercised.

---

## 3. Rules for Accounts and Data

| Rule | Reason |
| :--- | :--- |
| Everything is created through the API | The suite then proves sign-up, validation, and persistence, and needs no database access to any environment |
| No SQL, seed script, or fixture loaded into the database | Direct setup skips the code that real users hit and breaks on every schema change |
| Made-up identities use reserved ranges (documentation phone numbers, `example.org` addresses) | Nothing is ever sent to a real person |
| One-time codes are read from the mock sender's log line, never guessed or bypassed | No test-only back door ships in the application |
| A privileged account that cannot be self-created is provisioned once by an authorised person | The suite never creates privileged accounts on a shared environment |
| Credentials come from the environment or a file outside the repository, readable by the owner only | Never committed, never printed |
| Every record carries the run's tag and is safe to leave behind | Cleanup is best effort; a second run must not collide with the first |
| Local runs use their own throwaway database, dropped afterwards | A developer's working data is never touched |

---

## 4. The Coverage Check

A static check, part of the local gate and CI, with three inputs: the routes the API serves (from the router or the API specification), the `covers` lists of all cases, and an excuse file mapping a route to a reason.

| Problem it reports | Example |
| :--- | :--- |
| Served route with neither case nor excuse | `POST /v1/refunds: no smoke case and no reason` |
| Case covers a route the API does not serve | A renamed path left behind |
| Route claimed by two cases | Ownership unclear; one case must own it |
| Route both covered and excused | The excuse is stale: delete it |
| Excuse for a route no longer served | Stale entry |
| Excuse that names no real blocker | Under 30 characters, a placeholder (`TODO`, `later`), or "not written yet" |

```json
{
  "POST /v1/payments/capture": "Captures a real charge at the payment provider; no sandbox credential exists for this environment.",
  "POST /v1/admin/purge": "Irreversibly deletes tenant data and has no per-record scope to limit it to tagged rows."
}
```

An acceptable excuse states what would happen if the route were called and why that cannot be made safe. An endpoint is not done until it has its case or such an excuse. The decision function is pure (served set, cases, excuses in; problems out) and is unit-tested with planted bad inputs (see `quality-gate`).

---

## 5. Where the Suite Runs

| When | Target | Run from | Blocks |
| :--- | :--- | :--- | :--- |
| A change touches an endpoint | `local` | The working checkout | Offering the pull request |
| Before a release | `local` | A worktree of the release commit | The release; no flag skips it |
| After every release | The deployed environment | The same worktree | Calling the release verified |
| CI | Optional | The pull request commit | Merge, when run; the static coverage check always runs |

If CI minutes are scarce, keep the suite out of CI but keep the coverage check in, and make the release script run the suite itself.
