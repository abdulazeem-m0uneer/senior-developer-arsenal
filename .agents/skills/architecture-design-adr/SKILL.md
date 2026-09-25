---
name: architecture-design-adr
description: System architecture design, trade-off evaluation, and Architecture Decision Record (ADR) authoring. Use when planning new subsystems, evaluating technology choices, designing boundaries (monolith vs microservices), or documenting architectural decisions.
---

# Architecture Design & ADR Skill

This skill guides the agent in making sound technical trade-offs, structuring software systems cleanly, and documenting critical decisions through Architecture Decision Records (ADRs).

---

## 1. When to Use This Skill

Activate this skill when:
- Designing new service modules, APIs, or database models.
- Evaluating architectural trade-offs (e.g., synchronous REST vs asynchronous message queue; modular monolith vs microservices).
- Documenting major technical decisions with an ADR.
- Refactoring legacy code into Clean Architecture or Domain-Driven Design (DDD).

---

## 2. Architectural Analysis Framework

Before recommending or executing an architectural change, evaluate:
1. **Coupling & Cohesion**: Will this change increase coupling between independent modules? Can boundaries be decoupled via events or interfaces?
2. **Scalability & Bottlenecks**: What is the single point of failure? How does data volume or concurrent users impact the database and network?
3. **Operational Complexity**: Does the proposed solution introduce operational friction (e.g. running multiple new distributed services vs an in-process queue)?
4. **Reversibility**: Is this decision a "one-way door" or a "two-way door"? Can we iterate safely?

---

## 3. ADR Authoring Procedure

1. Identify the need for a documented decision (e.g., choice between PostgreSQL `pgvector` vs dedicated vector DB, or EF Core vs Dapper).
2. Create an ADR document inside `docs/adr/` using the [ADR Production Template](./references/adr-template.md).
3. Outline context, considered options, pros/cons matrix, and the final decision with consequences.
