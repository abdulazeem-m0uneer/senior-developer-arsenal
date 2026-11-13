---
type: llm
focus: { source: file, path: paging.py }
---

PASS if page() now treats the page number as 1-based so that page 1 of size 10 returns the first 10 items (start index is (number - 1) * size).
FAIL otherwise.
