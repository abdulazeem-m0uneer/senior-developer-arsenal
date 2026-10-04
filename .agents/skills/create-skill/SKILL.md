---
name: create-skill
description: 'Interactive meta-skill to architect, interview, scaffold, and install token-efficient agent skills following the Agent Skills standard (agentskills.io). Use when the user wants to create, scaffold, or customize a new skill, or runs /create-skill. Triggers on: "create skill", "new skill", "author skill", "/create-skill". Do not use for ADR authoring (use architecture-design-adr).'
---

# Skill Authoring & Scaffolding Procedure

Use this interactive skill to interview the user and generate a new production-grade, token-efficient agent skill adhering to the modern Agent Skills standard.

---

## 1. When to Use This Skill

Activate this skill when:
- Creating a new procedural skill or runbook for a specialized domain or proprietary internal tool.
- Packaging multi-step engineering checklists into progressive disclosure directories.
- The user runs the `/create-skill` slash command or asks to create a new skill.

*Boundary*: For architectural decision records and technology trade-offs, use `architecture-design-adr`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Run the 4-Question Structured Interview
Consult: [Interview Guide](./references/interview-guide.md)
Present all 4 core questions in a single round to minimize back-and-forth token consumption:
1. **Trigger & Scope**: What is the skill name, purpose, and exact triggers (e.g., slash command, prompt keywords)?
2. **Step-by-Step Runbook**: What concrete steps, commands, or tools does the agent execute?
3. **References & Progressive Disclosure**: What heavy documentation, checklists, or schemas should be extracted into `references/`?
4. **Scope & Destination**: Should this skill be installed globally (`~/.agents/skills/`, or the agent-specific global directory) or per-project (`.agents/skills/`)?

### Step 2: Scaffold Directory & Canonical Files
Consult: [Skill Template](./references/skill-template.md)
1. Create directory structure:
   ```text
   skills/<skill-name>/
   ├── SKILL.md
   └── references/
   ```
2. Author `SKILL.md` with standard YAML frontmatter (`name`, `description` with third-person summary, explicit triggers, and negative triggers). Wrap `description` in single quotes: it contains `: `, which is invalid in an unquoted YAML scalar.
3. Extract bulky manuals and checklists into `references/<name>.md`.

### Step 3: Enforce Token-Saving Guardrail
Mandate Section 4: `⚡ Token-Saving Execution Rule` in the generated `SKILL.md` to prevent conversational fluff and require surgical diffs.

---

## 3. Verification Protocol

1. Verify folder name exactly matches frontmatter `name`.
2. Verify `description` specifies third-person capabilities, trigger conditions, and negative boundaries.
3. If authored inside the arsenal repository, execute:
   ```bash
   python3 scripts/build.py --validate && python3 scripts/build.py
   ```
4. Reinstall for the agents in use (`./install.sh --global --target all` or `.\install.ps1 -Global -Target all`) and confirm the skill is discovered.

---

## 4. ⚡ Token-Saving Execution Rule

- Conduct interview in a single batch.
- Output created files with direct file links; never re-print the generated files into the chat.
