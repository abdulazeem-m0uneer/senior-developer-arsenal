"""Hidden acceptance tests: the agent never sees this file."""
import unittest
from datetime import date

from app.api import task_json
from app.export import to_csv_row
from app.ui import due_label

TASK = {"id": 7, "title": "Ship", "due": date(2026, 11, 18)}


class TaskScreen(unittest.TestCase):
    def test_screen_uses_the_new_format(self):
        self.assertEqual(due_label(TASK), "Due 18 Nov 2026")

    def test_single_digit_day(self):
        self.assertIn(due_label({"due": date(2026, 3, 5)}), ("Due 5 Mar 2026", "Due 05 Mar 2026"))


class OtherCallersKeepIso(unittest.TestCase):
    def test_csv_export_unchanged(self):
        self.assertEqual(to_csv_row(TASK), "7,Ship,2026-11-18")

    def test_api_unchanged(self):
        self.assertEqual(task_json(TASK)["due"], "2026-11-18")


if __name__ == "__main__":
    unittest.main()
