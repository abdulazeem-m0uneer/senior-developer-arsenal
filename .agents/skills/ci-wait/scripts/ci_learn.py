"""Turn one red CI run into one lesson: classify why it failed, count the minutes it wasted, record or repeat it.

Usage: python3 ci_learn.py <run-id> [--repo [HOST/]OWNER/NAME] [--ledger PATH] [--global] [--dry-run] [--json]
Reads `gh run view <id> --json ...` and the failed jobs' log (`--log-failed`, last 2 MB only), then picks exactly
one class, first match wins: superseded (run cancelled, or every failed job cancelled; but a job GitHub cancelled at
its timeout-minutes, "exceeded the maximum execution time", is timeout), outside (ci_wait.OUTSIDE_CAUSES, only in
steps that print no test result, as a test's own stderr is the test's; GitHub's runner-lost and billing messages
count anywhere), timeout (a job concluded timed_out, or the runner's own job or step time limit in a step that shows
no failing test; never a timeout a test printed), coverage (threshold message, unless tests failed; pytest-cov's
"FAIL Required test coverage" is no failing test), lint/type (the tools' own output, never a bare tool name), test
(sub-kind snapshot), coverage (a failed job or step named coverage), unknown. The runner's echo of a step
("##[group]Run ..." up to "##[endgroup]", holding only cyan script lines, `shell:` and indented `with:`/`env:`
inputs) is source, not output, and never decides the class; a "Run ..." group holding anything else (a script's own
::group::), or left open, is output. When the 2 MB cut lands inside an echo group, its echoed lines up to
"##[endgroup]" are dropped too.
Minutes wasted: every job's run time for superseded, else the jobs that failed, timed out or were cancelled.
The lesson is tagged ci-<class>,repo-<name> in the lessons-learned ledger (--ledger, default $LESSONS_FILE or
.agents/lessons.md; --global: the global ledger): an existing one, Active or Archive, counts a repeat (as
`lessons.py bump`), else one is added with the class's rule. outside and unknown record nothing. The lesson's
Mistake ends in "; runs counted: <ids>" (the newest that fit): a run already counted prints "already counted",
records nothing and exits 0.
Prints "<class>[/<sub-kind>] <minutes> min wasted, run <id> <branch>: <lesson id> <added|repeat xN|already counted
(xN)>" and the first deciding log line; --json prints the same as one object; --dry-run writes nothing and never
exits 3.
A run that passed (success, skipped, neutral) has nothing to record, except that a success of the same workflow and
branch as the red run removes the repository's red-runs record (a record without those fields, an older one, is removed
only by a success at its head sha; no write on --dry-run); one still running is refused (exit 2).
A red run classed test also leaves its failed test files for push_once.py's unrun-red check (G038): one record per
repository, "owner/name" lower case, in the JSON file $ARSENAL_RED_RUNS (default ~/.cache/arsenal/red-runs.json):
{"owner/name": {"run": id, "head_sha": sha, "time": epoch seconds, "files": [paths], "workflow": name, "branch":
name}}; "time" is the run's own update time (its creation time, else now, when gh gives none). The files come from the failed
log's failure lines (pytest FAILED/ERROR, jest and vitest FAIL, one path per test file name found, `.py`, `_test.go`,
`.test.` and `.spec.` files); a log naming none records an empty list. A red run replaces the repository's
record unless the record's run id is higher; other repositories keep theirs. A success clears it only when its run id is
higher than the record's (its creation time against the record's time when the record has no run id). --dry-run writes nothing; a state file that cannot be written is a warning on
stderr, never a failure (the ledger result stands).
Exit codes: 0 recorded, already counted or nothing to record, 2 unreadable or unfinished run, gh error, usage or
ledger error,
  3 recorded, and the lesson now needs a guard (lessons.py's PROMOTE / GUARD FAILED / EXEMPT recurred hint);
  a repeat with no guard and no exemption also prints lessons.py's "ESCALATE <id> x<hits>: ..." line on stderr.
"""
import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "lessons-learned" / "scripts"))

import ci_wait  # noqa: E402
import lessons  # noqa: E402

