---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite, Write, Edit, Bash]
tags: [task, lessons]
---

Requests to the billing service time out too early. Raise the request timeout to 30 seconds; app.py reads it from config/settings.json.
