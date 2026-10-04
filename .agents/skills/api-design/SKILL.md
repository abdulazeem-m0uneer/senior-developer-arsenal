---
name: api-design
description: 'Senior workflow for designing RESTful or RPC API contracts, input validation, and service interfaces in ASP.NET Core or Node.js. Use when the user asks to design endpoints, DTO contracts, API validation, or runs /api-design. Triggers on: "design API", "create endpoints", "API schema", "/api-design". Do not use for client-side state or fullstack synchronization (use fullstack-integration-master).'
---

# API Design & Interface Specification Skill

Follow this procedure when designing, specifying, or refactoring RESTful or RPC API endpoints and data transfer contracts.

---

## 1. When to Use This Skill

Activate this skill when:
- Designing new HTTP REST endpoints, request/response DTOs, or route controllers.
- Establishing boundary input validation schemas (FluentValidation, Zod, Pydantic).
- Standardizing error responses with RFC 7807 Problem Details.
- The user runs the `/api-design` slash command or asks to architect an API contract.

*Boundary*: For end-to-end client-server synchronization, optimistic UI mutations, or OpenAPI type generation, use `fullstack-integration-master`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Resource Modeling & Path Definition
Consult: [API Design Standards](./references/api-standards.md)
1. Define resource hierarchy with plural nouns (`/api/v1/orders/{orderId}/items`).
2. Map operations to standard HTTP verbs (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`).
3. Require `Idempotency-Key` headers on non-idempotent mutation routes.

### Step 2: Request & Response Contracts
1. Create strongly-typed DTOs (C# records, TypeScript interfaces, or Pydantic models).
2. For collections, enforce cursor pagination (`cursor`, `limit`, `hasMore`). Never allow unbounded queries.

### Step 3: Boundary Validation Schemas
Define strict schema validation rules at the HTTP boundary before domain logic execution:
- C#: FluentValidation validators registered in DI.
- Node.js: Zod schemas validating `req.body`, `req.query`, and `req.params`.
- Python: Pydantic v2 schemas with `extra='forbid'`.

### Step 4: Error Handling & RFC 7807 Format
Standardize all 4xx/5xx responses to RFC 7807 Problem Details envelopes containing `type`, `title`, `status`, `detail`, and `errors`.

---

## 3. Verification Protocol

1. Verify status codes: `201 Created` with `Location` header on resource creation, `204 No Content` on successful deletion.
2. Verify invalid payload returns `400 Bad Request` with structured RFC 7807 validation error dictionary.
3. Verify unauthorized requests return `401 Unauthorized` or `403 Forbidden` without leaking internal state.

---

## 4. ⚡ Token-Saving Execution Rule

- Output only the specific Route handler, DTO declaration, and Validation schema.
- Summarize endpoint contracts in a compact Markdown table (`Method`, `Path`, `Request DTO`, `Response DTO`, `Status`).
