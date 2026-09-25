# Fullstack Architecture & Integration Standards

These rules enforce end-to-end type safety, resilient state synchronization, and secure communication bridging Frontend (React/Angular) and Backend (Node.js/C# .NET).

---

## 1. End-to-End Contract & Type Safety

- **Shared Contracts**:
  - Never maintain duplicate, disconnected TypeScript interfaces for backend API payloads.
  - Generate TypeScript client types directly from C# OpenAPI / Swagger specs (via NSwag / openapi-typescript) or maintain a shared schema package (`@workspace/types`).
- **Boundary Validation**:
  - Backend must validate incoming requests (FluentValidation in .NET, Zod in Node).
  - Frontend must validate untrusted or dynamic third-party API payloads via Zod before rendering.

---

## 2. State Synchronization & Optimistic UI

- **Mutation Workflow (TanStack Query / Angular Signals)**:
  1. *Cancel in-flight queries* for the entity to prevent race condition overwrites.
  2. *Snapshot previous cache state* for potential rollback.
  3. *Optimistically write to local cache* with an ephemeral client ID (`temp_` or `UUIDv7`).
  4. *Dispatch network request*.
  5. *On error*: Restore previous cache snapshot and surface a toast with retry action.
  6. *On success / settle*: Invalidate query keys to re-sync with authoritative server state.

---

## 3. Real-Time & Event Streams (SSE / WebSockets)

- **Connection Resiliency**:
  - Implement exponential backoff with jitter on reconnects (`min: 1s, max: 30s`).
  - Implement bidirectional heartbeat pings to detect half-open TCP connections.
- **Server-Sent Events (SSE) Preference**:
  - Prefer SSE over WebSockets for unidirectional server-to-client notifications (order status changes, dashboard updates, background job progress). It uses standard HTTP and traverses proxies cleanly.

---

## 4. Fullstack Security Boundary

- **Credential Storage**:
  - Never store access tokens in `localStorage` or `sessionStorage` (vulnerable to XSS).
  - Use `HttpOnly`, `Secure`, `SameSite=Lax` cookies for browser authentication.
- **CSRF Defense**:
  - Protect state-changing mutations with custom headers (`X-Requested-With` or Anti-Forgery tokens).

---

## 5. ⚡ Token-Saving Output Rule
- Provide only the shared DTO, the API endpoint handler, and the client mutation hook/signal. Never re-print full project trees or redundant scaffolding.
