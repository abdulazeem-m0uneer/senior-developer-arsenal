---
name: api-design
description: Senior workflow for designing RESTful or RPC API contracts, input validation, and service interfaces in ASP.NET Core or Node.js.
---

# API Design Workflow

Use this workflow to design resilient, developer-friendly, and well-typed API endpoints.

## Steps

1. **Contract Specification**:
   - Define HTTP method, URI path (RESTful nouns), and query/body parameter contracts.
   - Establish status codes: `200 OK`, `201 Created` with Location header, `204 No Content`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `409 Conflict`, `422 Unprocessable Entity`.

2. **Schema & DTO Definitions**:
   - **C# / .NET**:
     - Define `record` request and response DTOs.
     - Author `AbstractValidator<TRequest>` using FluentValidation.
   - **Node.js / TypeScript**:
     - Define Zod schema with `.strict()`.
     - Infer TypeScript types via `z.infer<typeof Schema>`.

3. **Standardized Error Handling**:
   - Format all non-2xx responses using RFC 7807 `ProblemDetails`:
     ```json
     {
       "type": "https://api.domain.com/errors/conflict",
       "title": "Resource Conflict",
       "status": 409,
       "detail": "An active subscription already exists for this tenant.",
       "instance": "/api/v1/subscriptions"
     }
     ```

4. **Integration Test Generation**:
   - Scaffold an integration test validating:
     - Positive path (200/201).
     - Validation rejection (400) for missing/malformed attributes.
     - Authentication & authorization checks (401/403).
