#!/usr/bin/env python3
"""Squash-merge a pull request only when its current head is green and independently reviewed.

usage: merge_green.py <pr-number> [--yes] [-R owner/repo] [--expect check1,check2] [--gh-timeout 120]

All must hold on the CURRENT head (full 40-character SHA, pinned at merge time):
  - the pull request is OPEN;
  - it is not a draft;
  - it has checks, every one is SUCCESS, SKIPPED or NEUTRAL, at least one is SUCCESS,
    and every --expect check is present;
  - an independent review covers that exact head: a comment line
      REVIEW-RESULT head=<sha40> reviewer=<name> author=<name> verdict=mergeable blockers=0 highs=0
    whose reviewer differs from its author, or an APPROVED review on that head commit;
  - no reviewer's latest verdict on that head objects (a REVIEW-RESULT that is not clean, or CHANGES_REQUESTED).
The REVIEW-RESULT line is a convention between honest agents, not an identity check: protect the branch too.
Without --yes it is a dry run. Never --auto, never --admin.
Exit: 0 would merge / merged, 1 refused or not merged (also a merge-queue entry: check it later),
2 usage or gh error, 3 merged state unreadable after the merge call (check the pull request by hand),
4 a gh call did not answer within --gh-timeout seconds and the pull request is not known to be merged.
"""
import argparse
import functools
import json
import re
import subprocess
import sys

GREEN = ("SUCCESS", "SKIPPED", "NEUTRAL")
GH_TIMEOUT = 120  # seconds for one gh call
GH_TIMED_OUT = 124  # runner exit code for a gh call that hung, as timeout(1) reports it
EXIT_GH_TIMEOUT = 4
SHA_RE = re.compile(r"[0-9a-f]{40}")
REVIEW_RE = re.compile(
    r"^REVIEW-RESULT head=([0-9a-f]{40}) reviewer=(\S+) author=(\S+) verdict=(\S+) blockers=(\d+) highs=(\d+)\s*$",
    re.M)


