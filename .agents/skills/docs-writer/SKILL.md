---
name: docs-writer
description: 'Technical documentation runbook: pick the document type by reader need, write READMEs, runbooks a tired person can follow, and API reference entries stating what, why, who, how, errors and rules in the same change as the endpoint, keep one home per fact, and check docs in CI. Use when the user asks to write or fix a README, runbook or API reference, or runs /docs-writer. Triggers on: "write docs", "create a README", "write a runbook", "API reference", "/docs-writer". Do not use for endpoint contract design (use api-design) or decision records (use architecture-design-adr or decision-log).'
---

# Technical Documentation Procedure

This skill guides the agent through writing and maintaining documentation that a specific reader can act on, that states each fact in one place, and that CI keeps true.

---

## 1. When to Use This Skill

Activate this skill when:
- Writing or repairing a README, tutorial, how-to guide, runbook, or explanation page.
- Adding or changing an endpoint, command, or configuration key that needs a reference entry.
- Documents contradict each other, repeat each other, or describe behaviour the code no longer has.
- Adding documentation checks to CI: links, generated spec drift, examples that run.
- The user runs the `/docs-writer` slash command.

*Boundary*: For designing the endpoint contract itself, use `api-design`. For recording why a decision was taken, use `architecture-design-adr` or `decision-log`. For incident write-ups, use `incident-response`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Name the Reader and the Type
1. State who reads this and what they must be able to do afterwards; a page without a reader has no test for done.
2. Pick exactly one type: tutorial (learning by doing, one guaranteed path), how-to (a goal for someone who already knows the basics), reference (complete, dry facts for lookup), explanation (why it is this way).
3. Do not mix types on one page: a tutorial that stops to explain design loses the learner; a reference with narrative cannot be scanned. Split and link.
4. Find the existing home of each fact before writing; extend that page instead of creating a second one.

### Step 2: Write From the Source of Truth
Consult: [Documentation Templates](./references/templates.md)
1. Read the code, configuration, and tests first; every command, flag, path, and default is copied from what was run or read, never recalled.
2. README essentials in order: what it is and for whom, prerequisites with versions, install, run, test, configuration, where the rest of the docs live, how to contribute.
3. A runbook step has five parts: precondition, exact command, expected output, what to do if it differs, rollback. Write it for a tired person at night: no judgement calls, no "as appropriate".
4. Run every command and example before publishing; paste real output, trimmed.

### Step 3: API Reference in the Same Change
1. One entry per endpoint, written in the same change as the endpoint; an endpoint without an entry is not finished.
2. Each entry states: what it does, why it is designed this way, who calls it, how to call it (request, response, runnable example), each error with its cause and the caller's remedy, the business rules it enforces, and where the code lives.
3. Never guess the "why". Take it from a decision record, a specification, or the author; if none exists, ask, and record the open question instead of inventing a rationale.
4. Generate what can be generated (schemas, status codes) from the OpenAPI source; hand-write only purpose, reasoning, and rules.

### Step 4: One Home per Fact
1. Each fact (a port, a limit, a command, a rule) lives in one document; every other mention is a link to it.
2. When behaviour changes, search the docs for the old statement and correct every page that makes it, in the same change.
3. Delete what is obsolete; a dated "deprecated" banner is acceptable only with a removal date and a link to the replacement.

### Step 5: Edit for Plain Words, Then Gate in CI
Consult: [Documentation Review Checklist](./references/review-checklist.md)
1. Active voice, present tense, second person for instructions; one idea per sentence; the action before the reason.
2. Define each term once and use the same word for the same thing throughout; expand an abbreviation on first use.
3. Add CI checks: links resolve, the generated spec matches the committed one, examples execute, placeholders such as TODO fail the build.

---

## 3. Verification Protocol

```bash
npx markdownlint-cli2 "**/*.md" "#node_modules"              # structure and style
lychee --no-progress "**/*.md"                               # dead links, internal and external
npx @redocly/cli lint openapi.yaml                           # the spec is valid OpenAPI
<generate-spec command> && git diff --exit-code openapi.yaml # committed spec equals generated spec
python -m doctest -v docs/usage.md                           # Python examples run (Node.js and .NET: compile the samples in CI)
grep -rnE '\b(TODO|TBD|FIXME|lorem)\b' docs README.md        # must print nothing
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| API reference | New endpoint has no entry, or its "why" is invented | Callers misuse it; a false rationale outlives the code | `[Blocker]` | Write the entry in this change from the decision record |
| Runbook | Step has no expected output or failure branch | Operator cannot tell success from failure | `[Blocker]` | Add expected output, the "if it differs" action, rollback |
| Accuracy | README command fails on a clean checkout | First-run failure, lost trust | `[Blocker]` | Run from a clean clone, correct, add to CI |
| Structure | Same limit stated in three pages with two values | Readers act on the wrong one | `[Architecture]` | Keep one home, replace the others with links |
| Security | Real token or internal host name in an example | Credential or topology leak | `[Security]` | Replace with placeholders, rotate the token |

---

## 4. ⚡ Token-Saving Execution Rule

- **Link, Do Not Copy**: Point to the existing home of a fact; never restate another page inside the new one.
- **Section Edits**: Change only the section that is wrong; do not regenerate a whole document to fix one paragraph.
- **Template Fill**: Start from the template for the document type and fill it; skip sections that would be empty instead of padding them.
