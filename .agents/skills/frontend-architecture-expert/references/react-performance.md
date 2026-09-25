# React Performance & Concurrency Reference

Guidelines for maintaining 60fps UI, low Time-to-Interactive (TTI), and minimal re-render churn in React 18/19.

---

## 1. Re-render Mitigation Patterns

### Pattern 1: Component Composition Over Lifting State
Passing down components as `children` or slots isolates state updates to the parent without re-rendering the children:
```tsx
// ✅ Good: ExpensiveTree does NOT re-render when count increments
export function CounterWrapper({ children }: { children: React.ReactNode }) {
  const [count, setCount] = useState(0);
  return (
    <div>
      <button onClick={() => setCount(c => c + 1)}>Count: {count}</button>
      {children}
    </div>
  );
}
```

### Pattern 2: Selective Subscriptions with Zustand
Avoid context providers that cause entire trees to re-render when a single property updates:
```tsx
// ✅ Good: Only re-renders when activeTab changes
const activeTab = useAppStore(state => state.activeTab);
```

### Pattern 3: Transition & Deferred Values
Keep inputs responsive during expensive filtering operations:
```tsx
const [isPending, startTransition] = useTransition();

function handleSearch(query: string) {
  setSearchText(query); // urgent update
  startTransition(() => {
    setFilteredQuery(query); // non-urgent background render
  });
}
```

---

## 2. Server Components (RSC) Boundaries

- Place data-fetching Server Components at the layout/page level.
- Keep `"use client"` files small and focused solely on browser interactions:
```tsx
// ProductPage.tsx (Server Component - 0KB JS bundle sent to client)
import { ProductGallery } from './ProductGallery'; // Client Component

export default async function ProductPage({ params }: { params: { id: string } }) {
  const product = await db.products.findById(params.id); // Direct DB query on server
  return (
    <main>
      <h1>{product.name}</h1>
      <ProductGallery images={product.images} />
    </main>
  );
}
```
