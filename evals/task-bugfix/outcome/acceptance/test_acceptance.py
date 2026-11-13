"""Hidden acceptance tests: the agent never sees this file."""
import unittest

from pricing import apply_discount, cart_total


def total_or_rejection(call):
    """The total, or None when the function refused the input with an exception."""
    try:
        return call()
    except Exception:
        return None


class DiscountNeverGoesNegative(unittest.TestCase):
    def test_coupon_above_100_percent(self):
        for percent in (100.5, 150, 1000):
            total = total_or_rejection(lambda: apply_discount(80, percent))
            self.assertTrue(total is None or total >= 0, (percent, total))

    def test_cart_total_with_the_reported_coupon(self):
        total = total_or_rejection(lambda: cart_total([30, 50], 150))
        self.assertTrue(total is None or total >= 0, total)

    def test_normal_discounts_are_unchanged(self):
        self.assertEqual(apply_discount(50, 20), 40)
        self.assertEqual(apply_discount(50, 0), 50)
        self.assertEqual(apply_discount(50, 100), 0)
        self.assertEqual(cart_total([10, 20]), 30)
        self.assertEqual(cart_total([10, 30], 25), 30)


if __name__ == "__main__":
    unittest.main()
