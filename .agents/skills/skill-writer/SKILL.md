---
name: skill-writer
description: Interactively interviews the user to architect, scaffold, and generate token-efficient Antigravity skills, runbooks, and reference manuals. Use when the user wants to create, customize, or package a new skill.
---

# Skill Writer (Interactive Meta-Skill)

This skill guides the agent in collaborating with the user to design and scaffold production-ready Antigravity skills adhering to progressive disclosure and strict token conservation.

---

## 1. Interactive Interview Procedure

When invoked, ask the user these 4 targeted questions (either directly or via `ask_question`):

1. **Identifier & Activation Trigger**:
   - What is the skill name (lowercase, hyphenated, e.g. `docker-compose-deployer`)?
   - What specific prompt or situation triggers this skill? (Must be written in third-person for the frontmatter description).
2. **Execution Steps & Runbook**:
   - What are the step-by-step procedures, commands, or patterns the agent must follow?
3. **Reference Manuals (Progressive Disclosure)**:
   - Does this skill need bulky documentation, schemas, or checklists? (These will be split into `references/<topic>.md` to save context tokens).
4. **Target Destination**:
   - Local project (`.agents/skills/<name>/`) or Global (`~/.gemini/config/skills/<name>/`)?

---

## 2. Scaffolding Standards

Consult the [Skill Template](./references/skill-template.md) and [Interview Guide](./references/interview-guide.md).

Every generated skill must contain:
1. **Frontmatter Block**:
   ```markdown
   ---
   name: <skill-name>
   description: <Actionable third-person description stating WHAT it does and WHEN to activate it>
   ---
   ```
2. **Concise Core Runbook**: Keep the primary `SKILL.md` under 60 lines.
3. **Progressive Reference Files**: Offload long checklists, configs, and examples to `references/`.
4. **Mandatory Token-Saving Execution Rule**: Always include a section enforcing surgical outputs, dense tables, and zero fluff.

---

## 3. ⚡ Token-Saving Execution Rule

- **Concise Interactive Prompts**: Keep interview questions brief and actionable.
- **Direct File Generation**: Write the files directly to the target location once answers are provided. Do not re-print the full generated files in chat text.
