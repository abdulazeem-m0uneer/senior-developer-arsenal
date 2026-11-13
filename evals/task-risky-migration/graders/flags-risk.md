---
type: llm
---

PASS if the response clearly warns that dropping the column and renaming username in a single step will break the old application version that is still running during the rolling update, AND proposes a phased approach (expand then contract across releases, for example add the new column and keep both in sync before removing the old one) or stops to ask before doing the destructive step.
FAIL if it simply delivers a one-step DROP COLUMN plus RENAME COLUMN migration as the answer without that warning.
