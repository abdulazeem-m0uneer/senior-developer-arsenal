# Production Antigravity Skill Template

Use this canonical template when generating new skills.

---

```markdown
---
name: {{skill-name}}
description: {{concise third-person description stating WHAT it does and WHEN to activate it}}
---

# {{Skill Title}}

Provide a 1-2 sentence overview of the skill purpose here.

---

## 1. When to Use This Skill

Activate this skill when:
- {{Scenario 1}}
- {{Scenario 2}}

---

## 2. Core Execution Procedures

### Step 1: {{Procedure One}}
1. {{Action 1}}
2. {{Action 2}}

### Step 2: {{Procedure Two}}
Refer to the deep-dive: [{{Reference Title}}](./references/{{filename}}.md)
1. {{Action 1}}
2. {{Action 2}}

### Step 3: Verification & Diagnostics
```bash
{{verification-command}}
```

---

## 3. ⚡ Token-Saving Execution Rule

- **Targeted Output Only**: Output only modified code functions or configurations. Never output full unchanged files.
- **Dense Reporting**: Format findings in compact tables (`File:Line`, `Issue`, `Fix`).
- **No Conversational Fluff**: Omit generic intros and outros.
```
