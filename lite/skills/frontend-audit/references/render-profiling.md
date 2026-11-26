# Frontend Render Profiling & Performance Reference

Audit guide for diagnosing client-side rendering bottlenecks in React and Angular.

---

## 1. React Re-render Bottlenecks

### Common Culprits
1. **Unstable Prop References**: Passing inline object literals `style={{ margin: 0 }}` or inline arrow functions `onClick={() => doSomething()}` to memoized children in tight loops.
2. **Context Over-subscription**: Using a monolithic global context where updating one property re-renders every consuming component.
   - *Fix*: Split context or use Zustand atomic selectors: `useStore(state => state.activeId)`.
3. **Derived State Synchronization via Effects**: Using `useEffect` to copy props into state or synchronize calculations.
   - *Fix*: Compute derived state synchronously during render: `const filtered = useMemo(() => items.filter(...), [items])`.
4. **Unvirtualized DOM Lists**: Rendering $> 100$ items simultaneously without DOM recycling.
   - *Fix*: Integrate `@tanstack/react-virtual`.

---

## 2. Angular Change Detection & Performance

1. **Missing OnPush**: Default change detection checks entire component tree on every browser event.
   - *Fix*: Set `changeDetection: ChangeDetectionStrategy.OnPush` on every component.
2. **Signals vs Getters**: Recalculating expensive operations in template getters `get total() { ... }`.
   - *Fix*: Use `computed(() => ...)` for automatic memoization and fine-grained dependency tracking.
3. **Heavy Below-the-Fold Views**: Rendering offscreen charts, tables, or modals eagerly.
   - *Fix*: Wrap with `@defer (on viewport)` and `@placeholder`.
