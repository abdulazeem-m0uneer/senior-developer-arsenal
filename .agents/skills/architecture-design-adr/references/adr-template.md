# Architecture Decision Record (ADR) Template

Use this template to document significant technical decisions. Store records in `docs/adr/` numbered sequentially (e.g., `0001-use-postgresql-for-audit-trail.md`).

---

# ADR-[NUMBER]: [Short Title of the Decision]

- **Status**: [ Proposed | Accepted | Deprecated | Superseded by ADR-XXXX ]
- **Date**: YYYY-MM-DD
- **Author**: [Senior Software Engineer]
- **Deciders**: [Engineering Team / Tech Lead]

---

## 1. Context & Problem Statement
*Describe the context, requirements, and forces influencing this decision. What problem are we solving? What are the business and technical constraints?*

---

## 2. Decision Drivers
- Performance & latency requirements
- Developer productivity & maintainability
- Operational overhead & infrastructure costs
- Data integrity & transactional consistency guarantees

---

## 3. Considered Options
1. **Option 1**: [Title of Option 1]
2. **Option 2**: [Title of Option 2]
3. **Option 3**: [Title of Option 3]

---

## 4. Evaluation Matrix / Trade-Off Analysis

| Criteria | Option 1 | Option 2 | Option 3 |
| :--- | :--- | :--- | :--- |
| **Complexity** | Low | Medium | High |
| **Performance** | High | High | Very High |
| **Maintenance** | Easy | Moderate | Demanding |
| **Cost** | Minimal | Moderate | High |

### Detailed Pros and Cons:
- **Option 1**:
  - *Pros*: [...]
  - *Cons*: [...]
- **Option 2**:
  - *Pros*: [...]
  - *Cons*: [...]

---

## 5. Decision Outcome
**Chosen Option**: **Option [X]** because [primary technical rationale].

### Positive Consequences:
- [...]

### Negative Consequences / Trade-offs:
- [...]

---

## 6. Implementation Plan & Mitigations
- Step 1: [...]
- Step 2: [...]
- Mitigations for negative consequences: [...]
