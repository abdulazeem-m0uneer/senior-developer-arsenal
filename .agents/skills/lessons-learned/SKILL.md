---
name: lessons-learned
description: 'Mistake ledger. Use whenever the user says the agent made or repeated a mistake or corrects it, and after any confirmed root cause.'
---
<!-- routing (read by the skill router, not loaded into the skill listing): Use whenever the user says the agent made or repeated a mistake, corrects it, or asks to record a lesson, and after a confirmed root cause. Records it in the mistake ledger. Triggers: "you made this mistake before", "learn from this", "record this lesson", "never do that again", /lessons-learned. Not for preferences or facts (use agent-memory), decisions (use decision-log) or incidents (use incident-response). -->

# Lessons Learned Procedure

This skill guides the agent through turning a mistake into a short, enforceable lesson in a file that future sessions read, so the same mistake is not repeated. The agent itself does not change between sessions; the file does, and it only helps if it is loaded. Loading is therefore part of the procedure. The agent does not wait to be corrected: it audits its own work and records what it finds.

---

## 1. When to Use This Skill

Activate this skill when:
- The user corrects, rejects, or redoes the agent's work and the cause is understood.
- The agent itself detects it was wrong, with no user involved: it reverted or redid its own edit, a check failed after its change, it found a statement it made was false, or it broke a lesson already in the ledger.
- The agent is about to report a task done (the self-audit in Step 5).
- A failure's root cause is confirmed (Rule 0 on failure ended in a verified cause, not a guess).
- A build or test failed because of an assumption the agent made without checking.
- A CI/CD run went red on the agent's change, whether the cause was the change, a check the agent could have run locally first, or a flaky test or pipeline step (Step 4a).
- A review raised a `[Blocker]` or `[Performance]` finding on the agent's own change.
- A session starts or a new area is entered, to load the lessons that apply.
- The user runs the `/lessons-learned` slash command.

*Boundary*: A user's taste or standing preference goes to `agent-memory` or the user's memory. A domain fact or convention goes to `agent-memory` or `docs-writer`. A decision with an owner goes to `decision-log`. A production incident goes to `incident-response`. A lesson is only a mistake the agent made and a rule that would have prevented it.

---

## 2. Step-by-Step Execution Runbook

The script is `scripts/lessons.py` beside this file; resolve its path from this file. The project ledger defaults to `.agents/lessons.md` (commit it so the team shares it); `--file` or `$LESSONS_FILE` overrides it. A second, global ledger holds lessons that apply in every project: `$LESSONS_GLOBAL_FILE`, default `~/.agents/lessons.md`, never inside a repository. Its ids start with `G`; an id starting with `G`, or `--global`, sends a command there. Writers take an exclusive lock per ledger, so parallel sessions and subagents can record at the same time; a ledger that stays locked for 10 seconds makes the command exit 2 with nothing written, so retry it.

### Step 1: Load
Consult: [Lesson Format, Triggers & Promotion](./references/lesson-format-and-promotion.md)
1. Session start: `python scripts/lessons.py active`. It prints at most 15 project lessons, then the global ones under a `Global lessons` line (a global lesson that repeats a project lesson is left out). Treat each as a constraint on this session.
2. Entering an area (a database migration, a deploy, an auth flow): `python scripts/lessons.py search <keyword> [keyword]` (rules only; `--full` for whole lines). `python scripts/lessons.py show <id>` prints one lesson in full when its rule is not enough. Never read the whole file.
3. A lesson that contradicts the current code is reported as a conflict, not applied silently.
4. The plugin ships a `SessionStart` hook (`hooks/hooks.json`) that runs `active --hook` on startup, resume, clear and compact, so the list and the recording instructions are in context without being asked. The hook output is capped at 2,000 characters and prints each lesson as its id, tags, hit count and rule only (`show <id>` gives the rest): project and global lessons are ranked separately and alternated, so neither crowds out the other; within each, the three most repeated lessons come first, the rest are ordered by how well their tags and words match the files changed in the working tree and the last five commits (newest first when git is unavailable), and a final `(+N more: lessons.py search <words>)` line says how many did not fit. For installs without the plugin, wire the same hook from the reference.
5. A session that starts without the hook output in context runs `python scripts/lessons.py active --hook` itself once.

