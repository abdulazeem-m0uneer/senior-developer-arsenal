import unittest

from app import repo, service


class Deactivate(unittest.TestCase):
    def setUp(self):
        repo._USERS.clear()

    def test_last_active_admin_is_refused(self):
        service.create_user(1, "root", role="admin")
        with self.assertRaises(service.LastAdmin):
            service.deactivate_user(1)

    def test_member_is_deactivated(self):
        service.create_user(1, "root", role="admin")
        service.create_user(2, "ann")
        self.assertIs(service.deactivate_user(2).active, False)


if __name__ == "__main__":
    unittest.main()
