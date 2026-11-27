#!/usr/bin/env python3
"""One CI run per branch: refuse a push that would start a second run while the first is still going.

usage: push_once.py hook <remote> <url> [--base REF] [--fresh-base BASE]   (pre-push hook: push lines on stdin)
       push_once.py check [--remote origin] [--branch B] [--base REF] [--fresh-base BASE]

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
Fresh base: --fresh-base BASE (e.g. origin/development; env ARSENAL_PUSH_BASE, the option wins) guards against a
base that moved after the checks ran. Before pushing, `git fetch --quiet <remote> <base branch>` (BASE without a
leading "<remote>/"; 20 s, PUSH_ONCE_FETCH_TIMEOUT overrides, for tests) and the push is refused when the
fetched base tip is not an ancestor of the pushed head: "rebase onto it, rerun the checks that depend on the
base". A deletion, a push of the base branch itself and a non-branch ref pass; a fetch that fails or times out
passes with a warning, never blocks (the fetch has no stdin or prompt, and a timeout kills its ssh children; a bad
PUSH_ONCE_FETCH_TIMEOUT means 20 s; BASE loses its leading remote name whether the hook's <remote> is a name or a
URL; only an is-ancestor exit 1 refuses, an error passes). An opt-out below also passes a stale push, and says so
in its message and log line. ARSENAL_ALLOW_STALE_BASE=1 passes a stale push and logs it like the opt-outs
below (it waives this check only; the CI-run check still applies).
Unrun red (G038): ci_learn.py records, per repository (OWNER/REPO, lower case), the test files a red CI run failed in
a JSON state file (ARSENAL_RED_RUNS, default ~/.cache/arsenal/red-runs.json: {"owner/repo": {run, head_sha, time,
files}}). When a record exists, its head_sha is an ancestor of (or is) the pushed head, and it lists files, each file
must be named in a run of the local test log (ARSENAL_TEST_LOG, default <repository top>/.agents/test-run.log) that
starts at a `### arsenal-test-run <epoch>` marker line with epoch >= the record's time;
templates/pre-push writes it from AFFECTED_TESTS_CMD), else the push is refused
with the files and the command to run them. ARSENAL_ALLOW_UNRUN_RED=<reason> passes it and logs the reason like the
opt-outs below. It reads local files only: a missing, corrupt or unreadable state file, no record for the repository,
or a record whose head the pushed head does not contain, or gh or the network being down pass with a warning, never a
refusal. An unreadable test log refuses (every file counts as unrun, the message says so). An opt-out below skips it.
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
import contextlib
import datetime
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ZEROS = "0" * 40
RUNNING = {"in_progress", "queued", "waiting", "requested", "pending"}
PUSH_EVENTS = {"push", "pull_request", "pull_request_target", None}  # None: gh gave no event; count the run
OPT_OUTS = ("ARSENAL_ALLOW_PUSH", "ARSENAL_PUSH_REBASE")
FETCH_TIMEOUT = 20
LOG = Path(".agents") / "ci-optouts.log"
TEST_LOG = Path(".agents") / "test-run.log"
RED_RUNS = "~/.cache/arsenal/red-runs.json"  # ci_learn.py writes it; ARSENAL_RED_RUNS overrides both ends
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


def base_branch(remote, base):
    """`base` without its leading remote name: the hook's <remote> (a name or a URL), else any configured remote."""
    if base.startswith(f"{remote}/"):
        return base[len(remote) + 1:]
    first, _, rest = base.partition("/")
    code, names, _ = git("remote")
    return rest if rest and code == 0 and first in names.split() else base


def fetch_timeout():
    """PUSH_ONCE_FETCH_TIMEOUT seconds when it is a positive finite number, else FETCH_TIMEOUT."""
    try:
        value = float(os.environ.get("PUSH_ONCE_FETCH_TIMEOUT", FETCH_TIMEOUT))
    except ValueError:
        return FETCH_TIMEOUT
    return value if math.isfinite(value) and value > 0 else FETCH_TIMEOUT


