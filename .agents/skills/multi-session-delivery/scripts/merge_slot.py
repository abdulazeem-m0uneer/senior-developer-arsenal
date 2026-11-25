#!/usr/bin/env python3
"""A FIFO merge slot shared by the sessions of one checkout, so branch freshness is not chased in circles.

usage: merge_slot.py <command> [pr] [--lane L] [--state PATH | --bus-dir DIR] [-R owner/repo]
                     [--after 2] [--slot-minutes 40] [--claim-minutes 10]
                     [--gh-timeout 120] [--json] [--yes]

Why: on a protected branch that must be up to date, PR A updates its branch, CI runs, PR B merges meanwhile,
A is behind again and is refused, and every round costs a full CI run. One PR at a time holds the slot:
it updates its branch, waits for CI and merges; the others wait their turn in order.

Commands:
  refused <pr> --lane L   record one freshness refusal (the branch was behind its base); at --after N
                          refusals (default 2) the PR joins the queue, once
  request <pr> --lane L   join the queue now
  status [--json]         the holder (granted and waiting for its claim, or holding) with minutes left, then
                          the queue in order
  may-update <pr> [--lane L]
                          exit 0: this PR holds the slot (update the branch, wait for CI, merge with
                          merge_green.py, then release); a free slot with an empty queue is GRANTED to the
                          asking PR under the lock (already claimed: full lease), so a second caller gets 1;
                          the first call of a PR granted from the queue CLAIMS it and starts the full lease;
                          exit 1: hold, another PR holds the slot or this PR waits behind others
  release <pr>            the holder ends its slot (after the merge, or giving up); a non-holder is refused (1);
                          a PR that did hold it and was since dropped (found MERGED or CLOSED, by this or any
                          other command) is released too, exit 0 ("already merged"), so
                          `merge_green.py N --yes && merge_slot.py release N` works; so is a PR whose lease or
                          claim window had expired ("slot had expired"), exit 0 so set -e flows do not break,
                          and it never touches the current holder; a PR that never held the slot is refused
  reset --yes             clear the state (the only way out of a damaged state file)

Ready first: a PR that is READY (mergeStateStatus CLEAN, every check green as merge_green.py judges them, and
fresh by the merge script's freshness gate: its head contains its base's tip, or the earliest pull_request run of
the head was created after both the tip's committer date and the tip's ci.yml push run) overtakes a holder that
is known PENDING (a recognised not-CLEAN mergeStateStatus, a check queued or running, none failed). The asker of
`may-update` counts, queued or not. The holder goes back to the queue head, ahead of the others; when the
overtaker merges, closes or releases (or it is READY and overtakes back) it is granted again as a claim window
to its old expiry (at least --claim-minutes), claims a fresh lease with its first `may-update`, and is never displaced again.
A CLEAN holder, one with an UNKNOWN or unrecognised state, a failed check or a gh error
is never displaced, and nothing overtakes on missing data. A verdict read before the holder's last `may-update`
yes is dropped. A returning holder is restamped (update-branch) by its own `may-update` lease like any holder;
this script pushes nothing. The overtaken PRs, their leases and the go-ahead stamp live in the top-level
"ready_first" key, which older merge_slot.py versions keep when they save; an unclaimed overtaken holder an older
writer granted is upgraded to a claimed full lease. Freshness is asked only when an overtake is possible: for a
PENDING unprotected holder, the candidates in queue order up to the first fresh one.

Every command first refreshes the state: a holder past its expiry loses the slot; the holder and every queued
PR are read with `gh pr view` and MERGED or CLOSED ones are dropped; a free slot goes to the queue head as a
claim window of --claim-minutes (default 10): its first may-update claims it and starts the full
--slot-minutes lease (default 40); an unclaimed grant expires and the next head is granted. Dropped and expired
holders are remembered in the state ("gone", last 20, at most 24 h) so their late `release` still exits 0. A gh call that fails or times out drops nothing (an unknown state is not "merged"): a warning
is printed and the command carries on with what it knows.

gh is asked outside the lock (a slow gh never blocks other lanes); the state is then re-read and a verdict
is applied only to entries still there unchanged.

State: one JSON file, default <bus dir>/merge-slot.json (bus dir default .agents/bus), changed only under an
exclusive lock on a sibling .lock file and replaced atomically. MERGE_SLOT_NOW (ISO 8601 with offset) fixes
the clock for tests. Standard library only.
Exit: 0 ok, 1 hold or refused, 2 usage error, damaged, locked or unwritable state file, or unreadable clock.
"""
import argparse
import contextlib
import datetime as dt
import functools
import json
import os
import re
import sys
import time
from pathlib import Path

