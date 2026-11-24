#!/usr/bin/env python3
"""One CI run per branch: refuse a push that would start a second run while the first is still going.

usage: push_once.py hook <remote> <url> [--base REF]          (pre-push hook: push lines on stdin)
       push_once.py check [--remote origin] [--branch B] [--base REF]

Why: every push starts a new CI run, and a fix pushed while the last run is still going wastes that run's
minutes and hides its result. A pure rebase is different: the content is the same, so a merge train or a
rebase onto the moved base may push while CI runs.

For each pushed branch (git gives "<local ref> <local sha> <remote ref> <remote sha>" lines on stdin; `check`
builds one line from the branch, default the current one, and refs/remotes/<remote>/<branch>):
  * A branch deletion, or a ref that is not a branch, passes.
  * The repository is the pushed remote's: HOST/OWNER/REPO from <url> (`check`: `git remote get-url --push`),
    for scp-style, ssh://, git:// and http(s):// URLs. A URL naming no OWNER/REPO (a local path, file://, a
    deeper path) is no GitHub repository: pass, "CI not checked". An SSH host (scp-style or ssh://) is
    resolved with `ssh -G <host>` (its hostname line, 5 s), so a ~/.ssh/config alias such as github-work
    names its real host; ssh missing or failing, or a host starting with "-", keeps the host as written. ssh.github.com (GitHub's SSH over
    port 443) is github.com.
  * `gh run list --repo HOST/OWNER/REPO --branch <b> --json databaseId,status,headSha,event -L 10`; no run
    in_progress, queued, waiting, requested or pending that a push can start (event push, pull_request or
    pull_request_target; a run without an event counts) on the remote sha (the head this push replaces) is
    going: pass. --branch matches the head branch name only, so a run on another sha, such as a fork's pull
    request from a branch of the same name, is left alone; so is a scheduled, workflow_dispatch or other run,
    since a push neither starts nor cancels it. gh lists the newest run first; a refusal names the newest
    running one.
  * A run is going: a new branch (remote sha all zeros) passes. A fast-forward (remote sha is an ancestor of
    the local sha) is refused: "run <id> on <sha> is still running; wait for it, or cancel it on purpose with
    gh run cancel <id>". Any other push passes only as a pure rebase: the multiset of `git patch-id --stable`
    over the old head's commits not in the base equals the one over the new head's commits not in the base
    (patches without context lines, `git log -p --unified=0`, so a base change next to a branch change is pure),
    leaving out on each side a commit whose change the base already holds (git log --cherry-pick), so a
    rebase that drops a commit already landed on the base (cherry-picked, carried in a hotfix) is pure.
    A merge commit counts by its remerge diff (git 2.36+): nothing when clean, its own changes when not.
    An amend, a dropped or added commit, a merge with changed content, or a conflict resolved differently is
    refused while the run goes, and so is a push that drops commits the base already has (the old head's
    merge-base with the base is not in the new head, as when the base branch itself is reset).
    The old head unknown locally (not fetched) or no base found is refused, with what to do.
  Base: --base, else the remote's default branch (refs/remotes/<remote>/HEAD), else <remote>/main, main,
  <remote>/master, master.
Opt-outs (value 1), each logged as one JSON line {time, branch, local_sha, flag, reason} to
.agents/ci-optouts.log at the repository top, reason being what the check found:
  ARSENAL_PUSH_REBASE=1  a merge train's own rebase push: passes.
  ARSENAL_ALLOW_PUSH=1   any push: passes.
  With an opt-out set, a check that cannot run (a git error, a bad PUSH_ONCE_GH_TIMEOUT) passes and is logged.
gh missing, failing, timing out (30 s; PUSH_ONCE_GH_TIMEOUT overrides, for tests) or answering garbage:
pass with a warning. A push is never blocked because the CI API is down.
Exit: 0 pass, 1 refused, 2 usage error (bad hook input, not a repository) or a git command the rebase check
needs failed (for example git older than 2.36, which has no --diff-merges=remerge). Exit 2 blocks the push like
a refusal (fail-closed, unlike gh): fix git, or pass one push with ARSENAL_ALLOW_PUSH=1, which is logged.
Standard library only.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ZEROS = "0" * 40
RUNNING = {"in_progress", "queued", "waiting", "requested", "pending"}
PUSH_EVENTS = {"push", "pull_request", "pull_request_target", None}  # None: gh gave no event; count the run
OPT_OUTS = ("ARSENAL_ALLOW_PUSH", "ARSENAL_PUSH_REBASE")
LOG = Path(".agents") / "ci-optouts.log"
URL = re.compile(r"^(?:ssh|git|https?|git\+ssh|ssh\+git)://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$")
SCP_URL = re.compile(r"^(?:[^@/:]+@)?([^/:]{2,}):(.+)$")  # user@host:owner/repo; a 2+ letter host is no drive


class UsageError(Exception):
    """Bad hook input or no repository: exit 2."""


def git(*args, stdin=None):
    """(exit code, stdout, stderr) of `git <args>`."""
    out = subprocess.run(["git", *args], input=stdin, capture_output=True, text=True)
    return out.returncode, out.stdout, out.stderr.strip()


def resolve(ref):
    code, out, _ = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return out.strip() if code == 0 else None


def is_zero(sha):
    return set(sha) == {"0"}


def ssh_hostname(host):
    """The host `ssh -G` resolves an SSH config alias to; `host` itself when ssh cannot say."""
    if host.startswith("-"):  # would be read as an ssh option
        return host
    try:
        out = subprocess.run(["ssh", "-G", host], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                             timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return host
    names = [line.split()[1] for line in out.stdout.splitlines() if line.startswith("hostname ") and
             len(line.split()) == 2] if out.returncode == 0 else []
    return names[0] if names else host


def gh_repo(url):
    """HOST/OWNER/REPO for `gh --repo` from a remote URL; None when it names no GitHub-shaped repository."""
    match = URL.match(url) or (None if "://" in url else SCP_URL.match(url))
    parts = [part for part in match.group(2).split("/") if part] if match else []
    if len(parts) != 2:
        return None
    host = match.group(1)
    if not re.match(r"^(?:git|https?)://", url):  # an SSH URL: the host may be a ~/.ssh/config alias
        host = ssh_hostname(host)
    host = "github.com" if host == "ssh.github.com" else host
    return f"{host}/{parts[0]}/{parts[1].removesuffix('.git')}"


def running_runs(branch, repo, head_sha):
    """([running runs on `head_sha`], warning or None) for `branch` of `repo`; a gh problem is a warning, never a
    refusal. `--branch` matches the head branch name, a fork's pull request too, so only the sha counts."""
    try:
        timeout = float(os.environ.get("PUSH_ONCE_GH_TIMEOUT", "30"))
    except ValueError as error:
        raise UsageError(f"PUSH_ONCE_GH_TIMEOUT is not a number of seconds: {error}") from error
    args = ["gh", "run", "list", "--repo", repo, "--branch", branch, "--json", "databaseId,status,headSha,event",
            "-L", "10"]
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return [], "gh is not installed"
    except subprocess.TimeoutExpired:
        return [], f"gh run list did not answer within {timeout:g}s"
    except OSError as error:
        return [], f"gh: {error}"
    if out.returncode:
        return [], f"gh run list exited {out.returncode}: {out.stderr.strip()[:300]}"
    try:
        listed = json.loads(out.stdout)
        return [run for run in listed if run.get("status") in RUNNING and run.get("event") in PUSH_EVENTS and
                run.get("headSha") == head_sha], None
    except (ValueError, AttributeError, TypeError):
        return [], "gh run list printed something that is not a list of runs"


