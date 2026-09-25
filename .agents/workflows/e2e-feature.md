---
name: e2e-feature
description: Fullstack feature implementation workflow bridging database migration, backend endpoint, and frontend UI view.
---

# End-to-End Fullstack Feature Workflow

Use this workflow to deliver a cohesive vertical slice feature across the entire stack.

## Steps

1. **Database Schema & Migration**:
   - Write safe migration DDL with non-blocking indexes (`CREATE INDEX CONCURRENTLY` in Postgres).
   - Ensure foreign keys and data types (`TIMESTAMPTZ`, `UUIDv7`) adhere to standards.

2. **Backend API Endpoint & Validation**:
   - Define request/response DTOs.
   - Implement validation (FluentValidation in C# / Zod in Node).
   - Write repository query with `.AsNoTracking()` and selective projection.

3. **Client Mutation & State Sync**:
   - Generate or declare shared TypeScript client types.
   - Author frontend optimistic mutation hook (TanStack Query / Angular SignalStore) with rollback snapshot.

4. **Integration Verification**:
   - Run backend integration test and frontend component test.
   - Output summary in a single verification line.
