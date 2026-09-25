# Senior Frontend Engineering Standards (React & Angular)

These rules enforce modern, accessible, and high-performance frontend architecture across **React** (18/19) and **Angular** (17/18/19).

---

## 1. Core Principles (Both Frameworks)

- **State Hierarchy**:
  1. *Server Cache*: TanStack Query / SWR / Angular HttpClient + Signals. Do not duplicate server state into client state.
  2. *URL State*: Store search filters, pagination, active tabs, and modals in query params (`useSearchParams` / Router).
  3. *Client UI State*: Ephemeral UI state (open dropdowns, drawer toggles) using Zustand or framework signals.
- **Derived State**: Never use side-effects (`useEffect` or `effect()`) to synchronize state that can be synchronously computed.
- **Accessibility (a11y) & Semantic HTML**:
  - Always use native interactive elements (`<button>`, `<a>`, `<input>`).
  - Provide accessible names via `aria-label` or visible text for icon-only buttons.
  - Ensure complete keyboard operability (Tab, Enter, Escape).

---

## 2. React Standards (18/19)

- **Server Components (RSC) vs Client Components**:
  - Keep components Server Components by default.
  - Push `"use client"` down the component tree to the leaf interactive nodes (buttons, inputs, animated wrappers).
- **Render Optimization**:
  - Avoid object/array literals as props inside tight loop renders without memoization.
  - Use `@tanstack/react-virtual` for lists containing >100 items.
  - Do not use `useMemo`/`useCallback` prematurely; profile re-render bottlenecks first.
- **Clean Hooks**:
  - Keep effects strictly for synchronization with external non-React systems (timers, DOM events, WebSockets).
  - Always return cleanup functions in effects to prevent memory leaks and duplicate listeners.

---

## 3. Angular Standards (17/18/19)

- **Standalone & Signal-First Architecture**:
  - Author components with `standalone: true`. Eliminate legacy `NgModule` unless maintaining legacy packages.
  - Use **Signals** (`signal()`, `computed()`) for component reactivity.
  - Convert RxJS streams to signals via `toSignal()` at consumption boundaries.
- **Change Detection**:
  - Mandate `changeDetection: ChangeDetectionStrategy.OnPush` on every component.
- **Deferrable Views (`@defer`)**:
  - Wrap below-the-fold, heavy, or conditional UI sections with `@defer (on viewport)` or `@defer (on idle)` with `@placeholder` and `@loading` blocks.
- **Assets & Media**:
  - Mandate `NgOptimizedImage` for image assets to prevent Cumulative Layout Shift (CLS) and enforce responsive sizing.

---

## 4. ⚡ Token-Saving Output Rule
- Output only the specific component template, hook, or signal declaration. Never print unchanged entire component trees or generic CSS files.
