"""Tell which lanes are not working: open items only in the future and no sign of work for longer than a threshold.

usage: python3 -I idle.py [--threshold 30m] [--activity FILE] [--status FILE]
overdue.py chases items past their ETA; a lane whose every open item is still inside its ETA is never listed there,
even when the session stopped hours ago. This check runs on each coordinator tick, after overdue.py.
Lanes are the names in lanes.txt next to this script, or $BUS_LANES (pm, the coordinator, is not a lane). Open items
come from open-items.tsv, read as overdue.py reads it ($BUS_OPEN_ITEMS). Signs of work, per lane:
  - bus: the newest line the lane sent, from every inbox-*.md next to this script ("<ISO> | from <lane> | ...").
  - commit: --activity FILE, lines "<lane><TAB><ISO>" (the last commit time, from any command; "-" reads stdin).
    The newest of a lane's lines counts. Last activity is the newer of bus and commit.
    A bus or commit time later than now is not a sign of work: it is ignored, shown in the row and noted on stderr.
  - status: --status FILE, lines "<lane><TAB>busy|idle<TAB><ISO as-of>", written by whatever lists the agents in
    this runtime. The newest line not in the future counts. When every line of a lane is in the future, the
    newest is shown as future and ignored. A status is trusted only when its as-of is within the threshold;
    an older one is shown as stale and ignored.
A lane is IDLE when it has open items, none of them is past its ETA or unreadable (those are overdue.py's), it has
no trusted busy status, and either its last activity is older than the threshold (or it has none) or its trusted
status is idle. Activity exactly as old as the threshold is not idle. A trusted busy status always wins.
Output, one line per lane listed, in name order:
  IDLE <lane> | last <bus|commit> <ISO> (<n>m ago[; <f>]) | status <s> | open <key> ETA <eta>[, ...]
    | why <reason>[; ...]   (one line)
  EMPTY-QUEUE <lane> | last ... | status <s>
where <s> is busy|idle (as of <ISO>), stale busy|idle (as of <ISO>, <n>m old), future busy|idle (as of <ISO>),
unknown (no --status, or no line for the lane) or unavailable (the status file cannot be read), "last none" means no
activity (shown as "last none (<f>)" when only a future time exists), and <f> is "future bus|commit <ISO> ignored".
EMPTY-QUEUE is a lane with no open item: give it work; it is not an error. Prints "none" when nothing is listed.
A status file that is missing, unreadable or holds a bad line is reported on the first line,
  STATUS unavailable | <reason> | busy not trusted for any lane
then every lane is judged without status, and the exit is 2. A damaged inbox line is skipped and counted on stderr;
a name in --activity or --status that is not a lane is ignored with a note on stderr. There is no workday calendar
here: the routine that runs it (hourly inside the workday) decides when. $BUS_NOW fixes the clock for tests.
exit 0 none idle; exit 1 any IDLE; exit 2 bad usage, a bad $BUS_NOW, overdue.py missing, broken or too old, an
unreadable lanes, items, inbox or --activity file or a bad --activity line, or an unavailable status file (after the
report). Standard library only.
"""
import argparse
import datetime as dt
import importlib.util
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEXT_CHARS = 200
BUS_LINE = re.compile(r"(\S+) \| from ([a-z0-9][a-z0-9-]*) \| ", re.ASCII)
STATES = ("busy", "idle")
OVERDUE_NEEDS = ("clock", "window_seconds", "read_lanes", "lanes_file", "record_lines", "read_items")


class BadInput(Exception):
    """An input that cannot be read: exit 2."""


