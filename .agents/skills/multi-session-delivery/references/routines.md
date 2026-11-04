# Routines & Timers

How the coordinator's timed work runs so that reports and watches happen on time whether or not a session is open.

---

## 1. Why System Timers

| Option | Fails because | Use |
| :--- | :--- | :--- |
| `sleep` inside a session | Dies silently when the session closes | Never for a report |
| In-session cron of the agent tool | Jitter moves the run time; jobs expire and die with the session | Short reminders only |
| System timer (systemd user timer, launchd, Task Scheduler) | Survives restarts; `Persistent=true` catches up after boot | Every fixed-time routine |

Check each timer's next run time against the required time (`systemctl --user list-timers`) before saying a routine is set.

---

## 2. Timer Table (adapt names and times)

| Routine | Schedule | Guard | Model needed |
| :--- | :--- | :--- | :---: |
| day-start | every 15 min | runs once per day, after the workday start written by the coordinator | yes |
| watch | hourly inside the workday | skips outside the workday | yes |
| staging-alerts | every 5 min, all day | dedupe by alert fingerprint; "unreachable" only after 3 misses | no (plain script) |
| reconcile | every 2 h inside the workday | caps moves per run | yes |
| reports | fixed time daily | once per day | yes |
| day-end | every 15 min | runs once, 15 min before the workday ends | yes |
| weekly | fixed day and time, `Persistent=true` | once per ISO week, own lock, time limit | yes |

The workday start is a small state file the coordinator writes when the sessions start (`workday.json`: start time, length in hours). Watches read it and exit `ok` with "outside workday" when it does not cover now.

---

## 3. Runner Contract

One runner script starts every routine with the routine's prompt file:
1. Takes a lock per routine; a second start while one runs exits `skipped`.
2. Puts the read-only shims first on `PATH` and runs the agent headless with a deny list for write tools outside the routine's own state folder.
3. Applies a time limit and a daily quota check; over quota exits `skipped-quota`.
4. Writes the log to `<log dir>/<routine>-<date>.log`. The last line is exactly one status word: `ok`, `partial` or `failed`.
5. Anything other than `ok` (including a missing status line) raises a desktop alert and a bus line to the coordinator.

Test the runner with a fake agent command that prints each status word before enabling any timer, and run `bash -n` after every edit.

---

## 4. Read-Only Shims

Routines read untrusted text (ticket comments, emails, alerts). Shims for the version control tool, the forge CLI, the cluster CLI and the merge script sit first on `PATH` and allow only read subcommands:
- version control: `log`, `show`, `diff`, `status`, `fetch` without a refspec into a local ref, `ls-remote`, `rev-parse`; refuse `-c` and `--git-dir` style overrides;
- forge CLI: `pr view`, `pr list`, `pr checks`, `run view`, and `api` only without `-X`/`--method` other than GET and without `-f`, `-F`, `--field`, `--raw-field` or `--input` (any of those turns the call into a write);
- merge script: always refuse.

An absolute path to the real binary gets round a shim, so the routine prompts also forbid writes. Shims reduce the blast radius; they are not a sandbox.

---

## 5. Prompt Skeleton for One Routine

```text
You are the <project> coordinator running the <routine> routine, headless.
Read: SESSION-RULES.md, .agents/OPERATING-MODEL.md, .agents/pm/workday.json.
Do: <3-6 numbered steps, each naming the tool or script and its limit (pages, moves, tickets)>.
Never: write code, push, merge, change settings, put secrets in any output.
Report: <recipients and format>.
End with one line: ok | partial | failed.
```
