#!/usr/bin/env bash
set -euo pipefail
mkdir -p server client migrations
cat > server/__init__.py <<'PY'
PY
cat > client/__init__.py <<'PY'
PY
cat > migrations/001_init.sql <<'SQL'
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);
SQL
cat > server/db.py <<'PY'
import sqlite3
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def connect(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def migrate(conn):
    """Apply every migrations/*.sql file that has not been applied yet, in name order."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
    applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}
    for script in sorted(MIGRATIONS.glob("*.sql")):
        if script.name in applied:
            continue
        conn.executescript(script.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations (name) VALUES (?)", (script.name,))
    conn.commit()
PY
cat > server/api.py <<'PY'
def _to_dict(row):
    return {"id": row["id"], "title": row["title"], "done": bool(row["done"])}


def create_task(conn, payload):
    title = (payload.get("title") or "").strip()
    if not title:
        return 400, {"error": "title is required"}
    cursor = conn.execute("INSERT INTO tasks (title) VALUES (?)", (title,))
    conn.commit()
    row = conn.execute("SELECT id, title, done FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return 201, _to_dict(row)


def list_tasks(conn):
    rows = conn.execute("SELECT id, title, done FROM tasks ORDER BY id").fetchall()
    return 200, [_to_dict(row) for row in rows]
PY
cat > client/tasks_client.py <<'PY'
def build_create_payload(title):
    return {"title": title}


def format_task(task):
    mark = "x" if task["done"] else " "
    return f"[{mark}] {task['title']}"
PY
