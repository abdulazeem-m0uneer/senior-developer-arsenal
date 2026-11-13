---
type: regex
target: { source: file, path: tests/test_paging.py }
match: not_contains
---

@pytest\.mark\.(skip|xfail)|pytest\.(skip|xfail)\(|unittest\.skip|skipTest\(|\bxfail\b