def run_fetch(remote, branch, timeout):
    """git fetch that cannot prompt and, on timeout, is killed with its ssh or remote-helper children."""
    process = subprocess.Popen(["git", "fetch", "--quiet", remote, branch], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
                               env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    try:
        _, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise
    return process.returncode, err


def fetched_base_tip(remote, branch):
    """(tip sha or None, warning or None) of `branch` fetched from `remote` just now; a problem is a warning."""
    timeout = fetch_timeout()
    try:
        code, err = run_fetch(remote, branch, timeout)
    except OSError as error:
        return None, f"fresh-base: could not run git fetch: {error}"
    except subprocess.TimeoutExpired:
        return None, f"fresh-base: git fetch {remote} {branch} did not finish within {timeout:g}s"
    if code:
        return None, f"fresh-base: git fetch {remote} {branch} exited {code}: {err.strip()[:300]}"
    tip = resolve("FETCH_HEAD")
    return tip, None if tip else f"fresh-base: git fetch {remote} {branch} left no commit"


def stale_base(branch, local, base, base_name, tip):
    """The refusal message when `local` lacks the fetched base tip (is-ancestor exits 1), else None."""
    if is_zero(local) or branch == base_name:
        return None
    if git("merge-base", "--is-ancestor", tip, local)[0] != 1:
        return None
    return (f"{branch}: the base {base} moved to {tip} and this push does not contain it; rebase onto it, rerun "
            f"the checks that depend on the base")


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


def red_record(repo_key):
    """(record or None, warning or None) for `repo_key` in the red-runs state file; a problem is a warning."""
    path = Path(os.environ.get("ARSENAL_RED_RUNS") or RED_RUNS).expanduser()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"no CI record ({path} is missing)"
    except (OSError, ValueError) as error:
        return None, f"CI record unreadable ({path}: {error})"
    record = state.get(repo_key) if isinstance(state, dict) else None
    if record is None:
        return None, f"no CI record for {repo_key}"
    damaged = not isinstance(record, dict) or not (
        isinstance(record.get("files"), list) and all(isinstance(f, str) for f in record["files"])
        and isinstance(record.get("time"), (int, float)) and isinstance(record.get("head_sha"), str))
    if damaged:
        return None, f"CI record for {repo_key} is damaged ({path})"
    return record, None


RUN_MARKER = "### arsenal-test-run"
MARKER_LINE = re.compile(rf"^{RUN_MARKER} (\d+)[ \t]*$", re.MULTILINE)


def unrun_files(record, log_path, top=None):
    """(files of the record that the local test log does not name, warning or None). Only the log text from the first
    run marker at or after the record's time counts; with no such marker, or a missing or unreadable log, nothing is
    named, so every file counts as unrun."""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return list(record["files"]), None
    except OSError as error:
        return list(record["files"]), f"test log unreadable ({log_path}: {error})"
    start = next((m.end() for m in MARKER_LINE.finditer(text) if int(m.group(1)) >= record["time"]), None)
    if start is None:
        return list(record["files"]), None
    text = text[start:]
    text = relative_paths(text, top)
    return [name for name in record["files"] if not names_file(text, name)], None


def relative_paths(text, top):
    """The log text with `./` and the repository's absolute top path (as given and resolved) removed where they start
    a path, so ./tests/test_a.py and /<top>/tests/test_a.py read as tests/test_a.py."""
    for prefix in sorted({f"{top}/", f"{Path(top).resolve()}/"} if top else (), key=len, reverse=True):
        text = re.sub(rf"(?<![\w./]){re.escape(prefix)}", "", text)
    return re.sub(r"(?<![\w./])\./", "", text)


def names_file(text, name):
    """True when the log shows the file by path (tests/test_a.py) or as a dotted module (tests.test_a), as a whole
    token: not preceded by a path or word character and not followed by a word character."""
    module = re.sub(r"\.py$", "", name).replace("/", ".")
    # A dotted form must not be the start of a longer file name (test_a.pyc).
    return any(re.search(rf"(?<![\w./]){re.escape(form)}(?!{follow})", text)
               for form, follow in ((name, r"\w"), (module, r"\w|\.py")))


def drop_record(repo_key):
    """Remove `repo_key` from the red-runs file atomically; a failure is only a warning."""
    path = Path(os.environ.get("ARSENAL_RED_RUNS") or RED_RUNS).expanduser()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or repo_key not in state:
            return
        del state[repo_key]
        handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".red-runs-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(state, out)
            os.replace(temp, path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temp)
    except (OSError, ValueError) as error:
        print(f"push_once: warning: could not clear the CI record for {repo_key} in {path}: {error}", file=sys.stderr)


def unrun_red(top, repo, branch, local):
    """The refusal message when CI's last red run failed test files that no newer local test log names, else None.
    Warnings go to stderr; ARSENAL_ALLOW_UNRUN_RED=<reason> passes a refusal and logs it."""
    if is_zero(local) or not repo:
        return None
    key = "/".join(repo.lower().split("/")[-2:])
    record, warning = red_record(key)
    if not record:
        print(f"push_once: warning: {warning}; unrun red not checked", file=sys.stderr)
        return None
    code = git("merge-base", "--is-ancestor", record["head_sha"], local)[0]
    if code:
        why = "its head is not in this push" if code == 1 else f"its head {record['head_sha']} is unknown here"
        print(f"push_once: warning: CI record for {key} does not apply: {why}; unrun red not checked", file=sys.stderr)
        return None
    log_path = Path(top) / Path(os.environ.get("ARSENAL_TEST_LOG") or TEST_LOG)
    missing, warning = unrun_files(record, log_path, top)
    if warning:
        print(f"push_once: warning: {warning}; every failed file counts as unrun", file=sys.stderr)
    if not missing:
        drop_record(key)
        return None
    files = " ".join(missing)
    message = (f"{branch}: CI run {record.get('run')} failed {', '.join(missing)}, and no run marker in the test log "
               f"({log_path}) at or after it is followed by their names; run them locally first, writing the marker "
               f"and the run: {{ echo \"{RUN_MARKER} $(date +%s)\"; <your test command> {files}; }} >> {log_path} "
               f"2>&1 (the log must show each path or module name: rerun with the paths given "
               f"explicitly, or with a verbose runner, pytest -v <path>)")
    reason = os.environ.get("ARSENAL_ALLOW_UNRUN_RED")
    if reason:
        log_opt_out(top, branch, local, "ARSENAL_ALLOW_UNRUN_RED", f"{message} [reason: {reason}]")
        print(f"push_once: {message} [ARSENAL_ALLOW_UNRUN_RED={reason}: passes, logged to {LOG}]", file=sys.stderr)
        return None
    return message + "; or set ARSENAL_ALLOW_UNRUN_RED=<reason>"


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
        sub.add_argument("--fresh-base", default=os.environ.get("ARSENAL_PUSH_BASE") or None,
                         help="refuse a push that lacks the base tip fetched now (env ARSENAL_PUSH_BASE)")
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
        tip = None
        base_name = base_branch(args.remote, args.fresh_base) if args.fresh_base else None
        if args.fresh_base and any(not is_zero(local) for _, local, _ in pushes):
            tip, warning = fetched_base_tip(args.remote, base_name)
            if warning:
                print(f"push_once: warning: {warning}; base freshness not checked", file=sys.stderr)
        for branch, local, remote_sha in pushes:
            stale = stale_base(branch, local, args.fresh_base, base_name, tip) if tip else None
            if stale and flags:
                print(f"push_once: {stale} [stale base passed by the opt-out below]",
                      file=sys.stderr)
            elif stale and os.environ.get("ARSENAL_ALLOW_STALE_BASE") == "1":
                log_opt_out(top.strip(), branch, local, "ARSENAL_ALLOW_STALE_BASE", stale)
                print(f"push_once: {stale} [ARSENAL_ALLOW_STALE_BASE=1: passes, logged to {LOG}]", file=sys.stderr)
            elif stale:
                refused = True
                print(f"push_once: refused: {stale}", file=sys.stderr)
                continue
            unrun = None if flags else unrun_red(top.strip(), repo, branch, local)
            if unrun:
                refused = True
                print(f"push_once: refused: {unrun}", file=sys.stderr)
                continue
            try:
                passes, message = verdict(branch, local, remote_sha, args.remote, args.base, repo)
            except UsageError as error:
                if not flags:
                    raise
                passes, message = False, f"{branch}: {error}"
            if flags:
                message = f"{stale}; {message}" if stale else message
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
