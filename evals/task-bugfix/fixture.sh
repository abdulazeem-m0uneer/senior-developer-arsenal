#!/usr/bin/env bash
set -euo pipefail
cat > pricing.py <<'PY'
def apply_discount(total, percent):
    """Return the total after a percentage discount."""
    return total - total * percent / 100


def cart_total(prices, percent=0):
    return apply_discount(sum(prices), percent)
PY
