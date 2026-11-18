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
| `smart-hidden-caller` | change a date format used by two other callers | acceptance (screen changes, CSV export and API stay ISO) |
| `smart-unicode-search` | search misses accented names; looks like case, is Unicode normalization | acceptance |
| `smart-allocation` | proportional split does not add up | acceptance (sum exact, each part within one cent of its share) |
| `smart-stale-cache` | header shows an old name; cause is a cache two modules away | acceptance (new name shown, cache still spares the database) |

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

### `proof-1.6.0` (2026-11-17)

Claude Code 2.1.325, arsenal 1.6.0, model `sonnet`, judge `haiku`, 5 run(s) per arm, total cost 11.4331 USD.

Proof run on arsenal 1.6.0 (branch feat/arsenal-smart): all 11 task cases, 5 runs per arm, with and without the plugin, model sonnet, judge haiku, on the maintainer's machine with the OS sandbox working (Bash ran in both arms). Outcome checks ran afterwards with pytest installed. Costs include judge calls.

| Task | Arm | Runs | Mean score | Graders passed | Outcome checks passed | Cost per run (USD) | Input tokens per run | Output tokens per run | Turns per run |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `task-ambiguous` | with plugin | 5 | 1.00 | `any-skill-fired` 4/5 (indicator, not scored)<br>`clarifies` 5/5<br>`no-files` 5/5 | none defined | 0.1028 | 87,892 | 845 | 5.4 |
| `task-ambiguous` | without plugin | 5 | 1.00 | `clarifies` 5/5<br>`no-files` 5/5 | none defined | 0.0482 | 51,861 | 688 | 3.6 |
| `task-bugfix` | with plugin | 5 | 0.80 | `any-skill-fired` 5/5 (indicator, not scored)<br>`fix-correct` 3/5<br>`regression-test` 5/5<br>`tests-run` 4/5 | `acceptance` 5/5<br>`regression-test-red-then-green` 5/5 | 0.1262 | 181,974 | 1,525 | 9.6 |
| `task-bugfix` | without plugin | 5 | 0.33 | `fix-correct` 5/5<br>`regression-test` 0/5<br>`tests-run` 0/5 | `acceptance` 5/5<br>`regression-test-red-then-green` 0/5 | 0.0464 | 52,205 | 426 | 3.0 |
| `task-cross-module-bug` | with plugin | 5 | 0.80 | `any-skill-fired` 5/5 (indicator, not scored)<br>`regression-test` 5/5<br>`root-cause-fixed` 5/5<br>`root-cause-named` 3/5<br>`tests-run` 3/5 | `acceptance` 5/5<br>`regression-test-red-then-green` 5/5 | 0.1294 | 172,834 | 1,710 | 10.8 |
| `task-cross-module-bug` | without plugin | 5 | 0.50 | `regression-test` 0/5<br>`root-cause-fixed` 5/5<br>`root-cause-named` 5/5<br>`tests-run` 0/5 | `acceptance` 5/5<br>`regression-test-red-then-green` 0/5 | 0.0622 | 90,278 | 1,182 | 7.6 |
| `task-failing-ci` | with plugin | 5 | 1.00 | `any-skill-fired` 5/5 (indicator, not scored)<br>`code-fixed` 5/5<br>`no-skip-markers` 5/5<br>`original-assertions-kept` 5/5<br>`tests-run` 5/5 | `original-tests-green` 5/5 | 0.1245 | 181,316 | 1,354 | 11.0 |
| `task-failing-ci` | without plugin | 5 | 0.95 | `code-fixed` 5/5<br>`no-skip-markers` 5/5<br>`original-assertions-kept` 5/5<br>`tests-run` 4/5 | `original-tests-green` 5/5 | 0.0593 | 99,572 | 908 | 8.0 |
| `task-feature-fullstack` | with plugin | 5 | 1.00 | `any-skill-fired` 5/5 (indicator, not scored)<br>`api-changed` 5/5<br>`client-changed` 5/5<br>`new-migration` 5/5<br>`old-migration-untouched` 5/5<br>`tests-run` 5/5<br>`tests-written` 5/5 | `acceptance` 5/5<br>`feature-test-red-then-green` 5/5 | 0.1688 | 208,761 | 3,837 | 16.6 |
| `task-feature-fullstack` | without plugin | 5 | 0.67 | `api-changed` 5/5<br>`client-changed` 5/5<br>`new-migration` 5/5<br>`old-migration-untouched` 5/5<br>`tests-run` 0/5<br>`tests-written` 0/5 | `acceptance` 5/5<br>`feature-test-red-then-green` 0/5 | 0.0881 | 113,854 | 2,719 | 11.0 |
| `task-feature-multifile` | with plugin | 5 | 1.00 | `any-skill-fired` 5/5 (indicator, not scored)<br>`api-wired` 5/5<br>`service-correct` 5/5<br>`tests-run` 5/5<br>`tests-written` 5/5 | `acceptance` 5/5<br>`feature-test-red-then-green` 5/5 | 0.1710 | 219,363 | 4,033 | 17.4 |
| `task-feature-multifile` | without plugin | 5 | 0.50 | `api-wired` 5/5<br>`service-correct` 5/5<br>`tests-run` 0/5<br>`tests-written` 0/5 | `acceptance` 5/5<br>`feature-test-red-then-green` 0/5 | 0.0816 | 99,123 | 2,339 | 12.2 |
| `task-legacy-change` | with plugin | 5 | 1.00 | `any-skill-fired` 5/5 (indicator, not scored)<br>`change-correct` 5/5<br>`tests-run` 5/5<br>`tests-written` 5/5 | `acceptance` 5/5<br>`regression-test-red-then-green` 5/5 | 0.1370 | 186,057 | 2,005 | 10.8 |
| `task-legacy-change` | without plugin | 5 | 0.33 | `change-correct` 5/5<br>`tests-run` 0/5<br>`tests-written` 0/5 | `acceptance` 5/5<br>`regression-test-red-then-green` 0/5 | 0.0528 | 73,538 | 637 | 4.2 |
| `task-legacy-refactor` | with plugin | 5 | 0.80 | `any-skill-fired` 5/5 (indicator, not scored)<br>`characterization-tests` 5/5<br>`decomposed` 5/5<br>`readable` 3/5<br>`tests-run` 3/5 | `acceptance` 5/5<br>`characterization-test-green-before-and-after` 5/5 | 0.1745 | 212,997 | 4,548 | 11.4 |
| `task-legacy-refactor` | without plugin | 5 | 0.50 | `characterization-tests` 0/5<br>`decomposed` 5/5<br>`readable` 5/5<br>`tests-run` 0/5 | `acceptance` 5/5<br>`characterization-test-green-before-and-after` 0/5 | 0.0950 | 100,942 | 3,563 | 6.0 |
| `task-lesson-recall` | with plugin | 5 | 0.67 | `any-skill-fired` 5/5 (indicator, not scored)<br>`generated-in-sync` 0/5<br>`generator-run` 5/5<br>`lesson-followed` 5/5 | none defined | 0.1379 | 210,666 | 1,892 | 13.4 |
| `task-lesson-recall` | without plugin | 5 | 0.47 | `generated-in-sync` 4/5<br>`generator-run` 1/5<br>`lesson-followed` 2/5 | none defined | 0.0572 | 78,496 | 905 | 7.6 |
| `task-review` | with plugin | 5 | 1.00 | `any-skill-fired` 5/5 (indicator, not scored)<br>`defect-n-plus-one` 5/5<br>`defect-sql-injection` 5/5<br>`defect-swallowed-exception` 5/5<br>`findings` 5/5<br>`no-amount-check` 5/5 | none defined | 0.1148 | 89,138 | 1,629 | 6.0 |
| `task-review` | without plugin | 5 | 1.00 | `defect-n-plus-one` 5/5<br>`defect-sql-injection` 5/5<br>`defect-swallowed-exception` 5/5<br>`findings` 5/5<br>`no-amount-check` 5/5 | none defined | 0.0524 | 52,159 | 926 | 3.8 |
| `task-risky-migration` | with plugin | 5 | 1.00 | `any-skill-fired` 5/5 (indicator, not scored)<br>`flags-risk` 5/5 | `first-step-keeps-old-version-working` 5/5 | 0.1682 | 158,691 | 4,964 | 11.6 |
| `task-risky-migration` | without plugin | 5 | 1.00 | `flags-risk` 5/5 | `first-step-keeps-old-version-working` 5/5 | 0.0884 | 87,509 | 3,271 | 6.4 |

