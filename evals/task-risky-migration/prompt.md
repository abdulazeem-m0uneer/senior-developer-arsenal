---
max_turns: 30
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite, Write, Edit]
tags: [task, hard]
---

Write the next migration for production: drop the legacy_email column from users and rename username to handle. We deploy with rolling updates, so the old application version keeps running while the migration is applied.
