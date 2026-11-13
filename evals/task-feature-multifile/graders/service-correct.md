---
type: llm
focus: { source: file, path: app/service.py }
---

PASS if app/service.py has a deactivate function that sets active to False, records a deactivation timestamp, raises or returns a distinct error for an unknown user, AND refuses to deactivate a user who is the last ACTIVE admin (inactive admins must not count as remaining admins).
FAIL if any of those is missing, or if the last-admin check counts inactive admins.
