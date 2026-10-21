# Skill Writing Guide: Content, Calibration, and Failure Modes

Adapted from agentskills/agentskills docs (Apache-2.0), anthropics/skills `skill-creator` (Apache-2.0), and mattpocock/skills `writing-for-agents` (MIT).

---

## 1. Where the Content Comes From

A skill written from general knowledge produces generic procedure ("handle errors appropriately"). A useful skill is grounded in one of:

- **A task just completed.** Extract the sequence that worked, every correction the user made ("use X not Y", "check Z first"), the input and output formats seen, and the facts the agent did not know. Confirm the extraction with the user before scaffolding.
- **Project artifacts.** Runbooks, incident reports, review comments, issue threads, and the patch history. These carry the real schemas, failure modes, and reviewer expectations; a generic article does not.

Then run it on a real task and read the execution trace, not just the output. Wasted steps point at instructions that are vague (the agent tries several approaches), irrelevant (the agent follows them anyway), or a menu with no default.

---

## 2. What Goes in the Body

- **Add what the agent lacks, omit what it knows.** Project conventions, non-obvious edge cases, which tool to use. Not what a PDF is or how HTTP works. Test for each line: would the agent get this wrong without it? If not, cut it. If the agent already does the whole task well with no skill, the skill adds nothing.
- **Coherent unit.** Scope it like a function: one unit of work that composes. Too narrow forces several skills to load for one task; too broad cannot trigger precisely.
- **Moderate detail.** Concise stepwise guidance with one working example outperforms exhaustive coverage; every edge case written down is one more instruction the agent may follow when it does not apply.
- **Procedures, not answers.** Teach how to approach the class of problem, not the output for one instance. Templates, constraints ("never emit PII"), and tool-specific commands are fine; the approach must generalise.
- **Match specificity to fragility.** Fragile operations (a migration command, an exact sequence) get a prescriptive block: "run exactly this". Flexible work (what to look for in a review) gets the goal and the reason; an agent that knows why makes better context-dependent calls.
- **Defaults, not menus.** Name one tool and one escape hatch ("use X; for scanned input use Y"), never a list of equals.
- **Explain the why.** `ALWAYS` and `NEVER` in capitals are a yellow flag: reframe as the reason. Prohibitions drag the banned behaviour into attention; state the positive target ("write one-line comments") and keep a prohibition only as a guardrail that cannot be phrased positively.
- **Leading words.** One concept word the model already holds (tight, red, blast radius) replaces a restated sentence each time it appears and anchors the behaviour. A coined word costs definition tokens; reach for an existing one.

---

## 3. Patterns Worth Reusing

| Pattern | Use when | Shape |
| :--- | :--- | :--- |
| Gotchas | Environment facts that defy reasonable assumption | Bulleted corrections in `SKILL.md`, not a reference (the agent must see them before the situation) |
| Output template | A fixed deliverable shape | Fenced template inline if short; `assets/` if long or conditional |
| Checklist | Multi-step work with gates | `- [ ]` list with the command per step |
| Validation loop | Work that can be checked | Do, run validator, fix, repeat until clean |
| Plan, validate, execute | Batch or destructive operations | Structured plan file, validator against a source of truth, then execute |
| Bundled script | The same helper gets rewritten in every run | Write it once under `scripts/`, tested, non-interactive, `--help`, structured stdout, diagnostics on stderr, bounded output |

When the agent makes a mistake you had to correct, add the correction to the gotchas. That is the cheapest improvement loop there is.

---

## 4. Progressive Disclosure and Pointers

- The description (always loaded) decides whether the skill fires. The body (loaded on activation) must stay under the spec's 500 lines and roughly 5,000 tokens; the arsenal's 50–85 line target is well inside. References load on demand.
- Every pointer to a reference names the **condition** for reading it: "Read `references/api-errors.md` when the API returns a non-200 status" beats "see references/ for details". A must-read behind a weakly worded pointer is a variance bug: sharpen the wording first, inline the material only if that fails.
- Branching is the disclosure test: inline what every branch needs; push behind a pointer what only some branches reach.
- Keep references one level deep from `SKILL.md`; add a table of contents to any reference over 300 lines; organise multi-stack skills as one reference per stack so only the relevant one loads.
- Co-locate: a concept's definition, rules, and caveats under one heading. Scattered material fragments one meaning across many places; duplicated material repeats it and inflates its rank.

---

## 5. Steps and Completion Criteria

Every step ends on a condition the agent can check. "Understanding reached" invites stopping early; "every modified model accounted for" forces the digging. A checkable, exhaustive criterion is the strongest lever in the document. When later steps tempt the agent to rush the current one, sharpen the current criterion first; split the sequence across a real context boundary (a hand-off or a helper dispatch) only when the rush is observed and the criterion cannot be sharpened.

---

## 6. Pruning Pass Before Shipping

- [ ] Each meaning has one home; changing a behaviour is a one-place edit.
- [ ] The environment is a source of truth too (`package.json` scripts, config, `--help`): a line that restates it is a cache that goes stale. Cache only what cannot be looked up: the unwritten convention, the reason, the gotcha.
- [ ] Every line still bears on the task. Delete sediment: stale layers that stayed because removing felt risky.
- [ ] Hunt no-ops: an instruction the model obeys by default pays tokens to say nothing. Delete the sentence, not words from it. A leading word too weak to beat the default is a no-op too; the fix is a stronger word.
- [ ] Frontmatter validates (`name` equals folder, lowercase and hyphens, no leading, trailing, or double hyphen; `description` 1–1024 characters). Optional spec fields the arsenal validator does not accept (`license`, `compatibility`, `metadata`, `allowed-tools`) stay out of arsenal skills.

---
