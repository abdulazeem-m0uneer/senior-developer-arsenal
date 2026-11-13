import unittest

from pricing import apply_discount


class ApplyDiscount(unittest.TestCase):
    def test_rejects_a_coupon_above_100_percent(self):
        with self.assertRaises(ValueError):
            apply_discount(80, 150)

    def test_normal_discount(self):
        self.assertEqual(apply_discount(50, 20), 40)


if __name__ == "__main__":
    unittest.main()