import merge_green

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

DEFAULT_BUS_DIR = ".agents/bus"
STATE_NAME = "merge-slot.json"
LOCK_WAIT = 10.0
LOCK_POLL = 0.02
DEAD = ("MERGED", "CLOSED")
VIEW_FIELDS = "state,mergeStateStatus,baseRefName,headRefOid,statusCheckRollup"
CLEAN_GREEN, READY, PENDING, STALE, UNKNOWN = "clean", "ready", "pending", "stale", "unknown"
TIP_SHA = re.compile(r"[0-9a-f]{40}")
PENDING_MERGE_STATES = ("BLOCKED", "UNSTABLE", "BEHIND", "DIRTY", "HAS_HOOKS", "DRAFT")
RUNNING = ("QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED")  # a check run with no conclusion yet
API_REPO = "{owner}/{repo}"  # gh api fills these from the current repository
EXIT_HOLD = 1
EXIT_BAD = 2
GONE_MAX = 20  # holders remembered for a late release
GONE_MAX_AGE = dt.timedelta(hours=24)


class SlotError(Exception):
    """Exit 2: damaged or locked state, unreadable clock."""


def clock():
    value = os.environ.get("MERGE_SLOT_NOW")
    if not value:
        return dt.datetime.now().astimezone()
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        raise SlotError(f"MERGE_SLOT_NOW is not ISO 8601: {value!r}") from None
    return parsed if parsed.tzinfo else parsed.astimezone()


def _try_lock(handle):
    try:
        if fcntl:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


@contextlib.contextmanager
def locked(state_path):
    """Exclusive cross-process lock for one read-modify-write; the OS drops it when the holder exits."""
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path.with_name(f".{state_path.name}.lock"), "a+b") as handle:
        deadline = time.monotonic() + LOCK_WAIT
        while not _try_lock(handle):
            if time.monotonic() >= deadline:
                raise SlotError(f"{state_path} is locked by another merge_slot.py; nothing was written, retry")
            time.sleep(LOCK_POLL)
        yield


def empty_state():
    return {"holder": None, "queue": [], "refusals": {}, "gone": []}


def new_ready_first():
    return {"overtaken": [], "go_ahead": None, "leases": {}}


def _is_entry(item, fields):
    return isinstance(item, dict) and isinstance(item.get("pr"), int) and all(f in item for f in fields)


def _is_ready_first(item):
    return (isinstance(item, dict) and isinstance(item.get("overtaken"), list)
            and all(isinstance(pr, int) for pr in item["overtaken"])
            and _is_go_ahead(item.setdefault("go_ahead", None))
            and isinstance(item.setdefault("leases", {}), dict)
            and all(isinstance(lease, dict) for lease in item["leases"].values()))


def _is_go_ahead(item):
    return item is None or (isinstance(item, dict) and isinstance(item.get("pr"), int) and isinstance(item.get("n"), int))


def load(path):
    path = Path(path)
    if not path.exists():
        return {**empty_state(), "ready_first": new_ready_first()}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        holder, queue, refusals = state["holder"], state["queue"], state["refusals"]
        gone = state.setdefault("gone", [])
        ready_first = state.setdefault("ready_first", new_ready_first())
        valid = ((holder is None or _is_entry(holder, ("lane", "granted_at", "expires_at")))
                 and isinstance(queue, list)
                 and all(_is_entry(q, ("lane", "queued_at", "refusals")) for q in queue)
                 and isinstance(refusals, dict) and all(isinstance(v, int) for v in refusals.values())
                 and isinstance(gone, list) and all(_is_entry(g, ("reason", "at")) for g in gone)
                 and _is_ready_first(ready_first))
    except (OSError, ValueError, KeyError, TypeError):
        valid = False
    if not valid:
        raise SlotError(f"{path} is damaged or unreadable; fix it by hand or run `reset --yes` (the queue is lost)")
    return state


