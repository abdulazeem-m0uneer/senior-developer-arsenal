# Production Agent Skill Template

Use this canonical template when generating new skills. It is the layout every skill in the arsenal follows.

---

````markdown
---
name: {{skill-name}}
description: '{{Third-person capability summary}}. Use when the user asks to {{situations}} or runs /{{skill-name}}. Triggers on: "{{phrase}}", "{{phrase}}", "/{{skill-name}}". Do not use for {{neighbouring task}} (use {{other-skill}}).'
---

# {{Skill Title}} Procedure

This skill guides the agent through {{one-sentence outcome}}.

---

## 1. When to Use This Skill

Activate this skill when:
- {{Scenario 1}}
- {{Scenario 2}}
- The user runs the `/{{skill-name}}` slash command.

*Boundary*: For {{neighbouring task}}, use `{{other-skill}}`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: {{Procedure One}}
1. {{Action 1}}
2. {{Action 2}}

### Step 2: {{Procedure Two}}
Consult: [{{Reference Title}}](./references/{{filename}}.md)
1. {{Action 1}}
2. {{Action 2}}

---

## 3. Verification Protocol

```bash
{{verification-command}}
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| {{area}} | {{finding}} | {{risk}} | `[Blocker]` | {{fix}} |

---

## 4. ⚡ Token-Saving Execution Rule

- **Targeted Output Only**: Output only modified code functions or configurations. Never output full unchanged files.
- **Dense Reporting**: Format findings in compact tables (`File:Line`, `Issue`, `Fix`).
- **No Conversational Fluff**: Omit generic intros and outros.
````

---

## Rules the Validator Enforces

| Rule | Detail |
| :--- | :--- |
| Frontmatter keys | Exactly `name` and `description`, each on one line. |
| `name` | Lowercase words joined by hyphens; equal to the folder name. |
| `description` | 1 to 1024 characters, single-quoted, no apostrophes. Order: summary, "Use when", "Triggers on", "Do not use for". |
| Links | Every link resolves and stays inside the skill folder. |
| Line endings | LF only. |
| Wording | Agent-neutral: no product names or product-specific tool names. |
| Scripts | Under `scripts/`, standard library only, covered by a test in `tests/`; SKILL.md says the path is relative to the directory that contains it. |
