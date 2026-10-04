---
name: ui-ux-audit
description: 'Senior UI/UX and design audit workflow. Evaluates screens and components against 10 anti-slop gates, DTCG token compliance, state completeness, and WCAG 2.2 AA. Use when the user asks to audit UI, check anti-slop gates, verify contrast/touch targets, or runs /ui-ux-audit. Triggers on: "ui audit", "ux audit", "anti-slop audit", "audit contrast", "/ui-ux-audit". Do not use for frontend client re-render profiling (use frontend-audit) or backend profiling (use perf-audit).'
---

# UI/UX & Design Audit Workflow Skill

Follow this procedure when auditing or reviewing user interfaces, components, or design tokens against objective production criteria.

---

## 1. When to Use This Skill

Activate this skill when:
- Auditing web or native UI components for accessibility (WCAG 2.2 AA contrast and touch target sizing).
- Scanning for AI-generated design slop (emojis in UI, em-dashes in copy, identical stat cards, harsh pure black/white).
- Checking component state completeness (Default, Hover, Active, Focus-Visible, Disabled, Loading).
- The user runs the `/ui-ux-audit` slash command.

*Boundary*: For React/Angular re-render churn and memoization profiling, use `frontend-audit`. For code reviews, use `code-review`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Automated Verification Scan
Run the automated verification script bundled with this skill (path is relative to this skill's directory):
```bash
python scripts/verify_ui_ux.py <target-path>
```
Flags Unicode emojis, em-dashes, marketing fluff, and mismatched intent tokens.

### Step 2: Execute the 10 Anti-Slop Gates
Consult the anti-slop gates reference (`references/anti-slop-gates.md`) of the `ui-ux-architect` skill.
1. **Zero-Emoji Gate**: Zero emoji glyphs in UI; Lucide SVG with `currentColor` only.
2. **Intent Token Gate**: Red/danger for destructive actions; blue Delete button fails.
3. **Contrast Gate**: WCAG 2.2 AA ($\ge 4.5:1$ text, $\ge 3:1$ UI boundaries).
4. **State Completeness Gate**: All 6 states defined; `:focus-visible` ring preserved.
5. **Target Size Gate**: Targets $\ge 24\times 24$px desktop, $\ge 44\times 44$px touch, $\ge 48\times 48$px POS.
6. **Responsive Gate**: Fluid down to 280px without horizontal scrollbar.
7. **Keyboard & Focus Gate**: Full Tab navigation, Escape to close, focus trapped in modals.
8. **Anti-AI Copy Gate**: No em-dashes (`—`), no marketing filler ("elevate", "seamless").
9. **Visual Hierarchy Gate**: Hero metric $\ge 2.5\times$ body size; asymmetric layout.
10. **Theme Parity Gate**: CSS variables only; zero hardcoded hex colors in components.

### Step 3: Format the Audit Matrix
Consult: [Audit Matrix Template](./references/audit-matrix-template.md)
Produce a dense Markdown table reporting status per gate with actionable, surgical fixes.

---

## 3. Verification Protocol

1. Run this skill's `scripts/verify_ui_ux.py` against the project root to ensure automated gates pass.
2. Verify all failing gates in the matrix have corresponding 2–5 line surgical unified diffs.

---

## 4. ⚡ Token-Saving Execution Rule

- Deliver the structured matrix and surgical diffs only.
- Never reprint entire page source code or generic styles.
