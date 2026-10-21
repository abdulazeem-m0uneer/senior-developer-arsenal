# Documentation Templates

Type chooser, README, runbook, and API reference entry templates. Delete a section that would be empty; do not pad it.

---

## 1. Choose the Type by the Reader's Need

| Type | Reader says | Shape | Must have | Must not have |
| :--- | :--- | :--- | :--- | :--- |
| Tutorial | "I am new; show me it working" | One linear path to a visible result | Every step, exact commands, the expected result after each | Options, alternatives, design discussion |
| How-to | "I need to do X" | Numbered steps to one goal | Prerequisites, the goal in the title, verification at the end | Teaching of basics, exhaustive options |
| Reference | "What exactly does Y accept or return?" | Tables and entries, uniform structure | Completeness, accuracy, consistent order | Narrative, opinion, steps |
| Explanation | "Why is it this way?" | Prose with diagrams | Context, trade-offs, alternatives rejected, links to decisions | Instructions |
| Discovery questionnaire | "One person holds what we need to decide" | Themed questions, most important first, answer stubs; see [questionnaire-template.md](./questionnaire-template.md) | Purpose, recipient, how answers are used, deadline | Compound questions, questions the agent could look up |

---

## 2. README

````markdown
# <Project name>

<One sentence: what it is and who it is for. One more: what it is not.>

## Prerequisites
- <Runtime> <exact version or range>, <package manager> <version>
- <Services needed locally: database, cache> and how to start them

## Quick start
```bash
<clone>
<install from the lockfile>
<copy the example environment file>
<run>
<lint> && <typecheck> && <test>
```
Expected: `<the line that proves it started>`, <URL> answers, and the checks pass.

## Configuration
| Variable | Required | Default | Meaning |
| :--- | :---: | :--- | :--- |
| `<NAME>` | yes | none | <what it controls, valid values> |

## Documentation
- Architecture: `docs/architecture.md`; runbooks: `docs/runbooks/`; API reference: `docs/api/`

## Contributing and licence
<Branching, commit convention, what must pass before review; link to CONTRIBUTING.md. SPDX licence identifier.>
````

Node.js, .NET, and Python projects differ only in the commands: `npm ci && npm run dev`, `dotnet restore && dotnet run --project src/Api`, `uv sync && uv run python -m app`.

---

## 3. Runbook

````markdown
# Runbook: <symptom or task, as the alert or the operator words it>

Owner: <team>        Last verified: <date, by running it>        Applies to: <service, environment>

## When to use
<The alert name or the observable symptom. When NOT to use it, and which runbook to use instead.>

## Before you start
- Access needed: <role, tool, network>
- Safe to run during traffic: yes | no
- Stop and escalate to <contact> if: <conditions>

## Steps

### 1. <Imperative title>
- Precondition: <what must be true; how to check it>
- Command:
  ```bash
  <exact command, copy-paste ready, placeholders in <angle brackets>>
  ```
- Expected output: `<the line or value that means success>`
- If it differs: <the specific next action: go to step N, run X, escalate>
- Rollback: <exact command that undoes this step, or "none needed: read-only">

## Verify
<The check that proves the symptom is gone, with expected output.>
<Then: what to record, whom to tell, which follow-up to file.>
````

Rules: one action per step; no "check that everything looks fine"; destructive commands are marked and preceded by the command that shows what they will affect; every runbook is re-run on a schedule and its "Last verified" date updated.

---

## 4. API Reference Entry

Written in the same change as the endpoint. Schemas and status codes come from the OpenAPI source; the rest is hand-written.

```markdown
## <METHOD> <path template>

**Summary**: <under 80 characters, verb first>

### What it does
<Two or three sentences on the effect, including side effects: records created, messages sent, money moved.>

### Why it is designed this way
<The reasoning, from a decision record or specification, with a link. Why this shape and not the obvious alternative. Never a guess: if unknown, ask and note the open question.>

### Who calls it
<Which client or service, in which user flow, with which role or scope.>

### How to call it
- Auth: <scheme, required scope>
- Idempotency: <key header and retention, or "safe to retry", or "not idempotent">
- Request: <fields with type, constraints, example>
- Response: <status, fields, example>

<A runnable example: one curl command and its real response, trimmed.>

### Errors
| Status | Code | Cause | What the caller should do |
| :--- | :--- | :--- | :--- |
| 409 | `order_already_paid` | A payment for this order was already captured | Fetch the order; do not retry |
| 422 | `amount_below_minimum` | Amount is under the configured minimum | Correct the input |

### Rules it enforces
- <Each business rule in one line, with a link to the specification or decision that defines it.>

### Code
- Handler: `<path>`; rules: `<path>`; tests: `<path>`
```

An entry is refused when it holds placeholder text, a "why" that only restates the "what", a code path that does not exist, an error the endpoint never raises, or a rule no specification defines.
