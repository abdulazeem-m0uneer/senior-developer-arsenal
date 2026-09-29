# Vertical Slice Feature Architecture Reference

Guide for delivering fullstack features slice-by-slice across Database, Backend, and Frontend.

---

## 1. The Vertical Slice Flow

```text
┌──────────────────────────────────────────────┐
│ 1. DATA LAYER: Migration & Entity Mapping    │
│    - Non-blocking table/column DDL           │
│    - Repository/DbSet or ORM entity config   │
├──────────────────────────────────────────────┤
│ 2. BACKEND LAYER: Service & Route Handler    │
│    - Input boundary validation (Zod/Fluent)  │
│    - Business use-case logic & result types  │
│    - RFC 7807 problem details error mapping  │
├──────────────────────────────────────────────┤
│ 3. FRONTEND LAYER: Contract & UI View        │
│    - Type synchronization (OpenAPI client)   │
│    - TanStack Query hook / Angular Signal    │
│    - Optimistic UI update with rollback      │
│    - State-complete component (6 states)     │
└──────────────────────────────────────────────┘
```

---

## 2. Integration Checkpoints

- **Contract Match**: Verify payload keys and types match 1:1 between backend DTO and frontend client.
- **Rollback Safety**: If optimistic UI is used, ensure previous cache snapshot is restored on `onError`.
- **Accessibility**: Ensure form fields, buttons, and status messages meet WCAG 2.2 AA.
