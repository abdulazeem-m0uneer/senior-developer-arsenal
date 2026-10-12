#!/usr/bin/env python3
"""Wait for a pull request's checks and tell an outside failure from a failure of the change.

Usage: python3 ci_wait.py <pr> [--timeout 2400] [--interval 30] [--max-reruns 2] [--rerun-delay 240]
Exit codes:
  0  green; the tested commit and the merge command are printed
  1  the change failed (or an outside failure survived every rerun)
  2  the pull request or a run could not be read
  3  one CI run did not finish in time, or the pull request reports no checks
  4  jobs never started (billing, no runner); a rerun will not help
Outside failures are rerun (failed jobs only), never worked around. Nothing is merged here.
"""
import argparse
import json
import re
import subprocess
import sys
import time

EXIT_GREEN, EXIT_CHANGE_FAILED, EXIT_UNREADABLE, EXIT_NOT_FINISHED, EXIT_NEVER_STARTED = range(5)

# (label, pattern, rerunnable). Add a new outside cause here, in the change that meets it.
OUTSIDE_CAUSES = (
    ("registry rate limit", r"429 Too Many Requests|toomanyrequests|rate limit exceeded", True),
    ("registry or upstream unavailable",
     r"auth\.docker\.io|50[234] (Service Unavailable|Bad Gateway|Gateway Time-?out)", True),
    ("network", r"TLS handshake timeout|i/o timeout|ECONNRESET|EAI_AGAIN|connection reset by peer"
                r"|Temporary failure in name resolution|Could not resolve host", True),
    ("runner lost", r"received a shutdown signal|lost communication with the server"
                    r"|hosted runner encountered an error", True),
    ("CI provider", r"Failed to download action|Unable to download artifact"
                    r"|##\[error\]The service is unavailable", True),
    ("billing", r"account payments have failed|spending limit needs to be increased", False),
)
FAILED = {"failure", "timed_out", "cancelled", "startup_failure"}
ANSI = re.compile(r"\x1b\[[0-9;]*m")
ERROR_LINE = re.compile(r"FAIL|[Ee]rror:|##\[error\]")
RUN_ID = re.compile(r"/actions/runs/(\d+)")


class Unreadable(Exception):
    """A gh call did not return what was asked for."""


def classify_log(text):
    """Pure: the outside causes a failed job's log names, as (label, rerunnable) pairs."""
    return [(label, rerunnable) for label, pattern, rerunnable in OUTSIDE_CAUSES
            if re.search(pattern, ANSI.sub("", text or ""), re.IGNORECASE)]


def error_lines(text, limit=12):
    """Pure: the last distinct error lines of a log, colour codes removed, each cut to 240."""
    seen = []
    for raw in ANSI.sub("", text or "").splitlines():
        line = raw.strip()[:240]
        if ERROR_LINE.search(line) and line not in seen:
            seen.append(line)
    return seen[-limit:]


def run_gh(args):
    """Default runner: (exit code, stdout) of `gh <args>`."""
    try:
        done = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    except OSError:
        return 127, ""
    return done.returncode, done.stdout


def gh_json(runner, args, must_succeed=True, empty=None):
    code, out = runner(args)
    if must_succeed and code != 0:
        raise Unreadable(f"gh {' '.join(args)} exited {code}")
    if not out.strip() and empty is not None:
        return empty
    try:
        return json.loads(out)
    except ValueError as error:
        raise Unreadable(f"gh {' '.join(args)} printed no JSON") from error


def read_head(pr, runner):
    data = gh_json(runner, ["pr", "view", pr, "--json", "headRefOid"])
    head = data.get("headRefOid") if isinstance(data, dict) else None
    if not head:
        raise Unreadable(f"pull request {pr} has no head commit")
    return head


def poll_checks(pr, runner, sleep, interval, timeout):
    """The checks once none is pending; None when they stay pending or absent past the timeout."""
    waited = 0
    while True:
        # `gh pr checks` exits non-zero while checks are pending or failing: only stdout counts.
        checks = gh_json(runner, ["pr", "checks", pr, "--json", "name,bucket,link"],
                         must_succeed=False, empty=[])
        if not isinstance(checks, list):
            raise Unreadable("gh pr checks did not print a list")
        if checks and not any(check.get("bucket") == "pending" for check in checks):
            return checks
        if waited >= timeout:
            return None
        sleep(interval)
        waited += interval


