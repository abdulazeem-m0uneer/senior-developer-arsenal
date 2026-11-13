# Authority, Budget & End Report

The written grant, the scope matrix, budget arithmetic with the usage script, the limits a hook enforces, the wind-down sequence, the parking format, and the end report template.

---

## 1. The Authority Block

Written by the agent, confirmed by the user in one word before they leave, and kept at the top of the run notes.

```text
Run:        Week 2 items of docs/delivery-plan.md, in plan order
Window:     2025-03-04 18:00 to 2025-03-05 02:00 Europe/London
Budget:     one fifth of the weekly allowance; wind down at 85% of that share
Hard stop:  .claude/arsenal-run-limits.json: 600 tool calls, 480 minutes, deadline 02:00 (hook-enforced)
May merge:  pull requests into the default branch when review is clean, CI is green on the
            reviewed commit, and the application starts. Payment code included: yes
May release: staging only, through the release script, after its smoke test passes
Never:      production release, data deletion, history rewrite, branch rule changes,
            new paid resources, secret or access changes
Expires:    02:00 on 2025-03-05, or when the user is back, whichever is first
Granted by: the repository owner, 2025-03-04 17:52, "yes, go"
```

| Rule | Reason |
| :--- | :--- |
| The grant quotes the user's words and the time | Authority must be checkable after the run |
| Every line is explicit; a sensitive class (payments, auth, migrations) is in or out by name | "Do not stop" is not permission to merge, and the agent must not pick the wider reading |
| A refusal by the platform or a permission prompt is final | Retrying or routing around it is a bypass |
| The grant lapses on return | Yesterday's permission is not today's |
| Before a release, verify the branch rules are what the grant assumed; if not, report | The grant was given for a known set of safeguards |

---

## 2. Scope Matrix

| Action | Without a grant | With a merge grant | Always the user's |
| :--- | :---: | :---: | :---: |
| Branch, commit, push a feature branch, open a pull request | yes | yes | |
| Merge to the default branch on the three conditions | | yes | |
| Release to a pre-production environment | | only if named | |
| Release to production | | | yes |
| Drop data, force-push, delete branches others use, rewrite history | | | yes |
| Create paid resources or buy anything; edit branch rules, required checks, secrets, access | | | yes |
| Disable or skip a failing check to get a merge through | never | never | never |

---

## 3. Budget Arithmetic

The agent usually cannot read the allowance percentage itself, so it measures tokens and calibrates.

```bash
python scripts/usage_report.py --dir <transcripts-dir> --since-hour 14 --tz Europe/London
# since 2025-03-04T14:00:00+00:00 | files 41 | requests 1314 | ignored lines 0
# output 0.26M | fresh input 8.04M | cached reads 225.60M
```

| Flag | Meaning |
| :--- | :--- |
| `--dir` | Folder holding the session transcripts in JSON-lines form (`*.jsonl`, searched recursively) |
| `--since` | ISO 8601 cut-off; a time without an offset is read in `--tz`. The boundary is included |
| `--since-hour HH` | The latest `HH:00` in `--tz` that is not in the future: today, or yesterday before that hour |
| `--tz` | IANA zone name, default `UTC`. On systems without a zone database install the `tzdata` package |
| `--top N`, `--json` | Number of groups listed after the totals (a group is the first folder under `--dir`, ordered by output tokens); the same report as JSON |

