---
max_turns: 30
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite, Write, Edit, Bash]
tags: [task, hard]
---

Add user deactivation: a deactivate_user service function and an API handler for it. It must set active to False, record deactivated_at, and refuse to deactivate the last active admin.
