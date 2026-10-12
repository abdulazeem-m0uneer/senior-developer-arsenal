#!/usr/bin/env python3
"""Sum token usage from session transcripts in JSON-lines form.

Usage: python scripts/usage_report.py --dir <transcripts> [--since ISO | --since-hour HH] [--tz Area/City] [--top N] [--json]
A line of a *.jsonl file under --dir counts when it holds message.usage and a timestamp at or after the
cut-off (default 00:00 today in --tz); lines that share message.id and requestId count once.
Exit codes: 0 on success, 2 on a missing directory, an unknown time zone or an unreadable time.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
TOTAL_KEYS = ("input", "output", "cache_write", "cache_read")
USAGE_MARKER = '"usage"'


def parse_time(text, default_zone=timezone.utc):
    """An aware datetime from ISO 8601 text, or None; a time without an offset is read in default_zone."""
    try:
        moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except (AttributeError, ValueError):  # not text, or not ISO 8601
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=default_zone)


def parse_line(line):
    """(dedup key or None, timestamp, counts in TOTAL_KEYS order) for one line; None when unusable.
    A usage field that is missing or is not a positive integer counts as zero."""
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    message = entry.get("message") if isinstance(entry, dict) else None
    usage = message.get("usage") if isinstance(message, dict) else None
    moment = parse_time(entry.get("timestamp")) if isinstance(usage, dict) else None
    if moment is None:
        return None
    message_id, request_id = message.get("id"), entry.get("requestId")
    key = None if message_id is None and request_id is None else f"{message_id}:{request_id}"
    return key, moment, tuple(value if type(value) is int and value > 0 else 0 for value in map(usage.get, USAGE_FIELDS))


def summarise(lines, since, top=5):
    """Totals and the top groups by output tokens from (group, line) pairs at or after since."""
    groups, seen, ignored = {}, set(), 0
    for group, line in lines:
        if USAGE_MARKER not in line:
            continue
        record = parse_line(line)
        if record is None:
            ignored += 1
            continue
        key, moment, counts = record
        if moment < since or (key is not None and key in seen):
            continue
        seen.add(key)
        bucket = groups.setdefault(group, dict.fromkeys(("requests",) + TOTAL_KEYS, 0))
        bucket["requests"] += 1
        for name, value in zip(TOTAL_KEYS, counts):
            bucket[name] += value
    totals = {name: sum(bucket[name] for bucket in groups.values()) for name in ("requests",) + TOTAL_KEYS}
    ranked = sorted(groups.items(), key=lambda item: (-item[1]["output"], item[0]))[:max(top, 0)]
    return {
        "since": since.astimezone(timezone.utc).isoformat(), "requests": totals.pop("requests"),
        "ignored_lines": ignored, "totals": totals, "fresh_input": totals["input"] + totals["cache_write"],
        "groups": [{"name": name, **bucket} for name, bucket in ranked],
    }


def resolve_since(now, zone, since_text=None, since_hour=None):
    """The cut-off: an explicit time, else the latest HH:00 (default 00:00) in zone that is not after now."""
    if since_text is not None:
        moment = parse_time(since_text, zone)
        if moment is None:
            raise ValueError(f"--since is not an ISO 8601 time: {since_text}")
        return moment
    local = now.astimezone(zone)
    start = local.replace(hour=since_hour or 0, minute=0, second=0, microsecond=0)  # ValueError outside 0 to 23
    return start if start <= local else start - timedelta(days=1)


def transcript_files(directory):
    """Every *.jsonl file under directory, in a stable order."""
    return sorted(path for path in directory.rglob("*.jsonl") if path.is_file())


def read_lines(directory, files, since):
    """(group, line) pairs from files modified at or after since; the group is the first folder, else '.'."""
    for path in files:
        parts = path.relative_to(directory).parts
        group = parts[0] if len(parts) > 1 else "."
        try:
            if path.stat().st_mtime < since.timestamp():
                continue
            with path.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    yield group, line
        except OSError:  # an unreadable file is skipped, the rest still count
            continue


def millions(number):
    return f"{number / 1e6:.2f}M"


def render(report, file_count):
    totals = report["totals"]
    rows = [
        f"since {report['since']} | files {file_count} | requests {report['requests']}"
        f" | ignored lines {report['ignored_lines']}",
        f"output {millions(totals['output'])} | fresh input {millions(report['fresh_input'])}"
        f" | cached reads {millions(totals['cache_read'])}",
    ]
    rows += [f"  {group['name']}: requests {group['requests']}, output {millions(group['output'])}, "
             f"fresh input {millions(group['input'] + group['cache_write'])}" for group in report["groups"]]
    return "\n".join(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sum token usage from JSON-lines session transcripts.")
    parser.add_argument("--dir", required=True, help="folder that holds the transcript files")
    cut_off = parser.add_mutually_exclusive_group()
    cut_off.add_argument("--since", help="ISO 8601 time; without an offset it is read in --tz")
    cut_off.add_argument("--since-hour", type=int, metavar="HH", help="latest HH:00 in --tz, today or yesterday")
    parser.add_argument("--tz", default="UTC", help="IANA time zone name (default UTC)")
    parser.add_argument("--top", type=int, default=5, help="number of groups to list (default 5)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    options = parser.parse_args(argv)
    directory = Path(options.dir)
    try:
        if not directory.is_dir():
            raise ValueError(f"not a directory: {directory}")
        # UTC needs no time zone database, which some platforms lack.
        zone = timezone.utc if options.tz.upper() == "UTC" else ZoneInfo(options.tz)
        since = resolve_since(datetime.now(timezone.utc), zone, options.since, options.since_hour)
    except (ValueError, KeyError, OSError) as error:  # an unknown zone raises ZoneInfoNotFoundError, a KeyError
        print(f"usage_report: {error}", file=sys.stderr)
        return 2
    files = transcript_files(directory)
    report = summarise(read_lines(directory, files, since), since, options.top)
    print(json.dumps({**report, "files": len(files)}, indent=2) if options.json else render(report, len(files)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
