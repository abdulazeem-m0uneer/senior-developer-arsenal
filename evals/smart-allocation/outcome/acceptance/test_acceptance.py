"""Hidden acceptance tests: the agent never sees this file."""
import unittest
from fractions import Fraction

from billing.allocate import allocate

CASES = [
    (100, [1, 1, 1]), (1000, [1, 1, 1]), (1, [1, 1, 1]), (2, [1, 1, 1]), (10, [1] * 7),
    (101, [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]), (999, [3, 3, 3, 1]), (7, [1, 2, 4]),
    (0, [5, 1]), (12345, [17]), (50, [0, 1, 1]), (1000003, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]),
]


class AllocationIsFair(unittest.TestCase):
    def test_parts_add_up(self):
        for total, weights in CASES:
            self.assertEqual(sum(allocate(total, weights)), total, (total, weights))

    def test_every_part_is_within_one_cent_of_its_exact_share(self):
        for total, weights in CASES:
            parts = allocate(total, weights)
            for part, w in zip(parts, weights):
                exact = Fraction(total * w, sum(weights))
                self.assertLess(abs(part - exact), 1, (total, weights, parts))

    def test_zero_weight_gets_nothing(self):
        self.assertEqual(allocate(50, [0, 1, 1])[0], 0)

    def test_parts_are_whole_cents(self):
        for total, weights in CASES:
            self.assertTrue(all(isinstance(p, int) for p in allocate(total, weights)))


if __name__ == "__main__":
    unittest.main()
