# <PROJECT> session rules

Every session reads this file when it starts. A newer decision by the lead replaces a line here, and the coordinator updates the file the same day. How the routines run is in `.agents/OPERATING-MODEL.md`.

## Rules for every session

- Read this file, `.agents/OPERATING-MODEL.md` and your bus inbox (`bash .agents/bus/read.sh <name>`) before any work; acknowledge the lines once acted on (`--ack <line>`, printed by the read).
- Keep your fixed session name (`pm`, `backend`, `backend-b`, `web`, `mobile`) and the shared permission mode.
- On every start, write your own session id under your name in `.agents/pm/lanes.json`.
- **Priority:** urgent tickets and client-team tickets; then the features clients wait on; then the current plan week, hardest story first.
- **Skills and agents:** each task uses its matching skill; every builder, reviewer, tester and debugger is a specialist agent; every brief names its agent and skill.
- **Workday:** `<N>` hours from the time the sessions start. In the last hour start no new build chain; 15 minutes before the end send the coordinator your state and stop.
- **No repeated mistakes:** load your lessons before each task; record each mistake the same turn; a mistake seen twice gets a test, lint rule, hook or script guard; check the evidence before every claim.
- The tracker is the shared place with the lead and the business owner. Everything a person must see goes there with its evidence.
- Never bypass hooks. Never commit or push to a repository outside your lane.
- Never put a secret (token, key, password, personal data) in a message, a log line or a ticket.
- **Save tokens, deliver faster, stay accurate:**
  - **Reading:** code-graph or targeted search before reading; read only the lines you need; never re-read a file after your own edit; run tests and CI output quietly, failing lines only.
  - **Writing:** edit, don't rewrite; the smallest complete change; one line per event; a brief with only the files, the goal and the checks.
  - **Speed:** take the next ticket the moment a slot frees; contract first; affected tests while building, the full gate before pushing.
  - **Accuracy:** every change ships its tests; an independent review finds no Blocker or High before merging; CI green on the reviewed head; verified on staging before "done"; every claim backed by fresh evidence.

## pm (coordinator, workspace root)

- Owns the plan and progress, the tracker, questions, the gap watch, the rules watch, the staging health watch, and every email and report.
- Writes no product code, opens no pull requests and makes no releases.
- Relays the lead's instructions to the lanes, one instruction per message: bus first, then live.
- **The board shows the real work:** "in progress" means exactly the live work; a status changes only with evidence; every page of a listing is read; bulk changes go through the API.
- **Questions:** files every `Q:` line as a ticket (business owner or lead) and relays each answer back; records answers in the decision log.
- **Staging alerts:** a serious alert becomes an urgent ticket and an urgent line to the owning lane.
- **Reports:** `<schedule and recipients>`; each of its own mistakes reported the same turn.

## backend and backend-b

- Build backend features only, in `<repo-api>`. Never touch a client repository.
- **Split:** `backend` owns `<domain A>`, money, migration order, shared numbers and releases; `backend-b` owns `<domain B>` and asks `backend` for migration slots and releases.
- **Coordinate directly** (bus first, then live), copying the coordinator: ask for a migration slot and wait; name any shared file you change and why; one owner per story; on a collision pause, tell the coordinator, `backend` decides.
- **Contract first:** publish the schema in `<contract package>`, then build. Tell the client lanes when a contract is final and when its endpoint lands.
- **Agents:** at most 4 story agents, one whole story each, different modules; reviewers separate.
- **Done:** merged with a clean review and green CI, released, verified on staging. Merge only through the guarded merge script.
- Handle an `URGENT staging alert` line before any other work.
- Send the coordinator one line per event: `started|paused|merged|released|deployed|verified|blocked <ticket> <evidence>`; questions as `Q:` lines.

## web and mobile

- Build features in your own repository only. Never touch `<repo-api>`.
- Build from the published contracts without waiting for the backend merge; ask for a missing contract, never build a stand-in API.
- `<UI rule, e.g. the approved design is frozen; a visible change needs the lead's written approval, asked through the coordinator>`
- **Agents:** at most 4 story agents, one whole story each; reviewers separate.
- **Done:** merged with a clean review and green CI, deployed to staging, end-to-end tests passing against the real API.
- Send the coordinator one line per event: `started|paused|merged|released|deployed|verified|blocked <ticket> <evidence>`; questions as `Q:` lines.
