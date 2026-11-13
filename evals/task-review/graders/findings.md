---
type: llm
---

PASS only if the review identifies ALL THREE of these: (1) SQL injection from building the query with the customer name in an f-string, (2) the N+1 query pattern (one items query per order inside the loop), (3) the refund function swallowing every exception and returning True regardless.
FAIL if any of the three is missing. Formatting and extra findings do not matter.
