"""Hidden acceptance tests: the agent never sees this file."""
import unittest

from shop.cart import Cart
from shop.invoice import render
from shop.money import to_cents


class CentsAreExact(unittest.TestCase):
    def test_amounts_that_truncate_as_floats(self):
        for amount, cents in ((19.99, 1999), (0.29, 29), (1.15, 115), (0.1, 10), (5, 500), (0, 0)):
            self.assertEqual(to_cents(amount), cents, amount)

    def test_the_reported_invoice(self):
        cart = Cart()
        cart.add("widget", 19.99)
        self.assertEqual(render(cart).splitlines()[-1], "Total: 19.99")

    def test_quantities_multiply_exact_cents(self):
        cart = Cart()
        cart.add("bolt", 0.29, 3)
        self.assertEqual(cart.total_cents(), 87)
        self.assertEqual(render(cart).splitlines()[-1], "Total: 0.87")


if __name__ == "__main__":
    unittest.main()