def save(path, state):
    path = Path(path)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(temp, path)
    finally:
        with contextlib.suppress(OSError):
            temp.unlink()


def stamp(moment):
    return moment.isoformat(timespec="seconds")


def parse(text):
    try:
        moment = dt.datetime.fromisoformat(text)
    except (TypeError, ValueError):
        raise SlotError(f"state holds a time that is not ISO 8601: {text!r}") from None
    return moment if moment.tzinfo else moment.astimezone()


def drop(state, pr):
    state["queue"] = [q for q in state["queue"] if q["pr"] != pr]
    state["refusals"].pop(str(pr), None)
    unmark_overtaken(state, pr)


def overtaken(state):
    """The PRs a ready PR overtook, in the order they sit at the queue head; a holder among them is protected."""
    return state["ready_first"]["overtaken"]


def unmark_overtaken(state, pr):
    state["ready_first"]["overtaken"] = [p for p in overtaken(state) if p != pr]
    state["ready_first"]["leases"].pop(str(pr), None)


def judge_view(view):
    """CLEAN_GREEN (CLEAN, every check green), PENDING (recognised not-CLEAN state, a check running, none failed)
    or UNKNOWN (anything else, missing data included). Each rollup entry is judged on its own."""
    status, rollup = view.get("mergeStateStatus"), view.get("statusCheckRollup", 0)
    if not isinstance(status, str) or not isinstance(rollup, (list, type(None))):
        return UNKNOWN
    if status == "CLEAN":
        return CLEAN_GREEN if merge_green.checks_refusal(rollup, view.get("headRefOid") or "")[1] is None else UNKNOWN
    if status not in PENDING_MERGE_STATES or not rollup:
        return UNKNOWN
    entries = []  # (running, conclusion or state)
    for check in rollup:
        _, state = merge_green.check_state(check)
        entries.append(((state == "" and check.get("status") in RUNNING) or state in ("PENDING", "EXPECTED"), state))
    running = any(is_running for is_running, _ in entries)
    failed = any(not is_running and state not in merge_green.GREEN for is_running, state in entries)
    return PENDING if running and not failed else UNKNOWN


def earliest(runner, path, jq):
    """The earliest created_at the query finds, or None (a gh error, no run, an unreadable time)."""
    code, text = runner(["api", path, "--jq", jq])
    try:
        return dt.datetime.fromisoformat(text.strip()) if code == 0 and text.strip() else None
    except ValueError:
        return None


def read_tip(base, repo, runner):
    """(sha, committer date) of the base's tip, or None."""
    code, text = runner(["api", f"repos/{repo or API_REPO}/commits/{base}", "--jq", ".sha, .commit.committer.date"])
    sha, _, date = text.strip().partition("\n")
    return (sha, date.strip()) if code == 0 and TIP_SHA.fullmatch(sha) and date.strip() else None


def is_fresh(view, repo, runner, tips):
    """the merge script's freshness gate: the head contains the base tip, or the earliest pull_request run of the
    head was created after both the tip's committer date and the tip's ci.yml push run. Any gh error, empty
    answer or missing field is not fresh. `tips` caches the tip of each base for one look-up."""
    base, head = view.get("baseRefName"), view.get("headRefOid")
    if not base or not head:
        return False
    if base not in tips:
        tips[base] = read_tip(base, repo, runner)
    if not tips[base]:
        return False
    tip, tip_date = tips[base]
    api = f"repos/{repo or API_REPO}"
    code, status = runner(["api", f"{api}/compare/{tip}...{head}", "--jq", ".status"])
    if code != 0:
        return False
    if status.strip() in ("ahead", "identical"):
        return True
    started = earliest(runner, f"{api}/actions/runs?head_sha={head}&event=pull_request&per_page=100",
                       "[.workflow_runs[].created_at] | min // \"\"")
    pushed = earliest(runner, f"{api}/actions/runs?head_sha={tip}&event=push&per_page=100",
                      "[.workflow_runs[] | select(.path | endswith(\"/ci.yml\")) | .created_at] | min // \"\"")
    try:
        committed = dt.datetime.fromisoformat(tip_date)
    except ValueError:
        return False
    return bool(started and pushed) and started > max(committed, pushed)


