---
name: e2e-feature
description: 'Fullstack feature implementation workflow bridging database migration, backend endpoint, and frontend UI view. Use when the user asks to build an end-to-end feature across the entire stack or runs /e2e-feature. Triggers on: "build feature", "end to end", "fullstack feature", "implement slice", "/e2e-feature". Do not use for isolated backend API design (use api-design) or isolated UI audit (use frontend-audit).'
---

# End-to-End Vertical Slice Feature Skill

Follow this procedure when implementing a fullstack feature spanning the database, backend service, and frontend UI.

---

## 1. When to Use This Skill

Activate this skill when:
- Delivering an integrated fullstack feature slice from database persistence to user interface.
- Ensuring end-to-end type safety across API boundaries with optimistic UI rollbacks.
- The user runs the `/e2e-feature` slash command.

*Boundary*: For standalone backend API contracts without frontend UI, use `api-design`. For standalone design system tokens, use `ui-ux-architect`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Database Schema & Migration
Consult: [Vertical Slice Architecture Reference](./references/vertical-slice.md)
1. Author non-blocking DDL migration for new entities or columns.
2. Update ORM entity mapping (EF Core `EntityTypeConfiguration`, Prisma schema, or SQLAlchemy model).

### Step 2: Backend Application Service & API Route
1. Define request/response DTOs with boundary validation (FluentValidation / Zod / Pydantic).
2. Implement business logic handler returning domain Result types.
3. Expose REST/RPC route with proper HTTP status codes and RFC 7807 error envelopes.

### Step 3: Frontend Client Integration & UI View
1. Synchronize API types into frontend client.
2. Wire server state mutation using TanStack Query `useMutation` or Angular Signals.
3. Apply optimistic UI updates with snapshot capture for automatic rollback on error.
4. Render state-complete UI component handling Default, Hover, Active, Focus, Disabled, and Loading states.

---

## 3. Verification Protocol

1. Run backend integration tests asserting database persistence and validation boundaries.
2. Run frontend component tests asserting loading spinner, error alert, and successful optimistic update.
3. Output single-line verification summary: `E2E Feature verified across DB -> API -> UI`.

---

## 4. ⚡ Token-Saving Execution Rule

- Output only the modified migration snippet, backend handler, and frontend component.
- Never output full unbroken repository files.
