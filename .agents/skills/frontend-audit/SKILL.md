---
name: frontend-audit
description: Senior frontend performance, re-render, and accessibility audit workflow for React and Angular.
---

# Frontend Audit Workflow

Follow this procedure when reviewing or optimizing frontend applications.

## Steps

1. **State & Re-render Inspection**:
   - In React: Check for unstable object/function props passed to memoized children, redundant effects for derived state, and missing list virtualization.
   - In Angular: Check that `ChangeDetectionStrategy.OnPush` is active and component properties use `signal()` and `computed()` rather than manual dirty-checking.

2. **Bundle & Loading Audit**:
   - Verify code splitting on route boundaries (`React.lazy` / Angular `loadChildren`).
   - Check if heavy below-the-fold components use `@defer (on viewport)` in Angular or dynamic imports in React.
   - Verify image tags use modern responsive optimization (`NgOptimizedImage` or `next/image`).

3. **Accessibility (a11y) & Semantic Checks**:
   - Check for accessible names on icon buttons (`aria-label`).
   - Ensure color contrast and keyboard focus indicators are preserved.

4. **Structured Audit Output**:
   - Output a dense Markdown table (`File:Line`, `Dimension`, `Issue`, `Recommendation`).
   - Provide surgical 2-5 line fixes.
