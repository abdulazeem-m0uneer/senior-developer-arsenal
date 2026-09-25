# Node.js Event Loop Performance & Memory Management

Guidelines for maintaining low latency, zero event-loop blocking, and leak-free memory usage in Node.js applications.

---

## 1. Event Loop Golden Rules

1. **Avoid Synchronous I/O in Handlers**:
   - ❌ `fs.readFileSync`, `fs.writeFileSync`, `child_process.execSync`
   - ✅ `import { readFile } from 'fs/promises'; await readFile(...)`
2. **Prevent ReDoS (Regular Expression Denial of Service)**:
   - Avoid nested quantifiers like `(a+)+$` or `(a|aa)+$`.
   - Prefer parser combinators or strict string splitting over complex catastrophic-backtracking regexes.
3. **Partition Long Synchronous Computations**:
   - If an array transformation exceeds 10ms, yield to the event loop using `setImmediate()` or offload to a worker.

---

## 2. Worker Threads for CPU-Intensive Tasks

For cryptographic operations (scrypt, argon2 in bulk), image processing, or heavy parsing, use Node's `worker_threads`:

```typescript
import { Worker, isMainThread, parentPort, workerData } from 'worker_threads';

export function runWorkerTask<TInput, TOutput>(workerFile: string, data: TInput): Promise<TOutput> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(workerFile, { workerData: data });
    worker.on('message', resolve);
    worker.on('error', reject);
    worker.on('exit', (code) => {
      if (code !== 0) reject(new Error(`Worker stopped with exit code ${code}`));
    });
  });
}
```

---

## 3. Streaming & Backpressure

When exporting thousands of rows or streaming large files to an HTTP response, never load the entire dataset into memory:

```typescript
import { pipeline } from 'stream/promises';
import { createReadStream } from 'fs';
import type { Response } from 'express';

export async function streamFileToClient(filePath: string, res: Response) {
  res.setHeader('Content-Type', 'application/octet-stream');
  const sourceStream = createReadStream(filePath);
  
  // pipeline handles error propagation and automatically closes streams
  await pipeline(sourceStream, res);
}
```

---

## 4. Diagnosing Memory Leaks

Common causes of Node.js memory leaks:
1. **Unbounded Global Collections**: Caching user sessions or tokens in a plain JS object or `Map` without TTL or size eviction. Always use `lru-cache`.
2. **Dangling Event Listeners**: Attaching `emitter.on(...)` repeatedly inside request handlers without calling `emitter.off()`.
3. **Closures Retaining Large Outer Scopes**: Functions keeping references to huge buffers or DOM trees.