def inspect_run(run_id, runner):
    """One failed run: its failed jobs with steps, whether a job never started, its failed log."""
    data = gh_json(runner, ["run", "view", run_id, "--json", "jobs"])
    jobs = [job for job in data.get("jobs", []) if job.get("conclusion") in FAILED]
    summary = []
    for job in jobs:
        steps = [step.get("name", "?") for step in job.get("steps") or []
                 if step.get("conclusion") in FAILED]
        summary.append(f"{job.get('name', '?')}: {'; '.join(steps) or 'no step ran'}")
    _, log = runner(["run", "view", run_id, "--log-failed"])
    return {"jobs": summary, "never_started": any(not job.get("steps") for job in jobs), "log": log}


def judge(runs, reruns, max_reruns):
    """Pure: 'never-started', 'rerun' or 'change' for the inspected failed runs."""
    causes = [classify_log(run["log"]) for run in runs]
    blocked = any(not rerunnable for found in causes for _, rerunnable in found)
    if blocked or any(run["never_started"] for run in runs):
        return "never-started"
    if runs and all(causes) and reruns < max_reruns:
        return "rerun"
    return "change"


def report_failure(runs, out):
    for job in (job for run in runs for job in run["jobs"]):
        out(f"  {job}")
    out("Last error lines:")
    for line in error_lines("\n".join(run["log"] for run in runs)):
        out(f"  {line}")


def wait_for_pr(pr, runner, sleep, out, interval=30, timeout=2400, max_reruns=2, rerun_delay=240):
    reruns = 0
    while True:
        head = read_head(pr, runner)
        checks = poll_checks(pr, runner, sleep, interval, timeout)
        if checks is None:
            out(f"CI did not finish in {timeout // 60} minutes, or the pull request reports no checks.")
            return EXIT_NOT_FINISHED
        failing = [check for check in checks if check.get("bucket") in ("fail", "cancel")]
        if not failing:
            if read_head(pr, runner) != head:
                out("The head commit moved while waiting; waiting for the new commit.")
                continue
            out(f"CI is green on {head}.")
            out(f"Merge only that commit: gh pr merge {pr} --match-head-commit {head}")
            return EXIT_GREEN
        run_ids = sorted({match.group(1) for check in failing
                          if (match := RUN_ID.search(check.get("link") or ""))})
        runs = [inspect_run(run_id, runner) for run_id in run_ids]
        verdict = judge(runs, reruns, max_reruns)
        if verdict == "never-started":
            out("Jobs never started (billing or no runner): not the change, and a rerun will not help.")
            report_failure(runs, out)
            return EXIT_NEVER_STARTED
        if verdict == "change":
            out(f"CI is red after {reruns} rerun(s). Failed checks: "
                + ", ".join(check.get("name", "?") for check in failing))
            report_failure(runs, out)
            return EXIT_CHANGE_FAILED
        reruns += 1
        labels = sorted({label for run in runs for label, _ in classify_log(run["log"])})
        out(f"Outside failure ({', '.join(labels)}); rerun {reruns} of {max_reruns} in {rerun_delay} s.")
        sleep(rerun_delay)
        for run_id in run_ids:
            runner(["run", "rerun", run_id, "--failed"])
        sleep(2 * interval)


def wait(pr, runner=run_gh, sleep=time.sleep, out=print, **options):
    """Injectable entry point: returns the exit code."""
    try:
        return wait_for_pr(str(pr), runner, sleep, out, **options)
    except Unreadable as error:
        out(f"Could not read the pull request: {error}")
        return EXIT_UNREADABLE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pr", help="pull request number, URL or branch")
    parser.add_argument("--timeout", type=int, default=2400, help="seconds for one CI run")
    parser.add_argument("--interval", type=int, default=30, help="seconds between polls")
    parser.add_argument("--max-reruns", type=int, default=2, help="reruns of an outside failure")
    parser.add_argument("--rerun-delay", type=int, default=240, help="seconds before a rerun")
    args = parser.parse_args(argv)
    return wait(args.pr, interval=args.interval, timeout=args.timeout,
                max_reruns=args.max_reruns, rerun_delay=args.rerun_delay)


if __name__ == "__main__":
    sys.exit(main())
