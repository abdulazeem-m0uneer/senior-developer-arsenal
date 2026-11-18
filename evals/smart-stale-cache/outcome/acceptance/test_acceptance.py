"""Hidden acceptance tests: the agent never sees this file."""
import unittest

from users import repo, service
from users.cache import display_name
from web.header import header


class HeaderFollowsRenames(unittest.TestCase):
    def test_header_shows_the_new_name(self):
        service.rename(1, "Ada")
        self.assertEqual(header(1), "Signed in as Ada")
        service.rename(1, "Ada Lovelace")
        self.assertEqual(header(1), "Signed in as Ada Lovelace")

    def test_other_users_unaffected(self):
        service.rename(2, "Grace")
        service.rename(3, "Linus")
        header(2)
        service.rename(3, "Linus T")
        self.assertEqual(header(2), "Signed in as Grace")
        self.assertEqual(header(3), "Signed in as Linus T")

    def test_cache_still_spares_the_database(self):
        service.rename(4, "Alan")
        header(4)
        before = repo.READS["count"]
        for _ in range(50):
            header(4)
        self.assertEqual(repo.READS["count"], before)

    def test_empty_name_still_rejected(self):
        with self.assertRaises(ValueError):
            service.rename(5, "  ")


if __name__ == "__main__":
    unittest.main()
