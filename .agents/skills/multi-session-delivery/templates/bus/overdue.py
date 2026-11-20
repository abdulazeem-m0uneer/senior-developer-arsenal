"""List the bus's open items whose ETA has passed, oldest ETA first; the coordinator chases each owner.

usage: python3 -I overdue.py [--all] [--escalate-hours H] [--escalate-redates N]
       python3 -I overdue.py --waiting
       python3 -I overdue.py --accuracy
       python3 -I overdue.py --suggest SENDER --estimate DURATION [--min-history N] [--json]
       python3 -I overdue.py --health [--since 24h]
Reads open-items.tsv next to this script (written by send.sh), or $BUS_OPEN_ITEMS. An item is a key opened by
START or BLOCKER and still open: only a later DONE or CLEARED from the SAME sender closes it (another session
may reuse the key). A later START or BLOCKER of the same item whose ETA is later than the one before is a
re-date; repeating the same ETA or bringing it forward is not. An ETA is read in local time against its own record's
send time, as send_check.py reads a line: "YYYY-MM-DD HH:MM" as written; "MM-DD HH:MM" (or MM/DD) in the year that
puts it nearest the send time, so a date more than about six months before it is next year's (sent 12-30, "01-02
09:00" is next January) and one more than six months after it is last year's; "HH:MM" on the send day, or the next
day when that minute had already passed when it was sent (a time equal to the send minute is the same day). A date
or time that does not exist (13-40, 02-30, 29:99), a short form whose send time sits at the edge of the date range,
or any other text is unreadable; a send time that cannot be read in local time makes the record damaged. Output, one
line per item:
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
shows n/a. When any first ETA is unreadable, one more line counts them per session (the lines above leave
them out):
  UNREADABLE first ETA <n> | <sender> <n>[, <sender> <n>...]
The coordinator tells a session under 80% to add its median lateness to its next estimates and to record
each miss as a lesson:
  ACCURACY <sender> | finished <m> | on first ETA <n> of <m> (<pct>% or n/a) | median late <min> min | re-dated <r>x
  | open past first ETA <k>
--suggest prints the ETA SENDER should promise for work estimated at DURATION (30m, 2h, 1d): now + the estimate + the
sender's median lateness over ALL its finished items (minutes late against the first ETA, early or on time counts 0,
lower median: a session on time 10 times of 11 gets nothing added), rounded UP to the next quarter hour, as a line send.sh accepts, then one line saying how it
was derived:
  ETA <MM-DD HH:MM>
  estimate 2h + median lateness 53 min over 11 finished items (7 late)
With fewer than --min-history finished items (default 3) or an unknown sender it suggests the estimate alone and says
why. --json prints one object instead (eta, eta_text, estimate_min, median_late_min, finished, late, min_history, basis
"history" or "estimate-only", derivation). A DURATION that is bad or longer than the longest ETA send_check.py accepts (90 days, or $BUS_ETA_MAX_DAYS) is exit 2.
--health reads the send events (events.jsonl next to this script, or $BUS_EVENTS; one line per send.sh attempt,
written without the message text) for the window and prints one line:
  HEALTH ok|degraded | open <n> | overdue <n> | escalate <n> | sent <n> | refused <n> | unchecked <n> | untracked <n>
  | damaged <n>[ | unreadable <n>] | since <window>
degraded (exit 1) means a line went out unchecked or untracked (the guard did not run), a record or event line
is damaged, or an open item's ETA is unreadable (counted as "unreadable", shown only then): look before trusting
the other listings.
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
DEFAULT_ETA_DAYS = 90  # the horizon send_check.py accepts (BUS_ETA_MAX_DAYS); repeated here: no import, see due_at
WINDOW_UNITS = {"m": 60, "h": 3600, "d": 86400}
# "MM-DD HH:MM", "MM/DD HH:MM" or "HH:MM"; ASCII digits only
SHORT_ETA = re.compile(r"(?:(\d{1,2})[-/](\d{1,2})\s+)?(\d{1,2}):(\d{2})", re.ASCII)
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
            if sent_at.tzinfo is None:
                sent_at = sent_at.astimezone()
        except ValueError:  # also a naive send time outside years 1..9999 once read in local time
            damaged += 1
            continue
        ident = (sender, key)
        if eta in ("DONE", "CLEARED"):
            done = items.pop(ident, None)
            if done:
                finished.append({**done, "closed": sent_at})
            continue
        earlier = items.get(ident)
        due = due_at(eta, sent_at)
        items[ident] = {"key": key, "sender": sender, "eta": eta, "due": due, "text": text,
                        "opened": earlier["opened"] if earlier else sent_at,
                        "first": earlier["first"] if earlier else eta,
                        "first_due": earlier["first_due"] if earlier else due,
                        "redates": (earlier["redates"] + is_later(due, earlier["due"])) if earlier else 0}
    return items, finished, damaged


def due_at(eta, sent):
    """The ETA as an aware local datetime, read against `sent` (the record's send time) by the rules in the module
    docstring; None when the record holds something unreadable. The rules repeat send_check.py's eta_of on purpose:
    importing it would stop every report when the guard itself is broken, which is what --health must show."""
    try:
        return dt.datetime.strptime(eta, "%Y-%m-%d %H:%M").astimezone()
    except ValueError:
        pass
    found = SHORT_ETA.fullmatch(eta.strip())
    if not found:
        return None
    month, day, hour, minute = (None if part is None else int(part) for part in found.groups())
    if hour > 23 or minute > 59:
        return None
    try:
        return short_due(month, day, hour, minute, sent.astimezone().replace(tzinfo=None))
    except (ValueError, OverflowError):  # a send time at the edge of the date range: unreadable, never fatal
        return None


def short_due(month, day, hour, minute, local):
    """A short-form ETA (month and day None for "HH:MM") resolved against the naive local send time."""
    this_minute = local.replace(second=0, microsecond=0)
    if month is None:
        at = this_minute.replace(hour=hour, minute=minute)
        return (at + dt.timedelta(days=1) if at < this_minute else at).astimezone()
    dates = []
    for year in (local.year - 1, local.year, local.year + 1):
        try:
            dates.append(dt.datetime(year, month, day, hour, minute))
        except ValueError:  # 13-40, 02-30, 02-29 outside a leap year, or a year outside 1..9999
            continue
    return min(dates, key=lambda at: abs(at - local)).astimezone() if dates else None


def is_later(new, old):
    """A re-date: the new due time is after the previous one (an unreadable ETA, None, counts as the earliest)."""
    return new is not None and (old is None or new > old)


def listing(items, now, show_all, escalate_hours, escalate_redates):
    rows = []
    for item in items.values():
        due = item["due"]
        late = due is None or due < now
        if not (late or show_all):
            continue
        hours = (now - item["opened"]).total_seconds() / 3600
        first = item["first_due"]
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
    """{sender: {"finished", "on_time", "pct" (int or None), "median_late_min", "redates", "open_late",
    "unreadable"}}, by sender; measured against each item's first promised ETA. "unreadable" counts the finished and
    open items left out because their first ETA cannot be read. Also read by lessons.py metrics (--bus)."""
    lanes = {}

    def lane_of(sender):
        return lanes.setdefault(sender, {"finished": 0, "on_time": 0, "lates": [], "redates": 0, "open_late": 0,
                                         "unreadable": 0})

    for item in finished:
        lane = lane_of(item["sender"])
        lane["redates"] += item["redates"]
        due = item["first_due"]
        if due is None:
            lane["unreadable"] += 1  # an unreadable promise is neither kept nor missed, but counted
            continue
        lane["finished"] += 1
        if item["closed"] <= due:
            lane["on_time"] += 1
        else:
            lane["lates"].append(math.ceil((item["closed"] - due).total_seconds() / 60))
    for item in items.values():
        due = item["first_due"]
        if due is None:
            lane_of(item["sender"])["unreadable"] += 1
        elif due < now:
            lane_of(item["sender"])["open_late"] += 1
    return {sender: {"finished": lane["finished"], "on_time": lane["on_time"],
                     "pct": round(100 * lane["on_time"] / lane["finished"]) if lane["finished"] else None,
                     "median_late_min": statistics.median_low(lane["lates"]) if lane["lates"] else 0,
                     "redates": lane["redates"], "open_late": lane["open_late"], "unreadable": lane["unreadable"]}
            for sender, lane in sorted(lanes.items())}


def accuracy(items, finished, now):
    """ACCURACY lines, one per sender, measured against each item's first promised ETA, then one UNREADABLE line
    when any first ETA could not be read."""
    stats = accuracy_stats(items, finished, now)
    rows = [f"ACCURACY {sender} | finished {lane['finished']} | on first ETA {lane['on_time']} of "
            f"{lane['finished']} ({'n/a' if lane['pct'] is None else str(lane['pct']) + '%'}) | median late "
            f"{lane['median_late_min']} min | re-dated {lane['redates']}x | open past first ETA {lane['open_late']}"
            for sender, lane in stats.items()]
    unreadable = {sender: lane["unreadable"] for sender, lane in stats.items() if lane["unreadable"]}
    if unreadable:
        rows.append(f"UNREADABLE first ETA {sum(unreadable.values())} | "
                    + ", ".join(f"{sender} {count}" for sender, count in unreadable.items()))
    return rows


def window_seconds(text):
    """'30m', '24h' or '7d' in seconds; ValueError otherwise."""
    found = re.fullmatch(r"([1-9]\d*)([mhd])", text.strip())
    if not found:
        raise ValueError(f"window {text!r} is not a positive number followed by m, h or d (for example 24h)")
    return int(found.group(1)) * WINDOW_UNITS[found.group(2)]


def lateness_minutes(finished, sender):
    """Minutes each of the sender's finished items was late against its first ETA (early or on time is 0, rounded up
    to whole minutes as --accuracy does); an item whose first ETA is unreadable is left out."""
    return [max(0, math.ceil((item["closed"] - item["first_due"]).total_seconds() / 60))
            for item in finished if item["sender"] == sender and item["first_due"] is not None]


def quarter_up(at):
    """`at` (naive) rounded up to the next quarter hour; a time already on a quarter keeps it."""
    base = at.replace(minute=at.minute - at.minute % 15, second=0, microsecond=0)
    return base if base == at else base + dt.timedelta(minutes=15)


def eta_horizon_days():
    """send_check.py's longest ETA, in days: $BUS_ETA_MAX_DAYS when it is a whole number from 1 to 36500, else 90."""
    try:
        days = int(os.environ.get("BUS_ETA_MAX_DAYS") or DEFAULT_ETA_DAYS)
    except ValueError:
        return DEFAULT_ETA_DAYS
    return days if 1 <= days <= 36500 else DEFAULT_ETA_DAYS


