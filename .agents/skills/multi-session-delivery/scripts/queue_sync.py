#!/usr/bin/env python3
"""Rewrite the merge_slot.py queue from live gh state: merged and closed PRs out, ready PRs first.

usage: queue_sync.py [--yes] [--state PATH | --bus-dir DIR] [-R owner/repo] [--gh-timeout 120]

Why: the merge slot queue is first come, first served. A draft, a red or pending run or a branch that is
behind at its head wastes a claim window while a ready PR waits behind it.

One `gh repo view` reads the trunk (the default branch). One `gh pr view` per PR reads the holder and each
queued PR: state, isDraft, mergeStateStatus, baseRefName, headRefOid and statusCheckRollup.
  dropped   a queued PR that is MERGED or CLOSED leaves the queue, with its refusal count
  ready     OPEN, not a draft, mergeStateStatus CLEAN, checks green as merge_green.py judges them (pending is
            not green) and its base is the trunk
  order     ready PRs first, then the rest, then flagged PRs last; equals keep their queue order
  FLAG      a PR whose base is not the trunk (goes last), and a holder that is not ready
The holder is never dropped or moved. It is kept and flagged when it is not ready, merged or closed included
(merge_slot.py drops a merged holder on its next command).

Dry run by default: prints the new order with the reason for each PR and writes nothing. --yes writes the
queue under merge_slot.py's lock. gh is asked outside the lock, so the state is read again before writing:
an entry that left or changed meanwhile is not touched, and an entry that joined meanwhile is kept at the
end, unchecked. A gh call that fails, times out, answers with over 1 MB (merge_green.run_gh stops reading
and kills gh) or gives an unreadable answer (no JSON object, an unknown state, or a field of the wrong type,
such as a check that is not an object) stops the run before anything is written: an unknown state is never
guessed.

Exit: 0 ok (dry run printed, queue written or already in order, or no state file yet in an existing directory),
2 usage error, a missing state directory (a mistyped path), damaged, locked or unwritable state file (nothing is
ever created, dry run or --yes), 3 a gh call failed or its answer was unreadable, 4 a gh call timed out.
Nothing is written on 2, 3 or 4. Standard library only.
"""
import argparse
import functools
import json
import sys
from pathlib import Path

import merge_green
import merge_slot

FIELDS = "state,isDraft,mergeStateStatus,baseRefName,headRefOid,statusCheckRollup"
KNOWN_STATES = ("OPEN", *merge_slot.DEAD)
FIELD_TYPES = {"isDraft": bool, "mergeStateStatus": str, "baseRefName": str, "headRefOid": str}
CHECK_KEYS = ("name", "context", "conclusion", "state", "status")  # what merge_green.check_state reads
EXIT_GH = 3


class GhError(Exception):
    """A gh call gave no clear answer: exit `code`, write nothing."""

    def __init__(self, message, code=EXIT_GH):
        super().__init__(message)
        self.code = code


def ask(runner, args):
    """The JSON object gh printed for `args`, or GhError."""
    what = f"gh {' '.join(args[:3])}"
    code, text = runner(args)
    if code == merge_green.GH_TIMED_OUT:
        raise GhError(f"{what} timed out: {text.strip()}", merge_green.EXIT_GH_TIMEOUT)
    if code != 0:
        raise GhError(f"{what} exited {code}: {text.strip()[:500]}")
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise GhError(f"{what} returned no JSON object")
    return data


def trunk_of(repo, runner):
    data = ask(runner, ["repo", "view", *([repo] if repo else []), "--json", "defaultBranchRef"])
    ref = data.get("defaultBranchRef")
    name = ref.get("name") if isinstance(ref, dict) else None
    if not isinstance(name, str) or not name:
        raise GhError("gh repo view gave no default branch name")
    return name


def view(number, repo, runner):
    pr = ask(runner, ["pr", "view", str(number), *(["-R", repo] if repo else []), "--json", FIELDS])
    if pr.get("state") not in KNOWN_STATES:
        raise GhError(f"gh pr view {number} gave an unknown state: {pr.get('state')!r}")
    wrong = [field for field, kind in FIELD_TYPES.items() if not isinstance(pr.get(field), kind)]
    rollup = pr.get("statusCheckRollup")
    if not (rollup is None or isinstance(rollup, list) and all(map(readable_check, rollup))):
        wrong.append("statusCheckRollup")
    if wrong:
        raise GhError(f"gh pr view {number} gave unreadable fields: {', '.join(wrong)}")
    return pr


def readable_check(check):
    """A check run or commit status whose name and state fields are text or absent."""
    return isinstance(check, dict) and all(isinstance(check.get(key), (str, type(None))) for key in CHECK_KEYS)


def judge(pr, trunk):
    """(ready, reasons, flags): ready only with no reason and no flag."""
    if pr["state"] != "OPEN":
        return False, [f"is {pr['state']}"], []
    base = pr.get("baseRefName")
    flags = [] if base == trunk else [f"base is {base!r}, not the trunk {trunk!r}"]
    reasons = ["is a draft"] if pr.get("isDraft") else []
    if pr.get("mergeStateStatus") != "CLEAN":
        reasons.append(f"mergeStateStatus is {pr.get('mergeStateStatus')}, not CLEAN")
    _, refusal = merge_green.checks_refusal(pr.get("statusCheckRollup"), pr.get("headRefOid") or "")
    if refusal:
        reasons.append(refusal)
    return not reasons and not flags, reasons, flags