### Step 2: Capture Only a Verified Cause
1. Record after the root cause is a fact (inspected, reproduced, or confirmed by the user or by a command you ran), not while it is still a hypothesis. A mistake you found yourself is recorded the same way as one the user pointed out.
2. Skip typos, one-off environment glitches, and anything that is the user's preference.
3. Never write secrets, tokens, personal data, or blame of a person. The script refuses credentials (key, password or token assignments, known key and token formats, JWTs, PEM blocks, long random strings) with exit 2; file paths, git SHAs, UUIDs and long identifiers are accepted.
4. With the Claude Code plugin, a `Stop` hook (`hooks/guard.py`) asks once when a test, build, lint or CI command failed in the session, the same check did not pass again afterwards, and no `add` or `bump` followed (a red run that later goes green, as in red-first TDD, is not asked about). Apply items 1 and 2 to answer: record the verified cause, or say that nothing was learned (a check left red on purpose, a typo). `ARSENAL_GUARD=off` disables it. Each successful `add` or `bump` also appends the failed commands that preceded it in the session (at most three, since the previous lesson) to a local evidence file, `$LESSONS_EVIDENCE_FILE` or `~/.agents/lessons-evidence.jsonl`; credential values in commands are masked, secret-looking fields are withheld, the file stops at 5 MB, and `LESSONS_EVIDENCE=off` turns it off (see docs/LEARNING.md).

### Step 3: Write the Lesson
1. `python scripts/lessons.py add --tags node,sql --mistake "<what happened, observable>" --cause "<the false belief or skipped step>" --rule "<imperative that would have prevented it>" --check "<command or observation that detects it>"`
2. The cause names the wrong assumption ("assumed the column was nullable"), never a character flaw ("was careless").
3. The rule is an instruction for next time ("run the migration dry run before dropping a column"), under 200 characters.
4. If the script reports a duplicate, the existing lesson's count went up; if that lesson was in Archive it is back in Active. Sharpen the existing rule if the new case shows it was too vague; do not add a near copy.
5. A lesson about a tool or a habit that holds in any repository (a git flag, a shell quoting trap, "read the file before editing it") goes to the global ledger: add `--global`, or move an existing one with `python scripts/lessons.py globalize <id>`. Anything that names this project's files, schema, services or conventions stays in the project ledger.

### Step 4: Promote Repeats
1. At three hits the script prints `PROMOTE`. A mistake that keeps happening is a missing guard, not a missing reminder. A team that guards at the second hit sets `LESSONS_PROMOTE_AT=2` (or passes `check --min 2`): the threshold drives the hint, `check` and `unguarded`.
2. Prefer the strongest enforcement available: a failing test, a lint rule, a CI check, or a hook. `python scripts/lessons.py promote <id> --as test` prints a test stub built from the lesson's check; once the guard exists, `python scripts/lessons.py promote <id> --guard <path>` records it.
3. When no mechanical guard fits, `python scripts/lessons.py promote <id>` writes the rule as a line in `.agents/rules/lessons-promoted.md` beside the ledger (created with always-on frontmatter; `--rules-dir` picks another directory). Tighten the wording, narrow the trigger to a glob if it concerns one stack, and commit it.
4. A guard that covers only part of the rule (it blocks a secret in one command, while the rule also covers logs and fixtures): `promote <id> --guard <path> --keep-rule` records the guard and also writes the rule line, so the uncovered part stays in force.
5. A promoted lesson moves to Archive with `Promoted: <guard>` on its line and is no longer injected. Name the guard in the commit message. If the mistake happens again the lesson returns to Active and the script prints `GUARD FAILED`: fix the guard, not the wording of the lesson.
6. When the user mentions the same mistake recurred, `python scripts/lessons.py bump <id>` instead of adding; an archived lesson returns to Active.

