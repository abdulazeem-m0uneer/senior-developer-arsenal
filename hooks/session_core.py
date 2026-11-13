#!/usr/bin/env python3
"""SessionStart hook: inject the arsenal operating core (hooks/core.md) as additionalContext.

A plugin cannot ship always-on rules, so without this a plugin-only install never tells the agent to
use the skills or to test its changes. The text is static (prompt-cache friendly) and capped.
Never fails the session: always exits 0.
"""
import json
import sys
from pathlib import Path

MAX_CHARS = 1500


def main():
    try:
        text = (Path(__file__).resolve().parent / "core.md").read_text(encoding="utf-8").strip()[:MAX_CHARS]
        if text:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    except Exception:  # a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
