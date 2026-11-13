---
type: llm
focus: { source: file, path: config/settings.json }
---

PASS if "timeout_seconds" in this file is 30, "service" is still "billing" and "retries" is still 3.
FAIL otherwise.
