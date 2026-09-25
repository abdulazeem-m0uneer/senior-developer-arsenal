---
name: frontend-architecture-expert
description: Senior frontend architecture skill for React (18/19) and Angular (17/18/19). Use when designing components, optimizing client-side performance, eliminating unnecessary re-renders, configuring Signals/Hooks, or auditing web accessibility.
---

# Frontend Architecture Skill (React & Angular)

This skill guides the agent in designing high-performance, accessible, and maintainable web applications across modern React and Angular.

---

## 1. When to Use This Skill

Activate this skill when:
- Architecting React component trees (RSC, Client boundaries, hooks, context).
- Migrating or building Angular applications with Signals, Standalone Components, and `@defer`.
- Diagnosing render performance bottlenecks (React DevTools Profiler, Angular OnPush change detection).
- Implementing responsive, accessible UI patterns adhering to WCAG 2.1 AA.
- Structuring client state management (Zustand, TanStack Query, SignalStore).

---

## 2. Framework Execution Runbooks

### A. React Performance Runbook
Consult: [React Performance & Concurrency Guide](./references/react-performance.md)
1. **Render Profiling**: Identify components re-rendering unnecessarily due to unstable prop references.
2. **State Colocation**: Push state down as close as possible to the consuming component. Do not lift state to root contexts unless shared globally.
3. **List Virtualization**: Integrate `@tanstack/react-virtual` for datasets exceeding 100 DOM elements.

### B. Angular Signals & OnPush Runbook
Consult: [Angular Signals & Modern Best Practices](./references/angular-signals-best-practices.md)
1. **Signal State**: Replace mutable component properties with `signal<T>()`.
2. **Derived Reactivity**: Use `computed()` for calculated state; never recalculate in template getters.
3. **OnPush Strategy**: Set `changeDetection: ChangeDetectionStrategy.OnPush` on every component.
4. **Deferred Loading**: Wrap heavy charts, tables, or modals in `@defer (on viewport)`.

---

## 3. ⚡ Token-Saving Execution Rule

- **Targeted Code Output**: Output only the modified JSX/TSX component or Angular TypeScript/HTML snippet.
- **Concise Performance Analysis**: Summarize re-render bottlenecks and a11y violations in compact tables (`Location`, `Issue`, `Fix`). Never dump full component trees.