EXIT_OK, EXIT_UNREADABLE, EXIT_ESCALATE = 0, 2, 3
LOG_MAX = 2 * 1024 * 1024  # bytes of the failed log kept, from its end
EVIDENCE_MAX = 200
RED_RUNS = "~/.cache/arsenal/red-runs.json"  # ARSENAL_RED_RUNS overrides; push_once.py reads the same file
FAILURE_LINE = re.compile(r"^(?:FAILED|FAIL|ERROR|[❯×✕✗])\s")
TEST_FILE = re.compile(r"(?<![\w./@-])((?:[\w.@-]+/)*(?:test_[\w.-]*\.py|[\w.-]*_test\.(?:py|go)"
                       r"|[\w.-]*\.(?:test|spec)\.[cm]?[jt]sx?))(?![\w-])")
FAILED_FILES_MAX = 50
RUN_FIELDS = "jobs,conclusion,headBranch,headSha,event,url,workflowName,createdAt,updatedAt"
WASTED = {"failure", "timed_out", "cancelled"}
NOT_FAILED = {"success", "skipped", "neutral"}
RUNNER_CAUSES = {"runner lost", "billing"}  # outside causes only GitHub prints, even in the middle of a test step
LOG_LINE = re.compile(r"^([^\t]*)\t([^\t]*)\t(?:\d{4}-\d\d-\d\dT[\d:.]+Z ?)?(.*)$")
REPO_IN_URL = re.compile(r"^https?://[^/]+/([^/]+/[^/]+)/actions/runs/")  # github.com or an Enterprise Server
JOB_TIME_LIMIT = re.compile(r"exceeded the maximum execution time", re.I)  # timeout-minutes; GitHub says cancelled
CI_TIME_LIMIT = re.compile(  # the runner's own job or step time limit, never a timeout a test printed
    r"ran past .*limit|" + JOB_TIME_LIMIT.pattern + r"|The job running on runner .* has exceeded"
    r"|##\[error\].*\btimed out after \d+ minutes?\b", re.I)
COVERAGE_THRESHOLD = re.compile(r'coverage threshold|does not meet (the )?(global |"[^"]*" )?threshold'  # a glob's
                                r"|Required test coverage of|coverage .{0,40}(below|not met)"  # pytest-cov
                                r"|less than fail-under=", re.I)  # coverage.py
TEST_FAILED = re.compile(r"^FAIL(\s|$)|AssertionError|Snapshot .*mismatched|\b[1-9]\d* failed\b|--- FAIL:"
                         r"|^[1-9]\d* failing$")  # mocha


def failing_test(body):
    """A failing test's line; a coverage threshold line (pytest-cov's "FAIL Required test coverage ...") is not."""
    return bool(TEST_FAILED.search(body)) and not COVERAGE_THRESHOLD.search(body)


CLASS_PATTERNS = (  # (class, matcher) in precedence order after superseded and outside; lines are stripped
    ("timeout", CI_TIME_LIMIT.search),
    ("coverage", COVERAGE_THRESHOLD.search),
    ("lint/type", re.compile(r"\d+ problems? \(\d+ errors?|\berror TS\d{4}\b"  # eslint, tsc
                             r"|Code style issues found in"  # prettier --check
                             r"|^Would reformat: |\b\d+ files? would be reformatted\b"  # ruff format, black
                             r"|^Found \d+ errors?\.$|^\S+:\d+:\d+: [A-Z]+\d+ "  # ruff
                             r"|Found \d+ errors? in \d+ files? \(checked|^\S+\.pyi?:\d+: error: "  # mypy
                             r"|^(Unused|Unlisted|Unresolved|Duplicate) [a-zA-Z ]+ \(\d+\)$"  # knip
                             r"|^\d+ issues?:$|^\S+\.go:\d+:\d+: .+ \([a-z0-9]+\)$").search),  # golangci-lint
    ("test", failing_test),
)
SNAPSHOT = re.compile(r"Snapshot .*mismatched|\b[1-9]\d* snapshots? failed\b|toMatch(Inline)?Snapshot\(",
                      re.IGNORECASE)  # vitest, jest
