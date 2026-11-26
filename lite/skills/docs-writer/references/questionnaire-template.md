# Discovery Questionnaire Template

A question set for one named person who holds knowledge the team lacks, answered asynchronously or in one meeting.

## 1. When a Questionnaire, Not a Question

An open point that neither the user nor the agent can answer, held by one named person (a vendor, an ops owner, a domain expert) who will answer asynchronously or in one meeting. The user cannot be grilled about the subject; they can always be grilled about the *send*.

Two exchanges, then write:
1. **Who receives it**: role, expertise, relation to the user. Fixes tone and how much context the document must carry.
2. **What must come back**: the specific decisions or facts the user must walk away able to settle. A concrete list.

Write to `docs/questionnaires/<slug>.md` (or the project's location); report the path. Done when every item in the list is covered by a question.

---

## 2. Template

```markdown
# <Title>

**Purpose**: why this exists and the decision riding on it.
**From**: <user>  **To**: <recipient>  **How answers are used**: <where they go>

## Context
One paragraph that orients someone who was not in the user's head. Enough to answer well; not a page.

## How to answer
Deadline and rough effort. Partial answers and "I do not know" are useful; flag uncertainty rather than skipping.

## <Theme>
One `##` per theme once there are more than a handful of questions. Most important first: async may get one pass.
Each question is one idea, never compound, with an answer stub beneath, and a one-line
_why this matters_ only where it could be misread or invite a throwaway answer.

### What load must the system handle at launch?
_Why this matters: decides whether burst capacity is provisioned now or deferred._

>

## Anything else?
What we did not ask that you think we should know?
```

Answers that arrive go through `decision-log` (quoted, dated, with the decider) and the open-questions row is marked answered.

Adapted from mattpocock/skills (MIT).
