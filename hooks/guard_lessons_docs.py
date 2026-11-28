#!/usr/bin/env python3
"""The per-rule reference text of guard_lessons (its module docstring continues with it): one entry per built-in rule."""

RULES = r"""Built-in rules:
  pgrep-wait-loop    while/until pgrep -f: the pattern matches the waiting shell's own command line, so the loop
                     never ends. Wait on a recorded pid ($!), a lock file or a completion notice.
  hook-bypass        git --no-verify, git commit -n, setting core.hooksPath, git run with HUSKY=0 (on the
                     command or exported earlier in the same command line).
  help-probe         a script (a known suffix such as .sh or .py, run directly or through an interpreter, or a
                     command named in `programs`) run with --help, or with -h as its only argument: it may not parse
                     the flag and run for real. An interpreter run on a variable whose value is not known here
                     (`python3 "$SCRIPT" --help`) counts too: what follows an interpreter is a script.
  secret-in-message  a secret-looking value in the arguments of a command named in `programs` (none by default).
  calendar           in text a call sends (gh comments, PRs and issues, git commit messages, the registry's
                     `programs`, outbound MCP tools): a weekday that does not match its date, a date that does
                     not exist, a guessed time (16:4x), and with "workweek" (Sun-Thu) a promise on another day.
                     "guessed_times": false (hooks from 1.29.0, so give that entry "min_version": "1.29.0")
                     turns the guessed-time check off, for teams whose messages carry informal times
                     ("checked 14:5x"); weekdays, dates and the workweek are still judged.
                     "exceptions": "workdays.txt" names a file of approved extra workdays, one line per date,
                     `YYYY-MM-DD approved-by <who>: <reason>` (# comments allowed); a promise on a listed date
                     passes, and the refusal names the file. A relative path is read from the folder of the
                     registry file that holds the entry. A missing, unreadable or malformed file never refuses a
                     command: its good lines apply, the rest is a problem line (registry_problems, the session-start
                     header, `lessons.py guards`). "approvers": ["A. Lead"] accepts only lines approved by a listed
                     name (exact, case-sensitive); without it the record is advisory, no stronger than the word,
                     because anyone who can write the file can add a line: keep it outside the repository, owned by
                     the person who approves. Hooks before the release that added "exceptions" skip the whole
                     entry for the unknown key, so give such an entry "min_version": that release.
                     See guard_calendar.py.
  pipe-exit          a check (the Stop gate's test, build, lint or CI classifier), a git commit or a local script
                     piped into a later command, whose exit status is then acted on (&&, ||, if/while/until/!, or $? read by
                     the next command) without set -o pipefail or ${PIPESTATUS[...]}: the status is the last
                     command's, so a failed check reads as success.
  rerun-after-red    off until a registry entry names it. A test, build, lint or check command (the same check as the
                     Stop gate counts: tool and subcommand, flags and wrappers ignored) or a `git push` (same
                     operands) that failed last in this session and has no later pass, run again before a cause note
                     (`lessons.py cause "<assertion or check>: <cause or unknown>"`) was recorded after the failure.
                     A cause note inside a list (`;`, `&&`) is recorded (also when a later step failed, from its
                     "cause noted; rerun the failed command now" line), and the steps after an accepted one (both
                     sides, no --help) in that call are not refused when it runs on every path to them: in the same
                     if/case alternative or outside any, not in a || arm, after && only behind a cd to a directory
                     that exists, and naming a lessons.py that exists or a `lessons` shim on PATH; a step in a || arm after it is still judged, and
                     the steps before it are judged by the checks each runs. A check named by options only (`node --test <file>`) keeps
                     them in its name; a name that is only a variable (`bash ${test}`) is not recorded.
                     Hooks from 1.38.0 also judge CI: `gh run rerun <id>` (with or without --failed or --job) of a run
                     a gh run view, watch, list or gh pr checks output showed failed or cancelled (also the api rerun
                     calls), and `gh workflow run` of the workflow seen red, are refused until a cause note followed
                     that output; a green run closes them; a rerun that started re-opens the run (a second one needs
                     a new note); a gh pr checks output closes a run id whose
                     rows are all pass (or pass and skipping), and the "*" reds when every row passes; a red with no
                     run id or workflow name refuses only for 2 hours; a run never seen red passes, as do gh run
                     view, gh run watch and gh pr checks. See guard_ci_rerun.py.
  shell-syntax       off until a registry entry names it. A command the shell cannot parse (`<shell> -n`, "shell":
                     "bash" by default; bash, sh, dash, zsh, ksh or mksh), refused before any part runs: an
                     apostrophe inside a single-quoted argument ends the quote, and the lines before the error would
                     run. Set "shell" to the shell the agent runs commands in (zsh where that is the login shell):
                     a bash parse refuses valid zsh syntax. Judged first. Passes when the shell is missing or slow.
                     Entries need "min_version": "1.29.0".
                     See guard_syntax.py.
  unseen-hash        off until a registry entry names it (give it "min_version": "1.29.0"). In the same outbound text
                     as calendar (for git commit and tag, the message only), a commit-like hash (7 to 40 lowercase
                     hex characters with a digit and a letter, not a UUID segment, not part of a longer hex run, not
                     after #; a # after it and URLs included) that is not a prefix of a hex run in an entry of this
                     session's transcript, or the subagent's own, that the assistant did not write (user text such
                     as prompts, briefs and peer messages, tool results, queued messages and attachments; never the
                     assistant's text, thinking or tool inputs, request copies of them or compaction summaries; the
                     last "window_mb" MB, default and maximum 16). "allow": words that are not hashes (ed25519 and
                     binary literals are built in). MCP id fields (id, message_id, threadId; not sha) are not
                     judged. Fails open when the transcript is missing, unreadable or slow (on a timeout, only
                     hashes already judged unseen refuse). See guard_unseen_hash.py.
  unseen-time        off until a registry entry names it (give it "min_version": "1.33.5"). In the same outbound text
                     as unseen-hash, a clock time HH:MM (00-23:00-59) that no entry of this session's transcript the
                     assistant did not write shows (the same entries and window as unseen-hash). An ISO timestamp
                     with a zone there (2026-11-25T16:36:44Z) counts as its written time, its UTC time and its
                     time in the machine's zone. Not judged: a time in an "ETA MM-DD HH:MM" or "ETA HH:MM" clause,
                     after by, until, before or at the latest, in a code span, fenced block or URL, and the entry's
                     "allow" words (exact times). "programs", "window_mb" and "allow" as for unseen-hash; a time
                     older than the window still counts when guard.py track kept it: after each Bash call while the
                     rule is on, it reads the next 4 MB of the transcript (about 0.1 s while catching up, nothing when
                     idle) and keeps the times seen entries show in ~/.cache/arsenal/seen-times
                     ($ARSENAL_SEEN_TIMES_DIR); a line over 4 MB is skipped. A program
                     may be a task-tracker writer or report sender, also one an interpreter runs (`node api.mjs ...`;
                     a GET or HEAD request is a read): its argv text (also --body), a here-document body, and the
                     content of a --body-file or --file path readable at judge time are judged (`--body-file -`: the
                     here-document or echo/printf text piped in); a file the same call writes (> >> &> tee, any spelling) is judged by the call's here-document and echo/printf text
                     (an appended file by its old content too), not by what it holds now; a relative path starts from
                     the session directory, by calendar and unseen-hash too. Programs
                     that read positional file paths or a fixed folder (a mail composer or resender) are
                     not covered. Fails open
                     when the transcript is missing, unreadable or slow. See guard_unseen_time.py.
  typed-sha          off until a registry entry names it (give it "min_version": "1.30.0"). A literal hex value for
                     gh pr merge --match-head-commit (`V` or `=V`) or git push --force-with-lease=<ref>:<V> that is
                     shorter than 40 characters (the merge pin only: GitHub refuses it) or, 7 to 40 characters, was printed by no transcript entry the assistant did
                     not write (unseen-hash's check and window). A $NAME set on the same line is read, and $'<hex>'
                     counts as typed; a value from $(...), a backtick or a variable set elsewhere passes. Without a
                     transcript, or on an error or timeout, only the short-pin check applies. Bash only. See
                     guard_typed_sha.py.
  oom-first          off until a registry entry names it (give it "min_version": "1.30.0"). A Bash call that exited
                     134 or 137 (guard.py track's error events; an interrupted call does not count), run again (the
                     same command by the digest track stores of what it ran, wrappers, launchers and echo left out,
                     or one sharing a check key with it; --help and --version pass) before a later call read the
                     kernel log (journalctl -k, --dmesg, -t kernel or a grep for oom; dmesg; a cgroup's
                     memory.events; systemctl status). A failed call that ran under timeout (also behind systemd-run
                     or unshare) is also cleared by a later `lessons.py cause` note: exit 137 is then often the
                     timeout's SIGKILL. Only the newest 32 armed failures are judged. Reads the session state through
                     `session`; without it, or on a state it cannot read, it passes. Bash only. See guard_oom.py.
  timer-safety       off until a registry entry names it (give it "min_version": "1.33.0"). Bash: systemctl restarting
                     a *.timer (restart, try-restart, reload-or-restart, try-reload-or-restart, force-reload and
                     their aliases condrestart, reload-or-try-restart, condreload), or stopping one (stop, condstop,
                     disable/mask --now) and starting it again (start, enable/reenable --now) in the same call and
                     scope (through a for loop's values and ssh's remote command too): a Persistent= timer then
                     fires its missed run at once. Write, Edit and MultiEdit
                     (judge_outbound; for an edit, the file it would leave): a *.timer whose OnCalendar=
                     value `systemd-analyze calendar` refuses (one run, 2 s at most; a missing analyzer or a timeout
                     passes), or a *.service with Type=oneshot and no TimeoutStartSec=/TimeoutSec= that bounds it
                     (RuntimeMaxSec= does not). The reason names the fix. Fails open. See guard_timer.py.
  live-script        off until a registry entry names it (give it "min_version": "1.33.0"). A Write, Edit or MultiEdit
                     (judge_outbound) of a file a shell of this user reads now as its script: the shell (by
                     /proc/<pid>/exe or argv[0]: bash, sh, zsh, dash, ksh or mksh, bash-5.2 too) names it as its
                     script operand (same basename, or same file from its cwd; none with -c or -s), and a
                     descriptor from 10 up in /proc/<pid>/fd is the same file by device and inode (bash 255, dash
                     10; a script that ran cd still matches, one already replaced by mv does not, nor does a lock
                     file or saved stdout on 10 and up). A shell reads its script as it runs; python, node, perl
                     and ruby compile it first and never count. The reason says to write <path>.next, test it, then
                     mv it into place. Off without /proc; fails open. See
                     guard_live_script.py.
  dry-run-chain      off until a registry entry names it (give it "min_version": "1.33.0"). Bash: one command that runs
                     a program of the entry's "programs" (by name or path basename, or the script an interpreter runs;
                     none by default, so nothing is judged) as a dry run (--dry-run or --check, or no confirm flag;
                     a read-only status/wait/view call is neither) and later in the same command for real (a flag of "confirm", by default --yes, --apply,
                     --confirm or --force; it replaces the defaults): the real run goes ahead although the dry run
                     refused. Wrappers, sh -c, eval, ssh, pnpm/npm run and source as for the other rules; runs in
                     different if/else or case alternatives are not a chain. The reason says to run the dry run
                     alone, read its line, then the real run as a separate call. Fails open. See guard_dry_run_chain.py.
  outer-timeout      off until a registry entry names it (give it "min_version": "1.33.0"). Bash: one command that runs a
                     queueing program of the entry's "programs" (a gate-slot or lock wrapper; by name or path basename,
                     or the script an interpreter runs; none by default, so nothing is judged) under `timeout` (not
                     `timeout 0`) or `systemd-run` with a RuntimeMaxSec= other than 0 or infinity, at any depth of
                     wrappers (sudo, env [-S], nice, taskset, chrt, unshare, systemd-run, timeout, npx/pnpm/deno/bun
                     launchers, xargs, find -exec, docker exec, sh -c, su -c, eval, ssh): the timeout kills the job while it waits for its turn. The reason says to bound the
                     wait with the entry's "hint" (default "the tool's own wait setting") and to put the timeout
                     inside, on the command the program runs. A timeout inside the program and separate commands
                     pass, and so does a command that sets a variable of the entry's "no_queue_env" (at most 10 names)
                     to a value other than empty, 0, false, no or off, on the command or earlier on the line (a dry
                     run does not queue). Fails open. See guard_outer_timeout.py.
  wait-on-text       off until a registry entry names it (give it "min_version": "1.33.5"). Bash: a while/until loop whose
                     condition (not its body) reads a file of the entry's "paths" (shell globs; with a "/" they match
                     as a path suffix, without one the basename) with grep, rg, awk, sed, tail or cat: message text can
                     quote the event it waits for. Without "paths" nothing is judged. The reason says to wait on the
                     authoritative state. Fails open. See guard_wait_on_text.py.
  durable-path       off until a registry entry names it (give it "min_version": "1.33.5"). Bash: work scheduled to run
                     later whose script is under /tmp/ or in a scratchpad (a path with /scratchpad/, or a glob of the
                     entry's "scratch" list): systemd-run with --on-calendar, --on-active, --on-boot, --on-startup,
                     --on-unit-* or --timer-property, at or batch reading such a file or text, a crontab installed
                     from stdin with such a line. Write, Edit and MultiEdit (judge_outbound): a .service unit's
                     ExecStart*, a crontab file's or an at job file's command under those places. Running a script
                     now passes. The reason names the path and the fix. Fails open. See guard_durable_path.py.
  container-limits   off until a registry entry names it (give it "min_version": "1.38.0"). Bash: `docker run`,
                     `docker create`, `podman run`, `podman create` (also the `container run` and `container create`
                     forms) without both a memory limit (-m or --memory above 0) and a CPU limit (--cpus or
                     --cpu-quota above 0, or --cpuset-cpus), unless the image's name (after the last /, before : or @)
                     is in the entry's "allow" list; with "compose_project": true also `docker compose up` and
                     `docker-compose up` without -p or --project-name (or a COMPOSE_PROJECT_NAME set on the command or
                     earlier on the line, or a name set in the compose file's top-level `name:` or in .env /
                     --env-file in the current folder): two runs collide on container names. `docker run --help`, ps,
                     stats, logs and exec pass. The reason names what is missing. Fails open. See
                     guard_container_limits.py.
  commit-then-push   off until a registry entry names it (give it "min_version": "1.39.0"). Bash: a `git push`, or a
                     program of the entry's "programs" (a push wrapper such as push_once.py; by name or path basename,
                     also through a launcher or a shell variable, or the script an interpreter runs; none by default,
                     so only git push is judged), that follows a `git commit` (not --dry-run; git -C <dir> and other
                     global options are read through) unless both `git status` and `git log` (`git rev-parse HEAD`
                     counts as the log) were read after the commit and before the push, whatever the separators
                     (&&, ||, ;, newlines, if/then blocks) and also inside a $( ) or backticks, bare or double-quoted.
                     The commit may be in an earlier call: while the rule is on, the tracker (guard.py track) records
                     each call's commits, pushes, statuses and logs (also of a call that exited non-zero, taken as
                     having run all its commands), and a later push is judged against them; a push settles its
                     repository's commit. Not reads: output to /dev/null, git rev-parse --abbrev-ref HEAD, a command
                     inside a $( ) or backticks (captured, unless an echo or printf prints it), the arm of a || (it
                     runs only when the command before it failed), a list sent to the background with &. A read in
                     another arm of an if or case than the push does not count; a commit in another arm is not before
                     it; a read in the test of an if counts. The repository is the call's directory moved by cd and
                     git -C <dir> (a directory that is not known, such as $DIR, matches any); events are kept per
                     agent and repository (another repo's or subagent's commit is not this push's); an ssh remote
                     command and a here-document a shell runs (bash <<E, | bash) are judged. A push with no commit
                     before it, push --dry-run or -n, a push to a repository on this machine (a path, ./, ../, ~,
                     file://, or a variable set to one earlier in the same call; a remote name, host URL, host:path or
                     unknown variable still counts), push_once.py hook or check (they push nothing) and a
                     here-document that only writes a script pass. The reason says to read both, then push. Fails
                     open. See guard_commit_push.py.
  tool-result-read   off until a registry entry names it (give it "min_version": "1.33.5"). A Read (judge_outbound) of a file
                     inside <project>/<session>/tool-results/ under ~/.claude/projects/, or one
                     matching a glob of the entry's "paths" (with a "/" a path suffix, without one the basename): a
                     persisted oversized tool result. The reason says to narrow the source (a filter, a smaller
                     query, an extraction prompt). Other files there (memory, transcripts) pass. Fails open. See
                     guard_tool_result_read.py.
Also not seen: a pgrep inside a quoted "$(...)" in a loop condition or in the loop body (`while true; do pgrep -f x
|| break; done`), and a here-document fed to a shell
(`bash <<EOF`), whose body is dropped as data.
Time budget: string work and at most a few stat calls and two small file reads per Bash call, plus one `<shell> -n`
run (at most 1 s) when shell-syntax is on; unseen-hash adds one bounded transcript read (0.2 s at most), only when an
outbound text holds a hash, and typed-sha one more (one budget for the call) when a command types a SHA of 7
to 40 characters; oom-first and commit-then-push read the session state file once (shared with rerun-after-red); timer-safety runs one
`systemd-analyze calendar` (2 s at most) only for a Write, Edit or MultiEdit of a .timer file holding OnCalendar=
values, and reads the edited unit file (256 KB at most) only for an edit of a .timer or .service file; live-script
reads /proc (at most 2000 of this user's pids, 50 ms) for a Write, Edit or MultiEdit of an existing file;
dry-run-chain, outer-timeout, wait-on-text, durable-path, container-limits and tool-result-read are string work only (durable-path reads the edited
unit, crontab or at file for an Edit, 256 KB at most).
"""