def read_view(number, repo, runner):
    """(state, readiness, why, view): state is 'MERGED', 'CLOSED', 'OPEN', or None when gh did not give a clear
    answer; readiness is CLEAN_GREEN, PENDING or UNKNOWN (freshness is not asked here)."""
    target = ["-R", repo] if repo else []
    code, text = runner(["pr", "view", str(number), *target, "--json", VIEW_FIELDS])
    if code != 0:
        return None, UNKNOWN, text.strip(), {}
    try:
        view = json.loads(text)
        return view.get("state"), judge_view(view), "", view
    except (ValueError, AttributeError):
        return None, UNKNOWN, "unreadable gh answer", {}


def grant(state, pr, lane, now, minutes, say, claimed, returned=False):
    state["refusals"].pop(str(pr), None)
    state["gone"] = [g for g in state["gone"] if g["pr"] != pr]
    state["holder"] = {"pr": pr, "lane": lane, "granted_at": stamp(now), "claimed": claimed,
                       "expires_at": stamp(now + dt.timedelta(minutes=minutes))}
    if returned:
        state["holder"]["returned"] = True  # an older writer drops this: see refresh()
    who = f"#{pr}{f' ({lane})' if lane else ''}"
    say(f"granted: {who} holds the slot for {minutes:g} min" if claimed else
        f"granted: {who} has {minutes:g} min to claim the slot (its first may-update claims it)")


def grant_claim(state, entry, now, claim_minutes, say):
    """Grant a claim window. An overtaken PR (from the queue head or overtaking back) returns: its window runs to
    its old expiry, at least the claim window; its first may-update claims a fresh lease (the restamp the overtake
    forced needs one), and a holder whose CI failed never asks again, so it still lapses."""
    if entry["pr"] not in overtaken(state):
        grant(state, entry["pr"], entry["lane"], now, claim_minutes, say, claimed=False)
        return
    claim = dt.timedelta(minutes=claim_minutes)
    lease = state["ready_first"]["leases"].pop(str(entry["pr"]), {})
    until = max(parse(lease["expires_at"]), now + claim) if lease.get("expires_at") else now + claim
    grant(state, entry["pr"], entry["lane"], now, (until - now).total_seconds() / 60,
          say, claimed=False, returned=True)


def grant_head(state, now, options, say):
    """Grant the queue head as a claim window (see grant_claim)."""
    if not state["holder"] and state["queue"]:
        grant_claim(state, state["queue"].pop(0), now, options.claim_minutes, say)


def forget(state, pr, reason, now):
    """Remember a holder that lost the slot, so its late `release` is answered rather than refused."""
    state["gone"] = [g for g in state["gone"] if g["pr"] != pr] + [{"pr": pr, "reason": reason, "at": stamp(now)}]


def prune_gone(state, now):
    fresh = [g for g in state["gone"] if now - parse(g["at"]) <= GONE_MAX_AGE]
    state["gone"] = fresh[-GONE_MAX:]


def watched(state):
    """The entries whose pull request gh must be asked about: the holder, then the queue."""
    return ([state["holder"]] if state["holder"] else []) + list(state["queue"])


def asker_for(state, options):
    """The PR asking `may-update` when it neither holds the slot nor is queued: it may still overtake."""
    if options.command != "may-update":
        return None
    known = {entry["pr"] for entry in watched(state)}
    return None if options.pr in known else {"pr": options.pr, "lane": options.lane}


