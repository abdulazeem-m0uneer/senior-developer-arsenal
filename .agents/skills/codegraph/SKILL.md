---
name: codegraph
description: 'Fast AST-based structural code intelligence via CodeGraph MCP. Replaces expensive file reading, broad greps, and blind codebase exploration with precise symbol lookups, call hierarchies, caller/callee trees, and blast radius impact analysis. Triggers on: "codegraph", "code graph", "find callers", "find callees", "blast radius", "symbol definition", "who calls", "call hierarchy". Do not use for non-code config files or when no CodeGraph MCP server is connected.'
---

# CodeGraph Intelligence Skill (`codegraph`)

This skill integrates **CodeGraph** AST knowledge graph queries to eliminate the repetitive "grep-read-scan" loop that wastes thousands of tokens.

## 🎯 When to Use
- **Tracing Call Hierarchies**: Finding all functions/methods that call a specific symbol (`codegraph_callers`) or all functions invoked by a method (`codegraph_callees`).
- **Refactoring & Blast Radius Analysis**: Checking all downstream dependents before modifying, renaming, or deleting an interface, class, or endpoint (`codegraph_impact`).
- **Symbol Lookup & Definitions**: Jumping directly to symbol definitions without full-text grep scans across directories (`codegraph_search`, `codegraph_node`).
- **New Session Codebase Map**: Answering architectural questions about how components interact in a single query rather than reading dozens of files.

## 🚫 When NOT to Use
- Reading non-code configuration files (e.g. `yaml`, `json`, `ini`, `md`).
- Editing or modifying code (use surgical code edit tools).
- Natural language conceptual search without symbols (use `recall` or semantic search).

---

## 🛠️ MCP Tools & Capabilities

When CodeGraph MCP is connected to the session, the agent uses these high-precision tools:

| MCP Tool | Purpose | Token Saving vs Grep |
| :--- | :--- | :---: |
| `codegraph_callers` | Returns direct callers of a given symbol with file:line pointers. | ~80% |
| `codegraph_callees` | Returns all functions/APIs invoked inside a function body. | ~75% |
| `codegraph_impact` | Computes transitive dependency blast radius before refactoring. | ~90% |
| `codegraph_search` | Finds a symbol by name with kind, location, and signature. | ~70% |
| `codegraph_node` | Returns one symbol's signature, source, and docstring. | ~70% |
| `codegraph_explore` | Returns the source of several related symbols in one capped call. | ~85% |
| `codegraph_files` | Lists indexed files under a path. | ~60% |
| `codegraph_status` | Reports index health. | n/a |

---

## 📋 Session Execution Protocol

1. **Graph-First Navigation**: Whenever asked where a method is called, how a service works, or what depends on a class, **ALWAYS query CodeGraph tools first**. Do not run raw `grep` or recursively view files across directories.
2. **Surgical Verification**: Query the graph, retrieve the exact `file.cs:L45-L60` pointer, and view only the specific line slice.
3. **Auto-Sync / Indexing**: If CodeGraph is not yet initialized in the project root:
   ```bash
   npx @colbymchenry/codegraph init -i
   ```
