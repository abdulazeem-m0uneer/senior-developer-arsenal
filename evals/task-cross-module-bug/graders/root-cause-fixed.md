---
type: regex
target: { source: file, path: shop/money.py }
match: not_contains
---

int\(\s*amount\s*\*\s*100(\.0*)?\s*\)