def load_overdue():
    spec = importlib.util.spec_from_file_location("bus_overdue", HERE / "overdue.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    missing = [name for name in OVERDUE_NEEDS if not callable(getattr(module, name, None))]
    if missing:  # an older copy of overdue.py next to a newer idle.py
        raise ImportError(f"overdue.py too old or broken: no {', '.join(missing)}")
    return module


def iso_time(text):
    """An aware datetime from ISO text ("Z" allowed; a naive time is local); ValueError otherwise."""
    at = dt.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return at if at.tzinfo else at.astimezone()


def bus_activity(inboxes):
    """({sender: [line times]}, damaged line count) over the inboxes' line lists."""
    times, damaged = {}, 0
    for lines in inboxes:
        for line in lines:
            if not line.strip():
                continue
            found = BUS_LINE.match(line)
            try:
                at, sender = iso_time(found.group(1)), found.group(2)
            except (AttributeError, ValueError):  # no "<ISO> | from <lane> | " prefix, or a bad time
                damaged += 1
                continue
            times.setdefault(sender, []).append(at)
    return times, damaged


def commit_activity(lines):
    """{lane: [commit times]} from "<lane><TAB><ISO>" lines; BadInput naming the first bad line."""
    times = {}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        fields = line.rstrip("\n").split("\t")
        try:
            if len(fields) != 2:
                raise ValueError("expected <lane><TAB><ISO>")
            lane, at = fields[0].strip().lower(), iso_time(fields[1])
        except ValueError as error:
            raise BadInput(f"--activity line {number}: {error}") from None
        times.setdefault(lane, []).append(at)
    return times


def read_status(lines):
    """{lane: [(as-of, state)]} from "<lane><TAB>busy|idle<TAB><ISO>" lines; BadInput naming the first bad line."""
    status = {}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        fields = line.rstrip("\n").split("\t")
        try:
            if len(fields) != 3 or fields[1].strip().lower() not in STATES:
                raise ValueError("expected <lane><TAB>busy|idle<TAB><ISO as-of>")
            lane, state, as_of = fields[0].strip().lower(), fields[1].strip().lower(), iso_time(fields[2])
        except ValueError as error:
            raise BadInput(f"--status line {number}: {error}") from None
        status.setdefault(lane, []).append((as_of, state))
    return status


def minutes(seconds):
    return int(seconds // 60)


def newest_past(entries, now):
    """(newest entry not after now or None, newest entry after now or None); entries are tuples led by a time."""
    past = [entry for entry in entries if entry[0] <= now]
    future = [entry for entry in entries if entry[0] > now]
    return max(past, default=None), max(future, default=None)


def judge_status(entries, now, threshold):
    """(trusted state or None, label) for one lane's status lines (None: no line for the lane)."""
    if not entries:
        return None, "unknown"
    entry, future = newest_past(entries, now)
    if entry is None:
        as_of, state = future
        return None, f"future {state} (as of {as_of.isoformat()})"
    as_of, state = entry
    age = (now - as_of).total_seconds()
    if age > threshold:
        return None, f"stale {state} (as of {as_of.isoformat()}, {minutes(age)}m old)"
    return state, f"{state} (as of {as_of.isoformat()})"


def activity(lane, bus, commits, now):
    """([(time, source)] of the lane's newest bus line and commit not after now, [(time, source)] of the newest
    ones after now)."""
    past, future = [], []
    for source, times in (("bus", bus.get(lane, [])), ("commit", commits.get(lane, []))):
        newest, ahead = newest_past([(at,) for at in times], now)
        past += [(newest[0], source)] if newest else []
        future += [(ahead[0], source)] if ahead else []
    return past, future


def last_activity(lane, bus, commits, now):
    """The time of the newer of the lane's bus line and commit not after now (or None), and its label."""
    sources, future = activity(lane, bus, commits, now)
    note = "; ".join(f"future {source} {at.isoformat()} ignored" for at, source in future)
    if not sources:
        return None, f"last none ({note})" if note else "last none"
    at, source = max(sources)
    age = f"{minutes((now - at).total_seconds())}m ago"
    return at, f"last {source} {at.isoformat()} ({age}; {note})" if note else f"last {source} {at.isoformat()} ({age})"


def report(lanes, items, bus, commits, status, now, threshold):
    """IDLE and EMPTY-QUEUE lines, in `lanes` order. `status` None means the status file is unavailable."""
    rows = []
    for lane in lanes:
        held = sorted((item for item in items.values() if item["sender"] == lane), key=lambda item: item["key"])
        at, last = last_activity(lane, bus, commits, now)
        trusted, label = (None, "unavailable") if status is None else judge_status(status.get(lane), now, threshold)
        if not held:
            rows.append(f"EMPTY-QUEUE {lane} | {last} | status {label}")
            continue
        if trusted == "busy" or any(item["due"] is None or item["due"] < now for item in held):
            continue  # busy now, or overdue.py lists it
        why = []
        if at is None:
            why.append("no activity")
        elif (now - at).total_seconds() > threshold:
            why.append(f"no activity for over {minutes(threshold)}m")
        if trusted == "idle":
            why.append("status idle")
        if not why:
            continue
        why.append("only future ETAs")
        held_text = ", ".join(f"{item['key']} ETA {item['eta']}" for item in held)
        rows.append(f"IDLE {lane} | {last} | status {label} | open {held_text[:TEXT_CHARS]} | why {'; '.join(why)}")
    return rows


def read_input(name, stdin):
    """Lines of a file, or of stdin for "-"; OSError when it cannot be read."""
    if name == "-":
        return stdin.read().splitlines()
    return Path(name).read_text(encoding="utf-8", errors="replace").splitlines()


def main(argv=None, stdin=sys.stdin):
    parser = argparse.ArgumentParser(description="List lanes that hold only future ETAs and show no work.")
    parser.add_argument("--threshold", default="30m", help="idle after this long without activity (30m, 2h, 1d)")
    parser.add_argument("--activity", metavar="FILE", help='"<lane><TAB><ISO>" last-commit lines; - for stdin')
    parser.add_argument("--status", metavar="FILE", help='"<lane><TAB>busy|idle<TAB><ISO as-of>" lines; - for stdin')
    args = parser.parse_args(argv)
    if args.activity == "-" and args.status == "-":
        print("idle.py: only one of --activity and --status can read stdin", file=sys.stderr)
        return 2
    try:
        overdue = load_overdue()
    except (Exception, SystemExit) as error:  # noqa: BLE001 - any failure importing it (even sys.exit) is exit 2, never 1
        print(f"idle.py: cannot load overdue.py next to this script: {error!r}", file=sys.stderr)
        return 2
    try:
        threshold = overdue.window_seconds(args.threshold)
        now = overdue.clock()
    except ValueError as error:
        print(f"idle.py: --threshold or BUS_NOW: {error}", file=sys.stderr)
        return 2
    try:
        lanes = sorted(overdue.read_lanes(overdue.lanes_file()) - {"pm"})
        _, records = overdue.record_lines()
        items, _, damaged_items = overdue.read_items(records)
        inboxes = [path.read_text(encoding="utf-8", errors="replace").splitlines()
                   for path in sorted(HERE.glob("inbox-*.md"))]
        commits = commit_activity(read_input(args.activity, stdin)) if args.activity else {}
    except (OSError, UnicodeError, BadInput) as error:  # UnicodeError: stdin that is not text
        print(f"idle.py: {error}", file=sys.stderr)
        return 2
    bus, damaged_bus = bus_activity(inboxes)
    for count, where in ((damaged_items, "open-items.tsv"), (damaged_bus, "the inbox files")):
        if count:
            print(f"idle.py: {count} damaged line(s) in {where} skipped", file=sys.stderr)
    status, unavailable = {}, None
    if args.status:
        try:
            status = read_status(read_input(args.status, stdin))
        except (OSError, UnicodeError, BadInput) as error:
            status, unavailable = None, str(error)
    for name in sorted(set(commits) | set(status or {})):
        if name not in lanes:
            print(f"idle.py: {name} is not a lane in lanes.txt: ignored", file=sys.stderr)
    for lane in lanes:
        for at, source in activity(lane, bus, commits, now)[1]:
            print(f"idle.py: {lane} {source} time {at.isoformat()} is in the future: ignored", file=sys.stderr)
    rows = report(lanes, items, bus, commits, status, now, threshold)
    if unavailable:
        rows.insert(0, f"STATUS unavailable | {unavailable} | busy not trusted for any lane")
    print("\n".join(rows) if rows else "none")
    if unavailable:
        return 2
    return 1 if any(row.startswith("IDLE ") for row in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
