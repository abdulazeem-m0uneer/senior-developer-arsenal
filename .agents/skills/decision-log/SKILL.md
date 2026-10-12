---
name: decision-log
description: 'Decision recording runbook: one numbered log of one-line entries that quote the decider and date, amended entries marked not rewritten, a sweep of every document stating the old rule, and an open-questions list with owners. Use when the user asks to record a decision, apply an owner answer, reverse a recorded rule, or runs /decision-log. Triggers on: "record this decision", "the owner answered", "we decided", "reverse that decision", "/decision-log". Do not use for an architecture choice with trade-offs (use architecture-design-adr) or task board status (use delivery-board-sync).'
---

# Decision Log Procedure

This skill guides the agent through recording a decision in its one home, propagating it to every document that states the old rule, and parking what is still open with an owner.

---

## 1. When to Use This Skill

Activate this skill when:
- The product owner or another decider answers, decides, or overrules something in the session, in a review, or on a ticket.
- A reversible technical choice was made during the work and nothing records it yet.
- A recorded decision is reversed, narrowed, or extended.
- A gap is found that neither the documents nor the code answer.
- The user runs the `/decision-log` slash command.

*Boundary*: An architecture decision with alternatives, trade-offs, and consequences is a full record: use `architecture-design-adr` and cite its number from the log. For moving the task that a decision unblocks, use `delivery-board-sync`. For rewriting the documentation itself, use `docs-writer`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Find the Log and Check It Is Not Already Recorded
1. Locate the one decision log and the open-questions list from the project guide. If the project has neither, create them once (formats in the reference); never start a second log beside an existing one.
2. Fetch the remote, then grep the log and the open pull requests for the topic. Another session may have recorded it minutes ago; extend that work, do not write beside it.
3. Never read the log whole: grep for the keyword and read only the matching lines (`grep -n -i '<keyword>' "$LOG" | cut -c1-300`).

### Step 2: Classify What You Have
Consult: [Entry Formats & Sweep Checklist](./references/entry-formats-and-sweep.md)
1. **A decision by a person**: goes in the log, quoting their words.
2. **A reversible technical choice**: decide it yourself by established practice, record it in the log marked `lead`, and move on. Do not queue it for the owner.
3. **A point with no recorded answer**: an open question. Ask the decider now only if it blocks work now; otherwise park it (Step 5).
4. Never ask anyone to confirm what the log already decides. Cite the entry and proceed.

### Step 3: Write the Entry
1. One entry per topic, not per question, on one line: number, subject, decider, date, what it amends, then the quote and the rule in plain words.
2. Quote the decider verbatim. Add nothing they did not say; where the answer is silent, state which reading you took or park the remainder.
3. Do not rewrite an amended entry. Append `_(Amended on <date> by DEC-<n>.)_` to it so the history stays readable.

### Step 4: Sweep Every Statement of the Old Rule
1. Grep the documents for the old wording, the amended entry numbers, and two or three synonyms. A decision that lives only in the log changes nothing.
2. Fix each hit: state the new rule and cite the entry; link to the log instead of copying its text.
3. Leave dated records alone: the log itself, review reports, meeting notes, quoted words.
4. Keep stable identifiers: a withdrawn rule keeps its id and says `withdrawn (DEC-<n>)`; ids are never renumbered or reused. Recount any totals table the edit touched.
5. Code that now contradicts the rule is fixed in its own change, not in the documents change.

### Step 5: Park What Is Still Open
1. Add one row to the open-questions list: the question, who must answer, your recommendation, what it blocks, and the working rule until then.
2. When a question is answered, keep its row and mark it `Answered (DEC-<n>)`; do not delete it.

### Step 6: Number at Commit Time and Report
1. The number is provisional until commit: other writers take "the next free number" too. Fetch again immediately before committing; if it was taken, renumber across every file in the change and re-run the checks below.
2. Commit the log entry before, or together with, the documents that cite it. Report: the numbers written, the documents changed, and any document that still states the old rule and why.

---

## 3. Verification Protocol

```bash
LOG=docs/decisions/log.md                                        # the one log, as named in the project guide
git fetch origin && git show "origin/HEAD:$LOG" | grep -oE '^- \*\*DEC-[0-9]+' | grep -oE '[0-9]+' | sort -n | tail -1   # highest on the remote: yours is +1
grep -oE '^- \*\*DEC-[0-9]+' "$LOG" | sort | uniq -d              # must print nothing: no number used twice
grep -rniE '<old wording>|<synonym>' docs --include='*.md' | cut -c1-200      # only dated records may remain
comm -13 <(grep -oE '^- \*\*DEC-[0-9]+' "$LOG" | grep -oE 'DEC-[0-9]+' | sort -u) \
         <(grep -rhoE 'DEC-[0-9]+' docs --include='*.md' | sort -u)           # cited but not in the log: must be empty
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Sweep | `pricing.md:41` still states the 24-hour window | Two rules in force; the next reader builds the old one | `[Blocker]` | Rewrite the sentence, cite the entry |
| Log | Entry paraphrases the owner and adds a limit they never gave | An invented rule carries the owner's authority | `[Blocker]` | Quote verbatim; park the limit as an open question |
| Numbering | `DEC-142` appears twice after a parallel merge | Citations become ambiguous | `[Architecture]` | Renumber the later entry and every citation of it |
| Open list | Question has no owner and no recommendation | Nobody answers it; work stays blocked | `[Suggestion]` | Add the decider, a recommendation, what it blocks |

---

## 4. ⚡ Token-Saving Execution Rule

- **Grep, Never Read**: Find the next number and the touched entries with `grep`; never load the whole log or a whole specification.
- **Changed Sentences Only**: Edit and show only the sentences that state the old rule, never whole documents.
- **One Entry per Topic**: Fold a batch of related answers into one entry; do not write a line per question.
