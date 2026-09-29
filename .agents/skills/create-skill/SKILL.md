---
name: create-skill
description: Workflow to interactively create, scaffold, and install a new token-efficient Antigravity skill.
---

# Create Skill Workflow

Follow this procedure to scaffold a new skill with the user.

## Steps

1. **Trigger Interview**:
   - Ask the user the 4 core skill questions: Name/Trigger, Workflow steps, Reference materials, and Destination (Project or Global).
   - Use `ask_question` or concise text prompts.

2. **Scaffold Directory & Files**:
   - Create `<destination>/skills/<skill-name>/` and `references/`.
   - Author `SKILL.md` using the canonical template with YAML frontmatter.
   - Author reference manuals in `references/<name>.md`.

3. **Inject Token Conservation Rule**:
   - Verify the generated skill includes Section 3: `⚡ Token-Saving Execution Rule`.

4. **Install & Verify**:
   - If installed in `senior-developer-arsenal`, run `git status` and `.\install.ps1 -Global`.
   - Confirm file existence in a single-line summary.
