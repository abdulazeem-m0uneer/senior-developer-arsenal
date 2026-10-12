# Outside Failures & Exit Code Playbook

How to tell a fault of the infrastructure from a fault of the change, what each exit code of `scripts/ci_wait.py` asks for, and how to extend the classifier.

---

## 1. Exit Codes

| Exit | Meaning | What was printed | Next action |
| :---: | :--- | :--- | :--- |
| 0 | Every check passed or was skipped | The tested commit and the merge command | Merge that commit and no other, if the merge is authorised |
| 1 | The change failed, or an outside failure survived the rerun cap | Failed checks, failed jobs and steps, last error lines | Fix the change, push, run the script again. After the cap: escalate the outside cause, do not keep rerunning |
| 2 | The pull request, its checks, or a run could not be read | The `gh` call that failed | Check the number, the repository, `gh auth status`, and the network of this machine |
| 3 | One CI run did not finish in the timeout, or no check ever reported | The timeout | See section 4 |
| 4 | Failed jobs ran zero steps, or the log names billing | The jobs that never started | Not the change. Report to the owner of the CI account; a rerun will not help |

---

## 2. Classification Table

A failed run is an **outside failure** only when every failed run's log matches at least one row. One failed run with no match makes the whole result a failure of the change: a real defect must never be hidden behind a flaky neighbour.

| Cause | Typical log text | Rerun helps | Durable fix |
| :--- | :--- | :---: | :--- |
| Registry rate limit | `429 Too Many Requests`, `toomanyrequests`, `rate limit exceeded` | Yes, after a delay | Authenticated pulls, a pull-through mirror, dependency cache keyed on the lockfile |
| Registry or upstream unavailable | `503 Service Unavailable`, `502 Bad Gateway`, `504 Gateway Timeout`, a token endpoint that returns EOF | Yes | Mirror or vendor the artefact; pin by digest so a cache hit is possible |
| Network | `TLS handshake timeout`, `i/o timeout`, `ECONNRESET`, `EAI_AGAIN`, `Could not resolve host`, `connection reset by peer` | Yes | Retry with backoff inside the step that downloads, not around the test step |
| Runner lost | `received a shutdown signal`, `lost communication with the server`, `hosted runner encountered an error` | Yes | Smaller jobs, `timeout-minutes`, memory limits; self-hosted runners need health checks |
| CI provider | `Failed to download action`, `Unable to download artifact`, `The service is unavailable` | Yes, often only later | Check the provider's status page before a second rerun |
| Billing | `account payments have failed`, `spending limit needs to be increased` | No | The account owner settles it; exit 4 |
| Never started | Job conclusion is failure with zero steps | No | Runner labels, runner availability, concurrency limits, billing; exit 4 |

**Not outside failures**, whatever they look like:

| Looks like | Why it belongs to the change |
| :--- | :--- |
| A test that times out waiting for the application | The application or the test is slow or deadlocked; the log names no registry, network, or provider fault |
| A test that passes on rerun with no outside phrase in the log | A flaky test is a defect of the test or of the code under it. Fix or quarantine it in its own reviewed change |
| A connection refused to a service the job itself starts | The job did not wait for readiness; fix the health check |
| Out of memory in the build or test step | The change or the job sizing; a rerun hides it until it returns |
| A lockfile or checksum mismatch | The change touched dependencies without regenerating the lockfile |

---

## 3. Rerun Policy

| Rule | Reason |
| :--- | :--- |
| Rerun failed jobs only (`gh run rerun <id> --failed`) | Passed jobs already proved their part; a full rerun doubles cost and exposure to the same outside fault |
| At most two reruns per wait | Three identical outside failures in a row is an outage or a misclassified defect; a person must look |
| Wait before a rerun (default 240 s) | Rate limits and short outages clear in minutes, not seconds |
| Never rerun exit 4 | Nothing ran, so nothing can pass |
| Never rerun a failure of the change "to see" | It converts a deterministic signal into a coin toss and trains the team to ignore red |

---

## 4. When No Check Finishes (Exit 3)

1. `gh pr view <pr> --json mergeable,mergeStateStatus`: `CONFLICTING` means the provider cannot build a merge commit, so no check starts. Rebase and push.
2. `gh pr checks <pr>` prints "no checks reported": the workflow's trigger does not match (branch filter, path filter, draft pull request, workflow file invalid). Run `actionlint` and read the `on:` block.
3. Checks are pending for the whole timeout: a job waits for a runner or for a required approval of an environment. Look at the run once in the browser or with `gh run view <id>`.
4. A required check comes from an outside service that never reported: ask its owner; do not remove the requirement.

---

## 5. Adding a New Outside Cause

1. Copy the exact phrase from the failed log; prefer the provider's own wording over a generic word such as "timeout", which also matches failing tests.
2. Add or extend a row of `OUTSIDE_CAUSES` in `scripts/ci_wait.py`: label, regular expression, and whether a rerun can help.
3. Add the phrase to the sample table of the script's unit test, plus one change failure that must still not match.
4. Ship it in the same change that met the failure, with the log line quoted in the description.

```python
("registry rate limit", r"429 Too Many Requests|toomanyrequests|rate limit exceeded", True),
#  label                 phrases as the provider prints them                           rerun helps
```

---

## 6. Merge Rules

- [ ] The merge was authorised for this change by someone entitled to do so; green CI alone is not authorisation.
- [ ] `gh pr merge <pr> --match-head-commit <sha>` with the commit the script printed. A push after the green run makes the command fail, which is the point.
- [ ] Review approvals apply to the same commit; a force-push after approval needs a fresh look.
- [ ] With a merge queue, the queue's own run on the merged result is the tested commit; wait for it the same way.
- [ ] Never merge with an admin override while a required check is red or missing.

Wait-loop hazards when writing shell around the script: never `pgrep -f` or `pkill -f` on the loop's own command line (it matches itself), and never `while ! gh pr checks` without a timeout.
