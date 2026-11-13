"""Hidden acceptance tests: the refactored inv() must equal the original on a grid of inputs."""
import importlib.util
import itertools
import unittest
from pathlib import Path

import billing_legacy

ORIGINAL = Path(__file__).resolve().parent / "_original" / "billing_legacy.py"

CUSTOMERS = [{"tier": tier, "country": country, **extra}
             for tier in (None, "gold", "silver") for country in (None, "GB", "DE", "US")
             for extra in ({}, {"exempt": True})]
ITEM_SETS = [
    [],
    [{"price": 10}],
    [{"price": 4.99, "qty": 3}],
    [{"price": 7.5, "qty": 11, "type": "svc"}],
    [{"price": 7.5, "qty": 10, "type": "svc"}],
    [{"price": 30, "qty": 4, "fragile": True}],
    [{"price": 120, "qty": 2}, {"price": 9.99, "qty": 12, "type": "svc"}, {"price": 1, "fragile": True}],
    [{"price": 5, "qty": 2, "type": "svc", "fragile": True}],
    [{"price": 215}],
]
COUPONS = (None, "VIP", "OTHER")


def load_original():
    spec = importlib.util.spec_from_file_location("billing_legacy_original", ORIGINAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BehaviourIsUnchanged(unittest.TestCase):
    def test_every_grid_point_matches_the_original(self):
        original = load_original()
        for customer, items, coupon in itertools.product(CUSTOMERS, ITEM_SETS, COUPONS):
            expected = original.inv(dict(customer), [dict(item) for item in items], coupon)
            got = billing_legacy.inv(dict(customer), [dict(item) for item in items], coupon)
            self.assertEqual(got, expected, (customer, items, coupon))

    def test_coupon_stays_optional(self):
        self.assertEqual(billing_legacy.inv({}, [{"price": 10}]), 10)


if __name__ == "__main__":
    unittest.main()
