"""The report behind `lessons.py metrics`: per ledger and lane, lessons added and repeated per day, total repeats,
guard coverage, guard fires per day and, with a bus folder, the ETA accuracy per session. Imported by lessons.py;
not a command. Standard library only.

  collect(sources, guard_state, unguarded_repeats, threshold, days, today, lane_prefix, bus_dir) -> dict (the --json)
  markdown(data) -> Markdown text

Definitions (stated in the report too):
- Window: the last `days` calendar days, today included. Dates are local, as lessons.py writes them.
- Project: one ledger source, in the order lessons.py lists them (this ledger, each --ledger, the global ledger).
- Lane: the first tag that starts with the lane prefix (default `session:`; lessons.py adds a missing `:`) and names
  something after it; a lesson with none is under "(no lane)". An event's lane comes from the tags it was logged with,
  a lesson's from its tags now.
- Moved: a project stub `globalize` left (lessons.py guard_state "moved"). The global ledger holds the lesson, its hits
  up to the move and its guard state, so a stub is counted in this column, not in Lessons, the guard columns or the
  ledger-date fallback. Its adds and repeats logged before the move stay in the project's per-day columns, where they
  happened; both logs record the move as a "move" event, which is not an occurrence and is not counted per day.
  A stub that recurs after the move (lessons.py matches it, bumps it and prints GUARD FAILED) is "recurred": its
  repeat events after its last move event (file order) count in the project's Repeats, since the global lesson's hits
  never get them. A stub back in Active with no move event logged recurred an unknown number of times: it is named
  with no count.
- Added / repeated per day: from the ledger's events log (lesson_events.py) from the first day it holds an event on.
  Days before that (or every day, without a log) come from the ledger itself, which keeps only each lesson's last
  date: a lesson there counts once, on its last date, as added (hits 1) or repeated (hits above 1), unless the log
  holds an event for it (a moved lesson keeps its old date). The report names those days "from ledger dates: last
  change only". A lesson changed after the log started without an event (written by a lessons.py older than the log)
  is not counted per day; a lesson moved before the global log existed is counted on its date in both ledgers.
- Repeats: hits above 1 summed over every lesson the group holds now (all time, archive included), plus recurred stubs'
  logged repeats after their move.
- Guarded / unguarded / exempt: lessons.py's own guard_state (the rules of `unguarded` and `exempt`); "unguarded N+"
  is the `unguarded` command's list at the promotion threshold.
- Guard fires: the machine-wide lesson-guard hit log (guard_hits.py), per local day; a hit is not tied to a ledger.
- ETA accuracy: the bus template's overdue.py accuracy_stats over <bus>/open-items.tsv, at its clock ($BUS_NOW).
  ETAs are read in the full form ("YYYY-MM-DD HH:MM") and the short ones ("MM-DD HH:MM", "HH:MM") against each
  record's send time; items whose first ETA is still unreadable are left out of the table and counted per session
  ("unreadable" in --json, one line in Markdown).
Skipped and counted, never fatal: event lines that are not JSON or lack date, event or id; unknown event kinds;
events and ledger dates after today; damaged guard-hit lines; damaged bus records. A missing log, ledger or bus folder
prints one line, and so does a log that cannot be read (a folder in its place, no permission): an unreadable events log
falls back to ledger dates, an unreadable hit log counts no fires.
"""
import importlib.util
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import guard_hits
import lesson_events

MAX_DAYS = 366
NO_LANE = "(no lane)"
STATES = ("guarded", "unguarded", "exempt", "moved")
OCCURRENCES = ("add", "repeat")
OVERDUE = Path(__file__).resolve().parents[2] / "multi-session-delivery" / "templates" / "bus" / "overdue.py"
LEDGER_ONLY = "from ledger dates: last change only"


