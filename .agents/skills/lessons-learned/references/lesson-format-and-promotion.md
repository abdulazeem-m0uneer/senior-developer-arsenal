# Lesson Format, Triggers & Promotion

Detail for the `lessons-learned` skill: the line format, what counts as a capture trigger, worked examples, the promotion ladder, and how to load the Active list automatically.

---

## 1. File Layout

```markdown
# Lessons Learned

<!-- Managed by lessons.py. ... -->

## Active
- L001 [sql,migration] hits:2 | 2026-11-04 | Mistake: dropped a column that a report still read | Cause: assumed no reader outside the API | Rule: grep every reader (jobs, reports, views) before dropping a column | Check: grep -rn "<column>" in repo and SQL views

## Archive
- L002 [git] hits:3 | 2026-11-09 | Mistake: force pushed over a teammate's commit | Cause: assumed the branch was mine alone | Rule: push with --force-with-lease | Check: git log origin/<branch>..HEAD before pushing | Promoted: .agents/rules/lessons-promoted.md
```

One lesson per line. Fields are separated by ` | `; the script replaces any `|` in your text with `/`, cuts each field at 200 characters and the tag list at 60. Tags are lowercase stack or area words (`node`, `sql`, `git`, `deploy`, `auth`) so `search` finds them and the session-start ranking can match them against changed files. `Promoted:` is present only on a promoted lesson and names its guard. Project ids start with `L`, global ids with `G`.

Only lines under `## Active` are loaded. A lesson written by hand above the section headers is kept in the file but never loaded; `check` reports it as a problem. The file is read as UTF-8 with undecodable bytes replaced, so a damaged file degrades instead of failing the session; `check` reports such a file and every command that writes it refuses until it is converted, so the bad bytes are never silently replaced. A global ledger that cannot be read is ignored with a note on stderr.

**Writing safely.** Every command that changes a ledger (`add`, `bump`, `archive`, `promote`, `globalize`) holds an exclusive operating-system lock for that ledger while it reads, changes and rewrites it (`flock` on POSIX, `msvcrt.locking` on Windows; the lock file is `.<ledger name>.lock` beside the ledger, so processes with different temp directories still exclude each other; it is left in place, so git-ignore it, for example `.agents/.*.lock`; it falls back to the temp directory when the ledger directory is not writable). The system releases the lock when the process exits, however it exits, so a crash cannot leave a stale lock. A writer that cannot get the lock within 10 seconds exits 2 and writes nothing. The file is replaced in one rename, so a reader never sees half a ledger.

**Secrets.** `add` exits 2 on text that looks like a credential: an assignment to a key, secret, password, token or bearer name; a known format (`sk-...`, `ghp_...` and the other GitHub prefixes, `AKIA...`, `xox?-...`, a three-part JWT, a PEM `-----BEGIN` line); or an unbroken run of 32 or more characters that reads as random (hex longer than 40, or mixed letters and digits with no word-like pieces). File paths, 7 to 40 character git SHAs, UUIDs and long identifiers pass. Limits: a random string in a single letter case with no prefix and no key name beside it can pass, and so can base64 that contains `/`; the filter is a net, not a licence to paste credentials.

---

## 2. Capture Triggers

| Trigger | Record when | Typical cause field |
| :--- | :--- | :--- |
| User correction | The user redid, reverted, or rejected the work and said why | assumed X without checking Y |
| Confirmed root cause | Rule 0 on failure ended with a verified cause | skipped step Z |
| Failed build or test | The failure traces to the agent's own assumption | trusted a stale type, config, or doc |
| Blocker review finding | `[Blocker]` or `[Performance]` on the agent's own change | did not run the check the reviewer ran |
| Claim gate breach | The agent said done or passing without fresh evidence | reported from an earlier run |
| Same tool error twice | A repeated invocation mistake | wrong flag, path, or order |
| Self-detected rework | The agent reverted or redid its own edit | first attempt rested on an unchecked assumption |
| Self-detected false statement | The agent finds an earlier claim was wrong | stated from memory instead of reading the file |
| Lesson broken again | A loaded lesson was violated | read the lesson but did not apply it: `bump`, and consider promotion |

