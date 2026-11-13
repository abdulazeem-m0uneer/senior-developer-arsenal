---
max_turns: 6
allowed_tools: [Read, Glob, Grep, Skill]
tags: [trigger]
---

Our ASP.NET Core endpoint calls .Result on an HttpClient task and threads are starving under load. Refactor it properly.
