---
name: architecture-design-adr
description: System architecture design, trade-off evaluation, and Architecture Decision Record (ADR) authoring. Use when planning new subsystems, evaluating technology choices, designing boundaries (monolith vs microservices), or documenting architectural decisions. Triggers on: "architecture design", "ADR", "trade-off evaluation", "system design", "monolith vs microservices". Do not use for component UI/UX design (use ui-ux-architect) or database indexing alone (use database-architect).
---

# Architecture Design & ADR Authoring Skill

This skill guides the agent in making sound technical trade-offs, structuring software systems cleanly, and documenting critical decisions through Architecture Decision Records (ADRs).

---

## 1. When to Use This Skill

Activate this skill when:
- Designing new service modules, boundaries, APIs, or database models.
- Evaluating architectural trade-offs (synchronous REST vs asynchronous queues; modular monolith vs microservices).
- Documenting major technical decisions with an ADR.
- Refactoring legacy code into Clean Architecture or Domain-Driven Design (DDD).

*Boundary*: For component UI/UX design and token architecture, use `ui-ux-architect`. For database-specific schema and indexing design, use `database-architect`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Architectural Trade-off Evaluation
Evaluate the 4 core dimensions:
1. **Coupling & Cohesion**: Will this change increase coupling between independent domains? Can boundaries be decoupled via events or interfaces?
2. **Scalability & Bottlenecks**: What is the single point of failure? How do high traffic volumes impact latency and state persistence?
3. **Operational Complexity**: Does the solution require new infrastructure overhead (e.g. running distributed services vs in-process worker queues)?
4. **Reversibility**: Is this decision a "two-way door" or "one-way door"? Can we iterate safely with minimal blast radius?

### Step 2: Author the ADR Document
Consult: [ADR Production Template](./references/adr-template.md)
1. Assign incremental ID: `docs/adr/000X-short-title.md`.
2. Document Context, Options Considered, Decision, and Positive/Negative Consequences.
3. Include an options comparison matrix.

---

## 3. Verification Protocol

1. Verify the ADR file follows the standard template format.
2. Confirm both positive consequences (benefits) and negative consequences (trade-offs, operational burdens) are explicitly stated.
3. Validate that affected module interfaces conform to Clean Architecture boundaries.

---

## 4. ⚡ Token-Saving Execution Rule

- **Matrix-First**: Format option evaluations in compact markdown tables.
- **Concise Trade-offs**: Limit pros and cons to high-impact points (1–2 lines each). Avoid verbose narrative prose.
