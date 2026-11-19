"""List the bus's open items whose ETA has passed, oldest ETA first; the coordinator chases each owner.

usage: python3 -I overdue.py [--all] [--escalate-hours H] [--escalate-redates N]
       python3 -I overdue.py --waiting
       python3 -I overdue.py --accuracy
       python3 -I overdue.py --health [--since 24h]
Reads open-items.tsv next to this script (written by send.sh), or $BUS_OPEN_ITEMS. An item is a key opened by
START or BLOCKER and still open: only a later DONE or CLEARED from the SAME sender closes it (another session
may reuse the key). A later START or BLOCKER of the same item whose ETA is later than the one before is a
re-date; repeating the same ETA or bringing it forward is not. Output, one line per item:
  OVERDUE <key> | owner <sender> | ETA <YYYY-MM-DD HH:MM> | open <h>h | past first ETA <h>h | re-dated <n>x[ | ESCALATE] | <line>
--all also lists open items still inside their ETA (as "open ..."). ESCALATE marks an item re-dated at least
N times (default 2), or at least H hours (default 4) past its FIRST promised ETA, whatever it was re-dated to since:
hours open alone never escalate (a fresh item may run long and still be inside its promise), except for an item
whose first ETA cannot be read, which counts from when it was opened. Prints "none"
when nothing is listed. A damaged record line is skipped and counted on stderr.
--waiting lists instead each open BLOCKER whose acting session (the last " - <session>" in its line, a name from lanes.txt
next to this script or $BUS_LANES, or pm) is another session with no open item of its own whose key is, or whose
line names, the blocked key. Nobody has committed to unblock it, so the coordinator orders that session to send
a START with an ETA:
  WAITING <key> | blocked <sender> | needs <session> (no open item from it) | ETA <eta> | <line>
--accuracy reports instead, per session, how its estimates held: finished items, how many were finished by their
FIRST promised ETA, the median lateness of the late ones (lower median, whole minutes), the re-dates of the finished
items, and its items still open past their first ETA. On time means finished at or before the first ETA; lateness
is rounded up to whole minutes; an item whose first ETA is unreadable is left out; a session with nothing finished
shows n/a. The coordinator tells a session under 80% to add its median lateness to its next estimates and to record
each miss as a lesson:
  ACCURACY <sender> | finished <m> | on first ETA <n> of <m> (<pct>% or n/a) | median late <min> min | re-dated <r>x
  | open past first ETA <k>
--health reads the send events (events.jsonl next to this script, or $BUS_EVENTS; one line per send.sh attempt,
written without the message text) for the window and prints one line:
  HEALTH ok|degraded | open <n> | overdue <n> | escalate <n> | sent <n> | refused <n> | unchecked <n> | untracked <n>
  | damaged <n> | since <window>
degraded (exit 1) means a line went out unchecked or untracked (the guard did not run), or a record or event line
is damaged: look before trusting the other listings.
A missing open-items file next to this script means no items yet; a $BUS_OPEN_ITEMS that does not exist is an error.
exit 0 listed (or none, or healthy); exit 1 degraded health; exit 2 bad usage, a bad $BUS_NOW, an unreadable items or lanes file, or a missing
$BUS_OPEN_ITEMS. Standard library only.
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import statistics
import sys
from pathlib import Path

TEXT_CHARS = 200
WINDOW_UNITS = {"m": 60, "h": 3600, "d": 86400}
EARLIEST = dt.datetime.min.replace(tzinfo=dt.timezone.utc)  # sort key of an unreadable ETA: listed first


def clock():
    value = os.environ.get("BUS_NOW")
    if not value:
        return dt.datetime.now().astimezone()
    parsed = dt.datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.astimezone()


def read_items(lines):
    """({(sender, key): open item}, [finished items], damaged line count). Records are applied in file order."""
    items, finished, damaged = {}, [], 0
    for line in lines:
        if not line.strip():
            continue
        fields = line.rstrip("\n").split("\t")
        if len(fields) < 5 or not fields[2]:
            damaged += 1
            continue
        sent, sender, key, eta, text = fields[0], fields[1], fields[2].lower(), fields[3], "\t".join(fields[4:])
        try:
            sent_at = dt.datetime.fromisoformat(sent)
        except ValueError:
            damaged += 1
            continue
        if sent_at.tzinfo is None:
            sent_at = sent_at.astimezone()
        ident = (sender, key)
        if eta in ("DONE", "CLEARED"):
            done = items.pop(ident, None)
            if done:
                finished.append({**done, "closed": sent_at})
            continue
        earlier = items.get(ident)
        items[ident] = {"key": key, "sender": sender, "eta": eta, "text": text,
                        "opened": earlier["opened"] if earlier else sent_at,
                        "first": earlier["first"] if earlier else eta,
                        "redates": (earlier["redates"] + is_later(eta, earlier["eta"])) if earlier else 0}
    return items, finished, damaged


def due_at(eta):
    """The ETA as an aware local datetime; None when the record holds something unreadable."""
    try:
        return dt.datetime.strptime(eta, "%Y-%m-%d %H:%M").astimezone()
    except ValueError:
        return None


def is_later(eta, before):
    """A re-date: the new ETA is after the previous one (an unreadable ETA counts as the earliest)."""
    new, old = due_at(eta), due_at(before)
    return new is not None and (old is None or new > old)


def listing(items, now, show_all, escalate_hours, escalate_redates):
    rows = []
    for item in items.values():
        due = due_at(item["eta"])
        late = due is None or due < now
        if not (late or show_all):
            continue
        hours = (now - item["opened"]).total_seconds() / 3600
        first = due_at(item["first"])
        # an unreadable first promise is measured from the opening instead: a damaged record stays loud
        past_first = max(0.0, (now - first).total_seconds() / 3600) if first else hours
        escalate = item["redates"] >= escalate_redates or past_first >= escalate_hours
        line = (f"{'OVERDUE' if late else 'open'} {item['key']} | owner {item['sender']} | ETA {item['eta']}"
                f"{'' if due else ' (unreadable)'} | open {hours:.1f}h | past first ETA {past_first:.1f}h"
                f" | re-dated {item['redates']}x"
                f"{' | ESCALATE' if escalate else ''} | {item['text'][:TEXT_CHARS]}")
        rows.append((due or EARLIEST, line))
    return [line for _, line in sorted(rows, key=lambda row: row[0])]


def read_lanes(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    names = {line.strip().lower() for line in text.splitlines() if line.strip()}
    return names | {"pm"}


def mentions(text, key):
    return re.search(r"(?<![\w-])" + re.escape(key) + r"(?![\w-])", text, re.I) is not None


def waiting(items, lanes):
    """WAITING lines for open BLOCKERs whose acting session has taken nothing for them."""
    names = "|".join(re.escape(name) for name in sorted(lanes, key=len, reverse=True))
    acting = re.compile(r"\s-\s+(" + names + r")(?![\w-])", re.I)
    rows = []
    for item in items.values():
        if not re.match(r"BLOCKER\b", item["text"]):
            continue
        named = acting.findall(item["text"])  # "<cause> - <who acts> - ETA": the cause may name a session too
        lane = named[-1].lower() if named else None
        if lane is None:  # a BLOCKER naming its own sender is never listed: the item itself takes the key
            continue
        taken = any(other["sender"] == lane and (other["key"] == item["key"] or mentions(other["text"], item["key"]))
                    for other in items.values())
        if not taken:
            rows.append(f"WAITING {item['key']} | blocked {item['sender']} | needs {lane} (no open item from it) | "
                        f"ETA {item['eta']} | {item['text'][:TEXT_CHARS]}")
    return rows


def accuracy_stats(items, finished, now):
    """{sender: {"finished", "on_time", "pct" (int or None), "median_late_min", "redates", "open_late"}}, by sender;
    measured against each item's first promised ETA. Also read by lessons.py metrics (--bus)."""
    lanes = {}

    def lane_of(sender):
        return lanes.setdefault(sender, {"finished": 0, "on_time": 0, "lates": [], "redates": 0, "open_late": 0})

    for item in finished:
        lane = lane_of(item["sender"])
        lane["redates"] += item["redates"]
        due = due_at(item["first"])
        if due is None:
            continue  # an unreadable promise is neither kept nor missed
        lane["finished"] += 1
        if item["closed"] <= due:
            lane["on_time"] += 1
        else:
            lane["lates"].append(math.ceil((item["closed"] - due).total_seconds() / 60))
    for item in items.values():
        due = due_at(item["first"])
        if due is not None and due < now:
            lane_of(item["sender"])["open_late"] += 1
    return {sender: {"finished": lane["finished"], "on_time": lane["on_time"],
                     "pct": round(100 * lane["on_time"] / lane["finished"]) if lane["finished"] else None,
                     "median_late_min": statistics.median_low(lane["lates"]) if lane["lates"] else 0,
                     "redates": lane["redates"], "open_late": lane["open_late"]}
            for sender, lane in sorted(lanes.items())}


