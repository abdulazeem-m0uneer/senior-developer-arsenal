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
| 5 | One `gh` call did not answer within `--gh-timeout` (default 120 s) and was killed | The `gh` call that hung | Nothing is known about the checks. Check the network of this machine, `gh auth status` and the provider's status page, then run the script again; raise `--gh-timeout` only for a very large failed log |

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

---

## 7. Learning From a Red Run (`scripts/ci_learn.py`)

`python3 scripts/ci_learn.py <run-id> [--repo [HOST/]OWNER/NAME] [--ledger PATH] [--global] [--dry-run] [--json]` reads the run (`gh run view --json`) and the failed jobs' log (last 2 MB), then picks one class, first match wins:

| Class | Decided by | Lesson rule |
| :--- | :--- | :--- |
| superseded | run cancelled, or every failed job cancelled | Push once per run: wait for the running CI or cancel it on purpose |
| timeout (before superseded) | a cancelled job's `exceeded the maximum execution time`: GitHub reports a job stopped at its `timeout-minutes` as cancelled | Before pushing, run the shard locally under the CI time budget, or split the slow files |
| outside | an `OUTSIDE_CAUSES` phrase in a step that prints no test result (a test's own stderr, such as `Error: read ECONNRESET` or a diff line `"rate limit exceeded"`, belongs to the failing test); GitHub's own runner-lost and billing messages count in any step | none; the cause is printed |
| timeout | a job concluded `timed_out`, or the runner's own time limit in a step that shows no failing test: `ran past ... limit`, `exceeded the maximum execution time`, `The job running on runner ... has exceeded`, `##[error]... timed out after N minutes` (a step's `timeout-minutes`). Never a timeout a test printed: vitest's github-actions reporter repeats `Error: Request timed out after 5000ms` or `Test timed out in 5000ms` as an `##[error]` annotation, and `Timed out waiting for` is a server that never started; when the step also shows a failing test, the class is test | Before pushing, run the shard locally under the CI time budget, or split the slow files |
| coverage | a threshold message (`does not meet global threshold`, vitest's `does not meet "src/**" threshold`, `coverage ... below`, pytest-cov's `FAIL Required test coverage of N% not reached`, coverage.py's `Coverage failure: total of 85 is less than fail-under=90`), unless a test failed: jest prints its threshold after failing tests too. A threshold line is never a failing test, so a step whose only `FAIL` line is pytest-cov's is a coverage step | Run the changed-line coverage check before pushing |
| lint/type | the tools' own output, never a bare tool name (an install line or `Packages in scope` naming one is not lint): eslint `N problems (N errors`, tsc `error TS1234`, prettier `Code style issues found in`, ruff format and black `Would reformat: <path>` or `N files would be reformatted`, ruff `Found N errors.` or `path:1:2: F401 `, mypy `Found N errors in N files (checked` or `path.py:3: error: `, knip `Unused files (N)` (also `Unlisted`, `Unresolved`, `Duplicate` headings), golangci-lint `N issues:` or `path.go:1:2: ... (linter)` | Run lint and the type check on every touched workspace before pushing |
| test (`/snapshot`) | ` FAIL ` (also Go's `FAIL<tab>package`), `AssertionError`, `Snapshot ... mismatched`, `N failed` with N above 0, mocha `N failing`, `--- FAIL:`; sub-kind snapshot on vitest `Snapshot ... mismatched` or jest `N snapshot failed` / `toMatchSnapshot()` | Run the affected tests before pushing; a snapshot change needs its snapshot updated in the same commit |
| coverage | nothing above, and a failed job or step named coverage (a `Test with coverage` step that fails on an assertion is test) | Run the changed-line coverage check before pushing |
| unknown | nothing above | none |

- Colour codes are stripped, and the runner's echo of a step (`##[group]Run ...` up to `##[endgroup]`, holding only the cyan script lines, `shell:` and the indented `with:`/`env:` inputs) never decides the class: a script that prints a timeout message did not time out. A `Run ...` group holding any other line (a script's own `::group::Run unit tests` around its test output) is output and counts, and so is one still open when its step ends or the next group starts, since the runner always closes its own.
- When the 2 MB cut lands inside the runner's echo of a step, the echoed lines left before its `##[endgroup]` (cyan script lines, `shell:`, indented inputs) are dropped before classifying; anything else before the first group or step boundary is kept.
- A superseded run's log is read only to find a time-limit cancel; if it cannot be read, the run stays superseded and a note goes to stderr.
- Minutes wasted: every job's run time for superseded, else the jobs that failed, timed out or were cancelled; a job without both times counts 0.
- The lesson goes to the `lessons-learned` ledger through `lessons.py`'s own functions: an existing lesson with both tags (Active or Archive) counts a repeat, as `bump` does, else one is added. The lesson's Mistake ends in `; runs counted: <run ids>`, the newest that fit its 200 characters: a run already counted for it prints `<lesson id> already counted (xN)` (`--json`: action `counted`), writes nothing (ledger and events log alike) and exits 0, so a second run of the script on one run never counts a second repeat or escalates. A repeat that reaches the promotion threshold, or recurs past its guard, prints the `PROMOTE`, `GUARD FAILED` or `EXEMPT ... recurred` line and exits 3; a repeat with no guard and no exemption also prints lessons.py's `ESCALATE <id> x<hits>: ...` line on stderr. `--dry-run` prints that line after `dry run, nothing recorded:` and exits 0, since nothing was written. Exit 2 records nothing: an unreadable or unfinished run, a gh error or timeout, a usage error, or a ledger refusal (lock held, unparsable lines, global ledger inside the repository).
- The repository is `--repo [HOST/]OWNER/NAME` or the run URL's, on github.com or an Enterprise Server host; the tag uses NAME only, so both spellings share one lesson.
- Output: `<class>[/<sub-kind>] <minutes> min wasted, run <id> <branch>: <lesson id> <added|repeat xN|already counted (xN)>`, then `evidence: <first deciding line>` (200 characters at most).

Wait-loop hazards when writing shell around the script: never `pgrep -f` or `pkill -f` on the loop's own command line (it matches itself), and never `while ! gh pr checks` without a timeout.