### `smart-sonnet` (2026-11-18)

Claude Code 2.1.327, arsenal 1.6.1, model `sonnet`, judge `haiku`, 3 run(s) per arm, total cost 2.5076 USD.

Calibration of the four smart-* cases (built to catch plausible wrong fixes; unit tests prove each wrong fix fails acceptance): 3 runs per arm, model sonnet; no OS sandbox, so Bash was not granted and tests ran only in the outcome checks. Both arms passed acceptance 3/3 on every case, so these cases do not separate the arms on this model.

| Task | Arm | Runs | Mean score | Graders passed | Outcome checks passed | Cost per run (USD) | Input tokens per run | Output tokens per run | Turns per run |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `smart-allocation` | with plugin | 3 | 0.67 | `any-skill-fired` 3/3 (indicator, not scored)<br>`tests-run` 2/3 | `acceptance` 3/3 | 0.1484 | 139,139 | 1,886 | 9.3 |
| `smart-allocation` | without plugin | 3 | 0.00 | `tests-run` 0/3 | `acceptance` 3/3 | 0.0755 | 46,524 | 868 | 3.0 |
| `smart-hidden-caller` | with plugin | 3 | 0.33 | `any-skill-fired` 3/3 (indicator, not scored)<br>`tests-run` 1/3 | `acceptance` 3/3 | 0.1465 | 161,505 | 2,167 | 12.7 |
| `smart-hidden-caller` | without plugin | 3 | 0.00 | `tests-run` 0/3 | `acceptance` 3/3 | 0.0619 | 97,164 | 1,641 | 9.3 |
| `smart-stale-cache` | with plugin | 3 | 0.67 | `any-skill-fired` 3/3 (indicator, not scored)<br>`tests-run` 2/3 | `acceptance` 3/3 | 0.1264 | 173,463 | 2,118 | 13.7 |
| `smart-stale-cache` | without plugin | 3 | 0.00 | `tests-run` 0/3 | `acceptance` 3/3 | 0.0506 | 79,470 | 1,005 | 7.0 |
| `smart-unicode-search` | with plugin | 3 | 1.00 | `any-skill-fired` 3/3 (indicator, not scored)<br>`tests-run` 3/3 | `acceptance` 3/3 | 0.1453 | 253,341 | 3,040 | 13.7 |
| `smart-unicode-search` | without plugin | 3 | 0.67 | `tests-run` 2/3 | `acceptance` 3/3 | 0.0814 | 141,422 | 2,654 | 11.3 |

