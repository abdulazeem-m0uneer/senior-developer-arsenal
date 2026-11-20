---
name: multi-session-delivery
description: 'Coordinator plus build lanes for several long-running agent sessions on one product. Use for multi-repo or multi-session delivery.'
---
<!-- routing (read by the skill router, not loaded into the skill listing): Operating model for several long-running agent sessions on one product: a coordinator that writes no code plus build lanes and a message bus. Use for two or more apps or repos, or work too big for one session. Triggers: "PM session", "coordinator session", "lanes", "session bus", /multi-session-delivery. Not for collisions in one checkout (use parallel-sessions) or one unattended run (use autonomous-run). -->

# Multi-Session Delivery Procedure

This skill sets up and runs a team of long-running agent sessions that deliver one product together: a coordinator that keeps the plan, the tracker and the people informed, and build lanes that only build. Every lane knows what it owns, what it never touches, what to take next, and how to tell the others in one line.

---

## 1. When to Use This Skill

Activate this skill when:
- The product has two or more deliverable apps or repositories (an API plus a web console, a mobile app, a public site).
- One backend has more ready stories than one session can run, and its modules can be split by business domain.
- The lead is away for hours and wants delivery to continue with every status visible in the tracker.
- Sessions duplicate work, wait on each other, or lose instructions between restarts.
- The user runs the `/multi-session-delivery` slash command.

*Boundary*: For worktrees, staging by path and numbers taken at commit time inside one repository, use `parallel-sessions`. For one unattended run with a written authority and a token budget, use `autonomous-run` (its merge bar is stricter: no open finding at all; this model lets Medium and Low findings merge as follow-up tickets so lanes keep moving). For keeping the board in step with the plan, use `delivery-board-sync`; for recording decisions, `decision-log`; for the mistake ledger, `lessons-learned`; for waiting on CI, `ci-wait`.

Offer this model, do not impose it: present the lane table from Step 1 and ask the user to accept or change it before writing any file.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Define the Sessions
Consult: [Operating Model Template](./templates/OPERATING-MODEL.md)
1. One **coordinator** (PM) at the workspace root. It owns the plan and progress, the tracker, questions and answers, the gap and health watches, the rules file, every email and report, and relaying the lead's instructions. It writes no product code, opens no pull requests and makes no releases.
2. One **build lane** per deliverable (backend, web, mobile). Each row names the session, the repository and modules it owns, and what it never touches. Names are fixed for the life of the project; scripts and inboxes depend on them.
3. Split a large backend **by business domain, never by client**: each lane builds the endpoints of all clients for its domain. Exactly one backend lane owns the migration order, shared sequence numbers and releases; the others ask it.
4. All sessions run in the same permission mode and register their session id in [lanes.json](./templates/lanes.json) on every start, so the coordinator can read their progress. The same lowercase names go in the bus's `lanes.txt`.

### Step 2: One Priority Queue, Pulled Not Pushed
1. The tracker's queue is ordered by the coordinator: (1) urgent tickets and tickets raised by the client teams that consume the API, (2) features those clients wait on, (3) the current plan week, hardest and riskiest story first.
2. A lane with a free agent slot takes the highest open ticket in its own modules and sends `START <ticket> <what> - ETA <time>`. It does not wait to be assigned.
3. "In progress" on the board means exactly the live work. The coordinator reconciles the board with the lanes' events on a timer.

### Step 3: Build Flow Inside a Lane
1. **Contract first**: the API lane publishes the request and response schema in the shared contract package, then builds. Client lanes build against the published contract at once; a missing contract is asked for, never replaced by a stand-in API.
2. **One agent per whole story** (all endpoints and screens the flow needs), at most 4 story agents per lane, in different modules. No nested builders. Reviewers are separate agents.
3. **Done** means: merged with an independent review that found no Blocker or High (each Medium and Low becomes a follow-up ticket), CI green on the reviewed head, released, and verified on staging against the real API, which also proves the application starts. A ticket that serves stand-in data is not done.
4. While building run only the affected tests; run the full gate before pushing so no CI run is wasted.

