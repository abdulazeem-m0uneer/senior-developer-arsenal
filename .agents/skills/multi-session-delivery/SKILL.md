---
name: multi-session-delivery
description: 'Operating model for several long-running agent sessions on one product: a coordinator that writes no code and owns plan, tracker, and reports, plus build lanes with owned modules, a priority queue, contract first, one agent per story, an append-only message bus, a guarded merge script, and a mistake ledger. Use for two or more apps or repos, a backend too big for one session, an often-away lead, or /multi-session-delivery. Triggers on: "PM session", "coordinator session", "lanes", "session bus". Not for git collisions in one checkout (use parallel-sessions) or one unattended run (use autonomous-run).'
---

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
2. A lane with a free agent slot takes the highest open ticket in its own modules and sends `started <ticket>`. It does not wait to be assigned.
3. "In progress" on the board means exactly the live work. The coordinator reconciles the board with the lanes' events on a timer.

### Step 3: Build Flow Inside a Lane
1. **Contract first**: the API lane publishes the request and response schema in the shared contract package, then builds. Client lanes build against the published contract at once; a missing contract is asked for, never replaced by a stand-in API.
2. **One agent per whole story** (all endpoints and screens the flow needs), at most 4 story agents per lane, in different modules. No nested builders. Reviewers are separate agents.
3. **Done** means: merged with an independent review that found no Blocker or High (each Medium and Low becomes a follow-up ticket), CI green on the reviewed head, released, and verified on staging against the real API, which also proves the application starts. A ticket that serves stand-in data is not done.
4. While building run only the affected tests; run the full gate before pushing so no CI run is wasted.

### Step 4: Messages Between Sessions
Consult: [Session Bus](./templates/bus/README.md)
1. Every message is written to the receiver's inbox on the file bus first (`send.sh <to> <from> "<line>"`), then sent as a live message. The bus survives restarts; live messages do not.
2. On every start a session reads its inbox (`read.sh <me>`) before any work. Once a week the coordinator runs `archive.sh`, which moves old lines that were already read and shifts the read mark under the bus lock; never trim an inbox by hand.
3. Lane to coordinator, one line per event: `started|paused|merged|released|deployed|verified|blocked <ticket> <evidence>`. `verified` names the release it was checked on.
4. Questions: `Q: <question> | type: business or lead | context | blocks | working rule meanwhile`. Only the coordinator files question tickets and relays answers. Technical questions a lane can settle by best practice are decided and recorded there, never asked.
5. Lane to lane (two backend lanes): ask the owner lane for a migration slot and wait; announce any change to a shared file with the reason; one owner per story, handovers one way at a time; on a collision both lanes pause, tell the coordinator, and the owner lane decides (the lead decides if they disagree).
6. No secrets, tokens or personal data in any line.

### Step 5: Coordinator Duties
1. Keep the board true: status changes only with evidence, every page of every listing read, bulk changes through the tracker's API in one script, not one call per task.
2. File every `Q:` line as a ticket (business owner or lead), watch the answered column, record each answer in the decision log, relay it to the lane.
3. Watch for gaps (legacy or reference system, plan versus delivered) and for staging alerts; a serious alert becomes an urgent ticket and an urgent line to the owning lane, handled before any other work.
4. Send the reports the lead asked for (progress, plan, end of day, mistakes) with evidence and the list of decisions waiting on the lead.

### Step 6: Workday and Routines
Consult: [Routines & Timers](./references/routines.md)
1. The workday is N hours from the moment the sessions start; the coordinator announces start and end on the bus. In the last hour no lane starts a new build chain; 15 minutes before the end each lane sends its state and stops.
2. Fixed-time work runs from system timers, not from sleeps inside a session: a session that closes kills its own alarms silently.
3. Routines that read untrusted text (tickets, comments, emails) run with read-only shims for git, the forge CLI and the merge script first on `PATH`, and end with one status word: `ok`, `partial` or `failed`.

### Step 7: Guards Against Repeated Mistakes
1. Merge only through [merge_green.py](./scripts/merge_green.py): a dry run unless `--yes`, the full 40-character head pinned, checks green (pass `--expect` with the required check names so a workflow that has not started cannot be missed), an independent review on that exact head and no reviewer's latest verdict objecting. Its review line is a convention between honest agents, not an identity check, so keep branch protection on as well. Never run it with `--yes` while testing; test the dry run against a merged pull request.
2. Each lane loads its lessons ledger before every task and records a mistake the same turn; a mistake seen twice becomes a test, lint rule, hook or script guard (`lessons-learned`). Every red CI run counts: a check that could have run locally joins the pre-push gate, and a flaky test is fixed at its cause, so no failure costs pipeline minutes twice.
3. No sentence says done, merged, fixed or recovered without the command output, pull request or commit hash that proves it.

---

## 3. Verification Protocol

```bash
bash .agents/bus/send.sh backend pm "started T-1 smoke"      # prints: ok inbox-backend
bash .agents/bus/read.sh backend                             # shows the line once, then "(no unread messages)"
bash .agents/bus/archive.sh 7                                # archives only old lines already read
python3 <skill>/scripts/merge_green.py <merged-pr-number>    # dry run, no --yes: refused: ... is MERGED (exit 1)
systemctl --user list-timers                                 # each routine's next run equals its required time
```

Before declaring the model live, output the readiness table:

| Item | Evidence | Ready |
| :--- | :--- | :---: |
| Lane table accepted by the user | message or rules file commit | Yes / No |
| Rules file + operating model in the workspace | file paths | Yes / No |
| Bus round trip for every lane name | `send.sh` / `read.sh` output | Yes / No |
| Every lane registered in `lanes.json` and listed in `bus/lanes.txt` | file content | Yes / No |
| Merge guard dry run refuses a merged PR | command output | Yes / No |
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

---

## 5. ⚡ Token-Saving Execution Rule

- **One line per event**: bus and live messages carry a status, a ticket and an evidence token, never logs or file contents.
- **Briefs**: an agent brief names the agent, the skill, the files, the goal and the checks; nothing else.
- **Reports**: tables of tickets with evidence links; no narration of how the work went.