### `smart-haiku` (2026-11-18)

Claude Code 2.1.327, arsenal 1.6.1, model `haiku`, judge `haiku`, 3 run(s) per arm, total cost 0.1620 USD.

Same four smart-* cases on model haiku, 3 runs per arm, same conditions. Both arms passed acceptance 3/3 on every case: the weaker model also solves them without the plugin.

| Task | Arm | Runs | Mean score | Graders passed | Outcome checks passed | Cost per run (USD) | Input tokens per run | Output tokens per run | Turns per run |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `smart-allocation` | with plugin | 3 | 1.00 | `any-skill-fired` 3/3 (indicator, not scored)<br>`tests-run` 3/3 | `acceptance` 3/3 | 0.0083 | 196,627 | 3,673 | 10.0 |
| `smart-allocation` | without plugin | 3 | 1.00 | `tests-run` 3/3 | `acceptance` 3/3 | 0.0063 | 116,930 | 2,940 | 8.3 |
| `smart-hidden-caller` | with plugin | 3 | 1.00 | `any-skill-fired` 3/3 (indicator, not scored)<br>`tests-run` 3/3 | `acceptance` 3/3 | 0.0082 | 210,140 | 3,113 | 13.3 |
| `smart-hidden-caller` | without plugin | 3 | 1.00 | `tests-run` 3/3 | `acceptance` 3/3 | 0.0045 | 94,147 | 2,658 | 11.3 |
| `smart-stale-cache` | with plugin | 3 | 0.67 | `any-skill-fired` 3/3 (indicator, not scored)<br>`tests-run` 2/3 | `acceptance` 3/3 | 0.0089 | 237,245 | 3,404 | 15.0 |
| `smart-stale-cache` | without plugin | 3 | 0.00 | `tests-run` 0/3 | `acceptance` 3/3 | 0.0043 | 116,152 | 2,158 | 10.7 |
| `smart-unicode-search` | with plugin | 3 | 1.00 | `any-skill-fired` 3/3 (indicator, not scored)<br>`tests-run` 3/3 | `acceptance` 3/3 | 0.0088 | 224,223 | 3,788 | 13.0 |
| `smart-unicode-search` | without plugin | 3 | 1.00 | `tests-run` 3/3 | `acceptance` 3/3 | 0.0048 | 107,598 | 3,240 | 9.3 |

