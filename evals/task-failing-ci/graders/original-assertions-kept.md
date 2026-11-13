---
type: regex
target: { source: file, path: tests/test_paging.py }
flags: s
---

^(?=.*assert\s+page\(ITEMS,\s*1,\s*10\)\s*==\s*list\(range\(0,\s*10\)\))(?=.*assert\s+page\(ITEMS,\s*2,\s*10\)\s*==\s*list\(range\(10,\s*20\)\))(?=.*assert\s+page\(ITEMS,\s*3,\s*10\)\s*==\s*\[20,\s*21,\s*22,\s*23,\s*24\])