SCRIPT_ECHO = re.compile(r"\x1b\[36(;1)?m")  # the runner prints each line of a step's script in cyan
RUNS_COUNTED = re.compile(r"; runs counted: ([\d ]*)$")  # the end of a CI lesson's mistake text
RULES = {
    "superseded": "Push once per run: wait for the running CI or cancel it on purpose",
    "timeout": "Before pushing, run the shard locally under the CI time budget, or split the slow files",
    "coverage": "Run the changed-line coverage check before pushing",
    "lint/type": "Run lint and the type check on every touched workspace before pushing",
    "test": "Run the affected tests before pushing; a snapshot change needs its snapshot updated in the same commit",
}


class RunGroup:
    """An open "##[group]Run ..." group: the runner's echo of a step (its script in cyan, then `shell:`, and
    `with:`/`env:` blocks of indented inputs) or one a script opened itself with `::group::Run ...`."""

    def __init__(self, in_inputs=False):
        self.lines, self.echo, self.in_inputs = [], True, in_inputs

    def add(self, line, shown, plain):
        if plain in ("with:", "env:"):
            self.in_inputs = True
        elif not (SCRIPT_ECHO.match(shown.lstrip()) or plain.startswith("shell: ")
                  or (self.in_inputs and plain[:1].isspace())):
            self.echo = False  # a line the runner never echoes: the script opened this group
        self.lines.append(line)


def split_line(raw):
    """Pure: (job, step, text as shown, text without colour) of one --log-failed line."""
    match = LOG_LINE.match(raw.lstrip("\ufeff"))
    job, step, shown = match.groups() if match else ("", "", raw)
    return job, step, shown, ci_wait.ANSI.sub("", shown)


def drop_cut_echo_tail(text):
    """Pure: a log whose head was cut off, without the runner echo the cut may have landed in: the lines up to the
    first "##[endgroup]" go when each is one the runner echoes and no group or step starts before it."""
    lines, group, where = text.splitlines(keepends=True), RunGroup(in_inputs=True), None
    for index, raw in enumerate(lines):
        job, step, shown, plain = split_line(raw)
        body = plain.strip()
        where = where or (job, step)
        if (job, step) != where or body.startswith("##[group]"):
            return text
        if body.startswith("##[endgroup]"):
            return "".join(lines[index + 1:]) if group.echo else text
        if body:
            group.add(None, shown, plain)
    return text


def runtime_lines(text):
    """Pure: the log's (job, step, text) lines the steps printed, colour removed, echoed script groups left out.

    A closed "Run ..." group is dropped only when every line in it is one the runner echoes. The runner always closes
    its echo group, so a group still open when the step ends or the next group starts is output too."""
    lines, group, where = [], None, None  # group: the open "Run ..." group, None when none is open
    for raw in (text or "").splitlines():
        job, step, shown, plain = split_line(raw)
        body = plain.strip()
        if (job, step) != where or body.startswith("##[group]Run "):
            lines.extend(group.lines if group else ())
            group, where = None, (job, step)
        if body.startswith("##[group]Run "):
            group = RunGroup()
        elif body.startswith("##[endgroup]"):
            lines.extend(group.lines if group and not group.echo else ())
            group = None
        elif body:
            if group:
                group.add((job, step, body), shown, plain)
            else:
                lines.append((job, step, body))
    lines.extend(group.lines if group else ())
    return lines


def first_match(lines, matches):
    return next((body for _, _, body in lines if matches(body)), None)


def failed(item):
    return (item.get("conclusion") or "") not in NOT_FAILED


def superseded(run):
    """Pure: the run was cancelled, or every job that did not pass was cancelled (a newer push took its place)."""
    bad = [job for job in run.get("jobs") or [] if failed(job)]
    every_failed_job_cancelled = bool(bad) and all(job.get("conclusion") == "cancelled" for job in bad)
    return run.get("conclusion") == "cancelled" or every_failed_job_cancelled


def failed_coverage_part(jobs):
    """Pure: "failed: <name>" for the first failed job or step whose name says coverage, else None."""
    for job in jobs:
        for part in [job, *(job.get("steps") or [])]:
            if part.get("conclusion") == "failure" and "coverage" in (part.get("name") or "").lower():
                return f"failed: {part['name']}"
    return None


