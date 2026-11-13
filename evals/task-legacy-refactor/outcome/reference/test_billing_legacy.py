import unittest

from billing_legacy import inv


class Characterization(unittest.TestCase):
    def test_pins_current_results(self):
        self.assertEqual(inv({}, [{"price": 10}]), 10)
        self.assertEqual(inv({"country": "GB"}, [{"price": 30, "qty": 4, "fragile": True}]), 147.6)
        self.assertEqual(inv({"tier": "gold", "country": "DE"}, [{"price": 215}], "VIP"), 226.1)
        self.assertEqual(inv({}, [{"price": 7.5, "qty": 11, "type": "svc"}]), 74.25)
        self.assertEqual(inv({}, [{"price": 5}], "VIP"), 0)


if __name__ == "__main__":
    unittest.main()
