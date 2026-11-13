import unittest

from client.tasks_client import format_task
from server import api, db


class DueDate(unittest.TestCase):
    def test_api_returns_the_due_date_it_was_given(self):
        conn = db.connect()
        db.migrate(conn)
        status, created = api.create_task(conn, {"title": "pay rent", "due_date": "2026-01-31"})
        self.assertEqual((status, created["due_date"]), (201, "2026-01-31"))

    def test_client_shows_the_due_date(self):
        task = {"id": 1, "title": "pay rent", "done": False, "due_date": "2026-01-31"}
        self.assertEqual(format_task(task), "[ ] pay rent (due 2026-01-31)")


if __name__ == "__main__":
    unittest.main()