### Step 4b: Guard Shell Habits at the Tool Call
1. With the Claude Code plugin, the `PreToolUse` hook (`hooks/guard_lessons.py`) denies a Bash command that repeats a known habit mistake: a `while`/`until` wait loop on `pgrep -f`, a git hook bypass (`--no-verify`, `commit -n`, setting `core.hooksPath`, git run with `HUSKY=0`), a script (`.sh`, `.py` and the like, or one the registry names) probed with `--help`/`-h`, and a secret-looking value sent through a message command the registry names, a wrong weekday, an impossible date or a guessed time (`16:4x`) in a message being sent (a `gh` comment, a commit message, an outbound MCP tool; with a configured workweek, a promise on a non-workday that has no approved workday exception on record), a commit hash in a message being sent that nothing outside the model showed in the session (opt-in `unseen-hash`), and a check or local script piped into a filter whose exit status is then acted on (`npm test | tail && git push`) without `set -o pipefail` or `PIPESTATUS`. Commands are judged by their words after quotes and here-document bodies are removed, so a commit message or a `grep` for the pattern passes.
2. Tie a rule to its lesson, switch one off, or add your own (program, subcommand, arguments, assignments, loop) in `.agents/lesson-guards.json` (project) or `~/.agents/lesson-guards.json` (global); format in the reference. Then `promote <id> --guard .agents/lesson-guards.json`. `ARSENAL_LESSON_GUARDS=off` disables the hook for a session.
3. The registry is shared by every session, and sessions may run different plugin versions. From 1.10.0 an entry a hook cannot use is skipped, never a reason to refuse commands; hooks before 1.10.0 refuse every Bash command while the file holds such an entry, and `min_version` protects only hooks from 1.10.0 on. Before writing a change, run `python3 scripts/lessons.py guards --registry <candidate file>` (a dry run, nothing is written); after it, run `python3 scripts/lessons.py guards`: it reads the registries with this hook and with every cached plugin version, exits 1 when this hook or a version an install references has a problem, and warns about cached versions no install references (`--strict` counts them); give an entry that needs a newer rule `"min_version": "X.Y.Z"` (the first version that has the rule) so hooks older than that skip it quietly. `arsenal doctor` runs the same check, and the session-start lessons header counts skipped entries.
4. Each refusal is logged (time, lesson, rule, working directory, never the command) to `~/.agents/lesson-guard-hits.jsonl`; `python scripts/lessons.py hits --since 24h` counts them per lesson. The log only grows; truncate or rotate it when it gets large.

### Step 4c: Daily Repeat Check
1. `python scripts/lessons.py unguarded --min 2 [other ledgers...]` lists every lesson seen twice or more without a guard, Archive included (a retired lesson that repeated is still unguarded), most hits first.
2. Schedule it once a day with the recipe in the reference (a systemd user timer or cron): `unguarded`, `check` and `hits --since 24h` on every ledger, one summary line to the team's inbox, the full list to a file.
3. Route each unguarded repeat to the agent or person who owns the area it names; that owner builds the guard the same day and runs `promote <id> --guard <path>`. A repeat with no possible mechanical guard gets `promote <id>` (rule line) so it stops appearing.
4. Until then the repeat is not quiet: every session-start header names the repeats seen as often as the promotion threshold (`LESSONS_PROMOTE_AT`, default 3) that have no guard, project and global, Archive included, and the weekly retro lists all of them. A repeat that no test, lint, hook or CI check can catch gets a written exemption instead: `python scripts/lessons.py exempt <id> --reason "<why no mechanical guard fits>"`. It stays in its section and is no longer flagged, but only for the hits it was granted at: if it recurs, the script prints `EXEMPT ... recurred` and the lesson is flagged again until it gets a guard or a new exemption.

### Step 4d: Weekly Retro
1. Once a week (or at the end of a milestone), run `python scripts/lessons.py retro [--days 7] [--project]` in the repository. It reads the commits of the window (feat, fix, revert, files fixed more than once), the ledgers (new lessons, repeats, guards), the failure-evidence file and the guard hit log, and prints "What went well", "What repeated" and the top 3 actions. Each action names a lesson id or a commit.
2. Act on action 1 the same day, usually a guard for the most repeated unguarded lesson. Paste the retro into the team channel or the handoff; never edit its numbers by hand.

