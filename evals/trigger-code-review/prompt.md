---
max_turns: 6
allowed_tools: [Read, Glob, Grep, Skill]
tags: [trigger]
---

Review this diff before I merge:

```diff
- if user.role == 'admin':
+ if user.role in ('admin', 'staff') or user.id == 1:
      delete_account(target)
```
