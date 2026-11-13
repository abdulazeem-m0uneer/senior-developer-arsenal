# Eval Results

Measured with `claude plugin eval` (Claude Code 2.1.323) on 2026-11-13, model `sonnet`, judge `sonnet`. Re-run after changing skill descriptions or `hooks/core.md`; commands are in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Skill triggering (58 skills + 1 negative case, 1 run each)

56 of 59 cases passed on the first full run. The three misses were re-run 3 times each after their descriptions were rewritten:

| Skill | Result after rewrite | Note |
| :--- | :--- | :--- |
| `agent-memory` | 2 of 3 | |
| `quality-gate` | 2 of 3 | |
| `create-skill` | 1 of 3 | The failing runs refused because the test machine's own host instructions said skills cannot be created there; not reproduced elsewhere. |

Some cases accept either of two overlapping skills (for example `code-review` or `deep-review`); see each case's `graders/skill-fired.md`.

## Real tasks, with the plugin and without (2 runs per arm)

No shell was available (the OS sandbox was missing), so no run could execute tests; `tests-run` graders are not reported.

| Task | With plugin | Without plugin |
| :--- | :--- | :--- |
| Bug fix | regression test written 2/2; fix judged correct 1/2 | no test written; fix correct 2/2 |
| Legacy change (untested code) | tests written 2/2; change correct 2/2 | no test written; change correct 2/2 |
| Multi-file feature | tests written 2/2; service and API correct 2/2 | no test written; service and API correct 2/2 |
| Failing CI | code fixed, tests not weakened 2/2 | same 2/2 |
| Risky migration (rolling deploy) | risk flagged, phased plan 2/2 | same 2/2 |
| Code review (3 planted defects) | all found 2/2 | same 2/2 |
| Vague request | asked clarifying questions 2/2 | same 2/2 |

Reading: the measured gain is that code changes ship with tests. Correctness was not better than the baseline on these small tasks. With-plugin runs cost about 1.5 to 2 times the baseline. Before `hooks/core.md` existed, no skill fired on any plain task and no tests were written.
