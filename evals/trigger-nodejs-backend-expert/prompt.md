---
max_turns: 6
allowed_tools: [Read, Glob, Grep, Skill]
tags: [trigger]
---

Our Fastify service blocks the event loop when it parses large uploads. Fix the design.