def classify(run, text):
    """Pure: (class, sub-kind, evidence, outside cause) for a finished, failed run and its failed log."""
    jobs = run.get("jobs") or []
    bad = [job for job in jobs if failed(job)]
    lines = runtime_lines(text)
    if superseded(run):
        found = first_match(lines, JOB_TIME_LIMIT.search)
        if found:
            return "timeout", "", found, ""
        return "superseded", "", f"run concluded {run.get('conclusion')}; cancelled jobs: " + ", ".join(
            job.get("name", "?") for job in bad if job.get("conclusion") == "cancelled"), ""
    test_steps = {(job, step) for job, step, body in lines if failing_test(body)}
    outside_test_steps = [line for line in lines if line[:2] not in test_steps]  # a test's own stderr is the test's
    for label, pattern, _ in ci_wait.OUTSIDE_CAUSES:
        found = first_match(lines if label in RUNNER_CAUSES else outside_test_steps, re.compile(pattern, re.I).search)
        if found:
            return "outside", "", found, label
    timed_out = [job.get("name", "?") for job in jobs if job.get("conclusion") == "timed_out"]
    if timed_out:
        return "timeout", "", "job concluded timed_out: " + ", ".join(timed_out), ""
    for name, matches in CLASS_PATTERNS:
        if name == "coverage" and test_steps:
            continue  # jest prints its threshold even when tests fail; the failing test is the cause
        # a time limit in a step that shows a failing test: the failing test is the cause
        found = first_match(outside_test_steps if name == "timeout" else lines, matches)
        if found:
            sub = "snapshot" if name == "test" and any(SNAPSHOT.search(body) for _, _, body in lines) else ""
            return name, sub, found, ""
    found = failed_coverage_part(bad)  # only when no output says why: a "Test with coverage" step fails on tests too
    if found:
        return "coverage", "", found, ""
    return "unknown", "", next((body for _, _, body in reversed(lines) if ci_wait.ERROR_LINE.search(body)), ""), ""


def stamp(value):
    try:
        moment = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.year > 1 else None  # gh reports an unset time as 0001-01-01


def minutes_wasted(run, kind):
    """Pure: minutes of every job for superseded, else of the jobs that failed, timed out or were cancelled."""
    total = 0.0
    for job in run.get("jobs") or []:
        if kind != "superseded" and job.get("conclusion") not in WASTED:
            continue
        start, end = stamp(job.get("startedAt")), stamp(job.get("completedAt"))
        if start and end and end > start:
            total += (end - start).total_seconds() / 60
    return round(total, 1)


def repo_name(repo, url):
    in_url = REPO_IN_URL.search(url or "")
    parts = [part for part in (repo or (in_url.group(1) if in_url else "")).split("/") if part]
    if len(parts) < 2:
        raise ci_wait.Unreadable("no repository: pass --repo [HOST/]OWNER/NAME")
    return re.sub(r"[^a-z0-9._-]", "-", parts[-1].lower())  # NAME, with or without a host in front


def repo_key(repo, url):
    """OWNER/NAME in lower case: the key of a repository's record in the red-runs file."""
    in_url = REPO_IN_URL.search(url or "")
    parts = [part for part in (repo or (in_url.group(1) if in_url else "")).split("/") if part]
    return "/".join(parts[-2:]).lower().removesuffix(".git")


def failed_test_files(text):
    """Pure: the sorted test files named on the log's failure lines (FAILED/FAIL/ERROR ...), at most FAILED_FILES_MAX."""
    found = {match.group(1).removeprefix("./") for _, _, body in runtime_lines(text) if FAILURE_LINE.match(body)
             for match in TEST_FILE.finditer(body)}
    return sorted(found)[:FAILED_FILES_MAX]


def red_runs_path():
    return Path(os.environ.get("ARSENAL_RED_RUNS") or RED_RUNS).expanduser()


def read_red_state(path):
    """The red-runs file as a dict; a missing, unreadable or damaged file is None."""
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return state if isinstance(state, dict) else None


def save_red_state(path, state):
    """Write the red-runs file atomically; a failure is a warning on stderr, never an error."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".red-runs-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(state, out)
            os.replace(temp, path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temp)
    except OSError as error:
        print(f"warning: could not record the failed test files in {path}: {error}", file=sys.stderr)


def epoch(run, *fields):
    """Epoch seconds of the first of the run's `fields` that gh reported, else None."""
    moments = (stamp(run.get(field)) for field in fields)
    return next((moment.timestamp() for moment in moments if moment), None)


