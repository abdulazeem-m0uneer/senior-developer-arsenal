# Graph-First Exploration: When a Graph Beats Grep

Adapted from safishamsi/graphify (Apache-2.0).

---

## 1. Why a Graph, Not a Keyword Search

A keyword search returns every file that mentions a term; a graph returns the few nodes that are structurally related to it and the edges between them. Reading the raw files costs the same tokens on every question; the graph is paid for once and every later query reads a compact subgraph. The saving compounds with corpus size: on a handful of files the value is structural clarity, not compression; past a few dozen files the per-query cost drops by an order of magnitude.

| Question | Keyword search answers it | Graph answers it |
| :--- | :---: | :---: |
| Where does the string `X` appear | yes | no |
| Where is symbol `X` defined, who calls it | partly, with noise | yes |
| How does `A` reach `B` (the path, with the hops) | no | yes |
| Which modules form one cluster and which node bridges two clusters | no | yes |
| Which symbols are most connected (the "god nodes" that everything depends on) | no | yes |
| What breaks if `X` changes (transitive dependents) | no | yes |
| What does a comment, log line, or configuration value say | yes | no |

Rule: a question about *relationships* goes to the graph first; a question about *text* goes to the search tool. For config, docs, and literals the graph has nothing to add.

---

## 2. The Three Query Shapes

Whatever backend holds the graph, three question shapes cover almost every structural ask. Phrase the question in one of them before touching a tool:

1. **Query** — a natural question about a concept or area ("what connects authentication to the database pool"). Returns a scoped subgraph: the matching nodes, their neighbours, and the edges.
2. **Path** — two named symbols ("`UserService` to `DatabasePool`"). Returns the chain of hops and which cluster boundaries it crosses. Use this for "how does a request get from here to there" instead of walking calls one by one.
3. **Explain** — one named symbol. Returns its definition, callers, callees, and the cluster it belongs to.

Name the symbols at both ends of a flow in one call. Walking hop by hop is the grep loop in disguise.

---

## 3. Reading a Graph Report

A built graph usually comes with a summary. Read only these three sections before exploring; the rest is on demand:

- **God nodes**: the most connected symbols. They are the architecture's load-bearing walls: change them last, test them first, and start an unfamiliar-codebase orientation from them rather than from the directory tree.
- **Clusters (communities)**: groups with dense internal edges. Each is a candidate module boundary; a cluster that does not match a directory is a finding in itself (hidden coupling or a mis-filed file).
- **Surprising connections**: edges that bridge two clusters, cross file types (code to document), or link a leaf node to a hub. These are where cross-cutting concerns, undocumented dependencies, and accidental coupling live. Pick the one that crosses the most boundaries as the first question to trace.

Treat edge provenance as evidence quality. A graph built by parsing marks edges as *extracted* (seen in the source: a call, an import) or *inferred* (a tool or model guessed it, with a confidence score). Cite an extracted edge as fact; cite an inferred one as a hypothesis to confirm at the cited line.

---

## 4. Session Discipline

- When an index exists, query it before the first search or source read for any structural question, and put the same rule in the prompt of every subagent that explores code.
- Read raw files only at lines the graph (or an earlier read) already located.
- After editing code, refresh the index incrementally before querying it again; an index that trails the working tree gives confident wrong answers.
- A committed index file is rewritten whole on every build. A large diff to it in a pull request is expected churn, not a review finding.
- Exploration is finished when the question is answered with `file:line` citations, not when the whole graph has been seen.

---

## 5. Blast Radius Before a Change

Before renaming, deleting, or changing the signature of a symbol: ask the graph for its transitive dependents over the call, import, re-export, inheritance, and dynamic-import relations, to a bounded depth (start at 2). Dynamic imports are the hops a keyword search misses most often; they are exactly how codebases break require cycles, so the missing edge tends to sit under the most load-bearing module. Every dependent returned must be covered by the change or named as out of scope.

---

## 6. Optional Backends

Any tool that builds a symbol graph and answers the three query shapes qualifies. Two that do:

| Backend | Build | Query | Path | Explain | Impact | Refresh |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| CodeGraph (MCP) | `codegraph init -i` | `codegraph_explore` | `codegraph_explore` with both ends | `codegraph_node` | `codegraph_impact` | automatic, ~1 s lag |
| graphify (CLI, optional MCP) | `graphify .` | `graphify query "<q>"` | `graphify path "<A>" "<B>"` | `graphify explain "<X>"` | `graphify affected "<X>" --depth 2` | `graphify update .` |

graphify also parses documents and diagrams into the same graph, so a question such as "which design note describes this module" can be answered from one index; CodeGraph indexes code only. Choose by what is installed; the method above is the same for both.

---
