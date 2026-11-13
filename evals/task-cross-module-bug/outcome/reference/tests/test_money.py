import unittest

from shop.money import to_cents


class ToCents(unittest.TestCase):
    def test_does_not_lose_a_cent_to_float_truncation(self):
        self.assertEqual(to_cents(19.99), 1999)


if __name__ == "__main__":
    unittest.main()
