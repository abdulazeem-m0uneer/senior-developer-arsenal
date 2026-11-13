---
name: threat-model
description: 'Design-time threat modelling: data flows and trust boundaries, STRIDE, abuse cases, rated mitigations. Use to work out what an attacker could do to a feature, service or API before or while building it. Triggers: "threat model", "STRIDE", "abuse cases", "new trust boundary", /threat-model. Not for flaws in existing code (use security-audit) or personal data flows (use data-privacy).'
---

# Threat Model Procedure

This skill guides the agent through a design-time threat model of a feature, service, or API: a diagram, a ranked threat list, mitigations that point at the skill that implements them, and a test for each.

---

## 1. When to Use This Skill

Activate this skill when:
- A feature, service, or API is being designed or built and handles credentials, personal data, money, files, or tenant data.
- A design adds a trust boundary: a new client type, a public endpoint, a third-party provider, a queue, an admin plane.
- A design adds a new data class (payment data, health data, uploads) or a new third party.
- A security review asks "what can go wrong here" before any code exists to audit.
- The user runs the `/threat-model` slash command.

*Boundary*: Hunting exploitable flaws in code that already exists is `security-audit` (and the `security-auditor` subagent). Tracing personal data to logs, exports, and vendors is `data-privacy`. The architecture choice itself, with alternatives, is `architecture-design-adr`. Money-flow correctness is `payments-integrity`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Scope and Draw the Data-Flow Diagram
Consult: [Threat Model Template](./references/threat-model-template.md)
1. State in three lines: what is built, what it protects (assets), who uses it. Name what is out of scope.
2. List the elements: actors, processes, data stores, external entities, and every data flow between them.
3. Draw the diagram as text or mermaid and mark each trust boundary (internet to edge, client to API, service to service, service to database, tenant to tenant, vendor).
4. Read the existing design and code with targeted search; do not invent flows. Mark each unverified flow `assumed` and ask the owner.

### Step 2: Apply STRIDE per Element and per Crossing
Consult: [STRIDE Catalogue](./references/stride-catalogue.md)
1. Walk each element, then each flow that crosses a boundary. Test only the STRIDE letters that apply to that element type (matrix in the catalogue).
2. For each hit write one row: element, letter, threat in one sentence ("an attacker can ... so that ...").
3. Add the API and mobile catalogue items that fit the design (token storage, replay, BOLA, mass assignment, SSRF, rate-limit abuse, supply chain).
4. Add abuse cases: for each asset, the attacker goal and the cheapest path to it, including a legitimate user abusing a legitimate feature.

### Step 3: Rate
1. Score every threat likelihood (1-3) x impact (1-3) using the scale in the template. Ratings order the work; do not claim precision.
2. Rate on the unmitigated design, then re-rate after the planned mitigation to show the residual level.

### Step 4: Choose Mitigations and Map Them
1. One mitigation per threat, preferring removal of the feature or data over a control that must work forever.
2. Name the arsenal skill or rule that implements it: authn, authz, validation, secrets, dependencies to `security-audit`; PII to `data-privacy`; contracts, errors, idempotency, rate limits to `api-design`; money to `payments-integrity`; vendor calls to `provider-sdk`; schema and tenancy to `database-standards` and `database-architect`; shared pipelines and infra to `shared-infra-changes`; Node.js services to `nodejs-backend-expert`.
3. If a mitigation forces a structural choice, record it with `architecture-design-adr`; do not restate the ADR here.

### Step 5: Record Residual Risk
1. For each threat left open, write: the risk, why accepted, the owner by name, and a review date.
2. Record the acceptance as an entry via `decision-log`, quoting the owner; link the entry, do not copy it. A risk with no owner is not accepted, it is open.

### Step 6: Turn Mitigations into Controls and Tests
1. For each mitigation write the control (what is enforced, where) and the test that fails when it is removed: negative authz test, replay test, oversized or unexpected-field test, rate-limit test, dependency gate in CI.
2. Hand the list to `test-every-change`; the tests ship in the same change as the control.
3. Mark controls that cannot be tested as `monitored` and name the alert that proves them (see `observability`).

### Step 7: Set the Revisit Triggers
1. Write the model to the path the project guide names (default `docs/security/threat-model-<feature>.md`) and link it from the design.
2. List the triggers that reopen it: new trust boundary, new data class, new third party, new client type, new privilege level, an incident touching the area.

---

## 3. Verification Protocol

1. Every flow crossing a trust boundary has at least one STRIDE row or a stated "no applicable threat".
2. Every threat rated High has a mitigation, a control, and a test, or a named owner for the residual risk.
3. Every mitigation names an implementing skill or rule; every accepted risk links a `decision-log` entry.
4. Output the register:

| ID | Element / flow | STRIDE | Threat | L x I | Mitigation (skill) | Control / test | Residual |
| :--- | :--- | :---: | :--- | :---: | :--- | :--- | :--- |
| T-01 | Client to API, order fetch | E | User A reads user B's order by ID | 3x3 = 9 | Owner filter from session (`security-audit`) | Cross-user fetch returns 404 | Low |
| T-02 | Webhook endpoint | S, R | Forged provider event marks an order paid | 2x3 = 6 | Signature check, replay window (`provider-sdk`) | Bad signature and stale timestamp rejected | Low |

---

## 4. Negative Triggers

Do NOT use this skill when:
- A finished code path needs a vulnerability hunt with `file:line` evidence: use `security-audit`.
- The question is where personal data flows or is retained: use `data-privacy`.
- The task is choosing between architectures: use `architecture-design-adr`.
- A live incident is in progress: use `incident-response`.

---

## 5. ⚡ Token-Saving Execution Rule

- **Elements, Not Prose**: Model rows and bullets only; no narrative threat essays.
- **Applicable Letters Only**: Skip STRIDE letters that do not apply to the element type instead of writing "n/a" rows.
- **Link, Do Not Copy**: Cite skills, ADRs, and decision entries by name; never restate their content.