Do not record: typos, a flaky network, the user's taste ("prefers tabs"), a decision (use `decision-log`), a guess about the cause, or anything naming a person as the fault.

---

## 3. Writing Good Fields

| Field | Test | Weak | Strong |
| :--- | :--- | :--- | :--- |
| Mistake | Observable, no judgement | was careless with the migration | ran a migration that locked the table for 4 minutes |
| Cause | A false belief or skipped step | didn't think | assumed the table was small; never checked row count |
| Rule | An instruction that would have prevented it | be more careful | check `reltuples` before DDL; use `CONCURRENTLY` above 100k rows |
| Check | A command or observation | review it | `psql -c "select reltuples from pg_class where relname='orders'"` |

If the check is unknown, the script stores `none yet`; filling it in later is the first step of promotion.

---

## 4. Promotion Ladder

Text in a file only works if it is read and obeyed. Mechanical guards work every time. Climb as high as the mistake allows:

1. **A failing test or type error**: encode the mistake as a regression test (`test-every-change`).
2. **A lint rule, CI step, or `quality-gate` check**: the build fails on the pattern.
3. **A hook**: block or warn at the tool call (for example, refuse `git push --force` to a shared branch).
4. **A rule line** in the matching `.agents/rules/<file>.md`, proposed in a pull request.
5. **An `AGENTS.md` line**, only if it applies to most tasks; every line here costs tokens in every session.
6. **Stays a lesson**: low frequency, low cost.

The script does the bookkeeping:

| Command | Effect |
| :--- | :--- |
| `promote <id> --as test` | Prints a `unittest` stub named after the rule, failing with the lesson's check as its message. Marks nothing: adapt it to the project's test framework and make it pass. |
| `promote <id> --guard <path>` | The guard (test, lint config, hook, CI file) exists at `<path>`: the lesson moves to Archive with `Promoted: <path>`. Exits 2 if the path does not exist. |
| `promote <id>` | Rung 4: appends the rule, its check and the lesson id to `rules/lessons-promoted.md` beside the ledger (`.agents/rules/` for the project ledger, `~/.agents/rules/` for the global one; `--rules-dir` overrides), creating the file with `trigger: always_on` frontmatter, and marks the lesson promoted. Review the wording, change the trigger to `glob` with `globs` if it concerns one stack, and commit it. Agents that do not read `.agents/rules/` need the file wired in through their own rules mechanism or one line in `AGENTS.md`. |

A promoted lesson is no longer injected at session start. If the mistake happens again (`add` of a matching lesson, or `bump`), it returns to Active, keeps its `Promoted:` field, and the script prints `GUARD FAILED` with the guard's path: the guard did not hold and is what needs fixing. `check` lists un-promoted lessons at three hits as candidates, and recurred promoted ones separately. Mention the guard in the commit message so the history explains why the lesson left Active.

---

## 5. Loading Automatically

A lesson nobody loads teaches nothing.

- **Plugin install (Claude Code)**: nothing to do. `hooks/hooks.json` runs `lessons.py active --hook` on session startup, resume, clear and compact. The last matters: compaction drops context, and the hook puts the lessons back.
- **Other installs**: add the same to the project's `.claude/settings.json`, with the script path where the skill is installed:

```json
{
  "hooks": {
    "SessionStart": [
      { "matcher": "startup|resume|clear|compact",
        "hooks": [ { "type": "command",
        "command": "python3 .agents/skills/lessons-learned/scripts/lessons.py active --hook" } ] }
    ]
  }
}
```

- **Agents without hooks**: one line in `AGENTS.md`, "At session start run `python .agents/skills/lessons-learned/scripts/lessons.py active --hook`."
- **Manual**: the user runs `/lessons-learned`.

`--hook` emits the JSON a `SessionStart` hook uses to add context (`hookSpecificOutput.additionalContext`): a short instruction on how the agent records its own mistakes, then the project's Active lessons, then the global ones under a `Global lessons (every project):` line, or `(no lessons yet)` when both are empty, so a new project still gets the instruction. Plain `active` (no flag) prints every Active lesson as text for manual use.

