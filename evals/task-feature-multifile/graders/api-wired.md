---
type: llm
focus: { source: file, path: app/api.py }
---

PASS if app/api.py has a handler for deactivation that calls the service and maps the unknown-user case and the last-admin refusal to distinct non-200 responses.
FAIL otherwise.
