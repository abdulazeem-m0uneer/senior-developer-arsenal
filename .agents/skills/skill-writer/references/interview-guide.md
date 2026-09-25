# Skill Interview Guide & Prompting Strategy

Guidelines for conducting a lean, token-efficient interview when designing a new skill.

---

## 1. The 4-Question Framework

When gathering requirements from the user, avoid long open-ended chats. Ask these exact structured questions:

| Phase | Question | Output Needed |
| :--- | :--- | :--- |
| **1. Identity** | "What is the skill name and exact trigger phrase?" | `name` (kebab-case) and `description` (3rd person) |
| **2. Workflow** | "What are the 2-4 main steps the agent must execute?" | Numbered action items & tools to use |
| **3. Deep Dives** | "Are there large checklists, cheat sheets, or configs to offload?" | Files to create inside `references/` |
| **4. Target** | "Where should this be saved: Workspace (`.agents/skills/`) or Global (`~/.gemini/config/skills/`)?" | File system destination |

---

## 2. Progressive Disclosure Rules

1. **Keep `SKILL.md` under 60 lines**: Only include high-level instructions and tool invocation triggers.
2. **Move Bulk to `references/`**: Move large syntax cheat sheets, JSON schemas, and lengthy checklists to `references/` files. The agent will read them on-demand using relative links without blowing up the initial context window.
3. **Always Embed the ⚡ Token Rule**: Every generated skill must enforce token conservation on the executing agent.
