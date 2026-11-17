#!/usr/bin/env python3
"""Read the repository state and print the ordered plan to ship the current branch, or refuse an unsafe state.

Usage: python3 ship_plan.py [--repo DIR] [--base BRANCH] [--json] [--gh-timeout 30]
Reads git (branch, default branch, remotes, dirty paths, conflicts, upstream, commits ahead) and `gh pr view`.
Exit codes:
  0  safe to ship: the plan is printed
  2  not a git repository, a git call failed, or bad arguments
  3  unsafe state: every refusal is printed (default branch, detached HEAD, no remote, a merge conflict or an
     unfinished merge/rebase, a secret-looking file in the change, unknown default branch)
  4  nothing to ship: no commit ahead of the base and a clean working tree
  5  gh is missing, not authenticated, or did not answer: the pull request cannot be read or opened
Changes nothing: no commit, push or pull request is made here. Standard library only.
"""
import argparse
import fnmatch
import json
import os
import subprocess
import sys

EXIT_OK, EXIT_USAGE, EXIT_UNSAFE, EXIT_NOTHING, EXIT_GH = 0, 2, 3, 4, 5
GIT_TIMEOUT = 15
GH_TIMEOUT = 30
MAX_LISTED = 20
CI_WAIT = ".agents/skills/ci-wait/scripts/ci_wait.py"
FIX_ROUNDS = 3
SECRET_NAMES = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks", "id_rsa*", "id_ed25519*",
                "id_ecdsa*", "credentials.json", "service-account*.json", ".npmrc", ".pypirc", ".netrc", "*.tfstate",
                "secrets.*")
NOT_SECRET = (".env.example", ".env.sample", ".env.template", ".env.dist", "*.pub")


class Failure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def git(repo, *args, ok=(0,)):
    """stdout of a git command; Failure(EXIT_USAGE) on error or timeout."""
    try:
        out = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=repo, capture_output=True,
                             text=True, timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as error:
        raise Failure(EXIT_USAGE, f"git {args[0]}: {error}") from error
    if out.returncode not in ok:
        raise Failure(EXIT_USAGE, f"git {' '.join(args)}: {out.stderr.strip() or out.returncode}")
    return out.stdout


def git_maybe(repo, *args):
    """stdout, or None when git exits non-zero (a missing ref, no upstream)."""
    try:
        out = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=repo, capture_output=True,
                             text=True, timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as error:
        raise Failure(EXIT_USAGE, f"git {args[0]}: {error}") from error
    return out.stdout.strip() if out.returncode == 0 else None


def is_secret(path):
    name = path.rsplit("/", 1)[-1]
    if any(fnmatch.fnmatch(name, pattern) for pattern in NOT_SECRET):
        return False
    return any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_NAMES)


