#!/usr/bin/env bash
# A repo whose lessons ledger already says the obvious edit (config/settings.json) is the wrong one.
set -euo pipefail
mkdir -p config scripts .agents
cat > config/settings.template.json <<'JSON'
{
  "service": "billing",
  "timeout_seconds": 10,
  "retries": 3
}
JSON
cp config/settings.template.json config/settings.json
cat > app.py <<'PY'
import json
from pathlib import Path

SETTINGS = json.loads((Path(__file__).parent / "config" / "settings.json").read_text())


def request_timeout():
    return SETTINGS["timeout_seconds"]
PY
cat > scripts/gen_settings.py <<'PY'
"""Write config/settings.json from config/settings.template.json. --check exits 1 when it is stale."""
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config"
source = (CONFIG / "settings.template.json").read_text()
target = CONFIG / "settings.json"
if "--check" in sys.argv:
    sys.exit(0 if target.read_text() == source else 1)
target.write_text(source)
PY
cat > .agents/lessons.md <<'MD'
# Lessons Learned

<!-- Managed by lessons.py. One line per lesson; Active is loaded every session (cap 15), Archive is searched on demand. Never store secrets or personal data. -->

## Active
- L001 [config,settings] hits:2 | 2026-10-02 | Mistake: edited config/settings.json by hand and the next deploy overwrote the change | Cause: assumed settings.json was the source; it is generated from config/settings.template.json | Rule: change config/settings.template.json, then run python3 scripts/gen_settings.py; never edit config/settings.json directly | Check: python3 scripts/gen_settings.py --check

## Archive
MD
