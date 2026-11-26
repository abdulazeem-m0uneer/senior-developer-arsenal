# Agent Configuration Rules

Read in Step 4b of the security-audit skill. The script is `scripts/agent_config_scan.py`. An agent's hooks and MCP servers run with the developer's own rights on every session, so a bad entry there is code execution, not a style issue.

| Severity | Rule | Example that fires | Fix |
| :--- | :--- | :--- | :--- |
| high | `remote-exec` | a remote script piped into a shell in a hook or MCP command; a PowerShell download-and-execute | Vendor the script into the repository, pin it by hash, and run the local copy. |
| high | `secret` | `"env": {"YOUR_TOKEN_NAME": "YOUR_TOKEN"}` in `.mcp.json` | Reference an environment variable instead of the value, rotate the leaked value, and purge it from git history. |
| high | `bypass-default` | `"defaultMode": "bypassPermissions"`; Codex `sandbox_mode = "danger-full-access"` | Keep the default mode; grant narrow allow rules instead. |
| medium | `broad-allow` | `Bash`, `Bash(*)`, `*`, `Bash(curl:*)`, `Bash(sudo:*)`, `Bash(python3:*)` | Allow the exact commands the project runs (`Bash(npm test:*)`). |
| medium | `unpinned-mcp` | a package runner with no version, a `latest` tag, a uv tool run with no version | Pin the version (`some-server@1.4.2`, `tool==1.4.2`), so a hijacked release cannot run unasked. |
| medium | `insecure-mcp` | a remote server `url` that starts with `http://` | Use `https://`. Plain HTTP is accepted only for localhost. |
| medium | `temp-path-hook` | a hook running `bash /tmp/check.sh` or writing to `$TMPDIR` | Ship the script with the project or plugin; any local user can replace a file in a world-writable path. |
| medium | `no-approval` | Codex `approval_policy = "never"` | Use `on-request` or `untrusted` outside a sandboxed CI runner. |
| low | `all-project-mcp` | `"enableAllProjectMcpServers": true` | Approve project servers one by one (`enabledMcpjsonServers`). |
| low | `unparseable` | a config file that is not valid JSON or TOML | Fix the file: the agent may be ignoring it silently. |

## Notes

- Secrets come from the repo's single detector (`lessons-learned/scripts/ledger_store.py`): known token shapes, key, password or token assignments, and long random strings. A random identifier under an id-named key (`machineID`, `userId`, `uuid`) is not a secret. A token shape under any key still is.
- Line numbers point at the first place the offending value appears in the file.
- Files read: `.claude/settings.json`, `.claude/settings.local.json`, `.mcp.json`, `hooks.json` files up to three directories deep (vendored directories skipped), `.cursor/mcp.json` and `hooks.json`, `.codex/config.toml` and `hooks.json`, `.gemini/settings.json`, `.vscode/mcp.json`, `.agents/hooks.json`. With `--user`: `~/.claude/settings.json`, `~/.claude.json` (including its per-project servers), `~/.codex/config.toml`, `~/.gemini/settings.json`, `~/.cursor/mcp.json`.
