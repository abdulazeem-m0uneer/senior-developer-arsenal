---
name: requirements-grilling
description: 'Pre-build interrogation runbook: a frontier-driven question tree with a recommended answer per question, the agent fetching facts itself and asking the user only for decisions, a written design brief with the agent''s own calls marked, a fresh-eyes builder check, and a hard gate that nothing is built until the brief is approved. Use when a request is non-trivial and under-specified, before any plan or code, or when the user runs /requirements-grilling. Triggers on: "grill me", "stress-test this plan", "before you build", "what do you need from me", "/requirements-grilling". Do not use for a one-line clear task (do it), an architecture trade-off record (use architecture-design-adr), or questions for a third party (use the questionnaire reference in docs-writer).'
---

# Requirements Grilling Procedure

This skill guides the agent through finding out what the user wants, and why, before anything is built. The belief that you already know is usually thinner than it feels.

---

## 1. When to Use This Skill

Activate this skill when:
- A feature, change, or design request leaves a non-trivial choice open (scope, platform, data shape, success criterion, failure mode).
- The user asks to be grilled, to stress-test a plan, or to sharpen an idea.
- A plan or ADR is about to be written from a request that nobody has questioned.
- The user runs the `/requirements-grilling` slash command.

*Boundary*: Everything that matters is in the request (`make the icon cornflower blue`): do it, say what you did. For recording the chosen option with trade-offs use `architecture-design-adr`; for logging an owner's answer use `decision-log`; for writing the implementation plan use `implementation-plan`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Decide Whether to Ask at All
1. List what you know about *what* they want and *why*. Nothing non-trivial missing: skip this skill.
2. First message, two parts only: one line offering to skip the questions and start now; one open question anchored in a concrete moment (`What is the moment you wish this existed?`). If they opt out, name every how-it-gets-made choice you are making in one line each, then build.

### Step 2: Work the Frontier in Rounds
Consult: [Question Ladder & Design Brief](./references/question-ladder-and-brief.md)
1. Model the design as a tree: every decision branches into decisions that hang off it. The *frontier* is every question whose prerequisites are already settled.
2. Ask the whole frontier in one round. Number each question; end each with your recommended answer, worded so `yes` accepts it. A question that depends on another open question waits for the next round.
3. Facts are your job, decisions are theirs. A frontier question that needs a fact from the repository, tools, or the web: look it up (or dispatch `code-explorer`); ask the user only for what they alone can decide. Do not block the rest of the round on a running lookup.
4. Open questions first; a menu only when they are stuck. A guess they can correct (`I assume this is because X keeps biting you?`) often beats a question.

### Step 3: Play It Back as You Go
1. As soon as one part is understood, describe it back in 150-300 words, then return to the next frontier. Playback and questions alternate.
2. Mark every guess as yours. Only what they said goes in as theirs. End each playback with `What is wrong or missing?`
3. Mid-session growth (`this is really three projects`): say so, agree an order, grill one at a time.

### Step 4: Size the Work and Write the Brief
1. Pick a size and say it: quick task (do it); small change (describe in chat, then normal workflow); project (written brief, then `implementation-plan`).
2. For a project, write the design brief in the format from the reference: intent and why, goals / non-goals / anti-goals, constraints, the how they decided, what is left to the builder, your own calls listed separately.

### Step 5: Builder Check, Then Gate
1. Dispatch a fresh subagent with only the brief and the builder-check prompt from the reference. It returns only the questions it would still need answered, ranked; nothing else.
2. Sort its questions: already answered (put the answer in the brief), minor (settle it, mark as your call), theirs (the answer changes what gets built). Bring the `theirs` pile in one message, most important first. One round only.
3. **Hard gate**: nothing is built (no scaffold, no dependency install, no product code, no implementation skill) until the user approves the brief. Reading and exploring are allowed. A throwaway spike they said yes to may be built; keeping its output is a new request through this gate.

---

## 3. Verification Protocol

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Frontier | Round asks a question whose answer depends on another open question | Both answers guessed; tree built on sand | `[Architecture]` | Move it to the next round |
| Facts | User asked for a value that `grep` or the manifest answers | Wasted turn; user distrusts the process | `[Suggestion]` | Look it up, ask only decisions |
| Playback | A default the user never heard is in the brief as theirs | A choice they could not reject carries their authority | `[Blocker]` | Mark as agent's call; list it in the handover |
| Gate | Scaffold created after `sounds good` to an idea, before the brief | Approval covered what was shown, not what was written | `[Blocker]` | Stop; get approval of the written brief |

---

## 4. ⚡ Token-Saving Execution Rule

- **One Question per Branch**: Collapse synonyms; never read the ground-to-cover list out as questions.
- **Playback, Not Transcript**: Describe the understood part once; never restate the whole conversation.
- **Brief by Pointer**: Hand the builder-check subagent the brief path, never the chat history.

Adapted from obra/superpowers (MIT) and mattpocock/skills (MIT).
