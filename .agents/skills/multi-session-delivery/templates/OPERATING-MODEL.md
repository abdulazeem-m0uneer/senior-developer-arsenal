# <PROJECT> operating model

Copy this file to `<workspace>/.agents/OPERATING-MODEL.md` and the session rules to `<workspace>/SESSION-RULES.md`, then replace every `<PLACEHOLDER>`. Every session reads both files when it starts. A newer decision by the lead replaces a line here, and the coordinator updates this file the same day.

## Sessions

| Session | Owns | Never does |
| --- | --- | --- |
| **pm** (coordinator, workspace root) | Plan and progress, the tracker, questions and answers, gap watch, staging health watch, rules file, every email and report, relaying the lead's instructions | Product code, pull requests, releases |
| **backend** (`<repo-api>`) | `<domain A modules>`, money, migration order, shared sequence numbers, releases of `<repo-api>` | `<repo-web>`, `<domain B modules>` |
| **backend-b** (`<repo-api>`, optional) | `<domain B modules>` | Migration order and releases (asks `backend`), `<domain A modules>` |
| **web** (`<repo-web>`) | Web console features, built from the published contracts | `<repo-api>` |
| **mobile** (`<repo-mobile>`, optional) | Mobile app features, built from the published contracts | `<repo-api>` |

Session names are fixed. Every session runs in the same permission mode. Remove the rows you do not need.

## Priority (every free agent slot takes the next ticket itself)

1. Urgent tickets, and tickets raised by `<client team that consumes the API>`.
2. Features those clients wait on.
3. The current plan week, hardest story first.

`<tracker list or board>` is the queue; the coordinator keeps its order and tags. A lane with a free slot takes the highest open ticket in its own modules and sends `started <ticket>`.

## How work flows

- **Contract first:** the API lane publishes the schema in `<contract package>`, then builds; the client lanes build against the contract.
- **Agents:** at most 4 story agents per lane, one whole story each, in different modules. Reviewers are separate. Each brief names its agent and skill.
- **Done:** merged with a clean independent review (no Blocker or High) and green CI on the reviewed head, released, and verified on staging. A ticket is done only when its routes serve real data.
- **Merging:** only through the guarded merge script (dry run unless `--yes`, full head SHA pinned). A test never runs it against a live pull request.
- **Lessons:** load the lane's lessons before each task; record each mistake the same turn; a mistake seen twice gets a test, lint rule, hook or script guard.

## Messages

- **Bus:** `<workspace>/.agents/bus`. Send with `send.sh <to> <from> "<line>"`, then the live message. On every start run `read.sh <me>` first, then `read.sh <me> --ack <line>` once the lines are acted on.
- **Lane to coordinator:** `started|paused|merged|released|deployed|verified|blocked <ticket> <evidence>`; `Q: <question> | type: business or lead | context | blocks | working rule meanwhile`.
- **Questions:** only the coordinator creates question tickets. Business questions go to `<business owner>` in `<business status>`; lead questions go to `<lead>` in `<blocked status>`. Questions a lane can settle by best practice are decided there and recorded. Never re-ask a question that has an answer.
- **Session registry:** on every start each session writes its own session id under its name in `.agents/pm/lanes.json`.
- **Tracker:** everything a person must see goes there, with its evidence. "In progress" means exactly the live work.

## Automatic routines (system timers run by the coordinator, `<timezone>`)

| Timer | When | What |
| --- | --- | --- |
| day-start | every 15 min; runs once when the workday starts | Security and dependency news, gap watch, queue order and each lane's top 5 |
| watch | hourly inside the workday | New client-team requests, the answered column, the lanes' `Q:` lines, the hourly progress report |
| staging-alerts | every 5 minutes, all day | Alert manager: a paging alert or staging unreachable 3 times files an urgent ticket and tells the owning lane. A plain script, no model. |
| reconcile | every 2 hours inside the workday | The board matches the live work (API, every page, a capped number of moves per run) |
| reports | `<time>` daily | Work progress and plan progress, with the decisions waiting for the lead |
| day-end | once, 15 min before the workday ends | End-of-day report, with the day's mistakes and new lessons |
| weekly | `<day> <time>`, once per week, caught up at boot | Full gap re-scan, plan re-baseline, lessons promotion, bus archive |

Logs are in `<log dir>`. A routine ends with `ok`, `partial` or `failed`; anything else raises an alert and a bus line to the coordinator.

## The lead's part

The lead answers the tickets assigned to them. Those are listed every day in the report, one question each, with the working rule meanwhile. Nothing waits on the chat.