def default_base(remote):
    code, out, _ = git("symbolic-ref", "--quiet", f"refs/remotes/{remote}/HEAD")
    candidates = [out.strip()] if code == 0 else []
    candidates += [f"refs/remotes/{remote}/main", "refs/heads/main", f"refs/remotes/{remote}/master",
                   "refs/heads/master"]
    return next((ref for ref in candidates if resolve(ref)), None)


def patch_ids(base, head):
    """Counter of `git patch-id --stable` over the context-free patches of the commits of `head` not in `base`
    whose change `base` lacks."""
    # a merge counts by its remerge diff: empty when clean, the changed content when not (git 2.36+)
    # -U0: no context lines, so a base change next to a branch change leaves the branch's patch ids alone
    code, log, err = git("log", "-p", "--unified=0", "--diff-merges=remerge", "--no-color", "--no-ext-diff",
                         "--cherry-pick", "--right-only", f"{base}...{head}")
    if code:
        raise UsageError(f"git log {base}...{head} failed: {err}")
    code, ids, err = git("patch-id", "--stable", stdin=log)
    if code:
        raise UsageError(f"git patch-id failed: {err}")
    return Counter(line.split()[0] for line in ids.splitlines() if line.strip())


def verdict(branch, local, remote_sha, remote, base, repo):
    """(passes, message) for one pushed branch."""
    if is_zero(local):
        return True, f"{branch}: deletion"
    if not repo:
        return True, f"{branch}: the remote is not a GitHub repository; CI not checked"
    runs, warning = running_runs(branch, repo, remote_sha)
    if warning:
        return True, f"{branch}: warning: {warning}; CI state unknown, not checked"
    if not runs:
        return True, f"{branch}: no CI run going"
    run = runs[0]
    busy = (f"run {run.get('databaseId')} on {run.get('headSha')} is still running; wait for it, or cancel it on "
            f"purpose with gh run cancel {run.get('databaseId')}")
    if is_zero(remote_sha):
        return True, f"{branch}: new branch"
    if not resolve(remote_sha):
        return False, f"{branch}: {busy} (old head {remote_sha} is not here: git fetch {remote}, then push again)"
    if git("merge-base", "--is-ancestor", remote_sha, local)[0] == 0:
        return False, f"{branch}: {busy}"
    base_ref = base or default_base(remote)
    if not base_ref or not resolve(base_ref):
        return False, f"{branch}: {busy} (no base branch found to tell a rebase from a change: pass --base REF)"
    code, fork_point, _ = git("merge-base", base_ref, remote_sha)
    if code == 0 and git("merge-base", "--is-ancestor", fork_point.strip(), local)[0]:
        return False, f"{branch}: {busy} (this push drops commits already on {base_ref})"
    if patch_ids(base_ref, remote_sha) == patch_ids(base_ref, local):
        return True, f"{branch}: pure rebase onto {base_ref} (same patches), allowed while CI runs"
    return False, f"{branch}: {busy} (this push changes content: not a pure rebase onto {base_ref})"


