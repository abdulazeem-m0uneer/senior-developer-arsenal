"""Daily CI cost of one repository. Run as `usage_stats.py ci --repo [HOST/]OWNER/NAME [--days 1] [--json]
[--max-runs 50]`.

Lists the runs created in the last N days (1 to 400), today (UTC) included, with `gh run list -R <repo> --created
>=<first day> --json databaseId,conclusion,status,createdAt,headBranch,attempt -L 200`, and prints one line per day,
oldest first, a day without runs included:
  <date> runs <n>, red <n>, wasted <m> min (timeout <m>, coverage <m>, test <m>, lint/type <m>, superseded <m>,
  outside <m>, unknown <m>); repeats without a guard <n>[; skipped <k> attempt(s) over --max-runs <N> (not in the
  minutes)][; partial: gh listed its 200-run limit, older runs not counted]
`red` counts red attempts, on the day the run was created: an attempt that concluded failure, timed_out, cancelled or
startup_failure. The latest attempt is red when the list says so; every earlier attempt of a re-run run is read, as
gh lists only the latest. Each attempt is read with `gh run view <id> --attempt <k>` and classified and timed as
`ci_learn.py <id> --dry-run` does (classifier and wasted minutes); one whose view shows it did not fail is not red, and
one whose failed log gh will not serve (it exits non-zero, as for a job that never started) is classified from its jobs,
with a note on stderr. Nothing is written to any ledger. A run listed without a readable createdAt is not counted, with
a note on stderr. At most --max-runs attempts are read, newest first; the rest are not in the
minutes, a skipped latest attempt still counts as red, and each day's line says how many it skipped. When the list
reaches gh's 200-run limit, the oldest day it reached and every day before it are marked partial. "repeats without a
guard" counts the lessons with 2 or more hits and no guard (a rule stub alone is not one) or exemption that holds,
in the project ledger ($LESSONS_FILE or .agents/lessons.md) and the global one ($LESSONS_GLOBAL_FILE or
~/.agents/lessons.md): the same number on every line, as the ledgers are read now.
--json prints {repo, max_runs, repeats_without_guard, days: [{date, runs, red, wasted, skipped, partial,
minutes: {class: m}, red_runs: [{run, attempt, branch, class, sub_kind, minutes}]}]}.
Exit codes: 0 printed, 2 bad argument, a gh failure on the list or a run's --json view, any gh call that does not
answer in ci_wait.GH_TIMEOUT (120 s; a failed log included), or a ledger that is not a readable file.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ci-wait" / "scripts"))

import ci_learn  # noqa: E402  (it puts lessons-learned/scripts on the path)
import ci_wait  # noqa: E402
import lessons  # noqa: E402

EXIT_OK, EXIT_ERROR = 0, 2
LIST_LIMIT = 200
LIST_FIELDS = "databaseId,conclusion,status,createdAt,headBranch,attempt"
MAX_DAYS = 400  # GitHub's longest log retention: older runs cannot be classified
RED = ci_learn.WASTED | {"startup_failure"}  # GitHub shows a startup failure (bad workflow file) as red too
CLASSES = ("timeout", "coverage", "test", "lint/type", "superseded", "outside", "unknown")
REPEAT_HITS = 2
REPO = re.compile(r"^(?:[\w.-]+/)?[\w.-]+/[\w.-]+$")


class Failed(Exception):
    """A gh call or a ledger read failed: the report would be wrong, so none is printed."""


def first_day(today, days):
    return today - timedelta(days=days - 1)


def gh_json(args):
    """gh's JSON for `args`, timed out after ci_wait.GH_TIMEOUT as it is now (run_gh's default is fixed at import)."""
    return ci_wait.gh_json(lambda call: ci_wait.run_gh(call, timeout=ci_wait.GH_TIMEOUT), args)


def list_runs(repo, since):
    args = ["run", "list", "-R", repo, "--created", f">={since.isoformat()}", "--json", LIST_FIELDS,
            "-L", str(LIST_LIMIT)]
    runs = gh_json(args)
    if not isinstance(runs, list) or not all(isinstance(run, dict) for run in runs):
        raise ci_wait.Unreadable(f"gh {' '.join(args)} printed no run list")
    return runs


def created_day(run):
    moment = ci_learn.stamp(run.get("createdAt"))
    return moment.astimezone(timezone.utc).date() if moment else None


def attempts(run):
    """Pure: (the attempts to read as a range, newest first, so a huge count costs no memory; whether the list shows
    the latest red). The latest is first in the range when listed red; every earlier attempt follows."""
    latest = run.get("attempt") if isinstance(run.get("attempt"), int) and run["attempt"] > 1 else 1
    red = run.get("status") == "completed" and run.get("conclusion") in RED
    return range(latest if red else latest - 1, 0, -1), red


def read_attempt(repo, run_id, attempt):
    """(class, sub-kind, minutes) of one attempt, as ci_learn.py --dry-run finds them, or None when it did not fail."""
    where = ["-R", repo, "--attempt", str(attempt)]
    try:
        run = gh_json(["run", "view", str(run_id), *where, "--json", ci_learn.RUN_FIELDS])
    except (ci_wait.Unreadable, ci_wait.GhTimeout) as error:
        raise Failed(f"could not read run {run_id}: {error}") from error
    if not isinstance(run, dict):
        raise Failed(f"could not read run {run_id}: gh run view printed no run")
    if run.get("conclusion") not in RED:
        return None
    try:
        text = ci_learn.read_failed_log(str(run_id), where)
    except ci_wait.GhTimeout as error:  # nothing learned: classing it from its jobs would inflate `unknown`
        raise Failed(f"could not read run {run_id}: {error}") from error
    except ci_wait.Unreadable as error:
        print(f"note: run {run_id} attempt {attempt}: failed log unreadable ({error}); classified from its jobs only",
              file=sys.stderr)
        text = ""
    kind, sub, _, _ = ci_learn.classify(run, text + ci_learn.annotations_text(run, repo))
    return kind, sub, ci_learn.minutes_wasted(run, kind)


def repeats_without_guard():
    """Lessons seen REPEAT_HITS+ times without a guard in the project and global ledgers; one unreadable fails."""
    path = Path(os.environ.get("LESSONS_FILE") or ".agents/lessons.md")
    shared = lessons.global_path()
    for ledger in (path, shared):
        if ledger.exists() and not ledger.is_file():
            raise Failed(f"the ledger {ledger} is not a file")
    try:
        sources = lessons.ledger_sources(lessons.Ledger(path, "L"), [shared] if shared.is_file() else [], shared=False)
    except (OSError, lessons.Refused) as error:  # read here, not by open_global, which skips an unreadable one
        raise Failed(f"could not read the ledgers: {error}") from error
    return sum(1 for source in sources for lesson in source.lessons
               if lesson["hits"] >= REPEAT_HITS and lessons.unguarded(lesson))  # a rule-only promotion counts


def new_day(when):
    return {"date": when.isoformat(), "runs": 0, "red": 0, "wasted": 0.0, "skipped": 0, "partial": False,
            "minutes": dict.fromkeys(CLASSES, 0.0), "red_runs": []}


def report(repo, days, max_runs, today):
    """Pure but for gh and the ledgers: the --json object."""
    since = first_day(today, days)
    by_day = {since + timedelta(days=offset): new_day(since + timedelta(days=offset)) for offset in range(days)}
    runs = list_runs(repo, since)
    listed = [(created_day(run), run) for run in runs]
    undated = sum(1 for when, _ in listed if when is None)
    if undated:
        print(f"note: {undated} listed runs have no readable createdAt and are not counted", file=sys.stderr)
    if len(runs) >= LIST_LIMIT:  # gh kept the newest: the oldest day it reached and those before may be cut
        cut = min((when for when, _ in listed if when), default=max(by_day))
        for when, day in by_day.items():
            day["partial"] = when <= cut
    in_window = [(when, run) for when, run in listed if when in by_day]
    in_window.sort(key=lambda item: item[1].get("createdAt") or "", reverse=True)  # newest first
    read = 0
    for when, run in in_window:
        day = by_day[when]
        day["runs"] += 1
        todo, listed_red = attempts(run)
        budget = max_runs - read
        if len(todo) > budget:
            day["skipped"] += len(todo) - budget
            day["red"] += listed_red and budget == 0  # the latest is first in line: skipped only with no budget
        for attempt in todo[:budget]:
            read += 1
            found = read_attempt(repo, run.get("databaseId"), attempt)
            if found is None:
                continue
            kind, sub, minutes = found
            day["red"] += 1
            day["minutes"][kind] = round(day["minutes"][kind] + minutes, 1)
            day["wasted"] = round(day["wasted"] + minutes, 1)
            day["red_runs"].append({"run": run.get("databaseId"), "attempt": attempt,
                                    "branch": run.get("headBranch") or "?", "class": kind, "sub_kind": sub,
                                    "minutes": minutes})
    return {"repo": repo, "max_runs": max_runs, "repeats_without_guard": repeats_without_guard(),
            "days": [by_day[when] for when in sorted(by_day)]}


def shown(minutes):
    return f"{minutes:.1f}".removesuffix(".0")


def day_line(day, repeats, max_runs):
    parts = ", ".join(f"{kind} {shown(day['minutes'][kind])}" for kind in CLASSES)
    line = (f"{day['date']} runs {day['runs']}, red {day['red']}, wasted {shown(day['wasted'])} min ({parts}); "
            f"repeats without a guard {repeats}")
    if day["skipped"]:
        noun = "attempt" if day["skipped"] == 1 else "attempts"
        line += f"; skipped {day['skipped']} {noun} over --max-runs {max_runs} (not in the minutes)"
    if day["partial"]:
        line += f"; partial: gh listed its {LIST_LIMIT}-run limit, older runs not counted"
    return line


def run(repo, days, max_runs, as_json, today=None):
    if not REPO.match(repo or ""):
        print(f"--repo {repo!r} is not [HOST/]OWNER/NAME", file=sys.stderr)
        return EXIT_ERROR
    if not 1 <= days <= MAX_DAYS or max_runs < 0:
        print(f"--days must be 1 to {MAX_DAYS} and --max-runs 0 or more", file=sys.stderr)
        return EXIT_ERROR
    lessons.tolerate_unencodable_output()
    try:
        result = report(repo, days, max_runs, today or datetime.now(timezone.utc).date())
    except (ci_wait.Unreadable, ci_wait.GhTimeout, Failed) as error:
        print(f"ci: {error}", file=sys.stderr)
        return EXIT_ERROR
    if as_json:
        print(json.dumps(result))
    else:
        for day in result["days"]:
            print(day_line(day, result["repeats_without_guard"], max_runs))
    return EXIT_OK
