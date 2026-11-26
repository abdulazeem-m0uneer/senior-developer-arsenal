# Entry Formats & Sweep Checklist

Formats for the decision log and the open-questions list, the routing table, the numbering routine, and the checklist for propagating a decision.

---

## 1. Which Home

| What happened | Where it goes | Marked |
| :--- | :--- | :--- |
| A person with authority decides, answers, or overrules | Decision log | their role, for example `owner` |
| A reversible technical choice made by established practice | Decision log | `lead` |
| A structural choice with real alternatives and lasting cost | A full decision record (`architecture-design-adr`), cited from the log in one line | `lead` or the approver |
| A point no document and no code answers | Open-questions list | owner of the answer |
| A fact learned (a limit, a date, a provider behaviour), not a rule | The document that needs it, with its source | not numbered |

A decision said in a chat, a ticket comment, or a meeting is not a rule until it is in the log. Record it in the session that hears it.

---

## 2. Log Layout

One file, one line per entry, ascending numbers, newest last. A short header states the id prefix, the current range, and the rule that entries are amended, never rewritten.

```markdown
# Decision log

Entries DEC-1 to DEC-143. One line each. An entry is never rewritten: a later entry amends it.

- **DEC-141 (refund window; owner, 2025-03-02):** "Seven days, no exceptions for annual plans." Refunds are accepted for 7 days from payment on every plan. Partial refunds stay as they were.
- **DEC-142 (job queue on the main database; lead, 2025-03-04):** Background jobs use the existing database as the queue; no separate broker until throughput requires one. Reversible: the queue sits behind one interface.
- **DEC-143 (refund window for annual plans; owner, 2025-03-09; amends DEC-141):** "Make it thirty days for annual, I was wrong." Annual plans: 30 days. Monthly plans stay at 7 days.
```

After DEC-143 is written, DEC-141 gains a suffix and keeps its text:

```markdown
- **DEC-141 (refund window; owner, 2025-03-02):** "Seven days, no exceptions for annual plans." ... _(Amended on 2025-03-09 by DEC-143.)_
```

---

## 3. Entry Anatomy

`- **DEC-<n> (<subject>; <decider role>, <YYYY-MM-DD>; amends DEC-<x>; answers OQ-<y>):** "<their words>". <The rule in plain words.> <What stays as it was.>`

| Part | Rule | Reason |
| :--- | :--- | :--- |
| Number | Next free integer, taken at commit time | Parallel writers collide on reserved numbers |
| Subject | Three to six words, the noun a reader will grep for | The log is read by grep, not top to bottom |
| Decider and date | Role, not a private name; ISO date of the decision, not of the commit | Authority and order must be checkable later |
| `amends` / `answers` | Every entry narrowed or reversed, every question closed | Lets the sweep start from known citations |
| Quote | Verbatim, typos kept, in the decider's language | A paraphrase quietly changes the rule |
| Rule | One or two sentences, present tense, testable | Specifications will cite this sentence |
| What stays | Named when the decision is narrower than it sounds | Stops readers over-applying it |

Not in an entry: the discussion, the rejected options (that is a decision record), implementation steps, anything the decider did not say.

---

## 4. Open-Questions List

One table per area. A question has a stable id and is never deleted.

```markdown
| Id | Question | Who answers | Recommendation | Blocks | Working rule until answered |
| :--- | :--- | :--- | :--- | :--- | :--- |
| OQ-17 | Does a refund return the payment fee? | Product owner | No: fee is kept, stated on the receipt | Refund endpoint, receipt text | Build with the fee kept behind one setting |
| OQ-18 | **Answered (DEC-143).** Refund window for annual plans? | Product owner | 30 days | nothing | n/a |
```

- A question reaches the decider only when it blocks work now. Ask in one line with the choice and the recommendation.
- A recommendation the writer made for themselves is not an answer. Build on it only where the change is cheap to reverse, and say so in the row.
- Business questions and technical questions have different owners; name the role in every row.

---

## 5. Numbering Routine

```bash
git fetch origin                                             # other writers push to the log within the hour
grep -oE '^- \*\*DEC-[0-9]+' "$LOG" | grep -oE '[0-9]+' | sort -n | tail -1    # highest in the log
grep -rhoE 'DEC-[0-9]+' docs --include='*.md' | grep -oE '[0-9]+' | sort -n | tail -1   # highest cited anywhere
```

1. The next number is one above the larger of the two results: a document may cite a number whose entry is still on an unmerged branch.
2. Tell any helper writing documents in parallel that the number is provisional.
3. Repeat the fetch and the check immediately before the commit. If taken, renumber in every file of the change (`git diff --name-only` gives the list), then re-run the duplicate check.
4. Keep log changes small and merge them quickly; a long-lived branch that touches the log will conflict.

---

## 6. Sweep Checklist

- [ ] **Search terms listed**: the old wording, each amended entry number, the old value itself (`24 hours`, `24h`, `one day`), and the identifiers of the rules affected.
- [ ] **All repositories covered**: specifications, user-facing help, API reference, runbooks, agent guides, test names and fixtures that encode the old value.
- [ ] **Historical records skipped**: the log, review reports, dated notes, changelogs, quoted words. They describe what was true then.
- [ ] **Each hit rewritten to the new rule** with the entry cited; the rule text is not copied out of the log.
- [ ] **Question rows closed**: the row stays and its cell starts `**Answered (DEC-<n>).**`.
- [ ] **Withdrawn rules keep their id** and say `withdrawn (DEC-<n>)`; no id or event number is reused.
- [ ] **Status lines updated**: each touched document notes the entry numbers applied.
- [ ] **Totals still add up**: every count table the edit touched was recounted.
- [ ] **Code and configuration listed**: constants, validation limits, and messages that now differ from the rule, each with a follow-up change.
- [ ] **Legal or customer-facing wording flagged** for the decider; it is not silently reworded.
- [ ] **Second grep is clean**: re-run the search terms; only historical records remain.

---

## 7. Common Failures

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| Two documents state different limits | Entry written, sweep skipped | Run the sweep from the entry's `amends` list |
| The same question is asked again a week later | Answer lived only in a chat | Write the entry in the session that hears the answer |
| Log entry grows to a paragraph of debate | Trade-off discussion in the log | Move it to a decision record; keep one line and a link |
| Owner is asked to approve a queue library | Technical choice sent upward | Decide by practice, record it as `lead`, note that it is reversible |
| Old entry edited in place | Reversal treated as a correction | Restore the text; add a new entry and the amended suffix |