def suggest(finished_items, sender, estimate_text, min_history, now):
    """The ETA `sender` should promise for an estimate: a dict (see the module docstring); ValueError on a bad estimate."""
    seconds = window_seconds(estimate_text)
    horizon = eta_horizon_days()
    if seconds > horizon * 86400:
        raise ValueError(f"estimate {estimate_text!r} is more than {horizon} days: split the item or estimate less")
    estimate_min = seconds // 60
    lates = lateness_minutes(finished_items, sender)
    finished = len(lates)
    history = finished >= min_history and finished > 0
    late = statistics.median_low(lates) if history else 0
    missed = sum(1 for minutes in lates if minutes)
    start = now.astimezone().replace(tzinfo=None)
    eta = quarter_up(start + dt.timedelta(minutes=estimate_min + late))
    if (eta - start).total_seconds() > horizon * 86400:  # send_check refuses an ETA past its horizon
        raise ValueError(f"suggested ETA {eta:%Y-%m-%d %H:%M} (estimate + median lateness {late} min) is more than "
                         f"{horizon} days ahead: split the item or estimate less")
    if history:
        why = f"estimate {estimate_text} + median lateness {late} min over {finished} finished items ({missed} late)"
    elif finished:
        why = f"estimate {estimate_text} only: {finished} finished items, {min_history} needed (--min-history)"
    else:
        why = f"estimate {estimate_text} only: no finished items from {sender}"
    return {"sender": sender, "eta": f"{eta:%Y-%m-%d %H:%M}", "eta_text": f"ETA {eta:%m-%d %H:%M}",
            "estimate_min": estimate_min, "median_late_min": late, "finished": finished, "late": missed, "min_history": min_history,
            "basis": "history" if history else "estimate-only", "derivation": why}


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
    unreadable = sum(item["due"] is None for item in items.values())
    degraded = bool(unchecked or untracked or damaged or unreadable)
    line = (f"HEALTH {'degraded' if degraded else 'ok'} | open {len(rows)} | "
            f"overdue {sum(row.startswith('OVERDUE') for row in rows)} | "
            f"escalate {sum(' | ESCALATE | ' in row for row in rows)} | sent {counts.get('sent', 0)} | "
            f"refused {refused} | unchecked {unchecked} | untracked {untracked} | damaged {damaged}"
            f"{f' | unreadable {unreadable}' if unreadable else ''} | since {since}")
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
    mode.add_argument("--suggest", metavar="SENDER", help="the ETA SENDER should promise for --estimate")
    parser.add_argument("--estimate", help="work estimate for --suggest (30m, 2h, 1d)")
    parser.add_argument("--min-history", type=int, default=3, help="finished items --suggest needs (default 3)")
    parser.add_argument("--json", action="store_true", help="--suggest as one JSON object")
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
    if args.suggest and not args.estimate:
        print("overdue.py: --suggest needs --estimate (30m, 2h, 1d)", file=sys.stderr)
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
    elif args.suggest:
        try:
            found = suggest(finished, args.suggest.lower(), args.estimate,
                            args.min_history, now)
        except (ValueError, OverflowError) as error:
            print(f"overdue.py: --estimate: {error}", file=sys.stderr)
            return 2
        rows = [json.dumps(found)] if args.json else [found["eta_text"], found["derivation"]]
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
