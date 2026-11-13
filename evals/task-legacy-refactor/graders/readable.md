---
type: llm
focus: { source: file, path: billing_legacy.py }
---

PASS if inv delegates to several helper functions whose names say what they compute (for example a line subtotal, the coupon, the loyalty discount, tax) and the one-letter variable names are gone from the main logic.
FAIL if the function is only reformatted or renamed with its logic still in one block.
