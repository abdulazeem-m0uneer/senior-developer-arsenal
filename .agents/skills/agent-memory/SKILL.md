---
name: agent-memory
description: Long-term biomimetic agent memory management using Hindsight (vectorize-io/hindsight). Retains project architecture, records solved debugging lessons, and recalls contextual knowledge using hybrid retrieval (vector, keyword, graph, temporal).
triggers:
  - remember this decision
  - save architectural rule
  - recall project context
  - query memory bank
  - hindsight memory
  - /memory
---

# Agent Memory Skill (`agent-memory`)

This skill integrates **Hindsight** (`vectorize-io/hindsight`) to give Antigravity agents durable, long-term memory across sessions without consuming excessive context window tokens.

## 🎯 When to Use
- **Recording Architecture Decisions**: Saving domain rules, ADR summaries, or database invariants into the persistent project memory bank.
- **Root-Cause Investigation Retention**: Persisting resolved bug investigations from `investigate` to prevent rediscovering known bugs.
- **Context Retrieval**: Querying prior architectural patterns, team conventions, or business rules before designing new subsystems.
- **Cross-Session Continuity**: Recalling past constraints without loading bulky markdown files into the active context.

## 🚫 When NOT to Use
- Temporary scratchpad data or one-off code snippets.
- Reading active codebase source code (use code search or `view_file` directly).
- Overwriting active git files or documentation files.

---

## 🛠️ Core Memory Operations (The Three Verbs)

Hindsight exposes three fundamental verbs:

1. **`retain`**: Ingests new architectural facts, operational constraints, or project preferences.
2. **`recall`**: Hybrid multi-dimensional search (Semantic embeddings + BM25 keyword matching + Temporal recency + Knowledge Graph traversal).
3. **`reflect`**: Autonomous reasoning loop that synthesizes consolidated observations and mental models into a direct answer.

---

## 💻 Developer Usage

### 1. Using Python Embedded / CLI
Run memory actions directly using the arsenal helper script:

```bash
# Store an architectural fact or constraint
python scripts/memory.py retain --bank "<project-name>" --content "All timestamps must use TIMESTAMPTZ in UTC."

# Query relevant memories (Hybrid search)
python scripts/memory.py recall --bank "<project-name>" --query "What timestamp convention do we use?"

# Synthesize guidance using reflection
python scripts/memory.py reflect --bank "<project-name>" --query "What are our database indexing and migration policies?"
```

### 2. Using Antigravity / Agent MCP Tools
When the Hindsight MCP server is active, subagents can directly invoke native memory tools:
- `hindsight_retain(bank_id, content)`: Call after closing an investigation or agreeing on an ADR.
- `hindsight_recall(bank_id, query)`: Call before reviewing a PR or scaffolding new database models.
- `hindsight_reflect(bank_id, query)`: Call when a user asks high-level questions about project rules.

---

## 📋 Best Practices & Guardrails

- **Explicit Bank Naming**: Always name the `bank_id` after the target repository or service (e.g. `billing-service`, `senior-developer-arsenal`).
- **Token Efficiency**: Use `recall` and `reflect` instead of dumping massive history files into the prompt.
- **Atomic Observations**: Store distilled, high-signal technical constraints rather than raw conversational transcripts.
