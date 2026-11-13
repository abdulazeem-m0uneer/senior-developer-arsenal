---
type: llm
---

PASS if the response says the cause is in shop/money.py: to_cents truncates the floating-point product (int of amount times 100) instead of rounding it, and that this, not the invoice rendering, was fixed.
FAIL if the response blames or patches only shop/invoice.py or shop/cart.py, or names no cause.
