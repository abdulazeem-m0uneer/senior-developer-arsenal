# Eval Results

The skill-triggering results below and the earlier hand run of the real tasks were measured with `claude plugin eval` on 2026-11-13 (the version is not recorded here; the runs in `docs/eval-results.json` state theirs), model `sonnet`, judge `sonnet`; the recorded runs state their own conditions. Re-run after changing skill descriptions or `hooks/core.md`; commands are in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Skill triggering (58 skills + 1 negative case, 1 run each)

Measured on the descriptions as of commit `e385c72`, before they were shortened by about 30 percent. Not re-run since (no paid run was made), so these numbers do not describe the current descriptions, and they are not recorded in `docs/eval-results.json`. Re-run with `--tag trigger` before relying on them.

56 of 59 cases passed on the first full run. The three misses were re-run 3 times each after their descriptions were rewritten:

| Skill | Result after rewrite | Note |
| :--- | :--- | :--- |
| `agent-memory` | 2 of 3 | |
| `quality-gate` | 2 of 3 | |
| `create-skill` | 1 of 3 | The failing runs refused because the test machine's own host instructions said skills cannot be created there; not reproduced elsewhere. |

Some cases accept either of two overlapping skills (for example `code-review` or `deep-review`); see each case's `graders/skill-fired.md`.

## Real tasks: what is checked

Each `task-*` case gives a real task in a small fixture and runs it with the plugin and without. Three layers grade it:

| Layer | Runs where | Proves | Cannot prove |
| :--- | :--- | :--- | :--- |
| Deterministic graders (`regex`, `file_exists`, `tool_used`) | inside `claude plugin eval` | a test file was added, a test command was issued, the root-cause line is gone, the original assertions are still in the test file, an old migration was not edited, each planted review defect is named | that the tests pass, or that the code is right |
| Outcome checks (`evals/<case>/outcome.json`, run by `scripts/eval_outcomes.py`) | after the run, on the kept workspace | hidden acceptance tests pass on the final code; the tests the run added fail on the untouched fixture and pass on the final code (or pass on both, for a refactor); the fixture's own tests pass against the final code; the first new migration does not drop or rename what the running old version uses | anything about a run whose workspace was not kept; pytest-only features when pytest is not installed (reported as inconclusive) |
| Judge graders (`llm`) | inside `claude plugin eval` | what code cannot check: a review found a defect no keyword pins down, a vague request was met with questions, a migration answer warns about the rolling deploy | they are a model's opinion; read the votes before trusting a change in them |

`claude plugin eval` has no grader type that executes code (its types are `regex`, `tool_order`, `tool_used`, `file_exists`, `llm`, `baseline`), so the outcome checks run outside the harness and are not part of its score; the table below reports them in their own column. The `tests-run` grader only shows that a test command was issued. The migration check is static: it reads the SQL, it does not apply it to a database. Every case with an `outcome.json` ships a reference solution, and a unit test proves the checks pass on it and that the untouched fixture fails one (for the migration case the check requires that a migration was written: a run that writes none fails it).

| Case | Task | Outcome checks |
| :--- | :--- | :--- |
| `task-bugfix` | fix a discount that goes negative | acceptance; regression test red then green |
| `task-legacy-change` | add a rule to untested code | acceptance (other fees equal to the original on a grid); regression test red then green |
| `task-feature-multifile` | model, service and API change | acceptance (service); feature test red then green |
| `task-failing-ci` | make a red branch green | the fixture's own tests pass on the final code |
| `task-risky-migration` | destructive migration under a rolling deploy | first new migration keeps the old version working (written before `require_match`: a run that wrote no migration also counted as a pass, so the recorded `first-step-keeps-old-version-working` 1/1 rows below carry no information) |
| `task-review` | review a file with 3 planted defects | none (one keyword grader per defect, plus a judge) |
| `task-ambiguous` | vague request | none (judge; no file may be written) |
| `task-cross-module-bug` | symptom in the invoice, cause in the money module | acceptance; regression test red then green |
| `task-legacy-refactor` | refactor untested code, behaviour unchanged | acceptance (equal to the original on a grid); characterization test green before and after |
| `task-feature-fullstack` | migration, API and client change for one feature | acceptance (old database keeps rows, API and client agree); feature test red then green |