def accuracy(items, finished, now):
    """ACCURACY lines, one per sender, measured against each item's first promised ETA."""
    return [f"ACCURACY {sender} | finished {lane['finished']} | on first ETA {lane['on_time']} of "
            f"{lane['finished']} ({'n/a' if lane['pct'] is None else str(lane['pct']) + '%'}) | median late "
            f"{lane['median_late_min']} min | re-dated {lane['redates']}x | open past first ETA {lane['open_late']}"
            for sender, lane in accuracy_stats(items, finished, now).items()]


def window_seconds(text):
    """'30m', '24h' or '7d' in seconds; ValueError otherwise."""
    found = re.fullmatch(r"([1-9]\d*)([mhd])", text.strip())
    if not found:
        raise ValueError(f"window {text!r} is not a positive number followed by m, h or d (for example 24h)")
    return int(found.group(1)) * WINDOW_UNITS[found.group(2)]


def send_counts(lines, now, seconds):
    """({outcome: count} for events inside the window, damaged event lines)."""
    counts, damaged = {}, 0
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            when = dt.datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
            outcome = str(event["outcome"])
        except (ValueError, KeyError, TypeError, AttributeError):
            damaged += 1
            continue
        if when.tzinfo is None:
            when = when.astimezone()
        if now - dt.timedelta(seconds=seconds) <= when <= now:
            counts[outcome] = counts.get(outcome, 0) + 1
    return counts, damaged


