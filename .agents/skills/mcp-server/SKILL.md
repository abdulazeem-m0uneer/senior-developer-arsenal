---
name: mcp-server
description: 'Builds a tool server that lets agents call an outside API or service through well-named, schema-validated, paginated, annotated tools, then proves it with read-only evaluation questions an agent must answer through the tools alone. Use when the user asks to expose a service, database, or internal API to agents as tools, or runs /mcp-server. Triggers on: "build an MCP server", "expose this API to agents", "write tools for the agent", "tool server", "/mcp-server". Do not use for wrapping a provider inside the application (use provider-sdk) or designing the HTTP API of the application itself (use api-design).'
---

# Agent Tool Server Procedure

This skill guides the agent through designing, implementing, and evaluating a server that exposes an outside service to agents as tools, measured by whether an agent can finish real tasks through those tools.

---

## 1. When to Use This Skill

Activate this skill when:
- An external API, database, or internal service must become callable by agents as tools.
- An existing tool server returns too much, names tools ambiguously, or fails the agent on errors.
- The user runs the `/mcp-server` slash command.

*Boundary*: A provider called from the application's own code with a mock mode is `provider-sdk`. The application's own endpoint contracts are `api-design`. Writing the tool server's reference page is `docs-writer`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Plan the Tool Surface
Consult: [Tool Design Checklist](./references/tool-design-checklist.md)
1. Read the service's API reference and list the endpoints by how often a human task needs them; implement the common operations first.
2. Prefer broad coverage of the API over a few bespoke workflow tools; an agent composes basic tools, and it cannot compose what is missing. Add a workflow tool only when the same multi-call sequence recurs.
3. Name every tool `<service>_<verb>_<resource>` in snake case; other servers will be loaded beside this one.
4. Choose the transport: standard input/output for a local single-user server (never log to standard output there), streamable HTTP for a remote or multi-client one; the older server-sent-events transport is deprecated.

### Step 2: Implement
1. One shared client with authentication from environment variables, one error helper, one response formatter, one pagination helper. Tools call these; no logic is duplicated across tools.
2. Each tool: a strict input schema with constraints and per-field descriptions (and examples where the shape is not obvious), an output schema or structured content where the framework supports it, a description that states exactly what it does and returns, and the four behaviour annotations (read-only, destructive, idempotent, open-world).
3. Every list tool takes `limit` and an offset or cursor, defaults to 20–50 items, and returns `has_more`, the next position, and the total when cheap.
4. Every response passes through a character cap (around 25,000); over the cap, return the first half of the items, `truncated: true`, and a message saying how to narrow the query.
5. Errors are returned inside the tool result, not as protocol errors, and say what to try next ("add `status=active` to reduce results"). Internal details stay in the server log.
6. Validate paths, URLs, identifiers, and sizes; bind local HTTP servers to the loopback address and check the `Origin` header.

### Step 3: Evaluate With Questions, Not Unit Tests
Consult: [Evaluation Questions](./references/evaluation-questions.md)
1. Build and run the server; open it in an inspector client and list the tools.
2. Explore the real data with read-only calls, then write ten questions a human would ask of this service that need several tool calls, paging, and reasoning to answer, each with one short verifiable answer that will not change.
3. Hand the questions to a fresh agent with only the server attached. Each miss is a finding against the server (a missing tool, an oversized response, an unclear name), not against the agent.

---

## 3. Verification Protocol

```bash
npm run build && node dist/index.js --help            # or: python -m py_compile server.py
npx @modelcontextprotocol/inspector                   # tools listed with title, description, schema, annotations
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Naming | Tool named `search` with no service prefix | Collides with another server's tool | `[Blocker]` | Rename `<service>_search_<resource>` |
| Output | List tool returns the whole collection | Context overflow, truncated silently by the client | `[Blocker]` | `limit`, cursor, character cap with a narrowing hint |
| Schema | Free-form string where an enum exists | Agent guesses values, calls fail | `[High]` | Closed set with descriptions |
| Errors | Protocol error on a 404 | Agent cannot recover or retry | `[High]` | Result-level error with the next step |
| Eval | Fewer than 7 of 10 questions answered | Surface or responses do not serve real tasks | `[High]` | Fix the tool each miss points at, rerun |

---

## 4. ⚡ Token-Saving Execution Rule

- **Fetch Docs on Demand**: Load the protocol and SDK pages only for the step that needs them; never paste them into the reply.
- **One Tool, One Snippet**: Show one complete tool as the pattern; list the rest as names and schemas.
- **Eval Table Only**: Report the ten questions as a pass/fail table with the failing tool named.