def lane_of(tags, prefix):
    for tag in (tags or "").split(","):
        tag = tag.strip()
        if tag.startswith(prefix) and tag[len(prefix):].strip():
            return tag[len(prefix):].strip().replace("|", "/")  # a lane name is a Markdown table cell
    return NO_LANE


def parse_day(text):
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def project(source, guard_state, flagged, dates, today, prefix):
    """One ledger's counts: per-day added/repeated by lane, where each day came from, guard coverage."""
    try:
        events, malformed = lesson_events.read(source.path)
        log_error = None
    except OSError as error:
        events, malformed, log_error = None, 0, unreadable(error)
    skipped = Counter(malformed=malformed)
    known = []
    for event in events or []:
        if event["event"] not in lesson_events.KINDS:
            skipped["unknown_event"] += 1
        elif event["day"] > today:
            skipped["future_event"] += 1
        else:
            known.append(event)
    log_start = min((event["day"] for event in known), default=None)
    from_events = [log_start is not None and day >= log_start for day in dates]
    logged_ids = {event["id"] for event in known}
    last_move = {event["id"]: n for n, event in enumerate(known) if event["event"] == "move"}
    after_move = Counter(event["id"] for n, event in enumerate(known)
                         if event["event"] == "repeat" and n > last_move.get(event["id"], len(known)))
    recurred = []
    index = {day: n for n, day in enumerate(dates)}
    lanes = defaultdict(lambda: {"added": [0] * len(dates), "repeated": [0] * len(dates), "lessons": 0, "repeats": 0,
                                 **{state: 0 for state in STATES}, "moved_recurred": 0,
                                 "unguarded_repeats": 0})
    for event in known:
        if event["day"] in index and event["event"] in OCCURRENCES:
            lanes[lane_of(event["tags"], prefix)]["added" if event["event"] == "add" else "repeated"][
                index[event["day"]]] += 1
    for lesson in source.lessons:
        row, state = lanes[lane_of(lesson["tags"], prefix)], guard_state(lesson)
        row[state] += 1
        if state == "moved":
            repeats = after_move[lesson["id"]] if lesson["id"] in last_move else None
            if repeats or (repeats is None and lesson["section"] == "active"):
                row["moved_recurred"] += 1
                row["repeats"] += repeats or 0
                recurred.append({"id": lesson["id"], "repeats": repeats})
            continue
        row["lessons"] += 1
        row["repeats"] += lesson["hits"] - 1
        row["unguarded_repeats"] += id(lesson) in flagged
        day = parse_day(lesson["date"])
        if day is not None and day > today:
            skipped["future_ledger_date"] += 1
        elif day in index and not from_events[index[day]] and lesson["id"] not in logged_ids:
            row["added" if lesson["hits"] == 1 else "repeated"][index[day]] += 1
    rows = [{"lane": lane, **row, "added_total": sum(row["added"]), "repeated_total": sum(row["repeated"])}
            for lane, row in sorted(lanes.items(), key=lambda item: (item[0] == NO_LANE, item[0]))]
    return {"ledger": str(source.path), "ledger_found": source.path.is_file(),
            "events_log": str(lesson_events.path(source.path)), "events_log_found": events is not None,
            "events_log_error": log_error,
            "events_from": log_start.isoformat() if log_start else None,
            "day_source": ["events" if flag else "ledger" for flag in from_events],
            "skipped": {key: skipped[key] for key in ("malformed", "unknown_event", "future_event",
                                                      "future_ledger_date")},
            "recurred_after_move": recurred, "lanes": rows}


def unreadable(error):
    """The reason an existing log could not be read, without the path the report already names."""
    return error.strerror or str(error)


def guard_fires(dates):
    try:
        found, damaged = guard_hits.entries()
        error = None
    except OSError as failure:
        found, damaged, error = [], 0, unreadable(failure)
    index = {day: n for n, day in enumerate(dates)}
    per_day = [0] * len(dates)
    for when, _, _ in found:
        try:
            day = datetime.fromtimestamp(when).date()
        except (OverflowError, OSError, ValueError):
            damaged += 1
            continue
        if day in index:
            per_day[index[day]] += 1
    return {"log": str(guard_hits.path()), "log_found": guard_hits.path().is_file(), "per_day": per_day,
            "total": sum(per_day), "damaged": damaged, "error": error}


