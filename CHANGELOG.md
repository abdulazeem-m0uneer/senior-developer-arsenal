# Changelog

All notable changes to Senior Developer Arsenal are recorded in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The version is the one in the `VERSION` file, and each release is dated by the day its pull request merged (UTC).

## [1.37.1] - 2026-11-27

### Fixed

- Lite names no credential file anywhere (`.npmrc`, `.env`, `id_rsa`, `*.pem`, `*.key`, the agents' home-directory config files). Each is described instead, because the directory's scanner pairs any named credential file with HTTP use in any other skill. A test covers every lite file (#76).

## [1.37.0] - 2026-11-27

### Added

- `lite/`: a text-only edition for the Claude plugin directory, which accepts hooks, scripts, `network` and some subagent frontmatter only from Verified organizations. `scripts/build_lite.py` generates it from the same sources: 51 skills (Markdown and references only, with a note on steps that run a bundled script), 18 subagents without `omitClaudeMd`, and a manifest with accepted fields, with the icon found by path. Ten skills built around their scripts are left out. The full plugin is unchanged (#69).
- `tests/test_build_lite.py`: `lite/` is current and holds only what the directory accepts (#69).
- README "Two editions" table, `lite/` in the repository structure, the lite edition in `PRIVACY.md` (#75).

### Changed

- MCP plugins follow the plugin reference: `arsenal-hindsight` takes its memory bank from a `userConfig` option (`bank_id`, default `default`, set in `/config`) through `${user_config.bank_id}`, instead of reading `HINDSIGHT_BANK_ID` from the environment. **If you set `HINDSIGHT_BANK_ID`, set `bank_id` in `/config` once.** `arsenal-codegraph` declares `"type": "stdio"`. Both MCP plugins set `privacyPolicyUrl`. README, `docs/TARGETS.md` and the `agent-memory` skill say where the bank is set (#75).

### Fixed

- Lite text reworded where the directory's scanner warned, for credentials read from the machine and download-and-run commands: fake values for token and key names, no `curl` or `npx` downloads, install-then-run lines pointing to each tool's own instructions, agent config files named without the home path, and `node:http` (#70, #71, #72, #73, #74).

## [1.36.0] - 2026-11-26

### Added

- `plugin.json` declares `network.hosts`: `api.github.com`, `github.com` and `localhost:8888`, the only hosts the hooks and skill scripts reach; `PRIVACY.md` names them (#68).

## [1.35.0] - 2026-11-26

### Added

- Plugin directory listing fields in `.claude-plugin/plugin.json`: `homepage`, `repository`, `keywords`, `icon`, `documentationUrl`, `supportUrl`, `privacyPolicyUrl` and `termsOfServiceUrl` (#67).
- `PRIVACY.md`: what the plugin stores locally (usage-stats fields and the transcript reads behind them, lessons ledgers, lessons evidence, with their off switches) and what leaves the machine (#67).
- README: a "Start Here" section with the five skills to learn first (#67).
- README: an "Available for Work" section with contact links (#67).

### Fixed

- `test_eval_outcomes`: the missing-runner test is skipped where pytest is installed, since it checks the no-pytest runner; it failed on any machine with pytest (#67).

## [1.34.0] - 2026-11-26

### Added

- Optional scanner references, loaded only when their skill runs (no change to per-session context). Each tool has a use case and a command, runs only when already installed, and a tool that was not run is named in the report (#66):
  - `security-audit`: `references/scanner-tooling.md` (graudit, semgrep, sqlmap, sslscan, vulnhuntr); dynamic tools only against environments the user owns.
  - `mobile-expert`: `references/mobile-scan-tooling.md` (MobSF, QARK, drozer), with hits mapped to MASVS items.
  - `devops-ci`: `references/host-hardening-tooling.md` (Lynis, sslscan, trivy).
  - `test-strategy`: `references/fuzzing-tooling.md` (libFuzzer, AFL++, honggfuzz) for parsers and native bindings; each crash becomes a regression test.

## [1.33.5] - 2026-11-26

### Added

- Four opt-in lesson-guard rules (#65):
  - `wait-on-text` refuses a `while` or `until` loop whose condition reads the configured message files (`paths`). A loop that waits on message text matches lines that only quote the event, so the rule tells the caller to wait on the authoritative state instead.
  - `durable-path` refuses scheduled or persistent work whose script sits in `/tmp` or a session scratchpad, where cleanup or a reboot removes it. That covers `systemd-run` timers, `at` and `batch`, crontab lines, and written `.service`, `.timer` or crontab files.
  - `tool-result-read` refuses a Read of a persisted tool-result file under `~/.claude/projects/`, so the caller narrows the query at its source.
  - `unseen-time` refuses a past clock time in an outbound message unless that time appeared in tool output earlier in the session. ETAs and deadlines are exempt.

### Changed

- The built-in rule `pipe-exit` counts `git commit` as a check, so `git commit ... | tail -1 && git push` is refused. `git commit --dry-run` is not counted (#65).

### Fixed

- `dry-run-chain`: a `NAME=$(...)` capture that is not a leading assignment, such as `export n=$(...)`, `local n=$(...)` or `echo n=$(...)`, no longer makes the lesson-guard check raise (#65).

## [1.33.4] - 2026-11-25

### Changed

- `merge_slot.py` releases a slot holder whose required checks failed (#64):
  - at the next refresh, a holder whose checks show a failure or an error, with nothing still running, gives up the slot, unless the merge state is `UNSTABLE` (only non-required checks failed);
  - its failed head is recorded, and it rejoins after a re-run turns that head green, or after a new head is pushed;
  - pending, unknown, a `gh` error or a cancelled run keeps the slot;
  - a failed queued pull request is skipped whenever the slot is granted;
  - a `may-update` from a pull request on a failed head is refused.

## [1.33.3] - 2026-11-25

### Fixed

- Lesson-guard rule `dry-run-chain` no longer refuses a real run that only goes ahead after the dry run's result was checked (#63):
  - the dry run's output is captured into a variable, and the real run sits in an `if`, an `&&` list or a `case` arm that tests that variable, also inside a loop;
  - `set -o pipefail` is on for the chain, so the `&&` after `dry | tail` waits on the dry run's own status.

  A real run outside the tested branch, in the default arm, after `||`, or gated on a different or overwritten variable is still refused. So is pipefail that is set in a subshell, a branch, a pipeline stage or the background.

## [1.33.2] - 2026-11-25

### Added

- Lesson-guard rule `outer-timeout` takes an optional `no_queue_env` list of environment variables. A call that sets one of them to a value other than empty, `0`, `false`, `no` or `off` does not queue, so it passes. An example is the queueing program's own dry-run switch (#62).

### Fixed

- `outer-timeout`: a leading variable assignment on one command no longer carries over to later commands on the same line. Only a bare assignment or `export` does (#62).

## [1.33.1] - 2026-11-25

### Changed

- `merge_slot.py` lets a ready pull request go first (#61):
  - a pull request whose checks are green, that merges cleanly and already contains the base branch tip, takes the merge slot from a holder whose checks are still running;
  - the displaced holder keeps its place at the head of the queue, also through `queue_sync.py`;
  - when the holder gets the slot back, it is given a window up to the later of its old expiry and a fresh claim window;
  - a pending pull request never takes the slot from a pending holder, and a clean, protected or returning holder is never displaced;
  - unknown data or a `gh` error means the holder keeps the slot.

## [1.33.0] - 2026-11-25

### Added

- Lesson-guard rule `timer-safety`. It refuses three mistakes (#60):
  - stopping a systemd timer and starting it again, or restarting it, which fires a missed run, also when sent over ssh or inside a `for` loop;
  - a `.timer` file whose `OnCalendar=` value `systemd-analyze calendar` rejects;
  - a oneshot `.service` file with no `TimeoutStartSec=`.
- Lesson-guard rule `live-script`. It refuses a Write or Edit of a shell script that a running `bash`, `sh` or `zsh` is executing, because the shell reads the file as it runs (#60).
- Lesson-guard rule `dry-run-chain`. It refuses a dry run and the real run of the same configured program chained with `;`, `&&` or `||` in one call, so that the dry run's output is read before the real run starts (#60).
- Lesson-guard rule `outer-timeout`. It refuses an outer `timeout` or a `systemd-run` with `RuntimeMaxSec=` around a configured queueing program. Its `--help`, `--version` and `status` calls are allowed (#60).

## [1.32.1] - 2026-11-24

### Added

- `CHANGELOG.md` records every release from 1.0.0 on, and a test fails when the `VERSION` file has no section here (#59).
- `CONTRIBUTING.md` describes the release step: each version bump adds its section in the same pull request, and the merge commit is tagged `vX.Y.Z` with a GitHub release whose notes are that section (#59).

## [1.32.0] - 2026-11-24

### Added

- `ci-wait` gains `ci_learn.py`, which sorts a red or cancelled CI run by cause, prints the minutes it wasted and records it as a lesson (#58).
- `quality-gate` gains `changed_coverage.py`, which refuses a push when coverage of the changed lines is under a minimum, 90% by default (#58).
- `quality-gate` gains `push_once.py`, which refuses a new push while the branch's previous CI run is still running, but lets a pure rebase through (#58).
- `usage-stats ci` prints one line per day with runs, red runs, wasted minutes per cause and repeats without a guard (#58).

### Changed

- A lesson that reaches the promotion threshold without a guard now stops `lessons.py` with exit 3 until a guard or an exemption is attached (#58).

## [1.31.2] - 2026-11-24

### Added

- `test-every-change` gains `mutate.py`, which runs each mutant in a temporary copy and always removes that copy (#57).
- It runs the tests once on an unmutated copy first and stops when that run fails, so a broken setup is not reported as killed mutants (#57).

## [1.31.1] - 2026-11-24

### Added

- `lessons.py add` and `bump` end with a `LEARNED:` line that names the rule and its hit count (#56).
- The session-start lessons header asks the agent to say `Applying ID: rule` when a lesson changes what it does (#56).

## [1.31.0] - 2026-11-24

### Added

- `test-every-change` gains `tdd.py red`, which records a real failing test run as a `Test-Red:` git trailer (#55).
- `tdd.py check` lets any repository's CI refuse a feature or fix branch whose first commit has no test change or no recorded red run (#55).
- `tdd.py check --verify` re-runs the recorded command at that commit in a temporary worktree and requires it to fail (#55).

## [1.30.0] - 2026-11-23

### Added

- An opt-in `typed-sha` guard refuses a short or never-printed commit hash in `gh pr merge --match-head-commit` and `git push --force-with-lease` (#54).
- An opt-in `oom-first` guard refuses re-running a command that died with exit 134 or 137 until the kernel log or memory counters were read (#54).

## [1.29.1] - 2026-11-23

### Fixed

- The destructive-command guard refuses deleting the top level of a session's shared scratchpad, which held other agents' files (#53).

## [1.29.0] - 2026-11-23

### Added

- An opt-in `shell-syntax` guard refuses a Bash command that `bash -n` cannot parse, before any part of it runs (#52).
- An opt-in `unseen-hash` guard refuses a commit hash in an outbound message that no tool output in the session showed (#52).
- Custom guard entries take `args_all`, `args_none` and a subcommand list, so an unpinned `gh pr merge` can be refused on its own (#52).

### Changed

- Message guards now also read message scripts run through a shell or a variable, and the SendMessage tool (#52).
- The calendar guard can skip its guessed-time check with `"guessed_times": false` (#52).

## [1.28.1] - 2026-11-23

### Fixed

- `gate_lock.py` never hands its lock to the gate's child processes, so a long-lived child can no longer keep the lock after the job ends (#51).
- A `gate_lock.py run` killed with `kill -9` now reports that its gate still runs instead of clearing a lock that is still in use (#51).
- The multi-session guide says never to switch a watcher off while changing it (#51).

## [1.28.0] - 2026-11-23

### Added

- `multi-session-delivery` gains `queue_sync.py`, which rewrites the merge queue from live GitHub state (#50).
- It drops merged and closed pull requests, puts ready ones first, and flags any that target another branch (#50).
- It is a dry run by default and writes only with `--yes` (#50).

## [1.27.0] - 2026-11-23

### Added

- The message bus gains `idle.py`, which flags a lane whose open items are all inside their ETA but that shows no sign of work (#49).
- It reads the lane's last bus line, and optional commit times and busy status, before calling a lane idle (#49).

## [1.26.0] - 2026-11-23

### Added

- `payments-integrity` gains `confirm_status.py`, which polls a gateway until a payment status is final (#48).
- It reports paid or failed only when the reference, amount and currency match, and otherwise reports pending or mismatch by exit code (#48).

## [1.25.0] - 2026-11-23

### Added

- `shared-infra-changes` gains `kube_apply_check.py`, which runs before `kubectl apply` (#47).
- It refuses an apply when the live cluster has drifted from the reviewed plan: wrong context, namespace, resource version or owner label (#47).

## [1.24.2] - 2026-11-21

### Fixed

- The process-group kill helpers in `timer.py` and `gate_lock.py` refuse a group id of 1 or less, a value that is not an integer, and our own groups (#46).
- A mocked process can no longer turn a cleanup call into a signal sent to every process of the user (#46).

## [1.24.1] - 2026-11-21

### Added

- `multi-session-delivery` gains a long-run guide for about ten sessions over a week, with measured numbers (#45).

## [1.24.0] - 2026-11-21

### Added

- `multi-session-delivery` gains `timer.py`, which makes fixed-time routines systemd user timers that survive the session (#44).
- It validates the schedule, bounds each run in time and refuses a first run too close to its deadline (#44).
- `timer.py check` reads the next run back, and `pause` and `resume` never fire a missed run (#44).

## [1.23.0] - 2026-11-20

### Added

- `reading.py check-report` flags status claims such as merged, released or verified that have no source read in the same run (#43).

## [1.22.0] - 2026-11-20

### Added

- `quality-gate` gains `gate_lock.py`, which runs one pre-push gate at a time per user (#42).
- A lock left by a killed gate is cleared at once, so later pushes no longer wait on it (#42).

## [1.21.1] - 2026-11-20

### Fixed

- `send.sh` treats every refusal code from the bus check as a refusal, so a new rule can no longer let a line through unchecked (#41).

## [1.21.0] - 2026-11-20

### Added

- `overdue.py --suggest` proposes an ETA from the lane's past lateness (#40).

### Changed

- The bus refuses a later ETA on an item unless the line gives its cause (#40).

## [1.20.0] - 2026-11-20

### Added

- `multi-session-delivery` gains `reading.py`, which prints every status read from a file with its source time and age (#39).
- It flags a reading as stale or from the future, so an old value is not reported as current (#39).

## [1.19.1] - 2026-11-20

### Fixed

- `lessons.py guards --target` judges a candidate registry from the live registry's folder, so its relative paths resolve the same way (#38).

## [1.19.0] - 2026-11-20

### Added

- The calendar guard reads a file of approved workday exceptions, with an optional list of approvers (#37).

## [1.18.0] - 2026-11-20

### Added

- `arsenal repoint` lets running Claude Code sessions use the newest installed plugin from their next hook call, without a restart (#36).
- `--dry-run` prints the plan and `--undo` restores the previous version folders (#36).

## [1.17.0] - 2026-11-20

### Added

- `multi-session-delivery` gains `merge_slot.py`, a first-in, first-out turn to update and merge a pull request (#35).
- A pull request joins the queue after it is refused as out of date a set number of times (#35).

## [1.16.2] - 2026-11-20

### Fixed

- The help-probe guard now sees a script named through a variable set earlier in the same command line (#34).

## [1.16.1] - 2026-11-19

### Fixed

- `overdue.py` reads the short ETA forms people type, such as `MM-DD HH:MM` and `HH:MM` (#33).
- It counts the ETAs it cannot read instead of silently reporting every item as late (#33).

## [1.16.0] - 2026-11-19

### Added

- `lessons.py metrics` reports lessons added and repeated, guarded and unguarded counts, and guard fires, per ledger and per lane (#32).
- With `--bus` it adds ETA accuracy from the message bus, and `--json` gives the same report for machines (#32).

## [1.15.0] - 2026-11-19

### Added

- `delivery-board-sync` gains a close check that completes a tracker task only with one evidence line per closing criterion (#31).

## [1.14.0] - 2026-11-19

### Added

- `lessons.py guards --registry` checks a candidate registry before it is written into the shared file (#30).

### Changed

- `lessons.py guards` judges only the plugin versions an install still uses, not every cached folder (#30).

## [1.13.0] - 2026-11-19

### Added

- The session-start header lists lessons that keep repeating without a guard until each gets one (#29).
- `lessons.py exempt` records why no check can catch a lesson, and the weekly retro lists the unguarded repeats (#29).

## [1.12.0] - 2026-11-19

### Added

- A calendar guard checks dates and times in outbound messages: a weekday that does not match its date, a day outside the workweek, or a guessed time (#28).

## [1.11.1] - 2026-11-18

### Fixed

- `overdue.py` escalates by hours past an item's first promised ETA, not by how long it has been open (#27).

## [1.11.0] - 2026-11-18

### Added

- A built-in `pipe-exit` guard refuses acting on the exit status of a check whose output was piped through a filter (#26).

## [1.10.0] - 2026-11-18

### Added

- `lessons.py guards` checks the registry against every installed plugin version before a change goes live (#25).

### Fixed

- The lesson-guard hook skips a registry entry it cannot read instead of rejecting the whole file and blocking every command (#25).

## [1.9.1] - 2026-11-18

### Fixed

- `send.sh` stamps the inbox line and the event line with one UTC time, taken from `BUS_NOW` when it is set (#24).

## [1.9.0] - 2026-11-18

### Added

- The message bus requires an ETA or evidence on every started, stopped and finished item, and refuses lines that lack one (#23).
- The coordinator gains overdue, ETA accuracy and bus health reports (#23).

## [1.8.0] - 2026-11-18

### Added

- Four `smart-*` eval cases catch plausible wrong fixes, with recorded results (#19).
- A real-task eval reconstructs a refund bug from an application repository, with hidden acceptance tests (#21).

### Changed

- The skill listing a session loads is cut from about 24,100 to about 7,800 characters, with each description at most 180 characters (#20).

## [1.7.0] - 2026-11-18

### Added

- An opt-in `rerun-after-red` guard refuses running a failed check or push again until a cause is noted (#18).
- `lessons.py cause` records that cause in one line (#18).

## [1.6.1] - 2026-11-17

### Fixed

- The secret filter now catches bearer tokens and payment secret keys (#17).

## [1.6.0] - 2026-11-17

### Added

- The Stop gate reports dead code left by the turn: commented-out code, debug leftovers and orphaned imports, with a new `dead-code` skill for whole repositories (#16).
- A skill router names up to two matching skills for each prompt, and a cost guard questions subagent calls that ask for a more expensive model (#16).
- The `usage-stats` skill shows, from local records only, how often the plugin helped and where a skill should have fired (#16).
- The `ship` skill runs the gate, commits, pushes, opens the pull request and waits on CI with a bounded fix loop (#16).
- `arsenal doctor` checks the install and prints the exact repair for each problem (#16).

### Changed

- Builder subagents default to the balanced model to cut cost (#16).

## [1.5.0] - 2026-11-16

### Added

- Lesson-pattern guards refuse habit mistakes at the tool call, such as a `pgrep -f` wait loop, a hook bypass, a `--help` probe or a secret in a message (#15).
- A registry ties guards to lessons, and a hit log records each refusal (#15).
- `lessons.py unguarded` lists lessons that keep repeating with no guard, and `lessons.py hits` counts guard refusals per lesson (#15).

## [1.4.0] - 2026-11-16

### Added

- An operating-core hook injects a short core of rules at session start, and compaction hooks save and restore the work state (#12).
- Enforcement hooks add a Stop gate for changes without tests and a guard for destructive commands (#13).
- Hook configs for Codex, Gemini, Cursor, Copilot and Antigravity install with `--hooks` (#13).
- A trigger eval covers every skill, real-task evals compare runs with and without the plugin, and a token benchmark measures the plugin's fixed cost (#12, #13).
- `lessons.py show` prints one lesson in full (#14).

### Changed

- Lesson listings print one line per lesson, and project and global lessons share the session-start space fairly (#14).

### Fixed

- `ci_wait.py` and `merge_green.py` time out a `gh` call instead of hanging (#13).
- Lessons added in parallel are no longer lost, because the ledger file is locked (#13).
- The `quality-gate` skill no longer gives the invalid `dotnet test --no-incremental` command (#13).
- The message bus lock is taken atomically and a stale lock is taken over (#13).

## [1.3.1] - 2026-11-11

### Changed

- The `code-reviewer` and `qa-engineer` subagents run on the balanced model to cut cost (#11).

## [1.3.0] - 2026-11-10

### Added

- A read-only `risk-manager` subagent checks a coordinator's reports, tracker changes and instructions against their sources, and watches milestone risk (#10).

## [1.2.1] - 2026-11-05

### Changed

- The `node-specialist` subagent runs on a new balanced model tier to cut cost (#9).

## [1.2.0] - 2026-11-04

### Added

- An always-on minimal-change rule, tool read and write discipline, a `code-explorer` subagent and a `handoff` skill save tokens (#2).
- New `requirements-grilling`, `implementation-plan` and `mcp-server` skills, with UI/UX and workflow references (#3).
- A `reverse-engineer` skill traces one feature of a third-party app and rebuilds it clean-room (#4).
- A `lessons-learned` skill keeps a mistake ledger that loads at session start through a plugin hook (#5, #6).
- Five skills fill known gaps: `accessibility-audit`, `refactor-legacy`, `threat-model`, `kubernetes-ops` and `mobile-expert` (#7).
- A `multi-session-delivery` skill describes a coordinator with build lanes for several sessions on one product (#8).

### Fixed

- `lessons.py active --hook` prints SessionStart JSON, so the lessons reach the session (#7).

## [1.1.0] - 2026-10-12

### Added

- 16 skills from production practice, such as `ci-wait`, `quality-gate`, `payments-integrity`, `incident-response` and `legacy-parity` (#1).
- Three read-only subagents: `spec-reviewer`, `infra-reviewer` and `legacy-analyst` (#1).
- A plugin troubleshooting table in the README (#1).

### Fixed

- The Claude Code plugin now loads its subagents; before, none of them loaded (#1).

## [1.0.0] - 2026-10-04

### Added

- Skills, always-on rules and subagents for review, testing, security, QA, DevOps, frontend, backend, databases and UI/UX.
- A build that generates each agent's files and a Claude Code plugin from one `.agents` source.
- Non-destructive installers for every supported agent.
- CI with lint, test and smoke workflows.

[1.37.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/76
[1.37.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/75
[1.36.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/68
[1.35.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/67
[1.34.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/66
[1.33.5]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/65
[1.33.4]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/64
[1.33.3]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/63
[1.33.2]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/62
[1.33.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/61
[1.33.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/60
[1.32.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/59
[1.32.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/58
[1.31.2]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/57
[1.31.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/56
[1.31.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/55
[1.30.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/54
[1.29.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/53
[1.29.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/52
[1.28.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/51
[1.28.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/50
[1.27.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/49
[1.26.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/48
[1.25.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/47
[1.24.2]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/46
[1.24.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/45
[1.24.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/44
[1.23.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/43
[1.22.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/42
[1.21.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/41
[1.21.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/40
[1.20.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/39
[1.19.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/38
[1.19.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/37
[1.18.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/36
[1.17.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/35
[1.16.2]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/34
[1.16.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/33
[1.16.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/32
[1.15.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/31
[1.14.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/30
[1.13.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/29
[1.12.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/28
[1.11.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/27
[1.11.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/26
[1.10.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/25
[1.9.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/24
[1.9.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/23
[1.8.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/22
[1.7.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/18
[1.6.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/17
[1.6.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/16
[1.5.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/15
[1.4.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/14
[1.3.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/11
[1.3.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/10
[1.2.1]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/9
[1.2.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/8
[1.1.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/pull/1
[1.0.0]: https://github.com/abdulazeem-m0uneer/senior-developer-arsenal/tree/06d948df41c453d1d353752fcbf5868cc0962363
