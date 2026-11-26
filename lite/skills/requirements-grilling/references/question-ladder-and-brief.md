# Question Ladder, Design Brief & Builder Check

---

## 1. Round Format

```text
Q1 - <title>: <question; options only if they are stuck>
  -> recommended: <your answer, worded so "yes" accepts it>

Q2 - <title>: ...
  -> recommended: ...
```

- One idea per question; no compound questions; no list of example answers dangling off an open question.
- Plain language pitched slightly above the user; their vocabulary, no process jargon.
- The round ends when every frontier question is asked. The session ends when the frontier is empty and nothing is silently assumed.

---

## 2. Ground to Cover (territory, not a script)

| Area | What you need to know | Opening question that works |
| :--- | :--- | :--- |
| Kind of thing | What it is, what makes it special | `Walk me through the last time you needed this.` |
| Why now | The trigger; what success looks like to them | `What changes for you the day this works?` |
| Goals / non-goals / anti-goals | What must happen; what is out; what would make it a failure even if it technically works | `What would make you wince if I got it wrong?` |
| Prior art | What they have seen elsewhere, loved, hated | `What do you use today, and where does it hurt?` |
| Current state | What exists, what was tried | Look it up first; confirm, do not ask |
| How it gets made | Platform, language, libraries, resources: which choices are theirs, which are handed to you, what exists already | `Do you have views on the stack, or should I pick and state my defaults?` |
| Forced choice | Priority when goals conflict | `If it could only do one of these well, which?` |

A choice you make is written as your call, never as something they agreed to.

---

## 3. Fact Lookup Rule

| Question needs | Who answers | How |
| :--- | :--- | :--- |
| A value in the repository, manifest, config, schema, or `--help` | Agent | `grep`, `git show`, `code-explorer` subagent; keep asking the rest of the frontier meanwhile |
| A fact on the web (library behaviour, API limit) | Agent | Fetch; cite |
| A preference, priority, business rule, risk appetite | User | Ask; wait |
| Something only a third person knows | Neither | Park as open question with owner (`decision-log`), or draft a questionnaire for that person |

---

## 4. Offers That Save Rounds

- **Recon**: once grounded, offer to go look (codebase, their files, the web). Say what you would look for; they decide.
- **Spike**: a throwaway build is often the cheapest way to learn what they want. Spikes get no tests, no plan, no review; what the spike taught comes back into the conversation; keeping its code is a new request.
- **Show, do not tell**: a screen, layout, flow, or options that look different are easier to react to than to read about. Offer a mockup once, just in time; if declined, stay in text.

---

## 5. Design Brief Format

Location: `docs/specs/YYYY-MM-DD-<topic>-brief.md`, committed; the project guide's location wins.

```markdown
# <Topic> Design Brief

**Intent**: <what, for whom, why now>  (their words)
**Success**: <observable outcome>

## Goals / Non-goals / Anti-goals
- Goal: ...
- Non-goal: ...
- Anti-goal (failure even if it works): ...

## Constraints
<platform, stack, data, deadlines, compliance; exact values>

## Decided by the user
<each how-it-gets-made choice they made, as they made it>

## Agent's calls  (listed so they can be checked while reading)
- <choice>: <why>

## Left to the builder
<what a competent builder may decide without coming back>

## Open questions  (owner, what it blocks, working rule until answered)
```

A talented builder in the domain must be able to plan from it without going back to the user.

---

## 6. Builder Check Prompt

Dispatch a fresh general-purpose subagent with only this (fill domain and path):

```text
You are a talented <domain, e.g. backend engineer>. You have been handed a design brief
and must plan its build. You cannot talk to the author.

Read <BRIEF_PATH>.

Report only the questions you would still need answered before you could plan well:
places where you would have to guess and a wrong guess changes what gets built.
For each: the question, why the answer changes the plan. Rank by importance.
Skip what the brief leaves to the builder, anything you could reasonably decide
yourself, and wording nitpicks. If nothing important is left, say exactly:
"nothing important left".
```

Triage of its output: answered already (write the answer into the brief), minor (settle, mark as your call), theirs (one message to the user, most important first). Without a subagent tool, read the brief as that builder yourself.

---

## 7. Red Flags

| Thought | Reality |
| :--- | :--- |
| `I will offer options to save them effort` | Options steer. Get them describing first. |
| `I will fill in sensible defaults` | Fine, out loud. A default they never heard is one they could not reject. |
| `They said "sounds good" to the idea` | Approval covers what was shown. An unwritten brief is not approved. |
| `The spike works, I will keep building on it` | Keeping it is a new request. Back through the gate. |
| `I will ask about the stack` when `package.json` is right there | Facts are yours to find. |

Adapted from obra/superpowers (MIT) and mattpocock/skills (MIT).