def look_up(state, asker, repo, runner):
    """[(entry, state or None, readiness, why)] for the holder, the queue and the asker. Slow: runs outside the lock.

    The views come first. Freshness is asked only when an overtake is possible: the holder-to-be is PENDING and
    not protected; then the candidates in queue order (the asker last), stopping at the first fresh one."""
    entries = watched(state) + ([asker] if asker else [])
    rows = [[entry, *read_view(entry["pr"], repo, runner)] for entry in entries]
    alive = [row for row in rows if row[1] not in DEAD and row[0] is not asker]
    holder = alive[0] if alive else None
    if holder and holder[2] == PENDING and holder[0]["pr"] not in overtaken(state):
        tips = {}
        for row in alive[1:] + [r for r in rows if r[0] is asker]:
            if row[2] == CLEAN_GREEN:
                row[2] = READY if is_fresh(row[4], repo, runner, tips) else STALE
                if row[2] == READY:
                    break
    return [(entry, found, readiness, why) for entry, found, readiness, why, _ in rows]


def refresh(state, now, options, verdicts, go_ahead_seen, say, warn):
    """Apply gh verdicts only to entries still in the state unchanged, then expiry, then the grant."""
    for entry, found, _, why in verdicts:
        number = entry["pr"]
        if found is None:
            warn(f"warning: #{number} state unknown ({why}); kept")
        elif found in DEAD:
            if state["holder"] == entry:
                state["holder"] = None
                forget(state, number, found.lower(), now)
            elif entry in state["queue"]:
                state["queue"].remove(entry)
                state["refusals"].pop(str(number), None)
            else:
                continue
            say(f"dropped: #{number} is {found}")
    holder = state["holder"]
    if holder and not holder.get("claimed", True) and holder["pr"] in overtaken(state) and not holder.get("returned"):
        # an older merge_slot.py granted this overtaken PR its claim window: keep the place it was promised
        holder["claimed"] = True
        holder["expires_at"] = stamp(parse(holder["granted_at"]) + dt.timedelta(minutes=options.slot_minutes))
        state["ready_first"]["leases"].pop(str(holder["pr"]), None)
        say(f"claimed: #{holder['pr']} was overtaken and keeps its place for {options.slot_minutes:g} min")
    if holder and now >= parse(holder["expires_at"]):
        claimed = holder.get("claimed", True)
        say(f"expired: #{holder['pr']} ({holder['lane']}) " +
            (f"lost the slot at {holder['expires_at']}" if claimed else
             f"did not claim its grant by {holder['expires_at']}"))
        forget(state, holder["pr"], "expired" if claimed else "unclaimed", now)
        state["holder"] = None
    prune_gone(state, now)
    grant_head(state, now, options, say)
    if state["ready_first"]["go_ahead"] == go_ahead_seen:  # else a lane got a go-ahead since gh was asked
        overtake(state, {entry["pr"]: ready for entry, found, ready, _ in verdicts if found == "OPEN"},
                 now, options.claim_minutes, say, asker_for(state, options))
    live = {entry["pr"] for entry in watched(state)}
    for pr in [pr for pr in overtaken(state) if pr not in live]:
        unmark_overtaken(state, pr)


def overtake(state, readiness, now, claim_minutes, say, asker=None):
    """Ready first: the first queued PR that is READY takes the slot from a holder that is PENDING.

    The holder goes back to the queue head, after earlier overtaken holders, and is protected once it returns.
    An overtaken PR that overtakes back returns the same way (grant_claim), so it is never upgraded as an older
    writer's grant."""
    holder = state["holder"]
    if not holder or holder["pr"] in overtaken(state) or readiness.get(holder["pr"]) != PENDING:
        return
    first = next((q for q in [*state["queue"], *([asker] if asker else [])] if readiness.get(q["pr"]) == READY), None)
    if not first:
        return
    if first in state["queue"]:
        state["queue"].remove(first)
    state["ready_first"]["leases"][str(holder["pr"])] = {"expires_at": holder["expires_at"]}
    place = sum(q["pr"] in overtaken(state) for q in state["queue"])  # earlier overtaken holders keep the head
    state["queue"].insert(place, {"pr": holder["pr"], "lane": holder["lane"], "queued_at": holder["granted_at"],
                                  "refusals": 0})
    overtaken(state).insert(place, holder["pr"])
    say(f"overtaken: #{first['pr']} is ready, so it takes the slot from #{holder['pr']} (checks running); "
        f"#{holder['pr']} is back in the queue at place {place + 1}")
    grant_claim(state, first, now, claim_minutes, say)


