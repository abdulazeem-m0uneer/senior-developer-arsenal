# Contributing

## Golden rule

Edit `.agents/` only. Everything under `dist/`, `plugins/`, and `.claude-plugin/` is generated.

```bash
python3 scripts/build.py --validate   # lint the sources
python3 scripts/build.py              # regenerate dist/, plugins/, .claude-plugin/
git add -A                            # commit sources and generated output together
```

CI fails when the generated output is stale (`python3 scripts/build.py --check`).

## Source formats

| Artifact | Location | Format |
| :--- | :--- | :--- |
| Skill | `.agents/skills/<name>/SKILL.md` | Frontmatter with exactly `name` (equal to the folder) and a single-quoted `description`; references in `references/`, bundled scripts in `scripts/`. Links must stay inside the skill folder. |
| Rule | `.agents/rules/<name>.md` | Frontmatter `trigger` (`always_on`, `model_decision`, `glob`), single-quoted `description`, and `globs` (comma-separated, required for `glob`). |
| Subagent | `.agents/subagents/subagent-definitions.json` + `prompts/<name>.md` | JSON entry plus a plain-markdown prompt without frontmatter. |
| MCP server | `.agents/mcp/servers.json` | `type: stdio` (`command`, `args`) or `type: http` (`url`). |

Use the `create-skill` skill to scaffold a new skill. Keep wording agent-neutral: no product names or product-specific tool names inside skills, rules, or prompts.

## Standards for code in this repository

- SOLID, small single-purpose functions, no dead code.
- No file over 1000 lines (enforced by `build.py --validate`).
- Every change ships with tests.
- `install.sh` and `install.ps1` must stay behaviorally identical; change both and both smoke tests.
- Installer changes that delete or rewrite user files need a regression test in `tests/smoke.sh` and `tests/smoke.ps1` that proves user data survives.

## Running the tests

```bash
python3 scripts/build.py --validate && python3 scripts/build.py --check
python3 -m unittest discover -s tests -p "test_*.py"
python3 tests/check_formats.py        # needs PyYAML
bash tests/smoke.sh
pwsh -NoProfile -File tests/smoke.ps1 # also runs on Windows PowerShell 5.1 in CI
```

## Adding a target agent

1. Add its paths to `AGENT_DESTINATIONS` / `MCP_DESTINATIONS` and its formats to `render_agent` / `render_rule` / `render_mcp` in `scripts/build.py`.
2. Add the name to the target list in `install.sh`, `install.ps1`, and both smoke tests.
3. Document it in `docs/TARGETS.md` and the README table.

## Releases

Bump `VERSION`, run `python3 scripts/build.py`, and commit with a Conventional Commit message. Claude Code plugin users receive the update when the version changes.
