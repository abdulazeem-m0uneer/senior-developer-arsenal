# Tool Design Checklist

What makes a tool usable by an agent, in the order the agent meets it: name, description, schema, result, error.

---

## 1. Naming

| Rule | Example |
| :--- | :--- |
| Snake case, service prefix, verb, resource | `github_create_issue`, `slack_list_channels` |
| Server name: `<service>_mcp` (Python) or `<service>-mcp-server` (Node), no version number | `jira_mcp`, `jira-mcp-server` |
| One action per tool; no `manage_*` catch-alls | `*_get`, `*_list`, `*_search`, `*_create`, `*_update`, `*_delete` |

## 2. Description

- [ ] States narrowly what the tool does and returns; matches the implementation exactly.
- [ ] Names the return shape (fields, types) and gives one example value where the shape is not obvious.
- [ ] Says when to use a sibling instead ("for full-text search use `*_search`").

## 3. Input Schema

- [ ] Strict: unknown keys rejected.
- [ ] Each field has a description, a type, and constraints (min/max length, range, enum). Constraint messages say what was expected and what arrived.
- [ ] Closed sets are enums, never free strings. Identifiers say which identifier (`channel_id`, not `id`).
- [ ] `response_format: "markdown" | "json"` on tools that return data; markdown (default) for reading, JSON for processing.
- [ ] List tools: `limit` (default 20–50), `offset` or `cursor`, filters for every large collection.

## 4. Result

- [ ] Markdown: human-readable, timestamps converted, display names with ids in parentheses, verbose metadata omitted.
- [ ] JSON: every field and metadata, consistent names and types.
- [ ] Pagination metadata: `has_more`, `next_offset` or `next_cursor`, `total_count` when cheap.
- [ ] Character cap (about 25,000): over it, halve the items, set `truncated: true`, say how to narrow (a filter, a smaller `limit`).
- [ ] Structured content alongside text where the SDK supports it.

## 5. Annotations

| Annotation | Set true when |
| :--- | :--- |
| `readOnlyHint` | The tool changes nothing |
| `destructiveHint` | A call can delete or overwrite (default assumption: true) |
| `idempotentHint` | Repeating the same call changes nothing further |
| `openWorldHint` | The tool reaches outside systems (default assumption: true) |

Hints inform the client; they are not security. Never let a client's trust in a hint replace server-side checks.

## 6. Errors

- [ ] Returned in the result (`isError: true`), not as protocol errors, so the agent can read and recover.
- [ ] Message: what failed, what was expected, what to try next.
- [ ] Internal stack traces and upstream bodies stay in the server log.
- [ ] Timeouts and connection failures handled on every network call; resources released on error.

## 7. Transport and Security

- [ ] stdio: local, single user, logs to stderr only.
- [ ] Streamable HTTP: remote, several clients; stateless JSON unless sessions are needed. Local HTTP binds to `127.0.0.1` and validates `Origin`.
- [ ] Credentials from environment variables, validated at startup, never in code or responses.
- [ ] Paths, URLs, and identifiers validated; no shell interpolation of inputs.

## 8. Code Shape

- [ ] One API client, one error helper, one formatter, one pagination helper, shared by all tools.
- [ ] Full typing (no `any`; `unknown` plus narrowing), explicit async return types, type guards in error handling.
- [ ] Build produces a runnable entry point; `--help` runs without a network.
- [ ] Resources (URI-addressed, read-only data) for static or template data; tools for operations with validation or side effects.
