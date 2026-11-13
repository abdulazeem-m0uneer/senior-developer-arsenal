"""Hidden acceptance tests: database migration, API and client must agree on due_date."""
import unittest
from pathlib import Path

from client import tasks_client
from server import api, db

ORIGINAL_INIT = Path(__file__).resolve().parent / "_original" / "migrations" / "001_init.sql"
INIT = Path(db.__file__).resolve().parent.parent / "migrations" / "001_init.sql"


def fresh():
    conn = db.connect()
    db.migrate(conn)
    return conn


class Migration(unittest.TestCase):
    def test_first_migration_is_not_rewritten(self):
        self.assertEqual(INIT.read_text(encoding="utf-8"), ORIGINAL_INIT.read_text(encoding="utf-8"))

    def test_database_that_already_ran_the_first_migration_keeps_its_rows(self):
        conn = db.connect()
        conn.executescript(ORIGINAL_INIT.read_text(encoding="utf-8"))
        conn.execute("CREATE TABLE schema_migrations (name TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO schema_migrations (name) VALUES ('001_init.sql')")
        conn.execute("INSERT INTO tasks (title, done) VALUES ('old task', 1)")
        conn.commit()
        db.migrate(conn)
        status, tasks = api.list_tasks(conn)
        self.assertEqual(status, 200)
        self.assertEqual(tasks, [{"id": 1, "title": "old task", "done": True, "due_date": None}])

    def test_migrating_twice_is_harmless(self):
        conn = fresh()
        db.migrate(conn)
        self.assertEqual(api.list_tasks(conn), (200, []))


class Api(unittest.TestCase):
    def test_due_date_round_trips(self):
        conn = fresh()
        status, created = api.create_task(conn, {"title": "pay rent", "due_date": "2026-01-31"})
        self.assertEqual(status, 201)
        self.assertEqual(created["due_date"], "2026-01-31")
        self.assertEqual(api.list_tasks(conn)[1][0]["due_date"], "2026-01-31")

    def test_due_date_is_optional(self):
        conn = fresh()
        status, created = api.create_task(conn, {"title": "someday"})
        self.assertEqual(status, 201)
        self.assertIsNone(created["due_date"])
        self.assertEqual(created["title"], "someday")
        self.assertIs(created["done"], False)

    def test_invalid_due_date_is_rejected_and_not_stored(self):
        conn = fresh()
        for bad in ("tomorrow", "2026-13-45", "31/01/2026"):
            self.assertEqual(api.create_task(conn, {"title": "x", "due_date": bad})[0], 400, bad)
        self.assertEqual(api.list_tasks(conn), (200, []))

    def test_title_is_still_required(self):
        self.assertEqual(api.create_task(fresh(), {"due_date": "2026-01-31"})[0], 400)


class Client(unittest.TestCase):
    def test_payload_carries_the_due_date(self):
        self.assertEqual(tasks_client.build_create_payload("pay rent", "2026-01-31").get("due_date"), "2026-01-31")
        self.assertEqual(tasks_client.build_create_payload("someday")["title"], "someday")

    def test_client_payload_is_accepted_by_the_api(self):
        conn = fresh()
        status, created = api.create_task(conn, tasks_client.build_create_payload("pay rent", "2026-01-31"))
        self.assertEqual((status, created["due_date"]), (201, "2026-01-31"))
        self.assertEqual(api.create_task(conn, tasks_client.build_create_payload("someday"))[0], 201)

    def test_format_shows_the_due_date_only_when_set(self):
        task = {"id": 1, "title": "pay rent", "done": False, "due_date": "2026-01-31"}
        self.assertEqual(tasks_client.format_task(task), "[ ] pay rent (due 2026-01-31)")
        self.assertEqual(tasks_client.format_task({**task, "done": True, "due_date": None}), "[x] pay rent")


if __name__ == "__main__":
    unittest.main()