### Step 4e: Metrics Per Project and Lane
1. `python scripts/lessons.py metrics [--days 7] [--lane-tag session:] [--bus DIR] [--json] [--ledger FILE ...]` prints, per ledger and per lane (the tag `session:<name>`; untagged lessons are "(no lane)"), lessons added and repeated per day, total repeats, guarded, unguarded and exempt counts, guard fires per day and, with `--bus`, the ETA accuracy per session from that bus folder's `open-items.tsv`.
2. Per-day counts come from `<ledger stem>.events.jsonl`, which `add`, `bump` and `globalize` append to; days before it started are marked "from ledger dates: last change only". Details, and how to commit the log, in the reference.

### Step 4a: Learn From Every Red CI Run
A red run costs pipeline minutes and a review cycle. Every one is a lesson, the first time:
1. **The change failed a check that runs locally** (lint, type check, unit test, format, coverage, migration order): record the lesson with the exact local command as its `--check`, and add that command to the pre-push gate (`quality-gate`) in the same change, so the next push is stopped on the machine, not in CI.
2. **The change failed only in CI** (another OS, shell or runtime version, a service the laptop lacks): record which environment differs, and add the cheapest local stand-in (a container, the other shell, a matrix entry run locally) or a note in the gate saying the check exists only in CI.
3. **A flaky test or step**, not the change: rerun once to unblock (`ci-wait`), then find the cause (timing, ordering, shared state, clock) and fix it in the same pull request or a linked one. A rerun is not a fix; a flake left in place wastes every later run.
4. **An outside fault** (registry, network, billing): no lesson unless the agent could have prevented it; a repeat is a pipeline defect for `devops-ci`.
5. Before pushing, read the Active lessons tagged `ci` and run each `--check`. Tag CI lessons `ci` plus the stack, so the list stays searchable.

### Step 5: Self-Audit Before Saying Done
Run these checks on your own work with evidence, not memory, before reporting a task complete:
1. Did I revert, redo, or rewrite my own edit during this task? Why was the first attempt wrong?
2. Did any command or test fail because of something I assumed rather than checked?
3. Did I state something earlier in this session that I now know is false or unverified?
4. Did I break a lesson that was loaded at the start? If so, `bump <id>` instead of adding.
5. Did the user have to repeat an instruction to me?
A yes with a verified cause becomes a lesson (Step 3). All no: record nothing and say nothing; the audit is silent unless it finds something.

### Step 6: Keep It Small
1. Active holds 15 lessons at most; a new one evicts the least-hit, oldest lesson into Archive.
2. Run `python scripts/lessons.py check` (and `check --global`) at handoff or monthly; fix every `problem:` line (unparsable lines, lessons written above the `## Active` header, duplicate ids) and act on every `candidate`.

---

## 3. Verification Protocol

1. After `add`, `search` for a keyword of the rule and confirm the lesson comes back.
2. Session start shows the `Lessons ledger` header in context; if it is missing, the hook is not wired.
3. Each lesson is one line with mistake, cause, rule, and check; no transcripts, no secrets.
4. `check` exits 0; Active has at most 15 lines.
5. A promoted lesson is archived with a `Promoted:` field and its guard exists at that path.
6. `evals/task-lesson-recall` measures the loop end to end: a fixture repository whose ledger warns against the obvious edit, graded on whether the lesson was followed.

---

## 4. Negative Triggers

- Not a diary: no entry for routine work that went well.
- Not a rulebook: the global ledger is for your own repeated tool and habit mistakes; a standard every contributor should follow belongs in `.agents/rules/`, proposed through a pull request.
- Not a way to excuse errors: if the cause is unverified, report it as a hypothesis and record nothing yet.
- Not a ritual: the self-audit produces no output when it finds nothing; never invent a lesson to look diligent.

---

## 5. Token Conservation Directive

- Load only `active` (at most 15 lines per ledger) or a `search` (at most 10 lines); never `cat` the ledger.
- One `add` call per lesson; do not re-read the file after writing.
- Lessons are terse fragments, not paragraphs.
- The hook costs one header (about 85 tokens plus the script path) plus the lessons that fit, at most 2,000 characters (about 500 tokens) in total per session start, about ten lessons; nothing is re-read mid-session.
