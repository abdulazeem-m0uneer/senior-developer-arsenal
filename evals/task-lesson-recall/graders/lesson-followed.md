---
type: llm
focus: { source: file, path: config/settings.template.json }
---

This file is the source that config/settings.json is generated from. A recorded lesson in the repository says to change this file, not the generated one.
PASS if "timeout_seconds" in this file is 30.
FAIL if it is still 10 or any other value, or the key is missing.