## Real tasks: recorded runs

Scores, cost and tokens per arm, written by `scripts/eval_report.py --record` from the harness JSON into [eval-results.json](eval-results.json). Cost per run is the agent run plus its judge calls. Input tokens include cache writes and cache reads. Graders marked as an indicator are not part of the score, so both arms of a case are scored by the same graders. The procedure is in [CONTRIBUTING.md](../CONTRIBUTING.md).

<!-- eval-results:start (generated by scripts/eval_report.py from docs/eval-results.json; do not edit) -->

### `smoke` (2026-11-13)

Claude Code 2.1.321, arsenal 1.3.1, model `haiku`, judge `haiku`, 1 run(s) per arm, total cost 0.0122 USD.

Smoke run that proves the pipeline end to end: one case, one run per arm. It is too small to compare the arms. The eval shell could not start on the recording machine (the kernel restricts nested user namespaces), so no run could execute its tests and `tests-run` fails in both arms; the outcome checks ran the tests afterwards.

| Task | Arm | Runs | Mean score | Graders passed | Outcome checks passed | Cost per run (USD) | Input tokens per run | Output tokens per run | Turns per run |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `task-bugfix` | with plugin | 1 | 0.67 | `any-skill-fired` 1/1 (indicator, not scored)<br>`fix-correct` 1/1<br>`regression-test` 1/1<br>`tests-run` 0/1 | `acceptance` 1/1<br>`regression-test-red-then-green` 1/1 | 0.0079 | 153,024 | 2,836 | 10.0 |
| `task-bugfix` | without plugin | 1 | 0.33 | `fix-correct` 1/1<br>`regression-test` 0/1<br>`tests-run` 0/1 | `acceptance` 1/1<br>`regression-test-red-then-green` 0/1 | 0.0043 | 128,149 | 1,423 | 7.0 |

### `pilot` (2026-11-13)

Claude Code 2.1.321, arsenal 1.3.1, model `haiku`, judge `haiku`, 1 run(s) per arm, total cost 0.1133 USD.

Grader calibration pilot of the six `hard` cases after the outcome checks were added: one run per arm, so no row is evidence of a difference between the arms. The eval shell could not start on the recording machine either, so `tests-run` here only shows that a test command was issued; `inconclusive` means the run's tests need pytest, which was not installed where the outcome checks ran.

