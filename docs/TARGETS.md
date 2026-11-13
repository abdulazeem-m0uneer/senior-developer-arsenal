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
| `recommended_model: "fast"` | Claude `model: haiku`; Codex `model_reasoning_effort = "low"`; `inherit` everywhere else. For cheap read-only helpers such as `code-explorer`. |
| `recommended_model: "balanced"` | Claude `model: sonnet`; `inherit` everywhere else. For builders, reviewers and read-only checkers that should not run on the parent's top model. |

## Rules

Source: `.agents/rules/*.md` with `trigger` (`always_on`, `model_decision`, `glob`), `description`, and `globs` frontmatter. `globs` are required for `glob` and optional for `model_decision`.

| Agent | Format | Global | Project |
| :--- | :--- | :--- | :--- |
| Claude Code | `paths:` frontmatter for every rule with `globs` (`glob` rules and the `model_decision` rules, which all carry globs), none for the rest, so only `always_on` rules load every session; a rule without globs would too, and `build.py --validate` counts it against the always-on budget (sizes in [BENCHMARK.md](BENCHMARK.md)) | `~/.claude/rules/arsenal/` | `P/.claude/rules/arsenal/` |
| Cursor | `.mdc` with `description` / `globs` / `alwaysApply`; a `model_decision` rule keeps `description` only, so the model still chooses it | not file-based in Cursor | `P/.cursor/rules/` |
| GitHub Copilot | `.instructions.md` with `applyTo` (the rule's globs, `**` when it has none) | not installed | `P/.github/instructions/` |
| Windsurf | canonical file | not installed (global file is size-capped) | `P/.windsurf/rules/` |
| Antigravity | canonical file | `~/.gemini/config/rules/` | `P/.agents/rules/` |
| Codex CLI, OpenCode | canonical file, reached through the rules index in `AGENTS.md` | `~/.agents/rules/` | `P/.agents/rules/` |
| Gemini CLI | reached through `GEMINI.md` importing `AGENTS.md` | not installed | `P/GEMINI.md` block |

## Hooks

| Agent | Hook shipped | What it does |
| :--- | :--- | :--- |
| Claude Code (plugin) | `hooks/hooks.json`: `SessionStart` on `startup\|resume\|clear\|compact` | Runs `lessons.py active --hook` from the `lessons-learned` skill: prints the self-recording instruction, then the Active lessons of the project ledger (`.agents/lessons.md`) and of the global one (`$LESSONS_GLOBAL_FILE`, default `~/.agents/lessons.md`), at most 4,000 characters: the three most repeated first, the rest ranked by tag and word overlap with the paths in `git status` and the last five commits (two git reads in the session's `cwd`, 1.5 second timeout each; newest first when git is unavailable), and a `(+N more: lessons.py search <words>)` line when some did not fit. Prints `(no lessons yet)` after the instruction when both ledgers are empty or missing. Reads only; on any error prints nothing and exits 0. |
| Claude Code (plugin) | `hooks/hooks.json`: `SessionStart` (same entry, runs first) | Runs `hooks/session_core.py`: injects the static operating core from `hooks/core.md` (about 1,000 characters) so a plugin-only install uses the skills and tests its changes; rules cannot ship in a plugin. |
| Claude Code (plugin) | `hooks/hooks.json`: `UserPromptSubmit` | Runs `snapshot.py prompt` from the `handoff` skill: records the first user prompt (600 characters) and the last three (250 each) in a per-session file in the OS temp dir. Prints nothing, so it adds no context; no git, no subprocess; never fails the turn. |
| Claude Code (plugin) | `hooks/hooks.json`: `PreCompact`, and `SessionStart` on compact (same entry) | Runs `snapshot.py write` / `show` from the `handoff` skill: saves the original request, the latest user instructions, open todos (best effort: replayed from the session transcript, whose format is internal to Claude Code; a list that may be partial says so), pointers to `.plan-workspace/progress.md`, `.plan-workspace/*/progress.md`, `docs/plans/*.md` and this repository's handoff documents that exist, then branch, uncommitted files, recent commits and diff stat, to a per-session file in the OS temp dir (at most 4,000 characters, stamped with UTC time and repository), and re-injects it after compaction with its age. A failed git read shows as unavailable, not as a clean tree. Not shown in a different repository or on non-compact starts; writes nothing when there is neither a repository nor recorded task state; never fails the session. |
| Claude Code (plugin) | `hooks/hooks.json`: `SessionStart` on `startup\|resume\|clear` (second entry) | Runs `hooks/guard.py baseline`: records `HEAD` and the paths that are already dirty in a per-session file in the OS temp dir. Not run on compact, so the baseline survives compaction. Prints nothing. |
| Claude Code (plugin) | `hooks/hooks.json`: `PostToolUseFailure` and `PostToolUse` on `Bash` | Runs `hooks/guard.py track`: notes a test, build, lint or CI command that exited non-zero (observed on Claude Code 2.1.321: a non-zero exit arrives as `PostToolUseFailure`), one that passed, and a successful `lessons.py add` or `bump`. Prints nothing; no subprocess. |
| Claude Code (plugin) | `hooks/hooks.json`: `PreToolUse` (every tool) | Runs `hooks/guard.py pre`. For a destructive Bash command it prints a permission decision with a one-line reason naming the safer alternative: `deny` when `permission_mode` is `bypassPermissions`, `dontAsk` or `auto` (no human approves each call), `ask` in every other mode (what an unanswered `ask` does in a `-p` run is not documented for `PreToolUse` and was not observed). When a run limits file exists (`.claude/arsenal-run-limits.json`, see the `autonomous-run` skill) it counts the call and, once a limit is reached, denies every tool call except a `Write` or `Edit` of a `.md` file. Prints nothing for every other call; no subprocess; about 50 ms per tool call, nearly all of it Python start-up. `ARSENAL_GUARD_DESTRUCTIVE=allow` disables the destructive check only. |
| Claude Code (plugin) | `hooks/hooks.json`: `Stop` (not `SubagentStop`) | Runs `hooks/guard.py stop`: blocks the stop once, with a reason of a few hundred characters, when source files changed since the baseline and no test file did (up to 8 files named), or when a noted failure has neither a later passing run of the same check nor a lesson after it. Prints nothing otherwise, and nothing at all once a run limit is reached. Never asks twice about the same files or failures, and does nothing while `stop_hook_active` is true, so it cannot loop. Silent outside a git repository, when git fails, after a checkout or rebase away from the baseline, when a commit since the baseline is older than the session (a pull, a checkout of a branch that was already ahead), and in a working tree other than the baseline's. `ARSENAL_GUARD=off` disables it. |
| Claude Code without the plugin, OpenCode, Windsurf | none | Claude Code gets the hooks from the plugin (a settings.json copy would run each handler twice). OpenCode has a JavaScript plugin API and no command hooks. Windsurf's hook documentation describes another product's file. Wire by hand (`.claude/settings.json` snippet) or add one line to `AGENTS.md`; see the `lessons-learned` skill reference, section 5. |
| Codex, Gemini CLI, Cursor, Copilot, Antigravity | `install.sh --hooks` / `install.ps1 -Hooks`, see the table below | Session-start and stop gate only. |

The hooks need `python3` (or `python`) on `PATH`. The `lessons-learned` and operating core hooks read and print only. The snapshot hooks write two files per session, `arsenal-snapshot-<session_id>.md` and `arsenal-snapshot-<session_id>.prompts.json`, in the OS temp dir (owner-only where the OS supports it, never inside the project); the second holds truncated copies of your prompts. The guard hooks write a third, `arsenal-snapshot-<session_id>.guard.jsonl`, in the same place: the baseline commit, repository root, start time and dirty paths, the first 80 characters of each failed check command, the names of the checks that failed and passed, what was already asked, and, only while a run limits file exists, one timestamp per tool call. The guard is the only hook that can block or deny. Claude Code gets all of it from the plugin; the other agents get only the two ported events below, through `hooks/agent_hook.py`. `PreToolUse` (destructive commands, run limits), `track` (the failed-check record), compaction snapshots and `UserPromptSubmit` are not ported, so on those agents the Stop gate sees source changes without tests but never a failed check.

The guard classifies by path, and a change is a file added or edited since the baseline: deletions, pure renames and mode changes are not changes. Source is a code extension (`.py`, `.ts`, `.cs`, `.go`, `.rs`, `.java` and the like); a test is such a file named like one (`test_*`, `*_test.go`, `*.test.ts`, `*.spec.ts`, `*.cy.ts`, `*Tests.cs`) or any file, whatever its extension, under a test directory (`tests/`, `__tests__/`, `__mocks__/`, `testdata/`, `e2e/`, a top-level `spec/`). Ignored: docs, lockfiles, shell, SQL, config in a data format, config and tooling files written in code (`*.config.*`, `*.stories.*`, `setup.py`, `conf.py`, `noxfile.py`, dotfiles, `.storybook/`), migrations, and generated or vendored paths (`dist/`, `vendor/`, `node_modules/`, and `build/`, `out/`, `target/` at the top level). A failed check is recognised by its command (`pytest`, `npm test`, `make test`, `python3 tests/x.py`, `script --check` and the like, also behind `env`, `timeout` or `docker compose run`); text inside quotes is not read, so `bash -c "pytest"` is not seen. Known limits: a test file that was already dirty when the session started does not count as a test change, tests written inline in a source file (Rust `#[cfg(test)]`) are not seen, a file renamed with plain `mv` (not `git mv`) counts as a new file, commits pulled during the session that were made after it started count as changed, and a pipeline that hides the exit code (`pytest | tail`) hides a failure of its own, though it no longer counts as a pass: a check followed by a pipe, `||`, `;`, `&` or another command, or run with `--version` or `--help`, clears nothing. `ruff check`, `ruff format` and the other subcommands of `ruff`, `biome` and `pre-commit` are different checks. Each of these costs at most one question, answered in one sentence. A failure is dropped when the same check passes later in the session, so red-first TDD is not asked about. The same check means the recognised tool and subcommand, or the script path, without wrappers, directory prefix, interpreter and flags: `cd api && python3 -m pytest -x tests/a.py` and `pytest -q` are one check, `python3 tests/a.py` and `python3 tests/b.py` are two, and a command that runs several checks is dropped when each has passed. So a narrower passing run clears a wider failed one, which costs a missed question and never a wrong block.

The destructive-command check reads the program in command position after splitting the command at `;`, `&`, `|`, parentheses and newlines and skipping wrappers (`sudo`, `env`, `timeout`, `VAR=x`), so `echo "git push --force"` and a grep for the words are not hits. Listed: `git push` with `--force`, `-f`, `--mirror` or a `+refspec` anywhere, and with `--force-with-lease` or a branch deletion when the target is the remote's default branch or a protected name (`main`, `master`, `develop`, `release/*` and the like; the current branch is read from `.git/HEAD`); `git reset --hard`; `git clean -f` without `-n`; `git checkout -f`, `git checkout .` and `git restore .`; `git branch -D`; recursive `rm` and `chmod -R 777` on `/`, a top-level directory, `~`, `$HOME`, a repository root or its `.git`, `.`, `..`, `*` or a glob of one of these; `DROP DATABASE/TABLE/SCHEMA` and `TRUNCATE` given to `psql`, `mysql`, `mariadb`, `sqlcmd` or `sqlite3` as an argument, on a pipe or in a here-document, plus `dropdb` and `mysqladmin drop`; `terraform destroy` (also `tofu`, `terragrunt`, `apply -destroy`); `kubectl delete` of a namespace or with `--all`; `docker system prune --volumes`; `dd of=/dev/...` and `mkfs` on a device. The script given to `sh -c` or `eval` is read too. Not seen: a command built from variables or run through `xargs`, `find -exec`, `ssh` or a script file, command substitution inside double quotes, SQL in a file (`psql -f`), and anything after an unbalanced quote. It is a seat belt for the common accident, not a sandbox: keep permission rules and branch protection.

### Hooks for the other agents (`--hooks`)

`./install.sh --global|--project --target <list> --hooks` (`install.ps1 -Hooks`) copies `hooks/*.py`, `hooks/core.md` and `steps.json` (generated from `hooks/hooks.json` by `scripts/build_hooks.py` into `dist/hooks/`) to `<skills dir>/../arsenal-hooks/` and merges one marked entry per event into the target's hook file with `scripts/hooks_merge.py` (a `.bak-*` copy first; uninstall removes only that entry). Every run of the adapter prints nothing when there is nothing to say and always exits 0. Needs `python3` or `python`.

"Documented" means the vendor page below describes the file, the event name and the output field the adapter uses; it was checked by reading that page in the review phase of this change. "Verified live" means a real run of the product: **no for every row**, no hook was run inside any of these tools, only the adapter was run with their input shapes (`tests/test_agent_hooks.py`, `tests/smoke.sh`).

| Target | Config file (global / project) | Event: what runs | Output the adapter prints | Documented | Documentation | Verified live |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Codex CLI | `~/.codex/hooks.json` / `.codex/hooks.json` (project hooks load only in a trusted project) | `SessionStart`: operating core and lessons. `Stop`: test and lesson gate | `hookSpecificOutput.additionalContext`; Stop `{"decision":"block","reason"}` | yes | https://learn.chatgpt.com/docs/hooks (the page names `additionalContext` for SessionStart, not for Stop) | no |
| Gemini CLI | `~/.gemini/settings.json` / `.gemini/settings.json` | `SessionStart`: as above. `AfterAgent`: the gate | `hookSpecificOutput.additionalContext`; `{"decision":"deny","reason"}`; timeout in milliseconds | events, fields and decision: yes. The settings.json paths: not named on that page | https://geminicli.com/docs/hooks/reference/ | no |
| Cursor | `~/.cursor/hooks.json` / `.cursor/hooks.json` | `sessionStart`: as above. `stop`: the gate (`loop_count` above 0 counts as `stop_hook_active`) | `{"additional_context"}`; `{"followup_message"}` | yes, with a caveat: the page calls `sessionStart` fire-and-forget yet lists `additional_context`, so context injection is unconfirmed | https://cursor.com/docs/hooks | no |
| GitHub Copilot | `~/.copilot/hooks/arsenal.json` / `.github/hooks/arsenal.json` | `sessionStart`: as above. `agentStop`: the gate | `{"additionalContext"}`; `{"decision":"block","reason"}`; `bash`, `powershell`, `timeoutSec` | yes | https://docs.github.com/en/copilot/reference/hooks-configuration | no |
| Antigravity | `~/.gemini/config/hooks.json` / `.agents/hooks.json` (the file maps a hook name to its events) | `SessionStart`: as above. `Stop`: the gate | SessionStart `injectSteps`; Stop `{"decision":"continue","reason"}` | file, events and Stop decision: yes. The shape of an `injectSteps` step: not documented there. A forum report says Stop hooks in project `.agents/hooks.json` never fire in Antigravity IDE 1.107.0 on Windows | https://antigravity.google/docs/hooks/ | no |

Not ported on any of them: `PreToolUse`, `track`, compaction snapshots, `UserPromptSubmit`, the run-limit guard. Targets with no hook config: Claude Code through the installer, OpenCode, Windsurf (see above).

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

## Safety rules

| Situation | Behavior |
| :--- | :--- |
| Destination exists and was not created by the installer | Skipped and reported; `--force` replaces it. |
| Instruction file is a symlink (for example `CLAUDE.md -> AGENTS.md`) | Skipped; add the block to the link target yourself if you want it. |
| Instruction file is not UTF-8, or its block markers are duplicated or reversed | Skipped and left byte for byte unchanged. |
| Instruction file uses CRLF line endings or a UTF-8 BOM | The block is written with the same line endings and the BOM is kept. |
| A parent folder of the destination is a link into the arsenal repository | Skipped on install and on uninstall, so the arsenal sources are never modified. |
| Install record contains an absolute path, an empty path, or `..` | The entry is dropped and nothing is deleted for it. |
| Project path is the home directory or the arsenal repository | Refused. |

## Ownership and uninstall

Each install records what it created in a state file: `~/.config/senior-developer-arsenal/manifest` (global) or `P/.agents/.arsenal-manifest` (project). Uninstall removes only recorded paths, keeps paths another installed target still needs, strips the marked blocks, and removes directories it leaves empty. MCP entries are left in place.

## Not verified against a live install

These follow each vendor's published documentation but were not exercised against the running product: the Antigravity subagent directory and MCP config path, the OpenCode global config filename, the Windsurf MCP config path, the Hindsight HTTP MCP endpoint, and every hook in the table under Hooks for the other agents (none was run inside its tool). Adjust `scripts/build.py` (`AGENT_DESTINATIONS`, `MCP_DESTINATIONS`) if your version differs.
