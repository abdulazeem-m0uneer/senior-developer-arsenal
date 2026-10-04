# Supported Agents and Install Paths

`.agents/` is the single source of truth. `scripts/build.py` converts it into each agent's native format under `dist/`, and `dist/manifest.tsv` lists exactly what each installer places where. This page is the human-readable version of that manifest.

`~` is the home directory (`%USERPROFILE%` on Windows). `P` is the project root.

## Skills

Skills need no conversion: every `SKILL.md` follows the [Agent Skills standard](https://agentskills.io/specification).

| Agent | Global | Project |
| :--- | :--- | :--- |
| Claude Code | `arsenal` plugin | `arsenal` plugin |
| Codex CLI, OpenCode, Cursor, Windsurf, GitHub Copilot, Gemini CLI | `~/.agents/skills/<name>/` | `P/.agents/skills/<name>/` |
| Antigravity | `~/.gemini/config/skills/<name>/` | `P/.agents/skills/<name>/` |

## Subagents

Source: `.agents/subagents/subagent-definitions.json` plus `prompts/<name>.md`.

| Agent | Generated format | Global | Project |
| :--- | :--- | :--- | :--- |
| Claude Code | Markdown, `name` / `description` / `model` / `disallowedTools` | `arsenal` plugin | `arsenal` plugin |
| Codex CLI | TOML, `developer_instructions` / `sandbox_mode` | `~/.codex/agents/` | `P/.codex/agents/` |
| OpenCode | Markdown, `mode: subagent` / `permission` | `~/.config/opencode/agents/` | `P/.opencode/agents/` |
| Cursor | Markdown, `readonly` | `~/.cursor/agents/` | `P/.cursor/agents/` |
| GitHub Copilot | `<name>.agent.md`, `tools` | `~/.copilot/agents/` | `P/.github/agents/` |
| Antigravity | Markdown, `model: pro\|inherit` | `~/.gemini/config/agents/` | `P/.agents/agents/` |
| Gemini CLI | Markdown | `~/.gemini/agents/` | `P/.gemini/agents/` |
| Windsurf | no custom subagent format | not installed | not installed |

Mapping from the source manifest:

| Source field | Effect |
| :--- | :--- |
| `enable_write_tools: false` | Claude `disallowedTools: Write, Edit, NotebookEdit`; Cursor `readonly: true`; OpenCode `permission.edit: deny`; Codex `sandbox_mode = "read-only"`; Copilot `tools` without `edit`. |
| `recommended_model: "pro"` | Antigravity `model: pro`; Codex `model_reasoning_effort = "high"`; `inherit` everywhere else. |

## Rules

Source: `.agents/rules/*.md` with `trigger` (`always_on`, `model_decision`, `glob`), `description`, and `globs` frontmatter.

| Agent | Format | Global | Project |
| :--- | :--- | :--- | :--- |
| Claude Code | `paths:` frontmatter for glob rules, none for the rest | `~/.claude/rules/arsenal/` | `P/.claude/rules/arsenal/` |
| Cursor | `.mdc` with `description` / `globs` / `alwaysApply` | not file-based in Cursor | `P/.cursor/rules/` |
| GitHub Copilot | `.instructions.md` with `applyTo` | not installed | `P/.github/instructions/` |
| Windsurf | canonical file | not installed (global file is size-capped) | `P/.windsurf/rules/` |
| Antigravity | canonical file | `~/.gemini/config/rules/` | `P/.agents/rules/` |
| Codex CLI, OpenCode | canonical file, reached through the rules index in `AGENTS.md` | `~/.agents/rules/` | `P/.agents/rules/` |
| Gemini CLI | reached through `GEMINI.md` importing `AGENTS.md` | not installed | `P/GEMINI.md` block |

## Instruction files

A marked block (`<!-- BEGIN senior-developer-arsenal -->` ... `<!-- END senior-developer-arsenal -->`) is added to, never substituted for, these files:

| File | Targets | Content |
| :--- | :--- | :--- |
| `P/AGENTS.md` | all | The arsenal `AGENTS.md`. |
| `P/CLAUDE.md` | claude | `@AGENTS.md` import. |
| `P/GEMINI.md` | gemini | `@./AGENTS.md` import. |
| `~/.codex/AGENTS.md` | codex (global) | The arsenal `AGENTS.md`. |
| `~/.config/opencode/AGENTS.md` | opencode (global) | The arsenal `AGENTS.md`. |

## MCP servers

Source: `.agents/mcp/servers.json`. Registered only with `--codegraph` / `--hindsight`.

| Agent | Global config | Project config | Root key |
| :--- | :--- | :--- | :--- |
| Claude Code | `arsenal-codegraph` / `arsenal-hindsight` plugins | `P/.mcp.json` | `mcpServers` |
| Codex CLI | `~/.codex/config.toml` | `P/.codex/config.toml` | `[mcp_servers.<name>]` |
| OpenCode | `~/.config/opencode/opencode.json` | `P/opencode.json` | `mcp` |
| Cursor | `~/.cursor/mcp.json` | `P/.cursor/mcp.json` | `mcpServers` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | none | `mcpServers` |
| GitHub Copilot | `~/.copilot/mcp-config.json` (Copilot CLI) | `P/.vscode/mcp.json` (VS Code) | `mcpServers` / `servers` |
| Antigravity | `~/.gemini/config/mcp_config.json` (and `~/.gemini/antigravity/mcp.json` when it already exists) | `P/.agents/mcp_config.json` | `mcpServers` |
| Gemini CLI | `~/.gemini/settings.json` | `P/.gemini/settings.json` | `mcpServers` |

Merge guarantees: existing entries are preserved, a timestamped `.bak-*` copy is written before any change, and a file that cannot be parsed is left untouched with the snippet printed for manual use. Config files containing comments (JSONC) count as unparseable. For Codex, a table that already exists is never rewritten.

## Ownership and uninstall

Each install records what it created in a state file: `~/.config/senior-developer-arsenal/manifest` (global) or `P/.agents/.arsenal-manifest` (project). Uninstall removes only recorded paths, keeps paths another installed target still needs, strips the marked blocks, and removes directories it leaves empty. MCP entries are left in place.

## Not verified against a live install

These follow each vendor's published documentation but were not exercised against the running product: the Antigravity subagent directory and MCP config path, the OpenCode global config filename, the Windsurf MCP config path, and the Hindsight HTTP MCP endpoint. Adjust `scripts/build.py` (`AGENT_DESTINATIONS`, `MCP_DESTINATIONS`) if your version differs.
