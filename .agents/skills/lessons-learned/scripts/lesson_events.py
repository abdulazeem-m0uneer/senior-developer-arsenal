"""The lessons events log: one JSON line per add, repeat or move, beside its ledger, so per-day history can be counted.

Imported by lessons.py (writes, under the ledger lock) and metrics.py (reads); not a command. Standard library only.
The ledger keeps only each lesson's latest date and hit count; this log keeps every change from the day it starts.
Kinds: add (a new lesson), repeat (add of a duplicate, bump), move (`globalize`: logged in both ledgers, with the global
lesson's id in the global log and the stub's id in the project log; the lesson's earlier adds and repeats stay in the
project's log, so a move is not a new occurrence).
  path(ledger_path)                       <ledger dir>/<ledger stem>.events.jsonl (lessons.md -> lessons.events.jsonl),
                                          beside the resolved ledger, so a symlinked ledger is written and read alike
  append(ledger_path, kind, lesson, day)  one line {"time", "date", "event", "id", "tags", "ledger"}; raises OSError
                                          (time: local, with its UTC offset; ledger: the ledger's file name only,
                                          never a machine path, so a committed log carries no home directory)
  read(ledger_path)                       (events, skipped): events are dicts with a valid date, event and id;
                                          skipped counts lines that are not JSON or lack those fields;
                                          (None, 0) when there is no log; raises OSError when it cannot be read
The log only grows; it holds no lesson text, only ids and tags (both already checked for secrets by `add`).
"""
import json
import os
import time
from datetime import date
from pathlib import Path

KINDS = ("add", "repeat", "move")


def path(ledger_path):
    ledger = Path(ledger_path).resolve()
    return ledger.with_name(f"{ledger.stem}.events.jsonl")


def append(ledger_path, kind, lesson, day):
    """Append one event (O_APPEND: parallel writers of different ledgers never interleave a line)."""
    target = path(ledger_path)
    line = json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "date": day, "event": kind,
                       "id": lesson["id"], "tags": lesson["tags"], "ledger": Path(ledger_path).name})
    handle = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o644)
    try:
        os.write(handle, (line + "\n").encode("utf-8"))
    finally:
        os.close(handle)


def read(ledger_path):
    """(events, skipped). An event keeps its fields as written, plus "day" (a date); "event" may be any string."""
    try:
        lines = path(ledger_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return None, 0
    events, skipped = [], 0
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            day = date.fromisoformat(event["date"])
            if not isinstance(event["event"], str) or not isinstance(event["id"], str):
                raise TypeError("event and id are strings")
        except (ValueError, KeyError, TypeError):
            skipped += 1
            continue
        events.append({**event, "day": day, "tags": event.get("tags") if isinstance(event.get("tags"), str) else ""})
    return events, skipped
