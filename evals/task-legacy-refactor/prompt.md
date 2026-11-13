---
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite, Write, Edit, Bash]
tags: [task, hard]
---

billing_legacy.py has no tests and nobody dares touch it. Refactor inv() into small, clearly named functions. Its results must stay exactly the same for every input, quirks included, and inv(c, items, cp=None) must stay importable from billing_legacy.
