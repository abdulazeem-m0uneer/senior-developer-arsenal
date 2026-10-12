# Documentation Review Checklist

Review a document as its reader, then as a hostile maintainer. Plain-language rules, single-home rules, and CI checks.

---

## 1. Reader & Type

- [ ] **Reader named**: the first lines say who this is for and what they can do after reading.
- [ ] **One type**: tutorial, how-to, reference, or explanation; material of another type is moved out and linked.
- [ ] **Title is the task or the thing**: "Rotate the signing key", not "Key management notes".
- [ ] **Answer first**: the command, the value, or the conclusion comes before the background.
- [ ] **Scannable**: headings state content, steps are numbered, facts with several attributes are in tables.

---

## 2. Accuracy

- [ ] **Run, not recalled**: every command was executed on a clean checkout; every output is real and trimmed.
- [ ] **Versions stated**: prerequisites name exact versions or ranges; nothing says "latest".
- [ ] **Paths and names exist**: files, flags, environment variables, and endpoints match the code at this commit.
- [ ] **No invented reasons**: every "because" traces to a decision record, a specification, or the author; unknowns are listed as open questions.
- [ ] **Examples are complete**: copy-paste runs without hidden setup; placeholders use `<angle brackets>` and are explained.
- [ ] **No secrets or private data**: tokens, real customer data, and internal host names are replaced with obvious placeholders (`example.com`, `<token>`).

---

## 3. Runbook-Specific

- [ ] Each step has precondition, exact command, expected output, the action if it differs, and rollback.
- [ ] No step requires judgement ("if it looks slow"); thresholds are numbers.
- [ ] Destructive steps are marked and preceded by a read-only command that shows what they will affect.
- [ ] Escalation contact and stop conditions are at the top, not the bottom.
- [ ] "Last verified" date is within the agreed interval, set by someone who ran it end to end.

---

## 4. API Reference-Specific

- [ ] Every endpoint in the spec has an entry; every entry matches an endpoint that exists.
- [ ] What, why, who, how, errors, rules, and code location are all present and specific.
- [ ] The "why" explains a choice, not the behaviour again.
- [ ] Every listed error can really be raised by this endpoint, and every error it raises is listed, with cause and remedy.
- [ ] Every rule links to where it is defined; every code path resolves.
- [ ] The entry changed in the same commit range as the endpoint.

---

## 5. One Home per Fact

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| The same value appears on several pages | Copied instead of linked | Keep it where it is defined; link from the rest |
| Two pages disagree | One was updated, the copy was not | Find which matches the code, correct, then deduplicate |
| A page says "not yet built" about something that exists | Change did not sweep the docs | Search for the old statement in every change that alters behaviour |
| README repeats the whole setup guide | README grew into a manual | README keeps the quick start; the guide holds the detail |
| A fact lives only in a chat thread or a ticket | Never written down | Move it to its home page; link the ticket to the page |

Search before stating: `grep -rn "<old value or phrase>" docs README.md` on every behaviour change.

---

## 6. Plain Language

| Rule | Instead of | Write |
| :--- | :--- | :--- |
| Active voice, named actor | "The cache is invalidated" | "The worker invalidates the cache" |
| Imperative for steps | "You should now be able to run" | "Run" |
| Present tense | "This will return a list" | "Returns a list" |
| Short common words | "utilise", "in order to", "leverage" | "use", "to", "use" |
| One term per thing | "account", "profile", "user record" for the same object | Pick one, define it once |
| Concrete numbers | "a short while", "large files" | "30 seconds", "files over 50 MB" |
| No hedging | "It should probably work" | State what happens, or say it is untested |
| No time-relative words | "recently", "the new API", "soon" | A version or a date |

- [ ] Sentences average under 25 words; one idea each.
- [ ] Abbreviations are expanded on first use; a glossary exists once there are more than a handful of terms.
- [ ] Condition before instruction: "If the check fails, run X", not "Run X if the check fails" after the reader has already acted.
- [ ] Warnings come before the step they apply to.

---

## 7. CI Checks

| Check | Catches | Example tool |
| :--- | :--- | :--- |
| Markdown lint | Broken structure, heading jumps | `markdownlint-cli2` |
| Link check | Dead internal anchors and external URLs | `lychee`, run on pull requests (internal) and on a schedule (external) |
| Spec drift | Committed OpenAPI differs from the code | Regenerate, then `git diff --exit-code` |
| Spec lint | Missing descriptions, examples, error schemas | `@redocly/cli lint` or `spectral lint` |
| Reference completeness | Endpoint without an entry, entry with placeholder text | A script comparing the route list with the reference; fail on `TODO`, `TBD` |
| Examples run | Snippets that no longer compile or pass | `python -m doctest`; compile Node.js and .NET samples as test projects |
| Prose lint (optional) | Banned words, undefined terms, passive voice | `vale` with a small house style |

A check that reports and does not fail the build is not a check. Prove each new check bites by planting one bad input before trusting it.

---

## 8. Review Outcome

| Verdict | When |
| :--- | :--- |
| Reject | A command fails, a fact is wrong, a reason is invented, or a secret is present |
| Revise | Type is mixed, a fact has two homes, a runbook step lacks output or rollback |
| Accept | A person from the target audience followed it without asking a question |
