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


def _is_entry(item, fields):
    return isinstance(item, dict) and isinstance(item.get("pr"), int) and all(f in item for f in fields)


def load(path):
    path = Path(path)
    if not path.exists():
        return empty_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        holder, queue, refusals = state["holder"], state["queue"], state["refusals"]
        gone = state.setdefault("gone", [])
        valid = ((holder is None or _is_entry(holder, ("lane", "granted_at", "expires_at")))
                 and isinstance(queue, list)
                 and all(_is_entry(q, ("lane", "queued_at", "refusals")) for q in queue)
                 and isinstance(refusals, dict) and all(isinstance(v, int) for v in refusals.values())
                 and isinstance(gone, list) and all(_is_entry(g, ("reason", "at")) for g in gone))
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


def pr_state(number, repo, runner):
    """'MERGED', 'CLOSED', 'OPEN', or None when gh did not give a clear answer."""
    target = ["-R", repo] if repo else []
    code, text = runner(["pr", "view", str(number), *target, "--json", "state"])
    if code != 0:
        return None, text.strip()
    try:
        return json.loads(text).get("state"), ""
    except (ValueError, AttributeError):
        return None, "unreadable gh answer"


def grant(state, pr, lane, now, minutes, say, claimed):
    state["refusals"].pop(str(pr), None)
    state["gone"] = [g for g in state["gone"] if g["pr"] != pr]
    state["holder"] = {"pr": pr, "lane": lane, "granted_at": stamp(now), "claimed": claimed,
                       "expires_at": stamp(now + dt.timedelta(minutes=minutes))}
    who = f"#{pr}{f' ({lane})' if lane else ''}"
    say(f"granted: {who} holds the slot for {minutes:g} min" if claimed else
        f"granted: {who} has {minutes:g} min to claim the slot (its first may-update claims it)")


def grant_head(state, now, claim_minutes, say):
    if not state["holder"] and state["queue"]:
        head = state["queue"].pop(0)
        grant(state, head["pr"], head["lane"], now, claim_minutes, say, claimed=False)


def forget(state, pr, reason, now):
    """Remember a holder that lost the slot, so its late `release` is answered rather than refused."""
    state["gone"] = [g for g in state["gone"] if g["pr"] != pr] + [{"pr": pr, "reason": reason, "at": stamp(now)}]


def prune_gone(state, now):
    fresh = [g for g in state["gone"] if now - parse(g["at"]) <= GONE_MAX_AGE]
    state["gone"] = fresh[-GONE_MAX:]


def watched(state):
    """The entries whose pull request gh must be asked about: the holder, then the queue."""
    return ([state["holder"]] if state["holder"] else []) + list(state["queue"])


def look_up(entries, repo, runner):
    """[(entry, state or None, why)]. Slow: runs outside the lock."""
    return [(entry, *pr_state(entry["pr"], repo, runner)) for entry in entries]


def refresh(state, now, claim_minutes, verdicts, say, warn):
    """Apply gh verdicts only to entries still in the state unchanged, then expiry, then the grant."""
    for entry, found, why in verdicts:
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
    if holder and now >= parse(holder["expires_at"]):
        claimed = holder.get("claimed", True)
        say(f"expired: #{holder['pr']} ({holder['lane']}) " +
            (f"lost the slot at {holder['expires_at']}" if claimed else
             f"did not claim its grant by {holder['expires_at']}"))
        forget(state, holder["pr"], "expired" if claimed else "unclaimed", now)
        state["holder"] = None
    prune_gone(state, now)
    grant_head(state, now, claim_minutes, say)


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
        grant_head(state, now, options.claim_minutes, say)
    return 0


def cmd_request(state, options, now, say):
    enqueue(state, options.pr, options.lane, now, say)
    grant_head(state, now, options.claim_minutes, say)
    return 0


def cmd_may_update(state, options, now, say):
    holder, pr = state["holder"], options.pr
    if holder and holder["pr"] == pr:
        if not holder.get("claimed", True):
            holder["claimed"] = True
            holder["expires_at"] = stamp(now + dt.timedelta(minutes=options.slot_minutes))
            say(f"claimed: #{pr} holds the slot for {options.slot_minutes:g} min")
        say(f"yes: #{pr} holds the slot until {holder['expires_at']}: update, wait for CI, merge, then release")
        return 0
    places = [q["pr"] for q in state["queue"]]
    if not holder and not places:
        grant(state, pr, options.lane, now, options.slot_minutes, say, claimed=True)
        say(f"yes: nobody contended, so #{pr} now holds the slot until {state['holder']['expires_at']} "
            "(update, wait for CI, merge, then release; it also ends at expiry)")
        return 0
    # refresh grants a free slot to a non-empty queue, so a holder exists here
    where = f", position {places.index(pr) + 1} in the queue" if pr in places else ", not queued"
    say(f"hold: #{holder['pr']} holds the slot until {holder['expires_at']}{where}")
    return EXIT_HOLD


def cmd_release(state, options, now, say):
    holder = state["holder"]
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
    say(f"released: #{options.pr}")
    grant_head(state, now, options.claim_minutes, say)
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
            entries = watched(load(path))
        verdicts = look_up(entries, options.repo, runner)  # slow: no lock held
        with locked(path):  # re-read, because another lane may have written meanwhile
            state = load(path)
            before = json.dumps(state, sort_keys=True)
            now = clock()  # gh may have been slow: expiry and grant stamps use the time after it
            refresh(state, now, options.claim_minutes, verdicts, out, err)
            code = COMMANDS[options.command](state, options, now, out)
            if json.dumps(state, sort_keys=True) != before:
                save(path, state)
            return code
    except (SlotError, OSError) as error:
        err(f"error: {error}")
        return EXIT_BAD


if __name__ == "__main__":
    sys.exit(main())
