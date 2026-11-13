---
max_turns: 6
allowed_tools: [Read, Glob, Grep, Skill]
tags: [trigger]
---

We are adding a public file-upload endpoint that forwards files to an internal virus scanner and then stores them in S3. Before we build it, work out what an attacker could do to this design.