def run_number(value):
    """A run id as an int, or None when it is missing or not digits."""
    return int(value) if isinstance(value, (str, int)) and str(value).isdigit() else None


def write_red_record(key, run, at=None):
    """Replace `key`'s record with red run `run`, stamped `at` (epoch seconds; now when None), unless the record is of
    a higher run id; a damaged file starts over; the other keys stay."""
    path = red_runs_path()
    state = read_red_state(path) or {}
    held, new = state.get(key), run_number(run["run"])
    if isinstance(held, dict) and None not in (run_number(held.get("run")), new) and run_number(held["run"]) > new:
        return
    state[key] = {"run": run["run"], "head_sha": run["head_sha"], "time": time.time() if at is None else at,
                  "files": run["files"], "workflow": run["workflow"], "branch": run["branch"]}
    save_red_state(path, state)


def clears_record(record, run, created=None):
    """True when passing `run` answers the red run in `record`: a later run (higher run id; else created after the
    record's time) of the same workflow and branch. A record without those fields (an older one) is answered only by
    a run at its head sha."""
    if not isinstance(record, dict):
        return True  # a damaged record answers nothing; drop it
    held, new = run_number(record.get("run")), run_number(run.get("run"))
    if None not in (held, new):
        if new <= held:
            return False
    elif created is None or not isinstance(record.get("time"), (int, float)) or created <= record["time"]:
        return False
    if isinstance(record.get("workflow"), str) and isinstance(record.get("branch"), str):
        return (record["workflow"], record["branch"]) == (run["workflow"], run["branch"])
    return bool(run["head_sha"]) and record.get("head_sha") == run["head_sha"]


def clear_red_record(key, run, created=None):
    """Remove `key`'s record when the passing `run` answers it; a missing or damaged file stays untouched."""
    path = red_runs_path()
    state = read_red_state(path)
    if state is None or key not in state or not clears_record(state[key], run, created):
        return
    del state[key]
    save_red_state(path, state)


def read_run(run_id, repo):
    where = ["-R", repo] if repo else []
    run = ci_wait.gh_json(ci_wait.run_gh, ["run", "view", run_id, *where, "--json", RUN_FIELDS])
    if not isinstance(run, dict):
        raise ci_wait.Unreadable(f"gh run view {run_id} printed no run")
    return run, where


def read_failed_log(run_id, where):
    """The last LOG_MAX bytes of the failed jobs' log, read through a file so a huge log never sits in memory."""
    args = ["gh", "run", "view", run_id, *where, "--log-failed"]
    with tempfile.TemporaryFile() as sink:
        try:
            done = subprocess.run(args, stdout=sink, stderr=subprocess.DEVNULL, check=False,
                                  timeout=ci_wait.GH_TIMEOUT)
        except subprocess.TimeoutExpired as error:
            raise ci_wait.GhTimeout(f"{' '.join(args)} did not answer in {ci_wait.GH_TIMEOUT} s") from error
        except OSError as error:
            raise ci_wait.Unreadable(f"{' '.join(args)}: {error}") from error
        if done.returncode != 0:
            raise ci_wait.Unreadable(f"{' '.join(args)} exited {done.returncode}")
        size = sink.seek(0, os.SEEK_END)
        sink.seek(max(0, size - LOG_MAX))
        text = sink.read().decode("utf-8", errors="replace")
    return drop_cut_echo_tail(text.split("\n", 1)[-1]) if size > LOG_MAX else text  # and the line it went through


ANNOTATED_JOBS = 10  # check runs read per run: a time-limit cancel is told only in its annotations


