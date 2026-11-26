# End-to-End Type Safety & Contract Generation

Techniques for maintaining unbreakable type safety between backend and frontend codebases.

---

## 1. C# ASP.NET Core $\to$ TypeScript Contract Mapping

When the backend is .NET and the frontend is TypeScript (React/Angular):
1. **OpenAPI Generator**: Configure ASP.NET Core to generate an `openapi.json` contract at build time.
2. **Client Type Synthesis**:
   ```bash
   # Generate pristine TypeScript types from OpenAPI spec
   npx openapi-typescript ./swagger.json -o ./src/api/schema.d.ts
   ```
3. **Type-Safe Fetcher**:
   ```typescript
   import createClient from 'openapi-fetch';
   import type { paths } from './schema';

   export const api = createClient<paths>({ baseUrl: '/api/v1' });

   // Fully type-safe: compiler autocompletes params, body, and return types
   const { data, error } = await api.GET('/orders/{id}', {
     params: { path: { id: orderId } }
   });
   ```

---

## 2. Node.js $\to$ TypeScript Shared Contracts

When using a Node.js backend (Fastify/Express):
- Export Zod schemas from a shared package (`packages/shared-contracts`):
```typescript
// shared-contracts/order.ts
import { z } from 'zod';

export const CreateOrderSchema = z.object({
  customerId: z.string().uuid(),
  items: z.array(z.object({
    productId: z.string().uuid(),
    quantity: z.number().int().positive()
  })).min(1),
  notes: z.string().max(500).optional()
});

export type CreateOrderInput = z.infer<typeof CreateOrderSchema>;
```
- Backend validates with `CreateOrderSchema.parse(req.body)`.
- Frontend forms validate with the exact same `CreateOrderSchema` using React Hook Form / Angular Reactive Forms.
