"""Hidden acceptance tests for the service function; the API handler's name is free, so a judge grades it."""
import unittest

from app import repo, service


class DeactivateUser(unittest.TestCase):
    def setUp(self):
        repo._USERS.clear()

    def test_member_is_deactivated_and_stamped(self):
        service.create_user(1, "root", role="admin")
        service.create_user(2, "ann")
        service.deactivate_user(2)
        user = service.get_user(2)
        self.assertIs(user.active, False)
        self.assertIsNotNone(user.deactivated_at)

    def test_last_active_admin_is_refused(self):
        service.create_user(1, "root", role="admin")
        with self.assertRaises(Exception):
            service.deactivate_user(1)
        self.assertIs(service.get_user(1).active, True)

    def test_admin_can_go_while_another_active_admin_remains(self):
        service.create_user(1, "root", role="admin")
        service.create_user(2, "second", role="admin")
        service.deactivate_user(1)
        self.assertIs(service.get_user(1).active, False)

    def test_inactive_admins_do_not_count_as_remaining(self):
        service.create_user(1, "root", role="admin")
        service.create_user(2, "second", role="admin")
        service.deactivate_user(1)
        with self.assertRaises(Exception):
            service.deactivate_user(2)
        self.assertIs(service.get_user(2).active, True)

    def test_unknown_user_is_an_error(self):
        with self.assertRaises(Exception):
            service.deactivate_user(404)


if __name__ == "__main__":
    unittest.main()