def describe(ready, reasons, flags):
    if ready:
        return "ready"
    return "; ".join([f"FLAG {flag}" for flag in flags] + (["not ready: " + "; ".join(reasons)] if reasons else []))


def plan(state, views, trunk):
    """(new queue, dropped entries, report lines) from the PR views, keyed by PR number."""
    lines, dropped, ready = [], [], {}
    holder = state["holder"]
    if holder:
        ready_now, reasons, flags = judge(views[holder["pr"]], trunk)
        lines.append(f"holder: #{holder['pr']} ({holder['lane']}) kept, "
                     + ("ready" if ready_now else f"FLAG the holder is not ready: {'; '.join(reasons + flags)}"))
    for entry in state["queue"]:
        pr = views[entry["pr"]]
        if pr["state"] in merge_slot.DEAD:
            dropped.append(entry)
            lines.append(f"dropped: #{entry['pr']} is {pr['state']}")
        else:
            ready[entry["pr"]] = judge(pr, trunk)
    # ready first, flagged last (a flagged PR is never ready, so it never reaches the head over an unflagged one)
    # an overtaken holder keeps the head (stable sort: in the order it holds); ready first, flagged last
    pinned = merge_slot.overtaken(state)
    queue = sorted((e for e in state["queue"] if e not in dropped),
                   key=lambda e: (e["pr"] not in pinned, not ready[e["pr"]][0], bool(ready[e["pr"]][2])))
    lines += [f"{place}. #{e['pr']} ({e['lane']}) {describe(*ready[e['pr']])}" for place, e in enumerate(queue, 1)]
    if not queue:
        lines.append("queue: empty")
    return queue, dropped, lines


def write(path, queue, dropped, say):
    """Apply the plan to the state as it is now, under the lock; the queue length, or None when nothing changed."""
    with merge_slot.locked(path):
        state = merge_slot.load(path)
        before = json.dumps(state, sort_keys=True)
        for entry in dropped:
            if entry in state["queue"]:
                merge_slot.drop(state, entry["pr"])
        pinned = merge_slot.overtaken(state)  # read now: an overtake may have landed while gh was asked
        head = sorted((e for e in state["queue"] if e["pr"] in pinned), key=lambda e: pinned.index(e["pr"]))
        kept = [e for e in queue if e in state["queue"] and e not in head]
        joined = [e for e in state["queue"] if e not in kept and e not in head]
        for entry in joined:
            say(f"kept at the end, not checked: #{entry['pr']} ({entry['lane']}) changed or joined during the sync")
        state["queue"] = head + kept + joined
        if json.dumps(state, sort_keys=True) == before:
            return None
        merge_slot.save(path, state)
        return len(state["queue"])


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="write the new queue (default: dry run)")
    parser.add_argument("--state", help=f"state file (default <bus dir>/{merge_slot.STATE_NAME})")
    parser.add_argument("--bus-dir", default=merge_slot.DEFAULT_BUS_DIR)
    parser.add_argument("-R", "--repo", help="owner/repo for gh (default: the current repository)")
    parser.add_argument("--gh-timeout", type=float, default=merge_green.GH_TIMEOUT, help="seconds for one gh call")
    return parser


def main(argv=None, runner=None, out=print, err=None):
    err = err or (lambda line: print(line, file=sys.stderr))
    parser = build_parser()
    options = parser.parse_args(argv)
    if not 0 < options.gh_timeout < float("inf"):  # also rejects nan
        parser.error("--gh-timeout must be a positive, finite number")
    runner = runner or functools.partial(merge_green.run_gh, timeout=options.gh_timeout)
    path = Path(options.state) if options.state else Path(options.bus_dir) / merge_slot.STATE_NAME
    if not path.parent.is_dir():  # a mistyped path: locking would create the directory and a lock file
        err(f"error: no directory {path.parent} for the state file")
        return merge_slot.EXIT_BAD
    if not path.exists():  # a bus where nothing has queued yet; locking would create a lock file
        out(f"queue: no state file at {path}, nothing to sync")
        return 0
    try:
        with merge_slot.locked(path):  # short: read what to ask gh about
            snapshot = merge_slot.load(path)
        entries = merge_slot.watched(snapshot)
        if not entries:
            out("queue: empty, nothing to sync")
            return 0
        trunk = trunk_of(options.repo, runner)  # slow: no lock held
        views = {entry["pr"]: view(entry["pr"], options.repo, runner) for entry in entries}
        queue, dropped, lines = plan(snapshot, views, trunk)
        for line in lines:
            out(line)
        if not options.yes:
            out("dry run: nothing written; add --yes to write this order")
            return 0
        length = write(path, queue, dropped, out)
        out("no change: the queue is already in this order" if length is None else f"written: {length} queued")
        return 0
    except GhError as error:
        err(f"error: {error}; nothing was written")
        return error.code
    except (merge_slot.SlotError, OSError) as error:
        err(f"error: {error}")
        return merge_slot.EXIT_BAD


if __name__ == "__main__":
    sys.exit(main())