The script reads `message.usage.input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, plus `message.id`, `requestId`, and `timestamp` from each line. Lines sharing a message id and request id count once. Malformed lines are skipped and counted as ignored. "Fresh input" is input plus cache writes.

Calibration, with one reading from the user:

1. Ask the user once for the allowance percentage shown by their plan and run the script at the same moment. Each measure divided by that percentage is one percent in requests, output, fresh input, and cached reads.
2. The day's share is the allowance divided by the working days (five days: 20%). The wind-down threshold is 85% of the share (17%).
3. Estimate the current percentage from whichever measure is highest, and say in the report that it is an estimate. Recalibrate on every new reading; one point is a rough fit.

Worked example: 5% used at 1,314 requests and 0.26M output gives 1% = 263 requests = 0.052M output. Share 20% = 5,260 requests; wind down at 17% = 4,470 requests or 0.88M output, whichever comes first.

---

## 4. What a Hook Enforces and What Stays a Rule

With the Claude Code plugin, `hooks/guard.py pre` runs before every tool call. Without the plugin (every other agent, or a manual install) nothing below is enforced and the whole skill is prose.

**Run limits.** The file is `.claude/arsenal-run-limits.json` in the project (found from `$CLAUDE_PROJECT_DIR`, else the working directory, upward), or the path in `$ARSENAL_RUN_LIMITS`.

```json
{"max_tool_calls": 600, "max_minutes": 480, "deadline": "2025-03-05T02:00:00+00:00"}
```

| Key | Counted | Reached when |
| :--- | :--- | :--- |
| `max_tool_calls` | Tool calls of this session made while the file exists (the hook also fires for calls inside subagents) | The count equals the limit |
| `max_minutes` | Wall-clock minutes since the first counted tool call of this session | That many minutes have passed |
| `deadline` | Nothing; an ISO 8601 time with a UTC offset (`Z` or `+02:00`) | The time has passed, in any session |

- Every key is optional. No file means no counting and no enforcement.
- At a limit the hook denies every tool call with the reason and the file path. A `Read`, `Write` or `Edit` of a `.md` file still passes, so the handoff and the end report can be written (Claude Code only edits or overwrites an existing file it has read in the session, so after a limit the agent can create a new `.md` or extend one it can read). The agent cannot delete the limits file: the operator removes it before the next session, since a tripped file or a past `deadline` denies every call in later sessions too. Parallel tool calls can overshoot `max_tool_calls` by the parallel width; the turn-end gates for tests and lessons stop asking.
- A file that is not a JSON object of these keys with positive numbers and a valid deadline counts as a reached limit, so a typo cannot lift the cap silently. While it is damaged, a `Read`, `Write` or `Edit` of the file itself is allowed.
- The counts live in the per-session guard state in the OS temp dir and survive compaction, and a resume that keeps the session id. A new session id starts a new count: only `deadline` spans sessions.
- `ARSENAL_GUARD=off` in the environment disables the hook. The limit is a brake for an agent that follows its instructions, not a sandbox: before a limit is reached the agent can still edit the file, so name it under "Never" in the authority block, and add a permission rule that denies edits to it if that matters.

**Destructive commands.** In the permission modes where no human approves each call (`bypassPermissions`, `dontAsk`, `auto`) the same hook denies the listed destructive shell commands; in the other modes it asks. The list and its blind spots are in `docs/TARGETS.md`, section Hooks.

**Not enforced by anything in this repository:**

| Part of the skill | Status |
| :--- | :--- |
| Token or cost budget, the allowance share, the 85% and 95% thresholds | Prose. `usage_report.py` measures tokens only when the agent runs it; hook input carries no cost and no cumulative usage, so the limits file has no cost key. For a hard cost cap on a headless run use the CLI's own `--max-budget-usd` |
| Reading the plan's allowance percentage | Not possible from here; the user reads it once for the calibration in section 3 |
| A timer, scheduler or runner that starts the run, wakes it or winds it down | Not shipped. The agent checks the clock and the usage itself before each item; only the hard stop above is mechanical |
| Authority scope, expiry on the user's return, merge conditions, the start-up proof, parking | Prose, checked by the user against the end report |

---

## 5. Wind-Down Sequence

| At | Do | Do not |
| :--- | :--- | :--- |
| 85% of the share, or 1 hour left | Start nothing new; finish review and merge of what is in flight | Open another review round on a clean pull request |
| 95%, or 20 minutes left | Leave unfinished work as an open pull request labelled with its state | Merge something half-reviewed to "finish" |
| End (reserve the last 5% for it) | Start-up proof, board update, end report | Skip the report because the budget is tight |

---

## 6. Parking a Blocked Item

```text
Parked:     2.4 Refund receipt text
Question:   Does the receipt show the payment fee as a separate line? (one line, one choice)
Recommend:  Yes, separate line; matches the invoice layout
Who:        product owner
Blocks:     2.4 only; 2.5 and 2.6 proceed
State:      branch feat/refund-receipt pushed, no pull request; nothing merged
```

- Write the question into the open-questions list (`decision-log`) and onto the task (`delivery-board-sync`), then move on.
- Do not build on a recommendation the run wrote for itself, unless the change is trivially reversible and labelled as such.

---

## 7. End Report Template

```markdown
## Run report: 2025-03-04 18:00 to 01:40 Europe/London

**Application starts:** yes at the start (commit 9a1b2c3), yes at the end (commit 4f1c2ab): server, worker, scheduler up, health 200, no errors in logs.

### Merged
| Item | Pull request | Commit | Review | CI on that commit |
| :--- | :--- | :--- | :--- | :--- |
| 2.3 Refund endpoint | #71 | 4f1c2ab | clean, 1 round of fixes | green, run link |

### Open, not merged
| Item | Pull request | State | Next action |
| :--- | :--- | :--- | :--- |
| 2.6 Export job | #73 | review found 2 issues, 1 fixed | fix the pagination bound, re-review |
| 2.5 Refund export | none | not started: wind-down threshold reached at 01:10 | first item of the next run |

### Parked
| Item | Question | Recommendation | Who answers |
| :--- | :--- | :--- | :--- |
| 2.4 Receipt text | Fee as a separate line? | Yes | product owner |

### Usage
Since 18:00: 4,120 requests, output 0.81M, fresh input 24.9M, cached reads 702M. Estimated 15.7% of the weekly allowance against a 20% share (estimate from one calibration point). Hard limits: not reached (or: tool-call limit reached at 01:32, report written after it).
```
