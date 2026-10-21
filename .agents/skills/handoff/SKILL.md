---
name: handoff
description: 'Session handoff runbook: compact the current conversation into one short document a fresh agent reads instead of the history, with state, blockers, open hypotheses, files touched, pointers to existing artifacts, and the skills the next session should activate. Use before context fills, at the end of a long task, when switching agents or machines, or when the user runs /handoff. Triggers on: "handoff", "hand off", "continue in a new session", "context is full", "write a summary for the next agent", "/handoff". Do not use for a decision record (use decision-log) or a postmortem (use incident-response).'
---

# Session Handoff Procedure

Compact a long conversation into one document so the next session starts from a few hundred tokens, not the transcript. Adapted from Matt Pocock's `handoff` skill (MIT) and the Campsite Clean Handoff in `defensive-epistemology.md`.

---

## 1. When to Use This Skill

Activate this skill when:
- Context is near its limit, or the task will outlive this session.
- Work moves to another agent, model, machine, or person.
- A long task ends at a decision point the user must make.
- The user runs the `/handoff` slash command.

*Boundary*: A decision goes in the decision log (`decision-log`); an incident timeline goes in the postmortem (`incident-response`); code state goes in commits. The handoff points at those, never duplicates them.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Decide Where It Lives
1. Default: the OS temp dir (`$TMPDIR` or `/tmp`; `%TEMP%` on Windows) as `handoff-<repo>-<yyyymmdd-hhmm>.md`. Never inside the workspace unless the user asks; a handoff committed by accident is noise forever.
2. If the user passed arguments, treat them as what the next session will focus on and tailor the document to it.

### Step 2: Gather From Reality, Not Memory
1. `git status --short` and `git log --oneline -10`: what is committed, what is dirty.
2. The last test, lint, build result actually observed (status line only).
3. Open tasks from the task list or tracker, if any.
4. Paths/URLs of specs, plans, ADRs, issues, PRs already written. Reference, do not copy.

### Step 3: Write the Document
Consult: [Handoff Template](./references/handoff-template.md)
1. Keep it under ~60 lines. Every line must change what the next agent does.
2. State facts as verified or believed, as `defensive-epistemology.md` requires.
3. **Suggested skills** section: name the arsenal skills and subagents the next session should activate first.
4. Redact secrets, tokens, credentials, personal data.

### Step 4: Hand Over
1. Report the path and a one-line summary. Do not paste the document into chat.
2. Tell the user the next session's first message: `Read <path> and continue.`

---

## 3. Negative Triggers

- Not a transcript: no narration of what was tried in order; only what is true now and what remains.
- Not a design doc: unresolved design goes to `architecture-design-adr`.
- No code snippets beyond one decisive line; cite `file:line`.

---

## 4. Token Conservation Directive

- The point of the document is to replace re-reading; keep it dense.
- Read only `git` output and the task list to write it; do not re-open source files.
