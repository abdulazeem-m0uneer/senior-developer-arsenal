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
2. Author `SKILL.md` with standard YAML frontmatter (`name`, `description` with third-person summary, explicit triggers, and negative triggers) and the four numbered sections of the template. Wrap `description` in single quotes: it contains `: `, which is invalid in an unquoted YAML scalar.
3. Extract bulky manuals and checklists into `references/<name>.md`.
4. Draft the body against [Skill Writing Guide](./references/skill-writing-guide.md): content extracted from a real task or project artifacts, only what the agent lacks, one default per choice, prescriptive only where the operation is fragile, the reason instead of capitalised prohibitions, gotchas inline, every reference pointer stating when to read it, every step ending on a checkable completion criterion.
5. Run the pruning pass in that guide before validating: one home per meaning, no restated environment facts, no no-op sentences.

### Step 3: Enforce Token-Saving Guardrail
Mandate Section 4: `⚡ Token-Saving Execution Rule` in the generated `SKILL.md` to prevent conversational fluff and require surgical diffs.

### Step 4: Prove It Triggers and Helps
Consult: [Skill Eval Loop](./references/skill-eval-loop.md)
1. Trigger: about 20 labelled queries (near-miss negatives), three runs each, 60/40 train/validation split, revise the description on train failures, keep the best validation iteration.
2. Output: 2–3 realistic cases in `evals/evals.json`, each run with and without the skill from a clean context; assertions after the first outputs; grade with quoted evidence; keep the delta in tokens and pass rate.
3. Skip output evals for subjective deliverables (voice, style); keep trigger evals for every skill.

---

## 3. Verification Protocol

1. Verify folder name exactly matches frontmatter `name`.
2. Verify `description` specifies third-person capabilities, trigger conditions, and negative boundaries.
3. If authored inside the arsenal repository, execute:
   ```bash
   python3 scripts/build.py --validate && python3 scripts/build.py
   ```
4. Reinstall for the agents in use (`./install.sh --global --target all` or `.\install.ps1 -Global -Target all`) and confirm the skill is discovered.
5. Add the skill to the indexes that are kept by hand: the README skill list and command table, and the quick reference in `AGENTS.md`.

---

## 4. ⚡ Token-Saving Execution Rule

- Conduct interview in a single batch.
- Output created files with direct file links; never re-print the generated files into the chat.