def enqueue(state, pr, lane, now, say):
    if state["holder"] and state["holder"]["pr"] == pr:
        say(f"no-op: #{pr} already holds the slot")
    elif any(q["pr"] == pr for q in state["queue"]):
        say(f"no-op: #{pr} is already queued")
    else:
        state["gone"] = [g for g in state["gone"] if g["pr"] != pr]
        state["queue"].append({"pr": pr, "lane": lane, "queued_at": stamp(now),
                               "refusals": state["refusals"].get(str(pr), 0)})
        say(f"queued: #{pr} ({lane}) is position {len(state['queue'])}")


def cmd_refused(state, options, now, say):
    count = state["refusals"].get(str(options.pr), 0) + 1
    state["refusals"][str(options.pr)] = count
    say(f"refused: #{options.pr} freshness refusal {count} of {options.after}")
    if count >= options.after:
        enqueue(state, options.pr, options.lane, now, say)
        grant_head(state, now, options, say)
    return 0


def cmd_request(state, options, now, say):
    enqueue(state, options.pr, options.lane, now, say)
    grant_head(state, now, options, say)
    return 0


def stamp_go_ahead(state, pr):
    """Every yes counts: a verdict read before it must not displace the PR that may now merge."""
    last = state["ready_first"]["go_ahead"]
    state["ready_first"]["go_ahead"] = {"pr": pr, "n": last["n"] + 1 if last else 1}


def cmd_may_update(state, options, now, say):
    holder, pr = state["holder"], options.pr
    if holder and holder["pr"] == pr:
        if not holder.get("claimed", True):
            holder["claimed"] = True
            holder["expires_at"] = stamp(now + dt.timedelta(minutes=options.slot_minutes))
            say(f"claimed: #{pr} holds the slot for {options.slot_minutes:g} min")
        stamp_go_ahead(state, pr)
        say(f"yes: #{pr} holds the slot until {holder['expires_at']}: update, wait for CI, merge, then release")
        return 0
    places = [q["pr"] for q in state["queue"]]
    if not holder and not places:
        grant(state, pr, options.lane, now, options.slot_minutes, say, claimed=True)
        stamp_go_ahead(state, pr)
        say(f"yes: nobody contended, so #{pr} now holds the slot until {state['holder']['expires_at']} "
            "(update, wait for CI, merge, then release; it also ends at expiry)")
        return 0
    # refresh grants a free slot to a non-empty queue, so a holder exists here
    where = f", position {places.index(pr) + 1} in the queue" if pr in places else ", not queued"
    say(f"hold: #{holder['pr']} holds the slot until {holder['expires_at']}{where}")
    return EXIT_HOLD


def cmd_release(state, options, now, say):
    holder = state["holder"]
    queued = next((q for q in state["queue"] if q["pr"] == options.pr), None)
    if queued and options.pr in overtaken(state):  # it held the slot, was overtaken, and now gives its place up
        state["queue"].remove(queued)
        state["refusals"].pop(str(options.pr), None)
        unmark_overtaken(state, options.pr)
        say(f"released: #{options.pr} (it was overtaken; its place is given up)")
        return 0
    if not holder or holder["pr"] != options.pr:
        past = next((g for g in state["gone"] if g["pr"] == options.pr), None)
        if past:
            state["gone"].remove(past)
            say(f"released: #{options.pr} " + (f"(already {past['reason']})" if past["reason"] in ("merged", "closed")
                                              else "(slot had expired)"))
            return 0
        who = f"#{holder['pr']} holds it" if holder else "nobody holds it"
        say(f"refused: #{options.pr} does not hold the slot ({who})")
        return EXIT_HOLD
    state["holder"] = None
    state["refusals"].pop(str(options.pr), None)
    unmark_overtaken(state, options.pr)
    say(f"released: #{options.pr}")
    grant_head(state, now, options, say)
    return 0


