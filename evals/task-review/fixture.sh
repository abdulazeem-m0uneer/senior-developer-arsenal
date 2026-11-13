#!/usr/bin/env bash
set -euo pipefail
cat > orders.py <<'PY'
import sqlite3

db = sqlite3.connect("shop.db")


def orders_for_customer(customer_name):
    rows = db.execute(f"SELECT id, total FROM orders WHERE customer = '{customer_name}'").fetchall()
    result = []
    for order_id, total in rows:
        items = db.execute("SELECT sku, qty FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        result.append({"id": order_id, "total": total, "items": items})
    return result


def refund(order_id, amount):
    try:
        db.execute("UPDATE orders SET total = total - ? WHERE id = ?", (amount, order_id))
        db.commit()
    except Exception:
        pass
    return True
PY
