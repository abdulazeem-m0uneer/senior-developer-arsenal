---
type: llm
---

PASS if the response asks the user specific clarifying questions (such as which endpoints, which stack or framework, freshness or invalidation needs) or clearly lists the assumptions it would need confirmed, and does NOT present a full implementation for a guessed stack.
FAIL if it writes a complete caching implementation for a stack it guessed, or gives only generic advice without asking what it needs.
