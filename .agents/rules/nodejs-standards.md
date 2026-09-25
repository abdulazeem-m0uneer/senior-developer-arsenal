# Node.js & TypeScript Senior Engineering Standards

These rules enforce high-throughput, secure, and production-hardened Node.js backend services.

---

## 1. Modern TypeScript & Project Conventions

- **Strict Type Checking**:
  - Always enable `"strict": true`, `"noImplicitAny": true`, `"noImplicitReturns": true`, and `"noUncheckedIndexedAccess": true` in `tsconfig.json`.
  - Avoid `any`. Use `unknown` with type narrowing (type guards, Zod schemas) or generics.
- **Module System**:
  - Use ECMAScript Modules (`"type": "module"`). Use explicit file extensions in relative imports if required by module resolution.
- **Clean Architecture / Layering**:
  - **Routes / Controllers**: Parse HTTP requests, validate input via Zod, invoke application services, format responses.
  - **Services / Domain**: Business logic, transactional workflows, domain events. No raw HTTP request/response objects here.
  - **Data Access / Repositories**: Encapsulate database queries (`pg`, `Kysely`, `Drizzle`, `Prisma`), mapping rows to typed models.

---

## 2. Event Loop & Performance Guardrails

- **Zero Blocking of the Event Loop**:
  - Never call synchronous I/O methods (`fs.readFileSync`, `fs.writeFileSync`, `crypto.pbkdf2Sync`) in request handling hot paths.
  - For CPU-bound tasks (image processing, cryptographic hashing, massive JSON parsing), offload to a `Worker` thread or worker pool.
- **Stream Processing & Backpressure**:
  - When handling large files, CSV exports, or bulk database streams, use `stream.pipeline` or `for await (const chunk of stream)`.
  - Never buffer gigabyte-sized files into memory (`Buffer.concat` or string accumulation).
- **Memory Leak Prevention**:
  - Clean up event listeners (`emitter.removeListener`) and timers (`clearTimeout`, `clearInterval`).
  - Avoid global caching variables without eviction policies (use LRU caches with explicit size bounds).

---

## 3. Resilience, Error Handling & Lifecycle

- **Graceful Shutdown**:
  - Catch `SIGTERM` and `SIGINT`.
  - Step 1: Stop accepting new HTTP requests (`server.close()`).
  - Step 2: Allow in-flight requests to complete with a reasonable timeout (e.g. 10–15 seconds).
  - Step 3: Drain and disconnect database connection pools (`pool.end()`).
  - Step 4: Exit process cleanly (`process.exit(0)`).
- **Promise & Error Propagation**:
  - Always handle async errors. In Express, forward to `next(err)` or use `express-async-errors`. Fastify handles async rejections natively.
  - Listen for `unhandledRejection` and `uncaughtException` in process root, log error with structured metadata, and perform a controlled restart.
- **Result & Error Patterns**:
  - Define explicit custom error classes (e.g., `NotFoundError`, `UnauthorizedError`, `ConflictError`, `ValidationError`).
  - Map errors to standardized JSON responses with error codes and request correlation IDs.

---

## 4. Security & Production Hardening

- **Boundary Validation**:
  - Validate all incoming request payloads (`body`, `query`, `params`) using **Zod** or **Valibot**. Strip unknown/malicious properties before processing.
- **HTTP Headers & Defenses**:
  - Use `helmet` to set secure HTTP headers (HSTS, Content Security Policy, X-Content-Type-Options, Frameguard).
  - Configure CORS strictly. Never use `origin: "*"` in authenticated APIs with cookie credentials.
- **Rate Limiting**:
  - Apply rate limiting on authentication routes (login, password reset, MFA) and public mutation endpoints to prevent brute-force and DoS.
- **Safe SQL / Querying**:
  - Always use parameterized queries with `pg` (`$1, $2`), `kysely`, or `drizzle`. Never interpolate user input directly into SQL strings.