def run_gh(args, timeout=GH_TIMEOUT):
    try:
        done = subprocess.run(["gh", *args], capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return GH_TIMED_OUT, f"gh did not answer in {timeout} s"
    except OSError as error:
        return 127, str(error)
    return done.returncode, (done.stdout if done.returncode == 0 else done.stderr)


def check_state(check):
    """Check runs carry name/conclusion/status; commit statuses carry context/state."""
    return check.get("name") or check.get("context") or "?", check.get("conclusion") or check.get("state") or ""


def latest_by(items, key):
    latest = {}
    for item in items:
        latest[key(item)] = item  # gh lists comments and reviews oldest first
    return latest.values()


def find_review(pr, head):
    """The latest verdict of each reviewer on this head decides; one objection refuses."""
    results = [match for comment in pr.get("comments") or []
               for match in REVIEW_RE.findall(comment.get("body") or "") if match[0] == head]
    reviews = [r for r in pr.get("reviews") or []
               if (r.get("commit") or {}).get("oid") == head and r.get("state") in ("APPROVED", "CHANGES_REQUESTED")]
    passed, objections = [], []
    independent = [m for m in results if m[1].casefold() != m[2].casefold()]
    for _, reviewer, author, verdict, blockers, highs in latest_by(independent, lambda m: m[1].casefold()):
        if (verdict, blockers, highs) == ("mergeable", "0", "0"):
            passed.append(f"review by {reviewer} (author {author})")
        else:
            objections.append(f"{reviewer}: {verdict} blockers={blockers} highs={highs}")
    for review in latest_by(reviews, lambda r: (r.get("author") or {}).get("login", "?").casefold()):
        login = (review.get("author") or {}).get("login", "?")
        (passed if review["state"] == "APPROVED" else objections).append(
            f"approved review by {login}" if review["state"] == "APPROVED" else f"{login}: changes requested")
    return passed, objections


def judge(pr, expect=()):
    """Return (head, reason) when mergeable, or (None, refusal)."""
    if pr.get("state") != "OPEN":
        return None, f"is {pr.get('state')}, not OPEN"
    if pr.get("isDraft"):
        return None, "is a draft"
    if pr.get("autoMergeRequest"):
        return None, "has auto-merge enabled, which merges whatever head is current; disable it first"
    head = pr.get("headRefOid") or ""
    if not SHA_RE.fullmatch(head):
        return None, f"head is not a full SHA: {head!r}"
    checks = [check_state(c) for c in pr.get("statusCheckRollup") or []]
    if not checks:
        return None, f"has no checks on {head[:8]}"
    red = [name for name, state in checks if state not in GREEN]
    if red:
        return None, f"head {head[:8]} has checks not green: {', '.join(red)}"
    if not any(state == "SUCCESS" for _, state in checks):
        return None, f"head {head[:8]} has no successful check (all skipped or neutral)"
    missing = sorted(set(expect) - {name for name, state in checks if state == "SUCCESS"})
    if missing:
        return None, f"head {head[:8]} has expected checks missing or not successful: {', '.join(missing)}"
    passed, objections = find_review(pr, head)
    if objections:
        return None, f"has review objections on head {head[:8]}: {'; '.join(objections)}"
    if not passed:
        return None, f"has no independent review on head {head[:8]}"
    return head, f"{len(checks)} checks green, {passed[-1]}"


def merge_green(number, yes=False, repo=None, runner=run_gh, out=print, err=None, expect=()):
    err = err or (lambda line: print(line, file=sys.stderr))
    target = ["-R", repo] if repo else []
    code, text = runner(["pr", "view", str(number), *target,
                         "--json", "state,isDraft,autoMergeRequest,headRefOid,statusCheckRollup,comments,reviews"])
    if code == GH_TIMED_OUT:
        err(f"timeout: gh pr view #{number}: {text.strip()}; nothing was merged")
        return EXIT_GH_TIMEOUT
    if code != 0:
        err(f"error: gh pr view #{number}: {text.strip()}")
        return 2
    try:
        pr = json.loads(text)
    except ValueError:
        pr = None
    if not isinstance(pr, dict):
        err(f"error: gh pr view #{number} returned no JSON object")
        return 2
    head, reason = judge(pr, expect)
    if head is None:
        err(f"refused: #{number} {reason}")
        return 1
    if not yes:
        out(f"would merge: #{number} head {head}, {reason} (dry run; add --yes to merge)")
        return 0
    code, text = runner(["pr", "merge", str(number), *target, "--squash", "--match-head-commit", head])
    # A failed merge call may still have merged: read the state before reporting.
    view_code, state = runner(["pr", "view", str(number), *target, "--json", "state,mergeCommit"])
    try:
        after = json.loads(state) if view_code == 0 else None
    except ValueError:
        after = None
    if not isinstance(after, dict):
        err(f"unknown: #{number} merge call exited {code}, then its state was unreadable; check it by hand")
        return 3
    if after.get("state") == "MERGED":
        out(f"merged: #{number} head {head} as {((after.get('mergeCommit') or {}).get('oid') or '')[:8]}")
        return 0
    if code == GH_TIMED_OUT:
        err(f"timeout: #{number} merge call: {text.strip()}; it is {after.get('state', 'unknown')} now and may "
            "still merge: read its state again before retrying")
        return EXIT_GH_TIMEOUT
    err(f"not merged: #{number} is {after.get('state', 'unknown')} (refused, or waiting in a merge queue): "
        f"{text.strip()}")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pr", type=int)
    parser.add_argument("--yes", action="store_true", help="really merge (default: dry run)")
    parser.add_argument("-R", "--repo", help="owner/repo (default: the current repository)")
    parser.add_argument("--expect", default="", help="comma-separated check names that must be present and green "
                        "(a slow workflow that has not started yet is otherwise invisible)")
    parser.add_argument("--gh-timeout", type=float, default=GH_TIMEOUT, help="seconds for one gh call")
    options = parser.parse_args(argv)
    if not 0 < options.gh_timeout < float("inf"):  # also rejects nan
        parser.error("--gh-timeout must be a positive, finite number")
    expect = [name.strip() for name in options.expect.split(",") if name.strip()]
    return merge_green(options.pr, options.yes, options.repo, expect=expect,
                       runner=functools.partial(run_gh, timeout=options.gh_timeout))


if __name__ == "__main__":
    sys.exit(main())
