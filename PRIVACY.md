# Privacy

Senior Developer Arsenal is a set of skills, subagents, rules, hooks and scripts that run on your machine inside your AI coding agent. It has no server, no account and no telemetry.

## What the plugin stores

Everything below stays on your machine. You can read, edit or delete these files at any time.

- **Usage stats** (`~/.agents/arsenal-usage.jsonl`, or `$ARSENAL_USAGE_FILE`). A `SessionEnd` hook, on by default, reads the session's Claude Code transcript (and its subagent transcripts) to derive one line per session where the arsenal was active. That line holds: the session ID, its first and last dates, a 12-character project ID (a hash of the working directory with a random salt kept beside the store in `arsenal-usage.jsonl.salt`), the Claude Code and arsenal versions, the names and call counts of skills and subagents used, lesson IDs, token counts (input, output, cache), and counts of blocks, guard denials, checks and edits. It never stores a prompt, command, path, output or code. Turn it off with `ARSENAL_USAGE=off`.
- **Lessons ledgers** (`.agents/lessons.md` in the project, `~/.agents/lessons.md` for global lessons): the mistake, cause and rule text the agent records.
- **Lessons evidence** (`~/.agents/lessons-evidence.jsonl`, or `$LESSONS_EVIDENCE_FILE`): when a lesson is added or bumped, up to three failed commands that preceded it. Credential values are masked and secret-looking fields are withheld; the file stops at 5 MB. Turn it off with `LESSONS_EVIDENCE=off`.

## What leaves your machine

The plugin sends nothing to its author or to any service run by the project. Some scripts contact a service only when you run them and point them at it:

- `ci-wait`, `ship` and related scripts call GitHub through your own `gh` login.
- `payments-integrity` scripts call the payment gateway you configure.
- The optional `hindsight` and `codegraph` MCP servers are separate plugins. By default they run locally (`localhost` and a local command); what they store is set by those tools.

Your AI agent and its model provider handle your prompts and code under their own privacy terms. This plugin does not change that.

## Contact

Open an issue: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/issues