def default_branch(repo, remote, given):
    if given:
        return given
    head = git_maybe(repo, "symbolic-ref", "--quiet", "--short", f"refs/remotes/{remote}/HEAD")
    if head:
        return head.split("/", 1)[1]
    for name in ("main", "master"):
        if git_maybe(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{name}"):
            return name
    return None


def dirty_paths(repo):
    """Paths with staged, unstaged or untracked changes (renames give the new path)."""
    fields = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
    paths, index = [], 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":
            index += 1  # the original path of a rename or copy follows
    return paths


def in_progress(repo):
    git_dir = git(repo, "rev-parse", "--absolute-git-dir").strip()
    return [label for label, name in (("merge", "MERGE_HEAD"), ("rebase", "rebase-merge"), ("rebase", "rebase-apply"),
                                      ("cherry-pick", "CHERRY_PICK_HEAD"), ("revert", "REVERT_HEAD"))
            if os.path.exists(os.path.join(git_dir, name))]


def gh_pr(repo, branch, timeout):
    """The open pull request of the branch as a dict, None when there is none; Failure(EXIT_GH) when unknown."""
    try:
        out = subprocess.run(["gh", "pr", "view", branch, "--json", "number,url,state,isDraft,baseRefName"],
                             cwd=repo, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise Failure(EXIT_GH, "gh is not installed: install it and run `gh auth login`") from error
    except subprocess.TimeoutExpired as error:
        raise Failure(EXIT_GH, f"gh pr view did not answer within {timeout}s") from error
    except OSError as error:
        raise Failure(EXIT_GH, f"gh: {error}") from error
    if out.returncode == 0:
        try:
            pr = json.loads(out.stdout)
        except ValueError as error:
            raise Failure(EXIT_GH, "gh pr view returned unreadable output") from error
        return pr if isinstance(pr, dict) and pr.get("state") == "OPEN" else None
    message = out.stderr.strip()
    if "no pull requests found" in message.lower():
        return None
    if "auth" in message.lower() or "login" in message.lower():
        raise Failure(EXIT_GH, "gh is not authenticated: run `gh auth login`")
    raise Failure(EXIT_GH, f"gh pr view failed: {message or out.returncode}")


def inspect(repo, base=None, gh_timeout=GH_TIMEOUT):
    """The repository state and every refusal, as a dict."""
    top = git(repo, "rev-parse", "--show-toplevel").strip()
    branch = git_maybe(top, "symbolic-ref", "--quiet", "--short", "HEAD")
    remotes = git(top, "remote").split()
    remote = "origin" if "origin" in remotes else (remotes[0] if remotes else None)
    target = default_branch(top, remote, base) if remote else base
    refusals = []
    if branch is None:
        refusals.append("detached HEAD: check out a branch first")
    if not remote:
        refusals.append("no remote: add one (git remote add origin <url>)")
    if target is None and remote:
        refusals.append("default branch unknown: pass --base <branch>")
    if branch and target and branch == target:
        refusals.append(f"on the default branch '{target}': create a feature branch first")
    conflicts = [path for path in git(top, "diff", "--name-only", "--diff-filter=U", "-z").split("\0") if path]
    if conflicts:
        refusals.append(f"unresolved merge conflicts: {', '.join(conflicts[:MAX_LISTED])}")
    for label in in_progress(top):
        refusals.append(f"a {label} is in progress: finish or abort it first")
    dirty = dirty_paths(top)
    base_ref = f"{remote}/{target}" if remote and target and git_maybe(
        top, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{target}") else target
    ahead_files = []
    commits = 0
    if base_ref and branch and git_maybe(top, "rev-parse", "--verify", "--quiet", base_ref):
        commits = int(git(top, "rev-list", "--count", f"{base_ref}..HEAD").strip() or 0)
        ahead_files = [path for path in git(top, "diff", "--name-only", "-z", f"{base_ref}...HEAD").split("\0") if path]
    secrets = sorted({path for path in dirty + ahead_files if is_secret(path)})
    if secrets:
        refusals.append(f"secret-looking files in the change: {', '.join(secrets[:MAX_LISTED])} "
                        "(remove them from the change and add them to .gitignore)")
    upstream = git_maybe(top, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") if branch else None
    state = {"repo": top, "branch": branch, "base": target, "remote": remote, "upstream": upstream,
             "commits_ahead": commits, "dirty": dirty, "refusals": refusals, "pr": None}
    if not refusals and (commits or dirty):
        state["pr"] = gh_pr(top, branch, gh_timeout)
    return state


def plan(state):
    """The ordered steps for a safe state."""
    branch, base, remote = state["branch"], state["base"], state["remote"]
    steps = ["verify: run the repository's local gate (quality-gate skill: the commands CI runs) and keep its result"]
    if state["dirty"]:
        listed = " ".join(state["dirty"][:MAX_LISTED]) + (" ..." if len(state["dirty"]) > MAX_LISTED else "")
        steps.append(f"commit by explicit path (review each, Conventional Commits): git add -- {listed}")
    steps.append(f"push: git push -u {remote} {branch}" if not state["upstream"] else f"push: git push ({state['upstream']})")
    pr = state["pr"]
    if pr:
        steps.append(f"pull request #{pr.get('number')} is open ({pr.get('url')}): update its body with the new evidence")
    else:
        steps.append(f"open: gh pr create --base {base} --head {branch} --title <conventional title> "
                     "--body-file <commits + verification evidence>")
    steps.append(f"wait: python3 {CI_WAIT} <pr> (background); exit 0 green, 1 change failed, others: read ci-wait")
    steps.append(f"fix loop: at most {FIX_ROUNDS} rounds of a real fix plus its test, never a skipped or weakened check")
    steps.append("hand off: report the PR link, the tested commit and the CI run; merge only on the user's explicit "
                 "approval in this conversation")
    return steps


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan shipping the current branch.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--gh-timeout", type=float, default=GH_TIMEOUT)
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return EXIT_USAGE if error.code else EXIT_OK
    try:
        state = inspect(args.repo, args.base, args.gh_timeout)
    except Failure as error:
        print(f"ship_plan: {error}", file=sys.stderr)
        return error.code
    if state["refusals"]:
        code, steps = EXIT_UNSAFE, []
    elif not state["commits_ahead"] and not state["dirty"]:
        code, steps = EXIT_NOTHING, []
    else:
        code, steps = EXIT_OK, plan(state)
    if args.json:
        print(json.dumps({**state, "plan": steps, "exit": code}, indent=2))
    elif code == EXIT_UNSAFE:
        print("refused:\n" + "\n".join(f"  - {reason}" for reason in state["refusals"]))
    elif code == EXIT_NOTHING:
        print(f"nothing to ship: no commit ahead of {state['base']} and a clean working tree")
    else:
        print(f"ship {state['branch']} -> {state['base']} ({state['commits_ahead']} commit(s) ahead, "
              f"{len(state['dirty'])} changed path(s)):")
        print("\n".join(f"  {number}. {step}" for number, step in enumerate(steps, 1)))
    return code


if __name__ == "__main__":
    sys.exit(main())
