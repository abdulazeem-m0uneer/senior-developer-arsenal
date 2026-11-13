---
type: llm
focus: { source: file, path: pricing.py }
---

PASS if apply_discount can no longer return a negative total for a percent above 100, AND an out-of-range percent (above 100 or below 0) is handled deliberately (clamped or rejected with an error), AND a normal discount such as 20 percent off 50 still gives 40.
FAIL if a percent above 100 can still produce a negative total, or normal discounts are broken.
