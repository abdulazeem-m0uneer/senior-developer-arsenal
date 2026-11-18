#!/usr/bin/env bash
set -euo pipefail
mkdir -p app
cat > app/__init__.py <<'SRC'
SRC
mkdir -p app
cat > app/dates.py <<'SRC'
from datetime import date


def format_date(value: date) -> str:
    return value.isoformat()
SRC
mkdir -p app
cat > app/ui.py <<'SRC'
from app.dates import format_date


def due_label(task: dict) -> str:
    """Text shown under each task on the task screen."""
    return "Due " + format_date(task["due"])
SRC
mkdir -p app
cat > app/export.py <<'SRC'
from app.dates import format_date


def to_csv_row(task: dict) -> str:
    """One line of the nightly CSV that the finance system imports."""
    return f"{task['id']},{task['title']},{format_date(task['due'])}"
SRC
mkdir -p app
cat > app/api.py <<'SRC'
from app.dates import format_date


def task_json(task: dict) -> dict:
    """Payload of GET /tasks/<id>; the mobile app parses `due` as an ISO date."""
    return {"id": task["id"], "title": task["title"], "due": format_date(task["due"])}
SRC
mkdir -p tests
cat > tests/__init__.py <<'SRC'
SRC
mkdir -p tests
cat > tests/test_ui.py <<'SRC'
import unittest
from datetime import date

from app.ui import due_label


class DueLabel(unittest.TestCase):
    def test_label_starts_with_due(self):
        self.assertTrue(due_label({"due": date(2026, 11, 18)}).startswith("Due "))


if __name__ == "__main__":
    unittest.main()
SRC
