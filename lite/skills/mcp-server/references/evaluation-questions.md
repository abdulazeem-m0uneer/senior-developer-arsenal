# Evaluation Questions

The server is good when an agent with only the server attached can answer questions a human would actually ask. Ten questions, written after exploring the real data, graded by string comparison.

---

## 1. Process

1. **Read the tool list** from the running server: names, descriptions, schemas.
2. **Explore the data read-only**: list, search, page. Note identifiers, timestamps, names, attachments, and how far back the data goes.
3. **Write ten questions** that meet every rule below. Write them from the human's side ("which release note first mentioned…"), not from the tool's side.
4. **Solve each one yourself** through the tools, record the exact answer and the call sequence that found it.
5. **Run a fresh agent** per question with the server attached and nothing else; compare its answer to yours.

## 2. Question Rules

| Rule | Why |
| :--- | :--- |
| Independent: no question depends on another's answer or on a prior write | Runs in any order, in parallel |
| Read-only and idempotent: no state change needed to answer | Re-runnable, safe on production data |
| Realistic: a task a person assisted by an agent would want done | Measures usefulness, not trivia |
| Multi-hop: needs several calls, paging, and reasoning; sometimes dozens of calls | Stresses context handling and response size |
| Not solvable by one keyword search: paraphrase, use synonyms, never quote the target text | Tests the tools, not the search box |
| Mixed data types: ids and names, dates in several forms, file types, URLs | Probes whether results carry every useful form |
| Stable: the answer cannot drift (no live counts of reactions, members, replies) | Grades stay valid |
| One verifiable answer, short: a number, a name, a date, true/false, or a single choice | Graded by comparison, no judge |
| Some ambiguity allowed in the path, never in the answer | Forces tool-choice decisions while staying gradable |
| Do not limit questions to what the tools make easy | A question the server cannot answer is a finding |

## 3. Answer Rules

- Verified by you through the tools before the run; note the call sequence.
- Formatted unambiguously: specify the date format, units, or casing the answer must use.
- Diverse across the ten: different tools, different data areas, different reasoning shapes (lookup, aggregate, compare, earliest/latest, true/false).

## 4. Grading

```text
| # | Question (short) | Expected | Agent answer | Pass | Tool at fault |
```
Pass means an exact match after trimming and case folding. For every miss, name the tool whose name, description, schema, or response size caused it; that is the work item. Rerun after fixes.

## 5. File Shape

```xml
<evaluation>
  <qa_pair>
    <question>Which design document first proposed the retry budget, and in what month was it last edited? Answer as "title, YYYY-MM".</question>
    <answer>Resilience Plan, 2025-11</answer>
  </qa_pair>
</evaluation>
```
