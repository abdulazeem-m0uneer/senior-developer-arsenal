#!/usr/bin/env bash
set -euo pipefail
mkdir -p shop
cat > shop/__init__.py <<'PY'
PY
cat > shop/money.py <<'PY'
def to_cents(amount):
    """Convert a decimal amount such as 19.99 to integer cents."""
    return int(amount * 100)


def format_cents(cents):
    return f"{cents // 100}.{cents % 100:02d}"
PY
cat > shop/cart.py <<'PY'
from shop.money import to_cents


class Cart:
    def __init__(self):
        self.lines = []

    def add(self, name, unit_price, quantity=1):
        self.lines.append((name, to_cents(unit_price), quantity))

    def total_cents(self):
        return sum(cents * quantity for _, cents, quantity in self.lines)
PY
cat > shop/invoice.py <<'PY'
from shop.money import format_cents


def render(cart):
    rows = [f"{quantity} x {name}  {format_cents(cents * quantity)}" for name, cents, quantity in cart.lines]
    return "\n".join(rows + [f"Total: {format_cents(cart.total_cents())}"])
PY
