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

---

## Rules for Scripts Under `scripts/`

An agent reads a script's stdout and stderr to decide its next step, in a shell with no terminal. Design for that reader.

| Rule | Reason |
| :--- | :--- |
| Never prompt; take every input from flags, environment, or stdin | An interactive prompt hangs the agent forever |
| `--help` prints purpose, flags, defaults, exit codes, and two examples in under 30 lines | It is the only interface documentation the agent will read |
| A missing required flag fails with the options listed (`--env is required. Options: dev, staging, prod`) | A bare "invalid input" wastes a turn |
| Data to stdout as JSON, CSV, or TSV; progress and warnings to stderr | The agent can parse stdout and pipe it; diagnostics stay out of the way |
| Idempotent by default: "create if missing", not "create and fail on duplicate" | Agents retry |
| Reject ambiguous input; closed sets as enums | A guess inside the script is invisible to the agent |
| `--dry-run` on anything stateful or destructive; `--confirm` or `--force` to execute | Previews before changes |
| Distinct exit codes per failure class (not found, bad arguments, auth, upstream), documented in `--help` | The agent branches on the code without parsing prose |
| Bounded output: summary by default, `--limit` and `--offset` for more, or `--output <file|->` when large | Harness truncation at 10–30k characters loses the decisive line |
| Pin versions in one-off commands (`npx tool@9.0.0`); state runtime prerequisites in SKILL.md | Same behaviour next month, no silent environment assumption |
| Move a command into a script once it is hard to get right first time | A tested script beats a long inline command |

The arsenal adds: standard library only, a test under `tests/`, and the SKILL.md path stated relative to the directory containing the skill.