def annotations_text(run, repo):
    """Log-shaped lines of the non-success jobs' check-run annotations. A job cancelled at timeout-minutes has an
    empty failed log; only its annotation ("The job has exceeded the maximum execution time of 28m0s") says why.
    repo: [HOST/]OWNER/NAME, else read from the run URL. Unreadable annotations give no lines and a warning."""
    in_url = REPO_IN_URL.search(run.get("url") or "")
    parts = [part for part in (repo or (in_url.group(1) if in_url else "")).split("/") if part]
    if len(parts) < 2:
        return ""
    host = ["--hostname", parts[0]] if len(parts) > 2 else []
    lines = []
    jobs = [job for job in run.get("jobs") or [] if failed(job) and isinstance(job.get("databaseId"), int)]
    for job in jobs[:ANNOTATED_JOBS]:
        try:
            found = ci_wait.gh_json(ci_wait.run_gh, ["api", *host,
                                                    f"repos/{parts[-2]}/{parts[-1]}/check-runs/{job['databaseId']}"
                                                    "/annotations"], empty=[])
        except (ci_wait.Unreadable, ci_wait.GhTimeout) as error:
            print(f"annotations of {job.get('name', '?')} unreadable ({error}); classified from the log only",
                  file=sys.stderr)
            continue
        for note in found if isinstance(found, list) else []:
            if isinstance(note, dict) and note.get("message"):
                text = " ".join(str(note.get(key) or "") for key in ("title", "message")).strip()
                lines.append(f"{job.get('name', '?')}\tannotation\t##[error]{text.splitlines()[0][:500]}\n")
    return "".join(lines)


def failed_log(run_id, where, superseded_run):
    """The failed log; a superseded run is only read for a time-limit cancel, so an unreadable log keeps its class."""
    try:
        return read_failed_log(run_id, where)
    except (ci_wait.Unreadable, ci_wait.GhTimeout) as error:
        if not superseded_run:
            raise
        print(f"failed log unreadable ({error}); classified from the jobs only", file=sys.stderr)
        return ""


def open_ledger(args):
    if args.shared:
        return lessons.writable_global_path(args.ledger), "G"
    return Path(args.ledger), "L"


def find_lesson(ledger, tags):
    return next((lesson for lesson in ledger.lessons if tags <= set(lesson["tags"].split(","))), None)


def counted_runs(lesson):
    found = RUNS_COUNTED.search(lesson["mistake"])
    return found.group(1).split() if found else []


def count_run(lesson, run_id):
    """End the lesson's mistake text with the runs counted for it; the oldest go first when FIELD_MAX is reached."""
    base, runs = RUNS_COUNTED.sub("", lesson["mistake"]), [*counted_runs(lesson), run_id]
    while len(runs) > 1 and len(f"{base}; runs counted: {' '.join(runs)}") > lessons.FIELD_MAX:
        runs.pop(0)  # shortcut: a run older than the kept ones would count again; they are weeks apart by then
    suffix = f"; runs counted: {' '.join(runs)}"
    lesson["mistake"] = base[:lessons.FIELD_MAX - len(suffix)] + suffix


def new_lesson(kind, repo, minutes):
    return {"tags": f"ci-{kind},repo-{repo}", "hits": 1, "date": lessons.today(), "section": "active",
            "promoted": "", "mistake": lessons.clean(f"A {kind} failure reached CI on {repo} ({minutes} min wasted "
                                                     "the first time)"),
            "cause": "The check CI failed on was not run, or not run the same way, before pushing",
            "rule": RULES[kind], "check": lessons.clean(f"The next red run on {repo} is not ci-{kind}")}


def apply_lesson(ledger, kind, repo, run_id, minutes, write):
    """(lesson, action, escalation hint) after counting a repeat or adding the lesson; saved only when `write`.
    A run already counted for the lesson changes nothing: action "counted", no hint."""
    lesson = find_lesson(ledger, {f"ci-{kind}", f"repo-{repo}"})
    if lesson and run_id in counted_runs(lesson):
        return lesson, "counted", ""
    if lesson:
        lessons.recur(ledger, lesson)  # the path `lessons.py bump` takes
        action = "repeat"
    else:
        lesson = new_lesson(kind, repo, minutes)
        lesson["id"] = ledger.next_id()
        ledger.lessons.append(lesson)
        lessons.enforce_cap(ledger, lesson)
        action = "added"
    count_run(lesson, run_id)
    if write:
        ledger.save()
        lessons.log_event(ledger, "add" if action == "added" else "repeat", lesson)
        if action == "repeat":
            lessons.escalate(lesson)  # the ESCALATE line on stderr, as `lessons.py bump` prints it; main exits 3
    return lesson, action, lessons.promote_hint(lesson).strip()


