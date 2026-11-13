---
max_turns: 6
allowed_tools: [Read, Glob, Grep, Skill]
tags: [trigger]
---

This Postgres query on a 40-million-row orders table takes 9 seconds: SELECT * FROM orders WHERE customer_id = 42 ORDER BY created_at DESC LIMIT 20. Design the right indexes.
