import datetime

COLUMNS = "id, title, done, due_date"


def _to_dict(row):
    return {"id": row["id"], "title": row["title"], "done": bool(row["done"]), "due_date": row["due_date"]}


def _valid_date(value):
    try:
        datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return len(value) == 10


def create_task(conn, payload):
    title = (payload.get("title") or "").strip()
    if not title:
        return 400, {"error": "title is required"}
    due_date = payload.get("due_date")
    if due_date is not None and not _valid_date(due_date):
        return 400, {"error": "due_date must be an ISO date (YYYY-MM-DD)"}
    cursor = conn.execute("INSERT INTO tasks (title, due_date) VALUES (?, ?)", (title, due_date))
    conn.commit()
    row = conn.execute(f"SELECT {COLUMNS} FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return 201, _to_dict(row)


def list_tasks(conn):
    rows = conn.execute(f"SELECT {COLUMNS} FROM tasks ORDER BY id").fetchall()
    return 200, [_to_dict(row) for row in rows]
