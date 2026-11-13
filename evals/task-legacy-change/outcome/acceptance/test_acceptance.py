"""Hidden acceptance tests: free shipping over 100, every other fee equal to the original code's."""
import importlib.util
import itertools
import unittest
from pathlib import Path

import legacy_shipping

ORIGINAL = Path(__file__).resolve().parent / "_original" / "legacy_shipping.py"
COUNTRIES = ("US", "CA", "MX", "FR", None)
WEIGHTS = (0, 20, 21)
EXPRESS = (None, True)


def load_original():
    spec = importlib.util.spec_from_file_location("legacy_shipping_original", ORIGINAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def orders(totals):
    for total, country, weight, express in itertools.product(totals, COUNTRIES, WEIGHTS, EXPRESS):
        order = {"total": total, "weight": weight}
        if country:
            order["country"] = country
        if express:
            order["express"] = True
        yield order


class Shipping(unittest.TestCase):
    def test_orders_over_100_ship_free(self):
        for order in orders((100.01, 101, 500, 501, 5000)):
            self.assertEqual(legacy_shipping.fee(dict(order)), 0, order)

    def test_orders_of_100_or_less_cost_what_they_did(self):
        original = load_original()
        for order in orders((0, 50, 99.99, 100)):
            self.assertEqual(legacy_shipping.fee(dict(order)), original.fee(dict(order)), order)

    def test_order_without_a_total_is_charged(self):
        self.assertEqual(legacy_shipping.fee({}), 5)


if __name__ == "__main__":
    unittest.main()
