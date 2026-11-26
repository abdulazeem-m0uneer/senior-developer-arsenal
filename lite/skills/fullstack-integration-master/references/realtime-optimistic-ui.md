# Real-Time Events & Optimistic UI Mutations

Architectural patterns for resilient UI state synchronization and rollback safety.

---

## 1. TanStack Query Optimistic Mutation Pattern

```typescript
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api';

export function useUpdateOrderStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: OrderStatus }) =>
      api.PATCH('/orders/{id}/status', { params: { path: { id } }, body: { status } }),

    onMutate: async ({ id, status }) => {
      // 1. Cancel outgoing refetches so they don't overwrite optimistic update
      await queryClient.cancelQueries({ queryKey: ['orders', id] });

      // 2. Snapshot current state for rollback
      const previousOrder = queryClient.getQueryData(['orders', id]);

      // 3. Optimistically update local cache
      queryClient.setQueryData(['orders', id], (old: any) => ({
        ...old,
        status,
        updatedAt: new Date().toISOString()
      }));

      // 4. Return context containing rollback snapshot
      return { previousOrder };
    },

    onError: (err, newTodo, context) => {
      // Rollback to previous state on network failure
      if (context?.previousOrder) {
        queryClient.setQueryData(['orders', context.previousOrder.id], context.previousOrder);
      }
    },

    onSettled: (data, error, variables) => {
      // Always invalidate to synchronize with authoritative server data
      queryClient.invalidateQueries({ queryKey: ['orders', variables.id] });
    }
  });
}
```

---

## 2. Server-Sent Events (SSE) Stream Integration

Prefer SSE over WebSockets for lightweight, unidirectional real-time updates:

```typescript
export function subscribeToOrderEvents(orderId: string, onUpdate: (event: any) => void) {
  const eventSource = new EventSource(`/api/v1/orders/${orderId}/live-events`);

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    onUpdate(data);
  };

  eventSource.onerror = (err) => {
    console.error('SSE connection lost, browser auto-reconnecting...', err);
  };

  // Return cleanup function to close connection
  return () => eventSource.close();
}
```
