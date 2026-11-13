---
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite, Write, Edit, Bash]
tags: [task, hard]
---

Add an optional due date to tasks, end to end. Database: a new migration; existing databases already ran 001_init.sql and must keep their rows. API (server/api.py): create_task accepts an optional `due_date` (ISO date string such as 2026-01-31), create_task and list_tasks both return it as `due_date` (null when unset), and a `due_date` that is not a valid ISO date is a 400. Client (client/tasks_client.py): build_create_payload(title, due_date=None) sends it, and format_task appends ` (due 2026-01-31)` when the task has one.