| Task | Arm | Runs | Mean score | Graders passed | Outcome checks passed | Cost per run (USD) | Input tokens per run | Output tokens per run | Turns per run |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `task-cross-module-bug` | with plugin | 1 | 0.50 | `any-skill-fired` 1/1 (indicator, not scored)<br>`regression-test` 0/1<br>`root-cause-fixed` 1/1<br>`root-cause-named` 1/1<br>`tests-run` 0/1 | `acceptance` 1/1<br>`regression-test-red-then-green` 0/1 | 0.0080 | 156,670 | 2,774 | 10.0 |
| `task-cross-module-bug` | without plugin | 1 | 0.50 | `regression-test` 0/1<br>`root-cause-fixed` 1/1<br>`root-cause-named` 1/1<br>`tests-run` 0/1 | `acceptance` 1/1<br>`regression-test-red-then-green` 0/1 | 0.0039 | 91,902 | 1,411 | 7.0 |
| `task-failing-ci` | with plugin | 1 | 1.00 | `any-skill-fired` 0/1 (indicator, not scored)<br>`code-fixed` 1/1<br>`no-skip-markers` 1/1<br>`original-assertions-kept` 1/1<br>`tests-run` 1/1 | `original-tests-green` 1/1 | 0.0087 | 269,142 | 2,526 | 12.0 |
| `task-failing-ci` | without plugin | 1 | 1.00 | `code-fixed` 1/1<br>`no-skip-markers` 1/1<br>`original-assertions-kept` 1/1<br>`tests-run` 1/1 | `original-tests-green` 1/1 | 0.0046 | 131,000 | 1,882 | 10.0 |
| `task-feature-fullstack` | with plugin | 1 | 1.00 | `any-skill-fired` 1/1 (indicator, not scored)<br>`api-changed` 1/1<br>`client-changed` 1/1<br>`new-migration` 1/1<br>`old-migration-untouched` 1/1<br>`tests-run` 1/1<br>`tests-written` 1/1 | `acceptance` 1/1<br>`feature-test-red-then-green` 1/1 | 0.0133 | 308,248 | 8,337 | 17.0 |
| `task-feature-fullstack` | without plugin | 1 | 0.67 | `api-changed` 1/1<br>`client-changed` 1/1<br>`new-migration` 1/1<br>`old-migration-untouched` 1/1<br>`tests-run` 0/1<br>`tests-written` 0/1 | `acceptance` 1/1<br>`feature-test-red-then-green` 0/1 | 0.0078 | 169,676 | 5,555 | 15.0 |
| `task-feature-multifile` | with plugin | 1 | 1.00 | `any-skill-fired` 1/1 (indicator, not scored)<br>`api-wired` 1/1<br>`service-correct` 1/1<br>`tests-run` 1/1<br>`tests-written` 1/1 | `acceptance` 1/1<br>`feature-test-red-then-green` 0/1 (1 inconclusive) | 0.0144 | 354,625 | 8,218 | 21.0 |
| `task-feature-multifile` | without plugin | 1 | 0.50 | `api-wired` 1/1<br>`service-correct` 1/1<br>`tests-run` 0/1<br>`tests-written` 0/1 | `acceptance` 1/1<br>`feature-test-red-then-green` 0/1 | 0.0073 | 160,532 | 4,557 | 15.0 |
| `task-legacy-refactor` | with plugin | 1 | 1.00 | `any-skill-fired` 1/1 (indicator, not scored)<br>`characterization-tests` 1/1<br>`decomposed` 1/1<br>`readable` 1/1<br>`tests-run` 1/1 | `acceptance` 1/1<br>`characterization-test-green-before-and-after` 1/1 | 0.0182 | 398,331 | 13,490 | 14.0 |
| `task-legacy-refactor` | without plugin | 1 | 0.50 | `characterization-tests` 0/1<br>`decomposed` 1/1<br>`readable` 1/1<br>`tests-run` 0/1 | `acceptance` 1/1<br>`characterization-test-green-before-and-after` 0/1 | 0.0094 | 161,171 | 8,119 | 10.0 |
| `task-risky-migration` | with plugin | 1 | 1.00 | `any-skill-fired` 1/1 (indicator, not scored)<br>`flags-risk` 1/1 | `first-step-keeps-old-version-working` 1/1 | 0.0106 | 188,188 | 6,338 | 12.0 |
| `task-risky-migration` | without plugin | 1 | 1.00 | `flags-risk` 1/1 | `first-step-keeps-old-version-working` 1/1 | 0.0071 | 96,557 | 5,499 | 8.0 |

<!-- eval-results:end -->

## Real tasks, earlier hand run (2 runs per arm, before the outcome checks, no cost recorded)

These are the findings of the first hand run, on 7 cases and with the graders as they were then. They are kept as recorded and are not reproduced by the runs above.

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

Reading: the measured gain is that code changes ship with tests. Correctness was not better than the baseline on these small tasks. With-plugin runs cost about 1.5 to 2 times the baseline; that ratio was observed during the runs and the per-arm usage was not saved, so it cannot be reproduced from this repository. The fixed context cost of the plugin is measured in [BENCHMARK.md](BENCHMARK.md). Before `hooks/core.md` existed, no skill fired on any plain task and no tests were written.
