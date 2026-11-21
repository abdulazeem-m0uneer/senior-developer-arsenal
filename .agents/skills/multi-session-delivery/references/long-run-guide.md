# Running about ten agent sessions for a week

Field notes from one product built by one coordinator and about nine long-running agent lanes over several weeks. Every rule below is followed by the evidence that made it a rule. Every number comes from the project's own bus records, forge, lessons ledgers and timers, with its base and date range in [section 10](#10-numbers). Names of the product, people and services are removed.

---

## 1. Lane layout

Rules:
1. One **coordinator** owns the plan, the tracker, questions, reports and the rules file. It writes no product code.
2. **Build lanes** split by business domain, never by client: backend (core flows and releases), money-backend (payments, ledger), mobile (a second backend lane for the mobile flows), dashboard (web console), integration (an outside system). One backend lane owns migration order and releases.
3. **Support lanes** build nothing for the product: qa (verifies each release on staging), devops (CI, releases, machine health), risk (read-only checks of the coordinator's outward actions), quota-watcher (reads the usage quota and reports it).
4. Every session registers its id in [lanes.json](../templates/lanes.json) on each start and its name in the bus's `lanes.txt`. Names never change.
5. At most 4 story agents per lane, one agent per whole story, reviewers separate.

Evidence:
- The registry held 9 sessions plus the quota watcher, which reported on the bus without registering: 10 sessions in all.
- 10 inboxes carried 8029 lines in 16 active days over an 18-day span. The coordinator's inbox alone held about 1600 current lines plus about 2200 archived ones: the coordinator is the busiest reader, so keep its lines short.

---

## 2. The message bus

Rules:
1. Write to the receiver's inbox first with [send.sh](../templates/bus/send.sh), then send the live message. The file survives restarts; live messages do not.
2. Each start: [read.sh](../templates/bus/read.sh) `<me>`, act on each line, acknowledge. Archive weekly with [archive.sh](../templates/bus/archive.sh); never trim by hand.
3. One line per event:
   - `START <ticket> <what> - ETA <time>` before taking anything.
   - `BLOCKER <ticket> <exact cause> - <who acts> - ETA <time>` within 15 minutes of being stopped.
   - `DONE <ticket> <evidence>` with the merged commit, green run or check.
4. `send.sh` refuses a `START` or `BLOCKER` without a valid future ETA and a `DONE` without evidence (exit 6), a weekday that does not match its date (exit 4), and a later ETA without a cause (exit 7). Accepted lines go to `open-items.tsv`.
5. No secrets, tokens or personal data in any line. Every order the coordinator gives carries `by <time>`.

Evidence:
- `open-items.tsv` held 719 records from 9 senders in under 3 days: 341 START, 147 BLOCKER, 182 DONE, 49 CLEARED.
- Across all inboxes (16 active days over an 18-day span, wider than the record file), 347 lines began with START, 159 with BLOCKER and 186 with DONE.
- About 2 START lines per DONE: most items are re-dated or re-started at least once, so the record file, not memory, is the truth about what is open.

---

## 3. ETAs and ETA quality

Rules:
1. An ETA covers the whole path to done: build, tests, review, CI, merge, release, verification on staging.
2. Before promising, ask [overdue.py](../templates/bus/overdue.py) `--suggest <lane> --estimate <duration>`. It adds the lane's **median lateness over all its finished items** (early or on time counts 0) to the estimate. Promise the time it prints.
3. A re-date (an ETA later than the one before) must say why: `because <cause>` or `cause: <cause>`, at least 3 words. A `BLOCKER` already names its cause.
4. Hourly, the coordinator runs `overdue.py --health`, then `overdue.py`, then `--waiting`, and chases each `OVERDUE` owner for a new line within 15 minutes. `ESCALATE` (re-dated twice, or 4 hours past the first ETA) goes to the risk lane and the lead.
5. Daily, `overdue.py --accuracy`. A lane under 80% on its first ETA adds its median lateness and records each miss as a lesson tagged `eta`.

Evidence (`--accuracy` over 161 finished items; lane names are generic labels):

| Lane | Finished | On first ETA | Median late, late items only | Re-dates |
| :--- | ---: | :--- | ---: | ---: |
| backend | 19 | 5 (26%) | 195 min | 15 |
| devops | 26 | 16 (62%) | 32 min | 13 |
| integration | 11 | 9 (82%) | 74 min | 4 |
| dashboard | 17 | 17 (100%) | 0 min | 0 |
| mobile | 8 | 4 (50%) | 998 min | 15 |
| money-backend | 27 | 10 (37%) | 1609 min | 52 |
| coordinator | 28 | 22 (79%) | 50 min | 5 |
| qa | 25 | 22 (88%) | 20 min | 10 |

- In all, 105 of 161 (65%) finished by their first ETA, with 114 re-dates.
- The three backend lanes, which share the merge queue and the migration order, had the lowest on-time rates (26% to 50%). The lanes that verify releases or build screens against a published contract were at 82% to 100%.
- The median over late items only is the wrong number to add: it is large even for a lane that is rarely late (integration: 2 late items, 74 min). The suggestion uses the median over all finished items. With a 1 h estimate it added 83 min for backend and 187 min for money-backend, and 0 min for the other six lanes, because at least half of their items were on time.
- 77 of 347 inbox START lines carried a stated cause. A re-date without one leaves the coordinator unable to tell a slow lane from a blocked one.

---

## 4. Merge slots and the merge queue

Rules:
1. Merge only through [merge_green.py](../scripts/merge_green.py): dry run unless `--yes`, the full head SHA pinned, required checks named with `--expect`, an independent review on that exact head. Keep branch protection on as well.
2. When the base must be up to date, take a turn with [merge_slot.py](../scripts/merge_slot.py): `refused <pr> --lane L` after a merge refused for being behind; `may-update <pr>` before updating (exit 0: you hold the slot, update, wait for CI, merge, `release <pr>`; exit 1: wait). A grant is a 10-minute claim window, then a 40-minute lease.
3. Pull requests that add a migration also queue in one ordered list owned by the coordinator. A lane may append its own; it never reorders others.

Evidence:
- The backend repo merged 81 pull requests in 7 days with a median open-to-merge of 18.3 h; the dashboard repo merged 54 with a median of 19 min. The backend's longer median is the merge queue: migrations, reviews and up-to-date rebases waited in line.
- A snapshot of the backend slot file held one holder, an empty queue, 5 pull requests with one refusal each and 2 leases that expired unclaimed.

---

## 5. Quota stop

Rules:
1. One quota-watcher session reads the weekly usage at fixed times, writes it with [reading.py](../scripts/reading.py) `write FILE --key K --value V`, and sends one bus line with the percentage, the burn rate and the projected time of the threshold.
2. At the threshold (90% weekly here) the coordinator stops the whole team. No lane decides alone.
3. Every quote of the quota carries its age: `reading.py get FILE --key K --max-age 30m`. `STALE` (exit 1) is refreshed at the source or reported as stale with its age; never quoted as current.
4. Before any report or email, `reading.py check-report DRAFT` must exit 0.

Evidence:
- The watcher sent 85 lines in 2 days. On one day usage rose from 32% to 68% in about 13.5 h (about 2.7%/h that day); the watcher's running rate since its first reading was 1.7%/h. Its projection of the threshold moved from about 2 days ahead in the morning to 12 to 18 h ahead in the evening: a running average lags a fast day, so read the latest span too.
- The case behind rule 3: a watcher that stops leaves a file with an old percentage while real usage keeps rising. Only the age tells them apart.

---

## 6. Workday and nightly stop

Rules:
1. The workday is N hours from when the sessions start (8 here). The coordinator writes the start into a small state file; watches skip outside it. In the last hour no lane starts a new build chain; 15 minutes before the end each lane sends its state and stops.
2. Fixed-time work runs from system timers made with [timer.py](../scripts/timer.py): a validated `OnCalendar`, a oneshot bounded by `TimeoutStartSec`, a deadline margin. Read the next run with `timer.py check` before promising a time. Pause with `pause`, never by stopping the timer. Details in [routines.md](./routines.md).
3. Extra workdays are approved, not assumed: one line per date in a workdays file outside the repository, `YYYY-MM-DD approved-by <who>: <reason>`. The arsenal's calendar hook guard (`hooks/guard_lessons.py`, its `exceptions` key) lets a promise on a listed date pass and refuses one on any other non-workday.

Evidence:
- 26 durable timers ran the project's routines: day start and end, hourly watch, reconcile, reports, staging watch, nightly smoke and end-to-end runs, disk and memory watches, crash guard, worktree prune.
- 2 workday exceptions were approved in the week measured, each on or before its day.
- Alarms set as sleeps inside a session died with the session and the report never went out. That failure came back often enough to become a promoted rule (section 9).

---

## 7. Restarts and resume

Rules:
1. Keep one **live state file** per lane: open pull requests with their heads, running agents, what each waits on, the next step. Update it at every merge, launch and stop. After a restart, read it first and resume the named agents; do not rediscover.
2. On start a lane reads its rules file, the operating model, its inbox and its row in `lanes.json`, in that order.
3. When the skills plugin is upgraded mid-run, **repoint** instead of restarting: `arsenal repoint` (`scripts/repoint.py` at the repository root) turns each older installed version folder into a link to the newest, so running sessions run the new hooks from their next call. Old folders are kept beside the link for `--undo`.

Evidence:
- 28 older plugin versions were repointed to the newest in 9 runs within about 11 hours, while every session kept running.
- A machine crash guard and a watcher timer restart the editor and resume the sessions; the live state file is what makes the resume cheap.

---

## 8. Idle detection

Rules:
1. On every watch tick the coordinator checks load, memory, disk and each lane's last bus line. A lane with free agent slots and no open item gets the highest open ticket in its modules, or is told to take it.
2. `overdue.py --waiting` lists each `BLOCKER` whose acting session has no open item for it. That session is idle on someone else's work: order it to send a `START` with an ETA.
3. Never wait on something that will not fix itself; never wait on bus text. Wait on the authoritative state (`gh pr view N --json state`, the release log), a recorded pid or a lock file.

Evidence:
- 91 `WAITING` lines went out in the last 4 days: each was a lane blocked on a lane that had not committed to unblock it.
- 150 bus lines named an idle lane or idle slots, 78 of them from the coordinator. This counts mentions, not idle hours (section 10).

---

## 9. What went wrong and the guard each failure got

A mistake seen twice becomes a test, a lint rule, a hook or a script refusal (the `lessons-learned` skill, `lessons.py`). Seen counts are from the ledgers.

| Failure | Seen | Guard |
| :--- | ---: | :--- |
| Waited on a process with `pgrep -f`; the wait never ended | 17 | Hook refuses `while/until pgrep -f`; wait on a recorded pid, a lock or a notice |
| Named a cause or called a test flaky without reading the failing assertion | 15 | Rule: cite file:line or a trace line, or say "unknown" |
| Ran a local helper with `--help`; it ran for real | 11 | Hook refuses `--help`/`-h` on local scripts; read the header |
| Alarms as in-session sleeps; bad `OnCalendar`; a restarted timer fired a missed run | 8 | [timer.py](../scripts/timer.py) `make`, `check`, `pause` |
| Pattern kill hit another session's process | 7 | Rule: kill only pids you recorded. The arsenal ships no hook for it: enforce it with a project-local hook or an entry you add to the lesson-guards registry |
| Judged a check through a pipe; the pipe returned the last command's status | 5 | Hook refuses the pattern; redirect to a file and read `rc` |
| Secret value written in a bus line | 5 | Hook refuses secret-looking values in the arguments of registered programs (the bus send script) |
| Reported commit hashes that did not exist | 4 | Every hash in a report is copied from git output of the same turn; `reading.py check-report` flags a claim sentence (merged, fixed, green, released, ...) with no `(source: ...)` or `(live: ...)` marker as `NO-SOURCE`; a hash written alone is not a source |
| QA criteria taken from a brief instead of the merged code | 4 | Criteria cite the code or guide line at the release under test |
| Waited on bus text; it matched a line that only quoted the phrase | 3 | Wait on `gh pr view` state or the release log |
| Skipped git hooks to get a commit through | 3 | Hook refuses `--no-verify`, `commit -n`, `core.hooksPath`, `HUSKY=0` |
| A started or blocked item with no time | many | `send.sh` exit 6 |
| A re-date with no cause | 114 re-dates | `send.sh` exit 7 |
| A quota quoted from a file a stopped watcher left | 1 week | `reading.py get --max-age`, `check-report` |
| Two lanes updated the same branch for an up-to-date merge | repeated | `merge_slot.py` |

Measured effect: the guards fired 53 times in 7 days (0, 0, 4, 3, 11, 16, 19 per day). Each fire is a command refused before it ran. Guards were added during the same week, so the data does not separate more guards from more mistakes.

---

## 10. Numbers

All read on the last day of the range. Bus records and inboxes are local files; pull request numbers are from the forge, read-only.

| Measure | Value | Base (n) | Date range | How measured |
| :--- | :--- | :--- | :--- | :--- |
| Sessions | 10 (9 registered + quota watcher) | registry rows, inbox files | at end of range | `lanes.json` keys; inbox files |
| Bus lines, all inboxes | 8029 | 10 inboxes + 1 archive | 16 active days over an 18-day span | count of lines starting with a timestamp |
| START / BLOCKER / DONE, inboxes | 347 / 159 / 186 | 8029 lines | 16 active days over an 18-day span | first word after the sender field |
| Records in `open-items.tsv` | 719: 341 START, 147 BLOCKER, 182 DONE, 49 CLEARED | 9 senders | about 2.7 days at the end of week 3 | first word of the line field |
| Finished items | 161 | 8 lanes | same 2.7 days | `overdue.py --accuracy` |
| On first ETA | 105 of 161 (65%); per lane 26% to 100% | 161 finished items | same | `overdue.py --accuracy` |
| Re-dates of finished items | 114 | 161 finished items | same | `overdue.py --accuracy` |
| Median lateness added by `--suggest` | 83 min backend, 187 min money-backend, 0 min six others | 8 to 28 finished per lane | same | `overdue.py --suggest <lane> --estimate 1h` |
| Open items at read time | 58 open lines plus 3 OVERDUE lines (12 marked ESCALATE) | one `--all` read; the file grows, a later read differs | at end of range | `overdue.py --all` |
| START lines with a stated cause | 77 | 347 START lines | 16 active days over an 18-day span | lines containing `because` or `cause:` |
| OVERDUE chases sent | 209 | bus lines | last 3 days | lines beginning `OVERDUE` |
| WAITING orders sent | 91 | bus lines | last 4 days | lines beginning `WAITING` |
| Backend repo merges | 81, 11.6 per day; median open-to-merge 18.3 h | 81 PRs | last 7 days | `gh pr list --state merged --limit 500 --json number,mergedAt,createdAt` |
| Dashboard repo merges | 54, 7.7 per day; median 19 min | 54 PRs | last 7 days | same |
| Docs repo merges | 1, 0.1 per day; median 1 min | 1 PR | last 7 days | same |
| Merge slot snapshot | 1 holder, 0 queued, 5 PRs with 1 refusal, 2 leases expired | backend slot file | one read at end of range | `merge_slot.py` state file |
| Quota watcher lines | 85; one day 32% to 68% in about 13.5 h (about 2.7%/h); running rate since first reading 1.7%/h | 85 lines | 2 days in week 2 | lines from the watcher in the coordinator's inbox |
| Lessons, project ledgers | 295, 84 repeats, 24 guarded | 3 ledgers | all time | `lessons.py metrics --bus` |
| Lessons, global ledger | 79, 210 repeats, 8 guarded | 1 ledger | all time | `lessons.py metrics` |
| Lessons added / repeated | 117 / 33 | 4 ledgers | last 7 days | `lessons.py metrics`, per-day columns |
| Guard fires | 53 | all projects on the machine | last 7 days | `lessons.py metrics` |
| Durable timers | 26 project timers (28 on the host) | user timers | at end of range | `systemctl --user list-timers --no-legend` |
| Workday exceptions | 2 | approved lines | last 2 days | lines in the workdays file |
| Plugin repoints | 28 versions, 9 runs | version folders | about 11 hours | link targets and backup stamps in the plugin cache |
| Idle mentions | 150 lines (78 from the coordinator) | 8029 lines | 16 active days over an 18-day span | lines containing the word idle |

Repeats in the lesson rows are hits above 1 summed per lesson. A global lesson collects hits from every project, so the project and global ledgers are not comparable per lesson.

Not measured:
- **Idle hours per lane**: the bus records events, not gaps; no session logged when it went idle or came back. Lines naming idle are given instead.
- **Restarts and resume time**: no restart log with start and end times exists; the live state files are overwritten, not appended.
- **Send refusals (exit 4, 6, 7)**: the bus measured had no send-event log, so `overdue.py --health` could not count refusals.
- **Quota stops**: no event records the moment the team stopped for the quota; only the watcher's last reading before a stop is on the bus.
- **ETA accuracy before the record file**: `open-items.tsv` starts in week 3, so `--accuracy` covers under 3 days, not the whole run.