def log_opt_out(top, branch, local, flag, reason):
    entry = {"time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "branch": branch,
             "local_sha": local, "flag": flag, "reason": reason}
    path = Path(top) / LOG
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError as error:
        print(f"push_once: warning: could not log the opt-out to {path}: {error}", file=sys.stderr)


def parse_push_lines(text):
    """[(branch, local sha, remote sha)] for pushed branches; other refs are skipped."""
    pushes = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 4:
            raise UsageError(f"bad pre-push input line (want 4 fields): {line!r}")
        _, local, remote_ref, remote_sha = fields
        if remote_ref.startswith("refs/heads/"):
            pushes.append((remote_ref[len("refs/heads/"):], local, remote_sha))
    return pushes


def cli_push(remote, branch):
    if not branch:
        code, out, _ = git("symbolic-ref", "--quiet", "--short", "HEAD")
        if code:
            raise UsageError("not on a branch: pass --branch")
        branch = out.strip()
    local = resolve(f"refs/heads/{branch}")
    if not local:
        raise UsageError(f"no local branch {branch}")
    return [(branch, local, resolve(f"refs/remotes/{remote}/{branch}") or ZEROS)]


def remote_url(remote):
    code, out, err = git("remote", "get-url", "--push", remote)
    if code:
        raise UsageError(f"no remote {remote}: {err}")
    return out.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Refuse a push that would start a second CI run on a branch.")
    commands = parser.add_subparsers(dest="command", required=True)
    hook = commands.add_parser("hook", help="pre-push hook mode: push lines on stdin")
    hook.add_argument("remote")
    hook.add_argument("url")
    check = commands.add_parser("check", help="check a branch against its remote-tracking ref")
    check.add_argument("--remote", default="origin")
    check.add_argument("--branch")
    for sub in (hook, check):
        sub.add_argument("--base", help="the branch a rebase is measured against (default: remote's default)")
    args = parser.parse_args(argv)
    try:
        code, top, err = git("rev-parse", "--show-toplevel")
        if code:
            raise UsageError(f"not a git repository: {err}")
        if args.command == "hook":
            pushes, url = parse_push_lines(sys.stdin.read()), args.url
        else:
            pushes, url = cli_push(args.remote, args.branch), remote_url(args.remote)
        flags = [flag for flag in OPT_OUTS if os.environ.get(flag) == "1"]
        refused, repo = False, gh_repo(url) if pushes else None
        for branch, local, remote_sha in pushes:
            try:
                passes, message = verdict(branch, local, remote_sha, args.remote, args.base, repo)
            except UsageError as error:
                if not flags:
                    raise
                passes, message = False, f"{branch}: {error}"
            if flags:
                log_opt_out(top.strip(), branch, local, flags[0], message)
                message = f"{message} [{flags[0]}=1: passes, logged to {LOG}]"
            elif not passes:
                refused = True
            print(f"push_once: {'' if passes or flags else 'refused: '}{message}", file=sys.stderr)
    except UsageError as error:
        print(f"push_once: {error}", file=sys.stderr)
        return 2
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
