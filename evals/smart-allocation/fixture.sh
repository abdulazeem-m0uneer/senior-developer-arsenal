#!/usr/bin/env bash
set -euo pipefail
mkdir -p billing
cat > billing/__init__.py <<'SRC'
SRC
mkdir -p billing
cat > billing/allocate.py <<'SRC'
def allocate(total_cents, weights):
    """Split an amount in cents across accounts in proportion to their weights."""
    weight_sum = sum(weights)
    return [round(total_cents * w / weight_sum) for w in weights]
SRC
mkdir -p tests
cat > tests/__init__.py <<'SRC'
SRC
mkdir -p tests
cat > tests/test_allocate.py <<'SRC'
import unittest

from billing.allocate import allocate


class Allocate(unittest.TestCase):
    def test_even_split(self):
        self.assertEqual(allocate(900, [1, 1, 1]), [300, 300, 300])


if __name__ == "__main__":
    unittest.main()
SRC
