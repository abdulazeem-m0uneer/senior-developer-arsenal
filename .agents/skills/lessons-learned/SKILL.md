---
name: lessons-learned
description: 'Use whenever the user says the agent made or repeated a mistake, corrects it, or asks to record a lesson, and after any confirmed root cause or failure from a wrong assumption. Mistake ledger: record the verified cause as one line (mistake, cause, rule, check) in the project lessons file with the bundled script, deduplicate, load only the capped Active list at session start, and promote repeats into a test, lint, hook or rule. Triggers on: "you made this mistake before", "learn from this", "record this lesson", "never do that again", /lessons-learned. Not for preferences or facts (use agent-memory), decisions (use decision-log), or incidents (use incident-response).'
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

The script is `scripts/lessons.py` beside this file; resolve its path from this file. The ledger defaults to `.agents/lessons.md` in the project (commit it so the team shares it); `--file` or `$LESSONS_FILE` overrides it.

### Step 1: Load
Consult: [Lesson Format, Triggers & Promotion](./references/lesson-format-and-promotion.md)
1. Session start: `python scripts/lessons.py active`. It prints at most 15 lines. Treat each as a constraint on this session.
2. Entering an area (a database migration, a deploy, an auth flow): `python scripts/lessons.py search <keyword> [keyword]`. Never read the whole file.
3. A lesson that contradicts the current code is reported as a conflict, not applied silently.
4. The plugin ships a `SessionStart` hook (`hooks/hooks.json`) that runs `active --hook` on startup, resume, clear and compact, so the list and the recording instructions are in context without being asked. For installs without the plugin, wire the same hook from the reference.
5. A session that starts without the hook output in context runs `python scripts/lessons.py active --hook` itself once.

### Step 2: Capture Only a Verified Cause
1. Record after the root cause is a fact (inspected, reproduced, or confirmed by the user or by a command you ran), not while it is still a hypothesis. A mistake you found yourself is recorded the same way as one the user pointed out.
2. Skip typos, one-off environment glitches, and anything that is the user's preference.
3. Never write secrets, tokens, personal data, or blame of a person. The script refuses secret-like text.

### Step 3: Write the Lesson
1. `python scripts/lessons.py add --tags node,sql --mistake "<what happened, observable>" --cause "<the false belief or skipped step>" --rule "<imperative that would have prevented it>" --check "<command or observation that detects it>"`
2. The cause names the wrong assumption ("assumed the column was nullable"), never a character flaw ("was careless").
3. The rule is an instruction for next time ("run the migration dry run before dropping a column"), under 200 characters.
4. If the script reports a duplicate, the existing lesson's count went up. Sharpen the existing rule if the new case shows it was too vague; do not add a near copy.

### Step 4: Promote Repeats
1. At three hits the script prints `PROMOTE`. A mistake that keeps happening is a missing guard, not a missing reminder.
2. Prefer the strongest enforcement available: a failing test, a lint rule, a CI check, or a hook; then a line in the matching file under `.agents/rules/`; then a line in `AGENTS.md`.
3. After promoting, `python scripts/lessons.py archive <id>` and name the guard in the commit message.
4. When the user mentions the same mistake recurred, `python scripts/lessons.py bump <id>` instead of adding.

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
2. Run `python scripts/lessons.py check` at handoff or monthly; fix every `problem:` line and act on every `candidate`.

---

## 3. Verification Protocol

1. After `add`, `search` for a keyword of the rule and confirm the lesson comes back.
2. Session start shows the `Lessons ledger` header in context; if it is missing, the hook is not wired.
3. Each lesson is one line with mistake, cause, rule, and check; no transcripts, no secrets.
4. `check` exits 0; Active has at most 15 lines.
5. A promoted lesson is archived and its guard exists in the repository.

---

## 4. Negative Triggers

- Not a diary: no entry for routine work that went well.
- Not a rulebook: a lesson that applies to every project belongs in `.agents/rules/`, proposed through a pull request.
- Not a way to excuse errors: if the cause is unverified, report it as a hypothesis and record nothing yet.
- Not a ritual: the self-audit produces no output when it finds nothing; never invent a lesson to look diligent.

---

## 5. Token Conservation Directive

- Load only `active` (at most 15 lines) or a `search` (at most 10 lines); never `cat` the ledger.
- One `add` call per lesson; do not re-read the file after writing.
- Lessons are terse fragments, not paragraphs.
- The hook costs one header (about 70 tokens) plus at most 15 lines per session start; nothing is re-read mid-session.