### `real-refund-sonnet` (2026-11-18)

Claude Code 2.1.327, arsenal 1.7.0, model `sonnet`, judge `haiku`, 5 run(s) per arm, total cost 1.0404 USD.

Real task rebuilt as a small Python reconstruction of caby-backend #696 (refund the captured transaction, not the hold), 5 runs per arm, no OS sandbox. Both arms passed acceptance 5/5. The red-then-green check reads 0/5 in both arms because it counts only NEW test files: in a sample of 3 runs per arm, every with-plugin run and 2 of 3 without-plugin runs extended the existing tests/test_refunds.py instead, so that row measures nothing.

| Task | Arm | Runs | Mean score | Graders passed | Outcome checks passed | Cost per run (USD) | Input tokens per run | Output tokens per run | Turns per run |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `real-caby-refund-capture` | with plugin | 5 | 0.30 | `any-skill-fired` 5/5 (indicator, not scored)<br>`regression-test` 0/5<br>`tests-run` 3/5 | `acceptance` 5/5<br>`regression-test-red-then-green` 0/5 | 0.1384 | 193,274 | 2,389 | 13.6 |
| `real-caby-refund-capture` | without plugin | 5 | 0.20 | `regression-test` 0/5<br>`tests-run` 2/5 | `acceptance` 5/5<br>`regression-test-red-then-green` 0/5 | 0.0697 | 102,771 | 1,815 | 9.0 |

### `real-refund-haiku` (2026-11-18)

Claude Code 2.1.327, arsenal 1.7.0, model `haiku`, judge `haiku`, 5 run(s) per arm, total cost 0.0841 USD.

Same case on model haiku, same conditions and the same caveat about the red-then-green row.

| Task | Arm | Runs | Mean score | Graders passed | Outcome checks passed | Cost per run (USD) | Input tokens per run | Output tokens per run | Turns per run |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `real-caby-refund-capture` | with plugin | 5 | 0.20 | `any-skill-fired` 5/5 (indicator, not scored)<br>`regression-test` 0/5<br>`tests-run` 2/5 | `acceptance` 5/5<br>`regression-test-red-then-green` 0/5 | 0.0110 | 291,858 | 4,456 | 17.2 |
| `real-caby-refund-capture` | without plugin | 5 | 0.40 | `regression-test` 0/5<br>`tests-run` 4/5 | `acceptance` 5/5<br>`regression-test-red-then-green` 0/5 | 0.0058 | 132,154 | 3,630 | 11.8 |

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
