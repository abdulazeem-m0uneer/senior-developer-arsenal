---
name: ui-ux-architect
description: Senior UI/UX and design system architecture skill. Implements DTCG tokens, state-complete components, WCAG 2.2 AA accessibility, and production design systems. Use when the user asks to design UI components, create design tokens, or structure a design system. Triggers on: "design component", "create tokens", "DTCG tokens", "design system". Do not use for automated slop auditing (use ui-ux-audit) or client re-render profiling (use frontend-audit).
---

# UI/UX & Design System Architecture Skill

This skill equips the agent to act as a **Senior Design Architect**, building and auditing production-grade design systems, DTCG tokens, accessible components, and anti-slop interfaces.

---

## 1. When to Use This Skill

Activate this skill when:
- Designing or architecting component systems (React, Angular, HTML/Tailwind, or Native UI).
- Formulating, extending, or validating **DTCG design tokens** (`$type`, `$value`).
- Implementing state-complete UI controls (Default, Hover, Active, Focus-Visible, Disabled, Loading).
- Auditing screens against **WCAG 2.2 AA/AAA** accessibility (contrast, target sizing, keyboard navigation).
- Eliminating generic AI design slop (emojis in UI, em-dashes in copy, identical stat cards, harsh pure black/white).

---

## 2. Architecture & Design Protocol

### Step 1: Brief Inference (Decide Before Generating)
Before writing markup or CSS, determine and commit to:
1. **Domain & Density**: Enterprise/Fintech (dense, high information ratio) vs. Consumer (spacious, focal).
2. **Mood & Hierarchy**: "Precise", "Editorial", "Industrial", or "Utilitarian".
3. **Layout Rhythm**: Asymmetric bento grid, hero metric leading at $\ge 2.5\times$ body size. Never 3 equal cards.

### Step 2: Token Scaffolding
Consult: [DTCG Design Tokens Architecture](./references/dtcg-tokens.md)
- Ensure 3 tiers: Primitives $\rightarrow$ Semantic Aliases $\rightarrow$ Component Tokens.
- Map actions strictly by intent (`action.destructive` for danger; neutral outline for secondary).

### Step 3: State-Complete Component Engineering
Ensure all 6 interactive states are implemented:
- Default, Hover ($\Delta L \approx 4\text{--}8\%$), Active (scale $0.98$), Focus-Visible (2px outline + 2px offset), Disabled (`aria-disabled="true"`), and Loading (preserved dimensions + spinner).

---

## 3. Verification Protocol (The 10 Anti-Slop Gates)

Consult: [The 10 Anti-Slop Verification Gates](./references/anti-slop-gates.md)

Before marking any UI task complete, verify against the 10 gates:
1. **Zero-Emoji Gate**: No emoji in UI or code; inline SVGs with `currentColor` only.
2. **Intent Token Gate**: Red/danger for destructive actions; blue Delete button fails build.
3. **Contrast Gate**: WCAG 2.2 AA ($\ge 4.5:1$ normal text, $\ge 3:1$ large/UI boundaries).
4. **State Completeness Gate**: All 6 states defined; `:focus-visible` ring preserved.
5. **Target Size Gate**: Targets $\ge 24\times 24$px desktop, $\ge 44\times 44$px touch, $\ge 48\times 48$px POS.
6. **Responsive Gate**: Fluid down to 280px without horizontal scrollbar.
7. **Keyboard & Focus Gate**: Full Tab navigation, Escape to close, focus trapped in modals.
8. **Anti-AI Copy Gate**: No em-dashes (`—`), no marketing filler ("elevate", "seamless").
9. **Visual Hierarchy Gate**: Hero metric $\ge 2.5\times$ body size; asymmetric layout.
10. **Theme Parity Gate**: CSS variables only; zero hardcoded hex colors in components.

---

## 4. ⚡ Token-Saving Execution Rule

- **Targeted Output**: Output only the modified component snippet, template, or CSS/Tailwind classes.
- **Verification Matrix**: When auditing, output a compact Markdown table (`Gate`, `Component`, `Status`, `Surgical Fix`). Never dump full unmodified page source.
