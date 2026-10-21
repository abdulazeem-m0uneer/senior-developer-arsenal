---
name: codegraph
description: 'Fast AST-based structural code intelligence via CodeGraph MCP. Replaces expensive file reading, broad greps, and blind codebase exploration with precise symbol lookups, call paths, caller/callee trees, and blast radius impact analysis. Use when the user asks who calls a symbol, how a flow works, or what a change would break, or runs /codegraph. Triggers on: "codegraph", "code graph", "find callers", "find callees", "blast radius", "symbol definition", "who calls", "call hierarchy", "/codegraph". Do not use for non-code config files or when no CodeGraph MCP server is connected.'
---

# CodeGraph Structural Navigation Procedure

This skill guides the agent through answering structural questions about a codebase from the CodeGraph index instead of a grep-and-read loop.

---

## 1. When to Use This Skill

Activate this skill when:
- Tracing who calls a symbol, what a function calls, or how one symbol reaches another.
- Checking the blast radius before modifying, renaming, or deleting an interface, class, or endpoint.
- Jumping to a definition, signature, or source without scanning directories.
- Mapping an unfamiliar area at the start of a session.
- Orienting in an unfamiliar codebase: start from the most connected symbols and the cluster map, not from the directory tree.
- Deciding whether a question is structural (graph) or textual (search): see the table in the reference.
- The user runs the `/codegraph` slash command.

*Boundary*: For configuration, documentation, and literal text (log messages, comments), use your search tool. For conceptual recall with no symbol name, use `agent-memory`.

*Method*: The graph-first heuristics in [Graph-First Exploration](./references/graph-first-exploration.md) hold for any symbol-graph backend; this skill's tool names are one such backend.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Confirm the Index
Consult: [CodeGraph Architecture & Reference Guide](./references/codegraph-guide.md)
1. List the CodeGraph tools connected to the session; tool names differ between server versions, so use the ones that are present.
2. If the server reports that the project is not initialised, build the index once from the project root:
   ```bash
   npx @colbymchenry/codegraph init -i
   ```

### Step 2: Ask the Graph First
1. Current servers expose one tool, `codegraph_explore`: pass a question or a list of symbol and file names; it returns the source of the relevant symbols with line numbers, the call path among them, and what depends on them.
2. Older servers expose separate tools; map the question to the tool:

| Question | Tool |
| :--- | :--- |
| Where is it defined, what is its signature | `codegraph_search`, `codegraph_node` |
| Who calls it, what does it call | `codegraph_callers`, `codegraph_callees` |
| What breaks if it changes | `codegraph_impact` |
| Several related symbols at once | `codegraph_explore` |
| Which files are indexed, is the index healthy | `codegraph_files`, `codegraph_status` |

3. For a flow question, name the symbols at both ends of the flow in one query rather than walking it call by call.

### Step 3: Act on the Result
1. Treat returned source as already read; edit from it without reopening the file.
2. Open a file only for a detail the graph did not return, at the cited lines.
3. After writing a file, wait a moment before querying it again; the index trails writes by about a second.

---

## 3. Verification Protocol

1. Every structural claim in the answer cites `file:line` taken from a graph result.
2. Before a rename or a signature change, the list of dependents was produced and each one is covered by the change.
3. No broad recursive grep or whole-file read was used for a question the graph answers.

---

## 4. ⚡ Token-Saving Execution Rule

- **One Call, Many Symbols**: Put every symbol of interest in a single query instead of one call per symbol.
- **No Re-Verification**: Do not repeat a graph result with a grep; the index comes from a full parse.
- **Pointers, Not Dumps**: Answer with `file:line` and the decisive lines only.
