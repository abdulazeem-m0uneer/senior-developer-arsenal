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
```

One lesson per line. Fields are separated by ` | `; the script replaces any `|` in your text with `/`. Tags are lowercase stack or area words (`node`, `sql`, `git`, `deploy`, `auth`) so `search` finds them.

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

After promoting, `archive <id>` and mention the guard in the commit message so the history explains why the lesson left Active.

---

## 5. Loading Automatically

A lesson nobody loads teaches nothing. Pick one:

- **Hook (Claude Code)**: add to `.claude/settings.json` so the Active list is printed into every session's context. Adjust the script path to where the skill is installed.

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command",
        "command": "python3 .agents/skills/lessons-learned/scripts/lessons.py active" } ] }
    ]
  }
}
```

- **Pointer in `AGENTS.md`**: one line, "At session start run `python .agents/skills/lessons-learned/scripts/lessons.py active`."
- **Manual**: the user runs `/lessons-learned`.

Cost: at most 15 short lines per session.

---

## 6. Team and Global Use

- Commit `.agents/lessons.md` so every agent and teammate shares it; review additions like code.
- For lessons that hold across all your projects, keep a second ledger (for example `~/.agents/lessons.md`) and load it with `--file`.
- Prune: lessons not hit for months and covered by a guard belong in Archive, not Active.
