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
2 usage or gh error (an answer over 1 MB on one stream, 16 MB for the judging pull request view, counts: gh is killed), 3 merged state unreadable after the merge call (check the pull request by hand),
4 a gh call did not answer within --gh-timeout seconds and the pull request is not known to be merged.
"""
import argparse
import functools
import json
import re
import subprocess
import sys
import threading
import time

GREEN = ("SUCCESS", "SKIPPED", "NEUTRAL")
GH_TIMEOUT = 120  # seconds for one gh call
GH_TIMED_OUT = 124  # runner exit code for a gh call that hung, as timeout(1) reports it
GH_TOO_LONG = 125  # runner exit code for a gh answer over the call's limit on one stream; gh was killed
GH_MAX_OUTPUT = 1_000_000  # bytes; the default for small answers (a state, a merge, a repository)
PR_VIEW_MAX_OUTPUT = 16_000_000  # bytes; the judging view lists every comment and review, so a busy PR can pass 1 MB
WAIT_STEP = 0.05  # seconds between checks for an answer that ran over its limit
EXIT_GH_TIMEOUT = 4
SHA_RE = re.compile(r"[0-9a-f]{40}")
REVIEW_RE = re.compile(
    r"^REVIEW-RESULT head=([0-9a-f]{40}) reviewer=(\S+) author=(\S+) verdict=(\S+) blockers=(\d+) highs=(\d+)\s*$",
    re.M)


def wait_for(child, timeout, too_long):
    """Exit code of `child`; kills it once `too_long` is set. TimeoutExpired after `timeout` seconds.

    Only this thread waits on and signals the child: a kill from another thread can race the reap
    (CPython bpo-38630) and reach a reused pid."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        try:
            return child.wait(timeout=max(min(WAIT_STEP, remaining), 0))
        except subprocess.TimeoutExpired:
            if too_long.is_set():
                child.kill()
                return child.wait()
            if remaining <= WAIT_STEP:
                raise


def run_gh(args, timeout=GH_TIMEOUT, limit=GH_MAX_OUTPUT):
    """(exit code, stdout on 0 else stderr). At most `limit` bytes of each stream are held: more kills gh."""
    try:
        child = subprocess.Popen(["gh", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as error:
        return 127, str(error)
    answers, too_long = {}, threading.Event()

    def read(name, stream):
        answers[name] = stream.read(limit + 1)  # blocks until limit + 1 bytes or end of stream
        if len(answers[name]) > limit:
            too_long.set()  # the waiting thread kills gh

    readers = [threading.Thread(target=read, args=item, daemon=True)
               for item in (("out", child.stdout), ("err", child.stderr))]
    for reader in readers:
        reader.start()
    try:
        code = wait_for(child, timeout, too_long)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
        return GH_TIMED_OUT, f"gh did not answer in {timeout} s"
    except BaseException:
        child.kill()  # Ctrl-C or any other error must not leave gh running, as subprocess.run guarantees
        child.wait()
        raise
    finally:
        for reader in readers:
            reader.join(timeout=5)  # gh is gone; a leftover grandchild holding a pipe does not stall the caller
        if not any(reader.is_alive() for reader in readers):
            child.stdout.close()
            child.stderr.close()
    if too_long.is_set():
        return GH_TOO_LONG, f"gh answered with over {limit} bytes"
    return code, answers.get("out" if code == 0 else "err", b"").decode("utf-8", "replace")


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


def checks_refusal(rollup, head):
    """(checks, None) when every check is green and one succeeded, else (checks, refusal); pending is not green."""
    checks = [check_state(c) for c in rollup or []]
    if not checks:
        return checks, f"has no checks on {head[:8]}"
    red = [name for name, state in checks if state not in GREEN]
    if red:
        return checks, f"head {head[:8]} has checks not green: {', '.join(red)}"
    if not any(state == "SUCCESS" for _, state in checks):
        return checks, f"head {head[:8]} has no successful check (all skipped or neutral)"
    return checks, None


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
    checks, refusal = checks_refusal(pr.get("statusCheckRollup"), head)
    if refusal:
        return None, refusal
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
                         "--json", "state,isDraft,autoMergeRequest,headRefOid,statusCheckRollup,comments,reviews"],
                        limit=PR_VIEW_MAX_OUTPUT)
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
