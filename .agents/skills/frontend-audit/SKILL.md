---
name: frontend-audit
description: Senior frontend performance, re-render, and accessibility audit workflow for React and Angular. Use when the user asks to audit frontend performance, fix unnecessary re-renders, inspect change detection, or runs /frontend-audit. Triggers on: "frontend audit", "audit renders", "re-render churn", "OnPush audit", "/frontend-audit". Do not use for UI/UX visual taste and design tokens (use ui-ux-audit) or backend profiling (use perf-audit).
---

# Frontend Performance & Re-render Audit Skill

Follow this procedure when diagnosing client-side rendering bottlenecks, redundant re-renders, and change-detection inefficiencies in React and Angular.

---

## 1. When to Use This Skill

Activate this skill when:
- React components re-render excessively due to unstable prop references, context churn, or redundant effects.
- Angular applications suffer from default change detection overhead or eager rendering of offscreen components.
- The user runs the `/frontend-audit` slash command.

*Boundary*: For UI/UX design tokens, WCAG 2.2 touch sizing, and anti-slop verification, use `ui-ux-audit`. For server-side event loop or database latency, use `perf-audit`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: State Hierarchy & Prop Stability Audit
Consult: [Frontend Render Profiling Reference](./references/render-profiling.md)
1. **React**:
   - Inspect components for inline objects/functions passed to `React.memo` children.
   - Flag `useEffect` used to synchronize derived state; convert to synchronous render computations.
   - Verify list renderings $> 100$ items use `@tanstack/react-virtual`.
2. **Angular**:
   - Ensure `changeDetection: ChangeDetectionStrategy.OnPush` is present on all components.
   - Replace template getters with `computed()` signals.
   - Wrap heavy below-the-fold views in `@defer (on viewport)`.

### Step 2: Bundle & Loading Optimization
- Verify route-level code splitting (`React.lazy` or Angular `loadChildren`).
- Verify image assets use modern optimized image components (`NgOptimizedImage` or `next/image`).

### Step 3: Accessibility & DOM Sanity
- Ensure interactive elements are keyboard focusable and icon buttons possess `aria-label`.

---

## 3. Verification Protocol

Output findings in a compact Markdown table:

| Location | Dimension | Issue | Severity | Surgical Fix |
| :--- | :--- | :--- | :---: | :--- |
| `UserList.tsx:42` | Re-render | Inline object prop in `.map()` | `⚡ [Perf]` | Hoist object outside loop or memoize |
| `OrderCard.ts:18` | Change Detection | Missing `OnPush` strategy | `⚡ [Perf]` | Set `changeDetection: ChangeDetectionStrategy.OnPush` |

---

## 4. ⚡ Token-Saving Execution Rule

- Provide only the findings table and 2–5 line surgical code fixes.
- Never reprint entire unchanged component templates.
