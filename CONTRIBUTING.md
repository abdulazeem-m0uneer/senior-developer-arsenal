# Contributing

## Golden rule

Edit `.agents/` only. Everything under `dist/`, `plugins/`, `agents/`, and `.claude-plugin/` is generated.

```bash
python3 scripts/build.py --validate   # lint the sources
python3 scripts/build.py              # regenerate dist/, plugins/, agents/, .claude-plugin/
git add -A                            # commit sources and generated output together
```

CI fails when the generated output is stale (`python3 scripts/build.py --check`).

`docs/BENCHMARK.md` is generated too. It reports the context every session pays for (skill and subagent listings, session-start hook output, unconditional rules), so regenerate it after changing a skill or subagent description, a rule, `AGENTS.md`, `hooks/hooks.json` or a hook script:

```bash
python3 scripts/token_benchmark.py           # rewrite docs/BENCHMARK.md (offline, about 2 seconds)
python3 scripts/token_benchmark.py --check   # what CI runs
python3 scripts/token_benchmark.py --live --task overhead   # optional, paid: real runs with and without the plugin
```

`--live` calls `claude -p` on your own account (default model `haiku`, `--max-budget-usd 0.25` per run), writes `docs/benchmark-live.json`, and is never run in CI. A run of one task keeps the other recorded tasks only while the Claude Code version, model and arsenal version are unchanged; otherwise the record starts again. Do not put a token or cost figure in the docs that this script or `docs/EVALS.md` does not produce.

## Source formats

| Artifact | Location | Format |
| :--- | :--- | :--- |
| Skill | `.agents/skills/<name>/SKILL.md` | Frontmatter with exactly `name` (equal to the folder) and a single-quoted `description`; references in `references/`, bundled scripts in `scripts/`. Links must stay inside the skill folder. |
| Rule | `.agents/rules/<name>.md` | Frontmatter `trigger` (`always_on`, `model_decision`, `glob`), single-quoted `description`, and `globs` (comma-separated; required for `glob`, optional for `model_decision`, where they scope the rule on Claude Code and Copilot, which cannot leave the choice to the model). |
| Subagent | `.agents/subagents/subagent-definitions.json` + `prompts/<name>.md` | JSON entry plus a plain-markdown prompt without frontmatter. |
| MCP server | `.agents/mcp/servers.json` | `type: stdio` (`command`, `args`) or `type: http` (`url`). |

Use the `create-skill` skill to scaffold a new skill. Keep wording agent-neutral: no product names or product-specific tool names inside skills, rules, or prompts.

## Standards for code in this repository

- SOLID, small single-purpose functions, no dead code.
- No file over 1000 lines (enforced by `build.py --validate`).
- Every change ships with tests.
- `install.sh` and `install.ps1` must stay behaviorally identical; change both and both smoke tests.
- Installer changes that delete or rewrite user files need a regression test in `tests/smoke.sh` and `tests/smoke.ps1` that proves user data survives.

## Token budgets

Text that loads every session is capped by `build.py --validate`: each skill description at most 420 characters, all descriptions together at most 22,000 (lower it when they shrink), and the rules that load in every session together at most 20,000 on each target. That last cap counts what a target really loads: a rule without `globs` is unconditional on Claude Code and Copilot whatever its `trigger` says, so a new `model_decision` rule needs `globs` or room in the budget. The measured total is in `docs/BENCHMARK.md`. Put detail in the skill body or `references/`, not the description.

## Behaviour evals

`evals/` holds cases for Claude Code's `claude plugin eval`. Every run is a real model call on your own account, so nothing here runs on push; `.github/workflows/evals.yml` runs the real tasks weekly and on demand when the `ANTHROPIC_API_KEY` secret is set (inputs: runs per arm, default 10; cost ceiling; models) and uploads the results as an artifact.

**Skill triggering.** Each `trigger-<skill>` case sends a natural prompt and passes only if that skill is invoked; `no-trigger-*` cases pass only if no skill is. Free graders only (no judge model). Run them after changing any skill description; every skill must have a `trigger-<skill>` case (a unit test enforces it):

```bash
claude plugin eval . --trust-plugin --tag trigger --ablation none --runs 3 --no-publish --max-cost-usd 5
```

**Real tasks.** `task-*` cases give a task in a fixture built by the case's `fixture.sh` and compare the plugin against a no-plugin baseline. Run, check outcomes, record:

```bash
claude plugin eval . --trust-plugin --scaffold --allow-tools Write Edit Bash --tag task --runs 10 \
  --model sonnet --judge-model haiku --max-cost-usd 25 --threshold 0 --no-publish --keep-temp \
  --json /tmp/harness.json --output-dir /tmp/eval-out
python3 scripts/eval_outcomes.py --results /tmp/harness.json --out /tmp/outcomes.json   # runs model-written tests as you
python3 scripts/eval_report.py --record /tmp/harness.json --outcomes /tmp/outcomes.json --label weekly --note "..."
python3 scripts/eval_report.py --check   # the table in docs/EVALS.md matches docs/eval-results.json
```

- `--keep-temp` is required: the outcome checks and the token counts read each run's kept workspace and trace. Remove the kept `/tmp/claude-eval-*` directories afterwards.
- `eval_report.py --record` stores score, cost, tokens, grader verdicts and outcome checks per arm and run in `docs/eval-results.json` under the label (the same label replaces the earlier record) and rewrites the table in [docs/EVALS.md](docs/EVALS.md). Do not edit that table by hand, and do not put a cost or token figure in the docs that it or `token_benchmark.py` does not produce.
- The Bash grant needs the OS sandbox: `bubblewrap` and `socat` on Linux, and on Ubuntu 24.04 or later also `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`; without it every shell command in a run fails with `apply-seccomp: ... Permission denied` and no run can execute its tests. The `tests-run` grader only shows that a test command was issued; whether tests pass is decided by the outcome checks.
- Graders use only what the harness supports (`regex`, `tool_order`, `tool_used`, `file_exists`, `llm`, `baseline`; a unit test rejects other types and fields), and a case must allow the tools its graders need. Code cannot be executed by a grader, so anything that needs running goes in the case's `outcome.json` (check kinds are listed in `scripts/eval_outcomes.py`) with hidden tests in `outcome/acceptance/` and a reference solution in `outcome/reference/`; a unit test requires every check to pass on the reference and, unless doing nothing is a safe outcome for the case, one to fail on the untouched fixture.

## Running the tests

```bash
python3 scripts/build.py --validate && python3 scripts/build.py --check
python3 scripts/token_benchmark.py --check
python3 scripts/eval_report.py --check
python3 -m unittest discover -s tests -p "test_*.py"
python3 tests/check_formats.py        # needs PyYAML
bash tests/smoke.sh
pwsh -NoProfile -File tests/smoke.ps1 # also runs on Windows PowerShell 5.1 in CI
```

## Adding a target agent

Hooks for a target are separate and optional: add it to `HOOK_TARGETS` in `scripts/build_hooks.py` only when the vendor documents the config file, the event and the output field, and record it in the `docs/TARGETS.md` hooks table (installed with `--hooks`).

1. Add its paths to `AGENT_DESTINATIONS` / `MCP_DESTINATIONS` and its formats to `render_agent` / `render_rule` / `render_mcp` in `scripts/build.py`.
2. Add the name to the target list in `install.sh`, `install.ps1`, and both smoke tests.
3. Document it in `docs/TARGETS.md` and the README table.

## Releases

Bump `VERSION`, run `python3 scripts/build.py`, and commit with a Conventional Commit message. Claude Code plugin users receive the update when the version changes.