def record(args, kind, repo, minutes):
    path, prefix = open_ledger(args)
    with contextlib.redirect_stdout(sys.stderr):  # lessons.py notes (cap evictions) stay off the result line
        if args.dry_run:
            ledger = lessons.Ledger(path, prefix)
            lessons.refuse_stray(ledger)
            return apply_lesson(ledger, kind, repo, args.run_id, minutes, write=False)
        with lessons.locked(path):
            ledger = lessons.Ledger(path, prefix)
            lessons.refuse_stray(ledger)
            return apply_lesson(ledger, kind, repo, args.run_id, minutes, write=True)


def learn(args):
    run, where = read_run(args.run_id, args.repo)
    result = {"run": args.run_id, "branch": run.get("headBranch") or "?", "url": run.get("url") or "",
              "workflow": run.get("workflowName") or "", "head_sha": run.get("headSha") or "",
              "class": "", "sub_kind": "", "minutes": 0.0, "lesson": "", "action": "none", "hits": 0,
              "cause": "", "evidence": "", "escalation": "", "dry_run": args.dry_run}
    if not run.get("conclusion"):
        raise ci_wait.Unreadable("the run has not finished; run this again once it ends")
    if run.get("conclusion") in NOT_FAILED:
        result["class"] = run["conclusion"]
        if run["conclusion"] == "success" and not args.dry_run:
            clear_red_record(repo_key(args.repo, run.get("url")), result, epoch(run, "createdAt"))
        return result
    repo = repo_name(args.repo, run.get("url"))
    text = failed_log(args.run_id, where, superseded(run)) + annotations_text(run, args.repo)
    kind, sub, evidence, cause = classify(run, text)
    result.update({"class": kind, "sub_kind": sub, "minutes": minutes_wasted(run, kind), "cause": cause,
                   "evidence": evidence[:EVIDENCE_MAX], "repo": repo})
    if kind == "test" and not args.dry_run:
        write_red_record(repo_key(args.repo, run.get("url")),
                         {**result, "run": args.run_id, "files": failed_test_files(text)},
                         epoch(run, "updatedAt", "createdAt"))
    if kind in RULES:
        lesson, action, hint = record(args, kind, repo, result["minutes"])
        result.update({"lesson": lesson["id"], "action": action, "hits": lesson["hits"], "escalation": hint})
    return result


def summary(result):
    if result["class"] in NOT_FAILED:
        return f"run {result['run']} {result['branch']} concluded {result['class']}: nothing to record"
    label = result["class"] + (f"/{result['sub_kind']}" if result["sub_kind"] else "")
    if result["action"] == "none":
        tail = f"no lesson ({result['cause']})" if result["cause"] else "no lesson"
    else:
        tail = f"{result['lesson']} " + {"added": "added", "repeat": f"repeat x{result['hits']}"}.get(
            result["action"], f"already counted (x{result['hits']})")
        tail += " (dry run)" if result["dry_run"] else ""
    return f"{label} {result['minutes']:.1f} min wasted, run {result['run']} {result['branch']}: {tail}"


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_id", help="the Actions run id (digits)")
    parser.add_argument("--repo", help="[HOST/]OWNER/NAME; default: the repository in the run's URL")
    parser.add_argument("--ledger", default=os.environ.get("LESSONS_FILE") or ".agents/lessons.md")
    parser.add_argument("--global", dest="shared", action="store_true", help="record in the global ledger")
    parser.add_argument("--dry-run", action="store_true", help="classify and print; write nothing")
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    lessons.tolerate_unencodable_output()
    if not args.run_id.isdigit():
        parser.error(f"run id {args.run_id!r} is not a number")
    try:
        result = learn(args)
    except (ci_wait.Unreadable, ci_wait.GhTimeout) as error:
        print(f"could not read run {args.run_id}: {error}", file=sys.stderr)
        return EXIT_UNREADABLE
    except (lessons.Refused, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_UNREADABLE
    if args.json:
        print(json.dumps(result))
    else:
        print(summary(result))
        if result["evidence"]:
            print(f"evidence: {result['evidence']}")
        if result["escalation"]:
            print(("dry run, nothing recorded: " if args.dry_run else "") + result["escalation"])
    return EXIT_ESCALATE if result["escalation"] and not args.dry_run else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
