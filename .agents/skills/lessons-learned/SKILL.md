---
name: lessons-learned
description: 'Use whenever the user says the agent made or repeated a mistake, corrects it, or asks to record a lesson, and after a confirmed root cause. Records it in the mistake ledger. Triggers: "you made this mistake before", "learn from this", "record this lesson", "never do that again", /lessons-learned. Not for preferences or facts (use agent-memory), decisions (use decision-log) or incidents (use incident-response).'
---

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
2. Entering an area (a database migration, a deploy, an auth flow): `python scripts/lessons.py search <keyword> [keyword]`. Never read the whole file.
3. A lesson that contradicts the current code is reported as a conflict, not applied silently.
4. The plugin ships a `SessionStart` hook (`hooks/hooks.json`) that runs `active --hook` on startup, resume, clear and compact, so the list and the recording instructions are in context without being asked. The hook output is capped at 4,000 characters: the three most repeated lessons always come first, the rest are ordered by how well their tags and words match the files changed in the working tree and the last five commits (newest first when git is unavailable), and a final `(+N more: lessons.py search <words>)` line says how many did not fit. For installs without the plugin, wire the same hook from the reference.
5. A session that starts without the hook output in context runs `python scripts/lessons.py active --hook` itself once.

### Step 2: Capture Only a Verified Cause
1. Record after the root cause is a fact (inspected, reproduced, or confirmed by the user or by a command you ran), not while it is still a hypothesis. A mistake you found yourself is recorded the same way as one the user pointed out.
2. Skip typos, one-off environment glitches, and anything that is the user's preference.
3. Never write secrets, tokens, personal data, or blame of a person. The script refuses credentials (key, password or token assignments, known key and token formats, JWTs, PEM blocks, long random strings) with exit 2; file paths, git SHAs, UUIDs and long identifiers are accepted.
4. With the Claude Code plugin, a `Stop` hook (`hooks/guard.py`) asks once when a test, build, lint or CI command failed in the session, the same check did not pass again afterwards, and no `add` or `bump` followed (a red run that later goes green, as in red-first TDD, is not asked about). Apply items 1 and 2 to answer: record the verified cause, or say that nothing was learned (a check left red on purpose, a typo). `ARSENAL_GUARD=off` disables it.

### Step 3: Write the Lesson
1. `python scripts/lessons.py add --tags node,sql --mistake "<what happened, observable>" --cause "<the false belief or skipped step>" --rule "<imperative that would have prevented it>" --check "<command or observation that detects it>"`
2. The cause names the wrong assumption ("assumed the column was nullable"), never a character flaw ("was careless").
3. The rule is an instruction for next time ("run the migration dry run before dropping a column"), under 200 characters.
4. If the script reports a duplicate, the existing lesson's count went up; if that lesson was in Archive it is back in Active. Sharpen the existing rule if the new case shows it was too vague; do not add a near copy.
5. A lesson about a tool or a habit that holds in any repository (a git flag, a shell quoting trap, "read the file before editing it") goes to the global ledger: add `--global`, or move an existing one with `python scripts/lessons.py globalize <id>`. Anything that names this project's files, schema, services or conventions stays in the project ledger.

### Step 4: Promote Repeats
1. At three hits the script prints `PROMOTE`. A mistake that keeps happening is a missing guard, not a missing reminder.
2. Prefer the strongest enforcement available: a failing test, a lint rule, a CI check, or a hook. `python scripts/lessons.py promote <id> --as test` prints a test stub built from the lesson's check; once the guard exists, `python scripts/lessons.py promote <id> --guard <path>` records it.
3. When no mechanical guard fits, `python scripts/lessons.py promote <id>` writes the rule as a line in `.agents/rules/lessons-promoted.md` beside the ledger (created with always-on frontmatter; `--rules-dir` picks another directory). Tighten the wording, narrow the trigger to a glob if it concerns one stack, and commit it.
4. A promoted lesson moves to Archive with `Promoted: <guard>` on its line and is no longer injected. Name the guard in the commit message. If the mistake happens again the lesson returns to Active and the script prints `GUARD FAILED`: fix the guard, not the wording of the lesson.
5. When the user mentions the same mistake recurred, `python scripts/lessons.py bump <id>` instead of adding; an archived lesson returns to Active.

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
- The hook costs one header (about 85 tokens plus the script path) plus the lessons that fit, at most 4,000 characters (about 1,000 tokens) in total per session start; nothing is re-read mid-session.
