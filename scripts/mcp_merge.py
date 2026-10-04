#!/usr/bin/env python3
"""Merge one MCP server entry into a JSON config file without losing existing content.

Exit codes: 0 merged or unchanged, 2 the existing file could not be merged safely.
"""
import argparse
import json
import os
import shutil
import sys
import time


def load_entry(path, substitutions):
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    for pair in substitutions:
        key, _, value = pair.partition("=")
        text = text.replace("{{" + key + "}}", value)
    return json.loads(text)


def refuse(config, reason, key, name, entry):
    snippet = json.dumps({key: {name: entry}}, indent=2)
    print(f"error: {config}: {reason}; file left untouched. Add this manually:\n{snippet}", file=sys.stderr)
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="config file to update")
    parser.add_argument("--key", required=True, help="top-level key holding the servers map")
    parser.add_argument("--name", required=True, help="server name")
    parser.add_argument("--entry", required=True, help="JSON file with the server entry")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="replace {{KEY}} in the entry")
    parser.add_argument("--dry-run", action="store_true")
    options = parser.parse_args(argv)

    entry = load_entry(options.entry, options.set)
    config = os.path.realpath(options.file)
    data = {}
    exists = os.path.exists(config)
    if exists and os.path.getsize(config) > 0:
        try:
            with open(config, encoding="utf-8-sig") as handle:
                data = json.load(handle)
        except (ValueError, OSError) as error:
            return refuse(config, f"not valid JSON ({error})", options.key, options.name, entry)
    if not isinstance(data, dict) or not isinstance(data.get(options.key, {}), dict):
        return refuse(config, f"'{options.key}' is not a JSON object", options.key, options.name, entry)

    servers = data.setdefault(options.key, {})
    if servers.get(options.name) == entry:
        print(f"unchanged: '{options.name}' already registered in {config}")
        return 0
    servers[options.name] = entry
    if options.dry_run:
        print(f"[dry-run] would register '{options.name}' in {config}")
        return 0

    os.makedirs(os.path.dirname(config), exist_ok=True)
    if exists:
        shutil.copy2(config, f"{config}.bak-{time.strftime('%Y%m%d%H%M%S')}")
    temporary = f"{config}.tmp-{os.getpid()}"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    if exists:
        shutil.copymode(config, temporary)
    os.replace(temporary, config)
    print(f"registered '{options.name}' in {config}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
