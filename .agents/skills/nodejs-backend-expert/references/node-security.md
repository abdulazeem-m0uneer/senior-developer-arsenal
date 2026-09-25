# Node.js Application Security Hardening

Senior security guidelines for production Node.js services.

---

## 1. Input Validation with Zod

Never accept unvalidated payloads. Validate both shapes and values:

```typescript
import { z } from 'zod';
import type { Request, Response, NextFunction } from 'express';

export const CreateUserSchema = z.object({
  email: z.string().email().max(255).toLowerCase().trim(),
  password: z.string().min(12).max(128),
  role: z.enum(['ADMIN', 'MEMBER', 'VIEWER']),
  organizationId: z.string().uuid()
}).strict(); // strict() rejects unexpected extra fields

export function validateBody<T>(schema: z.ZodSchema<T>) {
  return (req: Request, res: Response, next: NextFunction) => {
    const result = schema.safeParse(req.body);
    if (!result.success) {
      return res.status(400).json({
        type: 'https://api.example.com/errors/validation',
        title: 'Validation Failed',
        status: 400,
        errors: result.error.flatten().fieldErrors
      });
    }
    req.body = result.data;
    next();
  };
}
```

---

## 2. Parameter Pollution & Prototype Pollution

- **Prototype Pollution Prevention**:
  - Never use naive recursive object mergers.
  - When storing dynamic key-value pairs from user input, use `new Map()` or `Object.create(null)` instead of `{}`.
  - Freeze shared prototypes if necessary: `Object.freeze(Object.prototype);`.
- **HTTP Parameter Pollution**:
  - Protect query parsing against array-tampering (e.g. `?id=1&id=2`). Validate types with Zod to enforce scalar values where arrays are not expected.

---

## 3. Timing-Safe Comparisons

When comparing authentication tokens, HMAC signatures, or password hashes:
```typescript
import { timingSafeEqual } from 'crypto';

export function secureCompare(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) {
    return false;
  }
  return timingSafeEqual(bufA, bufB);
}
```

---

## 4. HTTP Headers with Helmet

Always initialize security headers:
```typescript
import helmet from 'helmet';

app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      imgSrc: ["'self'", 'data:', 'https:']
    }
  },
  crossOriginEmbedderPolicy: true,
  crossOriginOpenerPolicy: true,
  crossOriginResourcePolicy: { policy: 'same-origin' }
}));
```
