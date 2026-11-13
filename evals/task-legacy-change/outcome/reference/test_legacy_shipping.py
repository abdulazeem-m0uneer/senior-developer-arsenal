import unittest

from legacy_shipping import fee


class Fee(unittest.TestCase):
    def test_orders_over_100_ship_free(self):
        self.assertEqual(fee({"total": 150, "country": "FR", "weight": 30, "express": True}), 0)

    def test_order_of_exactly_100_still_pays(self):
        self.assertEqual(fee({"total": 100, "country": "CA"}), 9)


if __name__ == "__main__":
    unittest.main()