### Step 4: Messages Between Sessions
Consult: [Session Bus](./templates/bus/README.md)
1. Every message is written to the receiver's inbox on the file bus first (`send.sh <to> <from> "<line>"`), then sent as a live message. The bus survives restarts; live messages do not.
2. On every start a session reads its inbox (`read.sh <me>`) before any work, acts on each line, then acknowledges (`read.sh <me> --ack <line>`, printed by the read); unacknowledged lines are shown again. Once a week the coordinator runs `archive.sh`, which moves old lines that were already acknowledged and shifts the read mark under the bus lock; never trim an inbox by hand.
3. Lane to coordinator, one line per event: `START <ticket> <what> - ETA <time>`, `BLOCKER <ticket> <exact cause> - <who acts> - ETA <time>`, `DONE <ticket> <evidence>`, and `paused|merged|released|deployed|verified <ticket> <evidence>`. `verified` names the release it was checked on.
4. **ETA on everything.** Before taking any item a session sends `START` with the time it will be done; within 15 minutes of anything that stops it (red CI, a refused merge, a conflict, data missing from another session, a broken tool) it sends `BLOCKER` naming the exact cause, who must act and when it will be solved; when finished it sends `DONE` with the merged commit, green run or check that proves it. A new time is a new `START` stating the cause; a later ETA than the one before counts as a re-date. An ETA covers the whole path to done (build, tests, review, CI, merge, release, verification), adds the session's median lateness from `overdue.py --accuracy`, and is promised only after checking the date with `date` and what the item waits on with `overdue.py --all`. `send.sh` refuses a `START` or `BLOCKER` without a valid future ETA and a `DONE` without key and evidence (exit 6), refuses the old words `started` and `blocked` that would skip the ETA, and refuses a weekday that does not match its date (exit 4). Accepted lines are recorded in `open-items.tsv` for `overdue.py`. `overdue.py` reads the full ETA form and the short ones (`MM-DD HH:MM`, `HH:MM`) against each record's send time, and counts the ETAs it cannot read. Every order the coordinator gives carries a `by <time>`.
5. Questions: `Q: <question> | type: business or lead | context | blocks | working rule meanwhile`. Only the coordinator files question tickets and relays answers. Technical questions a lane can settle by best practice are decided and recorded there, never asked.
6. Lane to lane (two backend lanes): ask the owner lane for a migration slot and wait; announce any change to a shared file with the reason; one owner per story, handovers one way at a time; on a collision both lanes pause, tell the coordinator, and the owner lane decides (the lead decides if they disagree).
7. No secrets, tokens or personal data in any line.

