#!/usr/bin/env python3
"""Merge the arsenal hook entries into an agent's JSON hook config, or take them out again, without
touching anything else in the file.

Usage:
  hooks_merge.py --file CONFIG --entry dist/hooks/<target>.json --set ARSENAL_HOOKS=<installed hook dir>
  hooks_merge.py --file CONFIG --entry dist/hooks/<target>.json --remove
  (--dry-run prints what would happen and writes nothing)

The entry is a JSON object. Each top-level object in it maps an event name to a list of handlers
(`hooks` for Codex, Gemini CLI, Cursor and Copilot; the hook name for Antigravity); every other top-level
value (`version`) is set only when the config has none. An arsenal handler is one whose text names
arsenal-hooks/agent_hook.py: a merge replaces those and appends the current ones after the user's own, so
running it twice changes nothing; --remove deletes them, drops the lists and objects that this empties, and
deletes the file when nothing but `version` is left. The file is backed up beside itself before any change.
Exit codes: 0 merged, removed or unchanged; 2 the existing file could not be changed safely (it is left
untouched). Time budget: one read and at most one write. Standard library only.
"""
import argparse
import json
import os
import shutil
import sys
import time

MARKER = "arsenal-hooks/agent_hook.py"
INERT_KEYS = {"version"}


class Unmergeable(Exception):
    pass


def substituted(value, pairs):
    """value with {{KEY}} replaced in every string, after parsing, so a path never has to be JSON-escaped."""
    if isinstance(value, str):
        for key, replacement in pairs:
            value = value.replace("{{" + key + "}}", replacement)
        return value
    if isinstance(value, list):
        return [substituted(item, pairs) for item in value]
    if isinstance(value, dict):
        return {key: substituted(item, pairs) for key, item in value.items()}
    return value


def owned(handler):
    return MARKER in json.dumps(handler)


def sections(entry):
    return {key: value for key, value in entry.items() if isinstance(value, dict)}


def kept_handlers(section, event):
    handlers = section.get(event, [])
    if not isinstance(handlers, list):
        raise Unmergeable(f"'{event}' is not a JSON array")
    return [handler for handler in handlers if not owned(handler)]


def merged(data, entry):
    result = dict(data)
    for key, value in entry.items():
        if key not in sections(entry):
            result.setdefault(key, value)
            continue
        section = result.get(key, {})
        if not isinstance(section, dict):
            raise Unmergeable(f"'{key}' is not a JSON object")
        result[key] = {**section, **{event: kept_handlers(section, event) + handlers
                                     for event, handlers in value.items()}}
    return result


def removed(data, entry):
    result = dict(data)
    for key, value in sections(entry).items():
        section = result.get(key)
        if not isinstance(section, dict):
            continue
        section = dict(section)
        for event in value:
            if event in section and kept_handlers(section, event) != section[event]:
                section[event] = kept_handlers(section, event)
                if not section[event]:
                    del section[event]
        if section != result[key]:
            result[key] = section
            if not section:
                del result[key]
    return result


def load(config):
    if not os.path.exists(config) or os.path.getsize(config) == 0:
        return {}
    try:
        with open(config, encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (ValueError, OSError) as error:
        raise Unmergeable(f"not valid JSON ({error})") from error
    if not isinstance(data, dict):
        raise Unmergeable("the top level is not a JSON object")
    return data


def save(config, data, exists):
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", required=True, help="hook config file to update")
    parser.add_argument("--entry", required=True, help="generated JSON with the arsenal hook entries")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="replace {{KEY}} in the entry")
    parser.add_argument("--remove", action="store_true", help="take the arsenal entries out")
    parser.add_argument("--dry-run", action="store_true")
    options = parser.parse_args(argv)

    with open(options.entry, encoding="utf-8") as handle:
        pairs = [(key, value) for key, _, value in (pair.partition("=") for pair in options.set)]
        entry = substituted(json.load(handle), pairs)
    config = os.path.realpath(options.file)
    exists = os.path.exists(config)
    verb = "remove the arsenal hooks from" if options.remove else "register the arsenal hooks in"
    try:
        data = load(config)
        result = removed(data, entry) if options.remove else merged(data, entry)
    except Unmergeable as error:
        print(f"error: {config}: {error}; file left untouched. To {verb} it by hand, use:\n"
              f"{json.dumps(entry, indent=2)}", file=sys.stderr)
        return 2
    if result == data:
        print(f"unchanged: arsenal hooks in {config}")
        return 0
    if options.dry_run:
        print(f"[dry-run] would {verb} {config}")
        return 0
    if options.remove and not set(result) - INERT_KEYS:
        shutil.copy2(config, f"{config}.bak-{time.strftime('%Y%m%d%H%M%S')}")
        os.remove(config)
    else:
        save(config, result, exists)
    print(f"{'removed the arsenal hooks from' if options.remove else 'registered the arsenal hooks in'} {config}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
