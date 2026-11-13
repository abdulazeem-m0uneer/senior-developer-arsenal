---
type: llm
focus: { source: file, path: legacy_shipping.py }
---

PASS if fee returns 0 for any order with total over 100, AND for totals of 100 or less every original branch still computes the same fee as before (US base 5, CA/MX base 9, other 20, the weight surcharges 7/11/25, and the express multipliers).
FAIL if orders over 100 can still be charged, or behaviour for totals of 100 or less changed.