### Step 5: Coordinator Duties
1. Keep the board true: status changes only with evidence, every page of every listing read, bulk changes through the tracker's API in one script, not one call per task.
2. File every `Q:` line as a ticket (business owner or lead), watch the answered column, record each answer in the decision log, relay it to the lane.
3. Watch for gaps (legacy or reference system, plan versus delivered) and for staging alerts; a serious alert becomes an urgent ticket and an urgent line to the owning lane, handled before any other work.
4. **Nothing stays unsolved unseen**: every hour run `python3 .agents/bus/overdue.py --health` first (exit 1 means a line went out unchecked or untracked, a record is damaged or an open item's ETA is unreadable: fix that before trusting the lists), then `python3 .agents/bus/overdue.py` and, for each `OVERDUE` line, order its owner to answer within 15 minutes with a new `START` or `BLOCKER` (a new ETA) or a `DONE` with evidence; raise each `ESCALATE` line (re-dated twice, or 4 hours past its first promised ETA) to the risk lane and the lead. `overdue.py --waiting` lists each `BLOCKER` whose acting session has taken nothing for it: order that session to send a `START` with an ETA. Each day run `overdue.py --accuracy`: tell a session under 80% on its first promised ETA to add its median lateness to its next estimates and to record each miss as a lesson (tag `eta`). For one report of ETA accuracy beside each lane's lessons (added and repeated per day, unguarded repeats), run `lessons.py metrics --bus .agents/bus` from `lessons-learned`; tag lane lessons `session:<lane>`.
5. Send the reports the lead asked for (progress, plan, end of day, mistakes) with evidence and the list of decisions waiting on the lead.

### Step 6: Workday and Routines
Consult: [Routines & Timers](./references/routines.md)
1. The workday is N hours from the moment the sessions start; the coordinator announces start and end on the bus. In the last hour no lane starts a new build chain; 15 minutes before the end each lane sends its state and stops.
2. Fixed-time work runs from system timers, not from sleeps inside a session: a session that closes kills its own alarms silently.
3. Routines that read untrusted text (tickets, comments, emails) run with read-only shims for git, the forge CLI and the merge script first on `PATH`, and end with one status word: `ok`, `partial` or `failed`.

### Step 7: Guards Against Repeated Mistakes
1. Merge only through [merge_green.py](./scripts/merge_green.py): a dry run unless `--yes`, the full 40-character head pinned, checks green (pass `--expect` with the required check names so a workflow that has not started cannot be missed), an independent review on that exact head and no reviewer's latest verdict objecting. Its review line is a convention between honest agents, not an identity check, so keep branch protection on as well. Never run it with `--yes` while testing; test the dry run against a merged pull request.
   On a protected branch that must be up to date, serialize freshness with [merge_slot.py](./scripts/merge_slot.py) (a FIFO slot in `<bus dir>/merge-slot.json`, under a lock). A lane runs `refused <pr> --lane L` when a merge is refused for being behind its base (at 2 refusals the PR queues) and `may-update <pr> [--lane L]` before updating a branch: exit 0 means you hold the slot (a free slot with an empty queue is taken by that call, so two lanes asking at once cannot both go) so update, wait for CI, merge with `merge_green.py`, then `release <pr>` (it exits 0 even when the merge already dropped the slot, so `merge_green.py N --yes && merge_slot.py release N` is safe); exit 1 means wait, because updating now only invites another round. A grant from the queue is a 10-minute claim window: the head's first `may-update` claims it and starts the 40-minute lease, and an unclaimed grant passes to the next PR. Merged or closed pull requests drop out on their own, and `release` of a PR that was already dropped or whose lease expired still exits 0 (it never touches the current holder); the coordinator reads `status`. A damaged state file exits 2 and is never reset silently (`reset --yes`).
2. Each lane loads its lessons ledger before every task and records a mistake the same turn; a mistake seen twice becomes a test, lint rule, hook or script guard (`lessons-learned`). Every red CI run counts: a check that could have run locally joins the pre-push gate, and a flaky test is fixed at its cause, so no failure costs pipeline minutes twice.
3. No sentence says done, merged, fixed or recovered without the command output, pull request or commit hash that proves it.
4. A reading without its age is a claim, not a fact. Every status quoted from a file (a quota written by a watcher, release or CI state) goes through [reading.py](./scripts/reading.py) `get FILE --key K --max-age 30m` and is quoted with its "as of" time, as `get` prints it. A `STALE` or `FUTURE` result (exit 1) is refreshed at its source or reported as stale with its age, never quoted as current; exit 2 means no reading at all. Watcher jobs record the time with the value (`reading.py write FILE --key K --value V`: each key keeps its own time, so writing one key never makes another look fresh). Before sending any report or email run `reading.py check-report DRAFT`: it lists every quoted "as of" older than the limit and every percentage or status word (quota, release, CI, green, ...) with no "as of" (a line read live this turn may carry `(live: <command>)` instead). Send only when it exits 0.

---

## 3. Verification Protocol

```bash
bash .agents/bus/send.sh backend pm "START T-1 smoke - ETA 18:00"   # prints: ok inbox-backend; without the ETA: exit 6
bash .agents/bus/read.sh backend                             # shows the line and the ack command, every time until acknowledged
bash .agents/bus/read.sh backend --ack 1                     # prints: ok read-mark-backend 1; the next read: "(no unread messages)"
bash .agents/bus/archive.sh 7                                # archives only old lines already acknowledged
python3 .agents/bus/overdue.py --all                         # lists T-1 as open with its ETA; none once DONE is sent
python3 <skill>/scripts/merge_green.py <merged-pr-number>    # dry run, no --yes: refused: ... is MERGED (exit 1); exit 4: gh hung, see --gh-timeout
python3 <skill>/scripts/merge_slot.py status                   # holder with minutes left, then the queue; may-update <pr>: exit 0 you hold it, 1 hold
python3 <skill>/scripts/reading.py get <file> --key <k> --max-age 30m   # "98% (as of <time>, 12 min old)"; STALE: ... exit 1; unreadable exit 2
python3 <skill>/scripts/reading.py check-report <draft>      # "ok: ..." exit 0; each stale or unmarked reading listed, exit 1
systemctl --user list-timers                                 # each routine's next run equals its required time
```

Before declaring the model live, output the readiness table:

| Item | Evidence | Ready |
| :--- | :--- | :---: |
| Lane table accepted by the user | message or rules file commit | Yes / No |
| Rules file + operating model in the workspace | file paths | Yes / No |
| Bus round trip for every lane name | `send.sh` / `read.sh` output | Yes / No |
| A START without ETA is refused, `overdue.py` lists an open item | exit 6, `overdue.py --all` output | Yes / No |
| Every lane registered in `lanes.json` and listed in `bus/lanes.txt` | file content | Yes / No |
| Merge guard dry run refuses a merged PR | command output | Yes / No |
| A reading older than its limit is refused, a draft with an unmarked percentage is flagged | `reading.py get` exit 1, `check-report` exit 1 | Yes / No |
| Routines scheduled at the right times | timer list | Yes / No |

---

## 4. Anti-Patterns

| Anti-pattern | Why it fails | Instead |
| :--- | :--- | :--- |
| Coordinator also builds | Reports and the board stall while it codes | Coordinator writes no product code |
| Backend split by client (one lane per app) | Two lanes edit the same module and migration chain | Split by domain; one lane owns migrations and releases |
| A new agent for every new request | Parallel agents grow past what can be reviewed | At most 4 per lane; queue the rest in the live state |
| Alarms as sleeps inside a session | Die with the session, report never sent | System timers plus a once-per-day guard |
| Renaming a session in the docs only | The bus refuses the new name | Change scripts and docs in one step, test both names |
| Reading page 0 of a paginated listing | Stale tickets left "in progress" | Read until the API says there are no more pages |
| Judging a failed mutating call by its error line | The action may have succeeded before the error | Read the target's state before reporting |
| Work started or blocked with no time | Nobody sees it is late until someone asks | `START`/`BLOCKER` with an ETA, `overdue.py` every hour |
| Quoting a status from a file with no age | A watcher stopped hours ago and the file still says 80% while the truth is 98% | `reading.py get --max-age`, quote the "as of", `check-report` before sending |

---

## 5. ⚡ Token-Saving Execution Rule

- **One line per event**: bus and live messages carry a status, a ticket and an evidence token, never logs or file contents.
- **Briefs**: an agent brief names the agent, the skill, the files, the goal and the checks; nothing else.
- **Reports**: tables of tickets with evidence links; no narration of how the work went.
