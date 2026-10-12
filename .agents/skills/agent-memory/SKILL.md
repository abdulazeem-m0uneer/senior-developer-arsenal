---
name: agent-memory
description: 'Long-term biomimetic agent memory management using Hindsight (vectorize-io/hindsight). Retains project architecture, records solved debugging lessons, and recalls contextual knowledge using hybrid retrieval (vector, keyword, graph, temporal). Use when the user asks to remember a decision, recall project context, or runs /agent-memory. Triggers on: "remember this decision", "save architectural rule", "recall project context", "query memory bank", "hindsight memory", "/agent-memory". Do not use for reading active source code (use codegraph or code search) or for the written decision record (use decision-log).'
---

# Agent Memory Procedure

This skill guides the agent through keeping durable project knowledge in a Hindsight memory bank and recalling it across sessions without loading history into the context window.

---

## 1. When to Use This Skill

Activate this skill when:
- Saving a domain rule, an ADR summary, or a database invariant that future sessions must respect.
- Closing an investigation whose root cause should not be rediscovered.
- Starting a design and needing the conventions and constraints agreed earlier.
- The user runs the `/agent-memory` slash command.

*Boundary*: For reading source code, use `codegraph` or your search tool. For the record that people read and review, use `decision-log` or `architecture-design-adr`; memory supports those records and does not replace them. Never store scratch data, secrets, or personal data.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Pick the Bank
Consult: [Hindsight Memory Architecture](./references/memory-architecture.md)
1. Name the bank after the repository or service (`billing-service`), never after a person or a session.
2. Confirm how memory is reached: the Hindsight MCP tools when the server is connected, otherwise the bundled script. Resolve the script path relative to the directory that contains this file.

### Step 2: Retain
1. Store one distilled fact per call, stated so it stands alone: the rule, its reason, and its scope.
2. Retain after an ADR is agreed, an investigation closes, or the user states a standing preference.
```bash
python scripts/memory.py retain --bank "<project-name>" --content "All timestamps use TIMESTAMPTZ in UTC; mixed zones broke the billing export."
```
With the MCP server: `hindsight_retain(bank_id, content)`.

### Step 3: Recall Before Deciding
1. Query before designing a subsystem, reviewing a change, or answering a question about project rules.
2. Use `recall` for facts and `reflect` for a synthesised answer across many memories.
```bash
python scripts/memory.py recall --bank "<project-name>" --query "What timestamp convention do we use?"
python scripts/memory.py reflect --bank "<project-name>" --query "What are our indexing and migration policies?"
```
With the MCP server: `hindsight_recall(bank_id, query)` and `hindsight_reflect(bank_id, query)`.

### Step 4: Check a Memory Before Acting on It
A memory records what was true when it was written. Before relying on one that names a file, a flag, or a version, confirm it still holds in the code.

---

## 3. Verification Protocol

1. After `retain`, run a `recall` with different wording and confirm the fact comes back.
2. Each retained item is one fact with its reason; no transcripts, no secrets, no personal data.
3. A recalled rule that conflicts with the current code is reported as a conflict, not applied silently.

---

## 4. ⚡ Token-Saving Execution Rule

- **Recall, Do Not Reload**: Query the bank instead of pasting history files into the prompt.
- **Atomic Facts**: Short, self-contained observations retrieve better and cost less than long notes.
- **Quote the Hit**: Report the recalled fact in one line with the query that found it.