def load_overdue():
    spec = importlib.util.spec_from_file_location("bus_overdue", OVERDUE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def eta_accuracy(bus_dir):
    """The bus's ETA accuracy per session; a missing, empty or unreadable bus is a status and a note, not an error."""
    if bus_dir is None:
        return None
    items_file = Path(bus_dir) / "open-items.tsv"
    result = {"bus": str(bus_dir), "status": "ok", "note": "", "sessions": [], "damaged": 0, "unreadable": 0}
    if not OVERDUE.is_file():
        return {**result, "status": "unavailable", "note": f"overdue.py not found at {OVERDUE}"}
    if not items_file.is_file():
        return {**result, "status": "missing", "note": f"no open-items.tsv in {bus_dir}: no ETA data"}
    try:
        overdue = load_overdue()
        lines = items_file.read_text(encoding="utf-8", errors="replace").splitlines()
        now = overdue.clock()
    except (OSError, ValueError) as error:  # ValueError: a $BUS_NOW that is not an ISO time
        return {**result, "status": "unreadable", "note": f"ETA accuracy not read: {error}"}
    items, finished, damaged = overdue.read_items(lines)
    sessions = [{"session": sender, **stats} for sender, stats in overdue.accuracy_stats(items, finished, now).items()]
    if not sessions:
        return {**result, "status": "empty", "damaged": damaged,
                "note": f"no finished or overdue items in {items_file} yet"}
    return {**result, "sessions": sessions, "damaged": damaged,
            "unreadable": sum(session["unreadable"] for session in sessions)}


def collect(sources, guard_state, unguarded_repeats, threshold, days, today, lane_prefix, bus_dir=None):
    dates = [today - timedelta(days=days - 1 - n) for n in range(days)]
    flagged = {id(lesson) for _, lesson in unguarded_repeats}
    return {"window": {"start": dates[0].isoformat(), "end": today.isoformat(), "days": days,
                       "dates": [day.isoformat() for day in dates]},
            "lane_tag": lane_prefix, "threshold": threshold,
            "projects": [project(source, guard_state, flagged, dates, today, lane_prefix) for source in sources],
            "guard_fires": guard_fires(dates), "eta_accuracy": eta_accuracy(bus_dir)}


def runs(dates, flags):
    """'a to b' spans of the dates whose flag is set."""
    spans, start = [], None
    for n, flag in enumerate(flags + [False]):
        if flag and start is None:
            start = n
        elif not flag and start is not None:
            spans.append(dates[start] if n - 1 == start else f"{dates[start]} to {dates[n - 1]}")
            start = None
    return ", ".join(spans)


def moved_cell(row):
    return f"{row['moved']} ({row['moved_recurred']} recurred)" if row["moved_recurred"] else str(row["moved"])


def project_lines(entry, dates, threshold):
    lines = ["", f"### {entry['ledger']}"]
    if not entry["ledger_found"]:
        lines.append("- no ledger file yet")
    ledger_days = runs(dates, [source == "ledger" for source in entry["day_source"]])
    if entry["events_log_error"]:
        lines.append(f"- events log {entry['events_log']} not read ({entry['events_log_error']}): every day is "
                     f"{LEDGER_ONLY}")
    elif not entry["events_log_found"]:
        lines.append(f"- no events log at {entry['events_log']}: every day is {LEDGER_ONLY} (a lesson counts once, "
                     "on its last date)")
    elif entry["events_from"] is None:
        lines.append(f"- events log {entry['events_log']} holds no usable event: every day is {LEDGER_ONLY}")
    else:
        lines.append(f"- per day from the events log from {entry['events_from']}"
                     + (f"; {ledger_days} {LEDGER_ONLY}" if ledger_days else ""))
    skipped = ", ".join(f"{count} {name.replace('_', ' ')}" for name, count in entry["skipped"].items() if count)
    if skipped:
        lines.append(f"- skipped: {skipped}")
    if entry["recurred_after_move"]:
        stubs = [f"{stub['id']} x{stub['repeats']}" if stub["repeats"] is not None
                 else f"{stub['id']} (how often is not in the events log)" for stub in entry["recurred_after_move"]]
        lines.append(f"- recurred after globalize (the guard failed; counted in Repeats here): {', '.join(stubs)}")
    if not entry["lanes"]:
        lines.append("- no lessons")
        return lines
    lines += ["", f"| Lane | Lessons | Repeats | Guarded | Unguarded | Unguarded {threshold}+ | Exempt | Moved | "
                  "Added | Repeated |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    lines += [f"| {row['lane']} | {row['lessons']} | {row['repeats']} | {row['guarded']} | {row['unguarded']} | "
              f"{row['unguarded_repeats']} | {row['exempt']} | {moved_cell(row)} | {row['added_total']} | "
              f"{row['repeated_total']} |"
              for row in entry["lanes"]]
    lines += ["", "Added/repeated per day:", "", "| Lane | " + " | ".join(day[5:] for day in dates) + " |",
              "|---|" + "---:|" * len(dates)]
    lines += [f"| {row['lane']} | " + " | ".join(f"{a}/{r}" for a, r in zip(row["added"], row["repeated"])) + " |"
              for row in entry["lanes"]]
    return lines


def markdown(data):
    window, dates = data["window"], data["window"]["dates"]
    lines = [f"## Lesson metrics: {window['start']} to {window['end']} ({window['days']} days)", "",
             f"Lane: tag `{data['lane_tag']}<name>`. Repeats: hits above 1, all time. Guarded, unguarded and exempt "
             "as `lessons.py unguarded` and `exempt` judge them. Moved: stubs `globalize` left; the global ledger "
             "counts those lessons."]
    for entry in data["projects"]:
        lines += project_lines(entry, dates, data["threshold"])
    fires = data["guard_fires"]
    lines += ["", "### Guard fires (this machine, every project)"]
    if fires["error"]:
        lines.append(f"- hit log {fires['log']} not read ({fires['error']})")
    elif not fires["log_found"]:
        lines.append(f"- no hit log at {fires['log']}")
    else:
        lines += ["", "| " + " | ".join(day[5:] for day in dates) + " | Total |", "|" + "---:|" * (len(dates) + 1),
                  "| " + " | ".join(map(str, fires["per_day"])) + f" | {fires['total']} |"]
        if fires["damaged"]:
            lines.append(f"- {fires['damaged']} damaged lines skipped")
    eta = data["eta_accuracy"]
    if eta is not None:
        lines += ["", f"### ETA accuracy (bus {eta['bus']})"]
        if eta["status"] != "ok":
            lines.append(f"- {eta['note']}")
        else:
            lines += ["", "| Session | Finished | On first ETA | Median late (min) | Re-dated | Open past first ETA |",
                      "|---|---:|---:|---:|---:|---:|"]
            lines += [f"| {row['session']} | {row['finished']} | {row['on_time']} of {row['finished']} "
                      f"({'n/a' if row['pct'] is None else str(row['pct']) + '%'}) | {row['median_late_min']} | "
                      f"{row['redates']} | {row['open_late']} |" for row in eta["sessions"]]
        if eta["damaged"]:
            lines.append(f"- {eta['damaged']} damaged bus records skipped")
        if eta["unreadable"]:
            lines.append(f"- {eta['unreadable']} items left out: first ETA unreadable ("
                         + ", ".join(f"{row['session']} {row['unreadable']}" for row in eta["sessions"]
                                     if row["unreadable"]) + ")")
    return "\n".join(lines)
