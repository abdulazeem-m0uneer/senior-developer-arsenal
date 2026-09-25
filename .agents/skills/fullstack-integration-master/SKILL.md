---
name: fullstack-integration-master
description: End-to-end fullstack engineering skill bridging Frontend (React / Angular) with Backend (.NET / Node.js) and Databases. Use when designing end-to-end features, synchronizing contracts, building optimistic UI mutations, or configuring real-time event streams.
---

# Fullstack Integration Skill

This skill guides the agent through building coherent, end-to-end fullstack features bridging frontend clients and backend APIs.

---

## 1. When to Use This Skill

Activate this skill when:
- Delivering complete features that span database schema, backend API endpoints, and frontend views.
- Synchronizing type contracts between C#/.NET or Node.js backends and TypeScript frontends.
- Implementing optimistic UI mutations with rollback resilience (TanStack Query / Angular SignalStore).
- Configuring Server-Sent Events (SSE) or WebSockets for real-time synchronization.
- Debugging end-to-end data flow, CORS, cookie authentication, or serialization mismatches.

---

## 2. Fullstack Delivery Procedure

### Step 1: Contract-First Design
Consult: [End-to-End Type Safety Guide](./references/e2e-type-safety.md)
1. Define the shared DTO contract and input validation schema.
2. Ensure both backend validator (FluentValidation / Zod) and frontend client types match identically.

### Step 2: Resilient Mutation & UI Sync
Consult: [Real-Time & Optimistic UI Guide](./references/realtime-optimistic-ui.md)
1. Write the backend mutation handler with idempotency and optimistic concurrency.
2. Implement the frontend mutation with instant cache update, error rollback snapshot, and query invalidation.

### Step 3: Verification
Verify both layers:
- Run backend integration tests.
- Verify frontend component compiles and mutation tests pass.

---

## 3. ⚡ Token-Saving Execution Rule

- **Contract + Mutation Only**: Output only the DTO interface, the endpoint handler, and the frontend mutation hook. Do not output surrounding scaffolding.
- **Zero Narrative**: Skip conversational transitions between backend and frontend code blocks.