What `--hook` selects. The host caps `additionalContext` at 10,000 characters and fifteen full-length lessons alone exceed that, so the hook output is limited to 4,000 characters:

1. The three most repeated lessons (two hits or more) come first, whatever the task.
2. The rest are scored against the session's files: the hook reads `cwd` from its stdin JSON (waiting at most half a second for it) and runs `git status --porcelain` and `git log -5 --name-only` there, each with a 1.5 second timeout. A tag that matches a word or file-type of a changed path (`py` counts as `python`, `sql` as `database`, `yml` as `ci`, and so on) scores 3; each matching word of the mistake, rule or check scores 1. Ties go to the newer lesson.
3. Without git, outside a repository, or on a timeout, every score is zero and the order is newest first.
4. Lessons are added in that order while they fit; a line over 700 characters is cut with ` ...`. If any did not fit, the last line is `(+N more: lessons.py search <words>)`.

The Active cap of 15 per ledger and its eviction rule are unchanged; ranking decides only what a session start shows. The hook never fails the session: on any error it prints nothing and exits 0.

Cost: about 85 tokens for the instruction, plus the script path, plus the lessons that fit, at most 4,000 characters (about 1,000 tokens) once per session start. Wall time measured on this repository on Linux, 15 lessons, median of 20 runs: 51 ms before ranking existed, 97 ms with it inside a git repository (two git reads), 65 ms outside one.

Not shipped on purpose: a `Stop` hook that forces a reflection every turn. It would spend tokens on turns with nothing to learn and can loop. What the Claude Code plugin ships instead is a conditional gate (`hooks/guard.py`): hooks on the Bash tool silently note each test, build, lint or CI command that exits non-zero, each one that passes, and each successful `lessons.py add` or `bump`; the `Stop` hook then blocks once, with the exact `add` command, only when such a failure has no later passing run of the same check (same tool and subcommand, whatever the flags and paths) and no lesson recorded after it. A turn with nothing to enforce prints nothing, so it costs no context. It cannot loop: it does nothing while `stop_hook_active` is true, and the question is written to the session state before it is shown, so the same failures are never asked about twice; answering that nothing was learned ends it. `ARSENAL_GUARD=off` disables it. Limits: a pipeline that hides the exit code (`pytest | tail`) is not seen as a failure and never counts as a pass, a narrower passing run (`pytest tests/a.py`) clears a wider failed one (`pytest`), and the gate cannot tell a check left red on purpose from a mistake, which is why it asks instead of recording. The self-audit in Step 5 of the skill still covers mistakes that no command reported.

---

## 6. Team and Global Use

- Commit `.agents/lessons.md` so every agent and teammate shares it; review additions like code.
- The global ledger is personal and lives outside every repository: `$LESSONS_GLOBAL_FILE`, default `~/.agents/lessons.md`. `active` and `search` read it after the project ledger; `add --global` writes to it; `globalize <id>` moves a project lesson there (the project copy is archived with `Promoted: global G###`; a matching global lesson gets the hits instead of a copy). Commands that take an id reach it through a `G` id or `--global`; `check --global` validates it. The script refuses to write a global ledger that sits inside the repository it is run from.
- What belongs there: mistakes about a tool or a habit that would repeat in any repository, such as a git flag, a shell quoting trap, a package manager's behaviour, or reporting a result without running the check. What does not: anything naming this project's files, schema, services, people or conventions; that stays in the project ledger, where the team sees it.
- A global lesson that says the same as an Active project lesson is not shown twice; the project's wording wins.
- Prune: lessons not hit for months and covered by a guard belong in Archive, not Active.

---

## 7. Measuring It

`evals/task-lesson-recall` checks that a recorded lesson changes behaviour. Its fixture is a small repository where the obvious edit (a generated `config/settings.json`) is the wrong one and `.agents/lessons.md` already says so; the graders pass only if the source template was changed and the generated file regenerated. Run it with the other `task-*` cases (see `CONTRIBUTING.md`); the with-plugin arm gets the lesson from the `SessionStart` hook, the baseline arm does not.