def health(items, damaged_items, events, now, since, escalate_hours, escalate_redates):
    """(line, degraded)."""
    rows = listing(items, now, True, escalate_hours, escalate_redates)
    counts, damaged_events = send_counts(events, now, window_seconds(since))
    refused = sum(n for outcome, n in counts.items() if outcome.startswith("refused"))
    unchecked, untracked = counts.get("unchecked", 0), counts.get("untracked", 0)
    damaged = damaged_items + damaged_events
    degraded = bool(unchecked or untracked or damaged)
    line = (f"HEALTH {'degraded' if degraded else 'ok'} | open {len(rows)} | "
            f"overdue {sum(row.startswith('OVERDUE') for row in rows)} | "
            f"escalate {sum(' | ESCALATE | ' in row for row in rows)} | sent {counts.get('sent', 0)} | "
            f"refused {refused} | unchecked {unchecked} | untracked {untracked} | damaged {damaged} | since {since}")
    return line, degraded


def main(argv=None):
    parser = argparse.ArgumentParser(description="List overdue bus items.")
    parser.add_argument("--all", action="store_true", help="also list open items inside their ETA")
    parser.add_argument("--escalate-hours", type=float, default=4.0)
    parser.add_argument("--escalate-redates", type=int, default=2)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--waiting", action="store_true", help="BLOCKERs whose acting session has taken nothing")
    mode.add_argument("--accuracy", action="store_true", help="per session: finished by the first promised ETA")
    mode.add_argument("--health", action="store_true", help="one line: open, overdue, sends, refusals, bypasses")
    parser.add_argument("--since", default="24h", help="window of --health (30m, 24h, 7d)")
    args = parser.parse_args(argv)
    if not math.isfinite(args.escalate_hours) or args.escalate_hours <= 0 or args.escalate_redates < 1:
        print("overdue.py: --escalate-hours must be above 0 and --escalate-redates at least 1", file=sys.stderr)
        return 2
    try:
        now = clock()
    except ValueError:
        print(f"overdue.py: BUS_NOW is not an ISO time: {os.environ.get('BUS_NOW')}", file=sys.stderr)
        return 2
    named = os.environ.get("BUS_OPEN_ITEMS")
    path = Path(named or Path(__file__).resolve().parent / "open-items.tsv")
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        if named:
            print(f"overdue.py: no open-items file at {path} ($BUS_OPEN_ITEMS)", file=sys.stderr)
            return 2
        lines = []
    except OSError as error:
        print(f"overdue.py: cannot read {path}: {error}", file=sys.stderr)
        return 2
    items, finished, damaged = read_items(lines)
    if damaged:
        print(f"overdue.py: {damaged} damaged line(s) in {path} skipped", file=sys.stderr)
    if args.waiting:
        lanes_file = Path(os.environ.get("BUS_LANES") or Path(__file__).resolve().parent / "lanes.txt")
        try:
            lanes = read_lanes(lanes_file)
        except (OSError, ValueError) as error:
            print(f"overdue.py: --waiting needs the session names: {error}", file=sys.stderr)
            return 2
        rows = waiting(items, lanes)
    elif args.accuracy:
        rows = accuracy(items, finished, now)
    elif args.health:
        events_path = Path(os.environ.get("BUS_EVENTS") or Path(__file__).resolve().parent / "events.jsonl")
        try:
            window_seconds(args.since)
            events = events_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            events = []
        except (OSError, ValueError) as error:
            print(f"overdue.py: --health: {error}", file=sys.stderr)
            return 2
        line, degraded = health(items, damaged, events, now, args.since, args.escalate_hours, args.escalate_redates)
        print(line)
        return 1 if degraded else 0
    else:
        rows = listing(items, now, args.all, args.escalate_hours, args.escalate_redates)
    print("\n".join(rows) if rows else "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