def status_view(state, now):
    holder = state["holder"]
    view = None
    if holder:
        left = max(0, int((parse(holder["expires_at"]) - now).total_seconds() // 60))
        view = {**holder, "claimed": holder.get("claimed", True), "minutes_left": left}
    return {"holder": view, "queue": state["queue"], "refusals": state["refusals"], "gone": state["gone"]}


def cmd_status(state, options, now, say):
    view = status_view(state, now)
    if options.json:
        say(json.dumps(view, indent=2))
        return 0
    holder = view["holder"]
    if holder:
        until = parse(holder["expires_at"]).strftime("%H:%M")
        phrase = f"holds until {until}" if holder["claimed"] else f"granted, waiting for claim until {until}"
        say(f"holder: #{holder['pr']} ({holder['lane']}) {phrase} ({holder['minutes_left']} min left)")
    else:
        say("holder: none")
    for place, item in enumerate(view["queue"], 1):
        say(f"{place}. #{item['pr']} ({item['lane']}) queued {item['queued_at']}, refusals {item['refusals']}")
    if not view["queue"]:
        say("queue: empty")
    return 0


COMMANDS = {"refused": cmd_refused, "request": cmd_request, "may-update": cmd_may_update,
            "release": cmd_release, "status": cmd_status}


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state", help=f"state file (default <bus dir>/{STATE_NAME})")
    common.add_argument("--bus-dir", default=DEFAULT_BUS_DIR)
    common.add_argument("-R", "--repo", help="owner/repo for gh (default: the current repository)")
    common.add_argument("--slot-minutes", type=float, default=40.0, help="how long a grant lasts")
    common.add_argument("--claim-minutes", type=float, default=10.0,
                        help="how long a PR granted from the queue has to claim it with may-update")
    common.add_argument("--gh-timeout", type=float, default=merge_green.GH_TIMEOUT, help="seconds for one gh call")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("refused", "request", "may-update", "release"):
        one = sub.add_parser(name, parents=[common])
        one.add_argument("pr", type=int)
        if name in ("refused", "request"):
            one.add_argument("--lane", required=True)
        if name == "may-update":
            one.add_argument("--lane", default="", help="recorded when this call takes a free slot")
        if name == "refused":
            one.add_argument("--after", type=int, default=2, help="refusals before the PR joins the queue")
    sub.add_parser("status", parents=[common]).add_argument("--json", action="store_true")
    sub.add_parser("reset", parents=[common]).add_argument("--yes", action="store_true")
    return parser


def main(argv=None, runner=None, out=print, err=None):
    err = err or (lambda line: print(line, file=sys.stderr))
    parser = build_parser()
    options = parser.parse_args(argv)
    for name, value in (("--slot-minutes", options.slot_minutes), ("--claim-minutes", options.claim_minutes), ("--gh-timeout", options.gh_timeout)):
        if not 0 < value < float("inf"):
            parser.error(f"{name} must be a positive, finite number")
    if getattr(options, "pr", 1) < 1:
        parser.error("pr must be a positive number")
    if getattr(options, "after", 1) < 1:
        parser.error("--after must be at least 1")
    if options.command == "reset" and not options.yes:
        parser.error("reset clears the holder and the queue: add --yes")
    runner = runner or functools.partial(merge_green.run_gh, timeout=options.gh_timeout)
    path = Path(options.state) if options.state else Path(options.bus_dir) / STATE_NAME
    try:
        clock()  # fail early on an unreadable MERGE_SLOT_NOW
        if options.command == "reset":
            with locked(path):
                save(path, empty_state())
            out("reset: merge slot cleared")
            return 0
        with locked(path):  # short: read the entries to ask gh about
            snapshot = load(path)
            go_ahead_seen = snapshot["ready_first"]["go_ahead"]
        verdicts = look_up(snapshot, asker_for(snapshot, options), options.repo, runner)  # slow: no lock held
        with locked(path):  # re-read, because another lane may have written meanwhile
            state = load(path)
            before = json.dumps(state, sort_keys=True)
            now = clock()  # gh may have been slow: expiry and grant stamps use the time after it
            refresh(state, now, options, verdicts, go_ahead_seen, out, err)
            code = COMMANDS[options.command](state, options, now, out)
            if json.dumps(state, sort_keys=True) != before:
                save(path, state)
            return code
    except (SlotError, OSError) as error:
        err(f"error: {error}")
        return EXIT_BAD


if __name__ == "__main__":
    sys.exit(main())
