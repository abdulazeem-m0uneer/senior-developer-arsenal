# Senior API Design Standards (REST & RPC)

Reference guide for designing enterprise RESTful and RPC API contracts.

---

## 1. URL Path & Resource Hierarchy

- Use plural nouns for resources: `/api/v1/orders`, `/api/v1/orders/{orderId}/items`.
- Avoid verbs in REST paths: Use HTTP methods (`POST`, `GET`, `PUT`, `PATCH`, `DELETE`) to denote operations.
- Non-CRUD operations: Use explicit sub-resource action paths:
  - `POST /api/v1/orders/{orderId}/cancel`
  - `POST /api/v1/users/{userId}/reset-password`

---

## 2. Idempotency & Verbs

- `GET`: Safe, idempotent, cacheable. Never mutates server state.
- `PUT`: Idempotent full replacement. Client provides entire resource representation.
- `PATCH`: Non-idempotent or idempotent partial update. Use JSON Merge Patch (`application/merge-patch+json`) or standard DTO.
- `DELETE`: Idempotent removal. Return `204 No Content` or `200 OK` with deleted entity metadata.
- `POST`: Non-idempotent creation or execution. Support `Idempotency-Key` header on critical paths (payments, orders).

---

## 3. RFC 7807 Problem Details Error Format

Standard error response envelope (`application/problem+json`):

```json
{
  "type": "https://api.example.com/errors/validation-failed",
  "title": "Validation Failed",
  "status": 400,
  "detail": "One or more parameters in the request failed validation.",
  "instance": "/api/v1/orders",
  "errors": {
    "items": ["Order must contain at least one item."],
    "paymentMethod": ["Invalid payment method specified."]
  }
}
```

---

## 4. Pagination & Filtering

- **Cursor Pagination** (Recommended for high volume):
  - `GET /api/v1/orders?cursor=eyJpZCI6MTIzfQ&limit=25`
  - Returns `items: []`, `nextCursor: string | null`, `hasMore: boolean`.
- **Offset Pagination** (Only for bounded, small datasets):
  - `GET /api/v1/orders?page=1&pageSize=20`
  - Never allow unbounded queries; enforce server-side maximum `pageSize` (e.g., max 100).
