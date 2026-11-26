# Privacy

Senior Developer Arsenal is a set of skills, subagents, rules, hooks and scripts that run on your machine inside your AI coding agent. It has no server, no account and no telemetry.

## What the plugin stores

- **Lessons ledger:** mistakes the agent records, in files inside your project and, for global lessons, in your home directory.
- **Usage stats:** the `usage-stats` skill keeps its counts in a local store on your machine. Nothing is uploaded.

You can read, edit or delete these files at any time.

## What leaves your machine

The plugin sends nothing to its author or to any service run by the project. Some scripts contact a service only when you run them and point them at it:

- `ci-wait`, `ship` and related scripts call GitHub through your own `gh` login.
- `payments-integrity` scripts call the payment gateway you configure.
- The optional `hindsight` and `codegraph` MCP servers are separate plugins. By default they run locally (`localhost` and a local command); what they store is set by those tools.

Your AI agent and its model provider handle your prompts and code under their own privacy terms. This plugin does not change that.

## Contact

Open an issue: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/issues
