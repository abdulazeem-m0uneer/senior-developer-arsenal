---
name: nodejs-backend-expert
description: Specialized Node.js and TypeScript backend engineering skill. Use when developing, profiling, refactoring, or securing production-grade Node.js servers (Fastify, Express, NestJS), managing async event loops, streams, and database connectivity. Triggers on: "Node.js", "TypeScript backend", "Fastify", "Express", "NestJS", "event loop lag", "stream backpressure". Do not use for Python services (use python-backend-expert) or .NET services (use csharp-dotnet-expert).
---

# Node.js & TypeScript Backend Engineering Skill

This skill guides the agent in developing robust, resilient, and non-blocking Node.js services.

---

## 1. When to Use This Skill

Activate this skill when:
- Designing or maintaining Fastify, Express, or NestJS APIs.
- Profiling or diagnosing event loop lag, memory leaks, and GC pauses.
- Implementing streaming data pipelines with backpressure (`stream.pipeline`).
- Hardening application security (Zod schema validation, CORS, CSP, rate limiting).
- Structuring modular TypeScript backends with clean domain separation.

*Boundary*: For C# / .NET services, use `csharp-dotnet-expert`. For Python services, use `python-backend-expert`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Non-Blocking Event Loop Architecture
Consult: [Event Loop Performance & Profiling](./references/event-loop-perf.md)
- Never execute synchronous CPU-intensive operations (hashing, large regex, large array transforms) on the primary event loop.
- Offload intensive workloads using Node.js `worker_threads` or asynchronous job queues.
- Monitor event loop latency using `perf_hooks.monitorEventLoopDelay()`.

### Step 2: Defensive Security & Boundary Validation
Consult: [Node.js Security Reference](./references/node-security.md)
- Validate every request body, query parameter, and route parameter with Zod before domain logic execution.
- Mount `helmet` middleware for HTTP security header protection.
- Implement rate-limiting on sensitive and resource-heavy routes.
- Prevent prototype pollution by using `Object.create(null)` or `Map` collections for dynamic dictionaries.

### Step 3: Resilient Process Lifecycle & Graceful Shutdown
Equip HTTP servers with graceful termination handling:
```typescript
import { createServer } from 'http';
import { pool } from './database.js';

const server = createServer(app);

async function handleShutdown(signal: string) {
  server.close(() => console.log('HTTP server closed.'));
  try {
    await pool.end();
    process.exit(0);
  } catch (err) {
    process.exit(1);
  }
}

process.on('SIGTERM', () => handleShutdown('SIGTERM'));
process.on('SIGINT', () => handleShutdown('SIGINT'));
```

---

## 3. Verification Protocol

Verify the codebase using npm/pnpm commands:
```bash
# 1. Type check without emitting files
npx tsc --noEmit

# 2. Run linter
npm run lint

# 3. Run unit & integration tests
npm test
```
Report status in a single line: `✅ Typecheck, Lint & Tests Passed`.

---

## 4. ⚡ Token-Saving Execution Rule

- Output only modified TypeScript functions, Zod schemas, or handlers. Never paste entire service files.
- Summarize linting and test results in a single line. Omit verbose npm headers.
