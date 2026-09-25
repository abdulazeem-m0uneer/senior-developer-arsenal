---
name: nodejs-backend-expert
description: Specialized Node.js and TypeScript backend engineering skill. Use when developing, profiling, refactoring, or securing production-grade Node.js servers (Fastify, Express, NestJS), managing async event loops, streams, and database connectivity.
---

# Node.js & TypeScript Backend Engineering Skill

This skill guides the agent in developing robust, resilient, and non-blocking Node.js services.

---

## 1. When to Use This Skill

Activate this skill when:
- Designing or maintaining Fastify, Express, or NestJS APIs.
- Profiling or diagnosing event loop lag, memory leaks, and GC pauses.
- Implementing streaming data pipelines, backpressure, or worker thread pools.
- Hardening application security (Zod schema validation, CORS, CSP, rate limiting).
- Structuring modular TypeScript backends with clean domain separation.

---

## 2. Core Execution Procedures

### A. Non-Blocking Event Loop Architecture
Refer to the deep-dive: [Event Loop Performance & Profiling](./references/event-loop-perf.md)
- Never execute synchronous CPU-intensive algorithms (hashing, large regex, large array transforms) on the primary event loop.
- Offload intensive workloads using Node.js `worker_threads` or asynchronous job queues.
- Monitor event loop latency using `perf_hooks.monitorEventLoopDelay()`.

### B. Defensive Security & Production Hardening
Refer to the deep-dive: [Node.js Security Reference](./references/node-security.md)
- Validate every request body, query parameter, and route parameter with Zod before domain logic execution.
- Mount `helmet` middleware for HTTP security header protection.
- Implement rate-limiting on sensitive and resource-heavy routes.
- Prevent prototype pollution by using `Object.create(null)` or `Map` collections for dynamic key dictionaries.

### C. Resilient Process Lifecycle & Graceful Shutdown
Always equip HTTP servers with graceful termination handling:
```typescript
import { createServer } from 'http';
import { pool } from './database.js';

const server = createServer(app);

async function handleShutdown(signal: string) {
  console.log(`Received ${signal}. Starting graceful shutdown...`);
  
  // 1. Stop taking new HTTP traffic
  server.close(() => console.log('HTTP server closed.'));

  try {
    // 2. Drain database connection pools
    await pool.end();
    console.log('Database pool drained.');
    process.exit(0);
  } catch (err) {
    console.error('Error during shutdown:', err);
    process.exit(1);
  }
}

process.on('SIGTERM', () => handleShutdown('SIGTERM'));
process.on('SIGINT', () => handleShutdown('SIGINT'));
```

### D. Verification Commands
```bash
# Type check without emitting files
npm run typecheck # or: npx tsc --noEmit

# Run linter
npm run lint

# Run unit & integration tests
npm test
```
