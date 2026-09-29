# Design Tokens Community Group (DTCG) Architecture

Reference guide for authoring, structuring, and consuming production design tokens.

---

## 1. DTCG Format Specification

All token files adhere to the DTCG specification using `$value`, `$type`, and optional `$description`:

```json
{
  "color": {
    "brand": {
      "primary": {
        "$value": "#2563EB",
        "$type": "color",
        "$description": "Core brand identity color"
      }
    }
  }
}
```

---

## 2. Three-Tier Token Architecture

```text
┌────────────────────────────────────────────────────────┐
│ COMPONENT TOKENS (Scoped to UI components)             │
│ button.primary.bg -> {semantic.action.primary}         │
├────────────────────────────────────────────────────────┤
│ SEMANTIC ALIASES (Purpose & context)                   │
│ action.primary -> {primitive.color.blue.600}           │
│ surface.page   -> {primitive.color.neutral.50}         │
├────────────────────────────────────────────────────────┤
│ PRIMITIVE TOKENS (Raw values - never used in markup)   │
│ color.blue.600 -> #2563EB                              │
│ space.4        -> 16px                                 │
└────────────────────────────────────────────────────────┘
```

---

## 3. Standard Semantic Taxonomy

### A. Color Semantics
- `surface.canvas`: App background (Light: `#F9FAFB`, Dark: `#0B0F19`).
- `surface.card`: Card / container fill (Light: `#FFFFFF`, Dark: `#111827`).
- `surface.subtle`: Secondary container (Light: `#F3F4F6`, Dark: `#1F2937`).
- `text.primary`: High-contrast body text (Light: `#111827`, Dark: `#F9FAFB`).
- `text.secondary`: Muted descriptive text (Light: `#4B5563`, Dark: `#9CA3AF`).
- `border.subtle`: Dividers and card borders (Light: `#E5E7EB`, Dark: `#374151`).
- `action.primary`: Main affirmative button (`#2563EB`).
- `action.destructive`: Dangerous / irreversible action (`#DC2626`).
- `action.warning`: Cautionary action (`#D97706`).
- `action.success`: Affirmation and success indicators (`#16A34A`).

### B. Typography Scale (Major Third - 1.25 Modular Ratio)
Base font size = 16px (1rem).
- `type.scale.xs`: 12px (0.75rem) - Badges, metadata.
- `type.scale.sm`: 14px (0.875rem) - Secondary body, table cells.
- `type.scale.base`: 16px (1rem) - Standard body copy, inputs.
- `type.scale.md`: 20px (1.25rem) - Card titles, subheadings.
- `type.scale.lg`: 25px (1.5625rem) - Section headers (h3).
- `type.scale.xl`: 31.25px (1.953rem) - Page headers (h2).
- `type.scale.xxl`: 39px (2.441rem) - Hero metrics, display titles (h1).

### C. Spacing Scale (4px Base Unit)
- `space.1`: 4px - Tight icon gaps.
- `space.2`: 8px - Button internal vertical padding, badge margins.
- `space.3`: 12px - Input field vertical padding.
- `space.4`: 16px - Standard grid gutter, button horizontal padding.
- `space.6`: 24px - Card internal padding.
- `space.8`: 32px - Section spacing, modal margins.
- `space.12`: 48px - Macro section transitions.

### D. Corner Radii & Elevation
- `radius.sm`: 4px - Badges, tags.
- `radius.md`: 8px - Buttons, inputs, dropdown items.
- `radius.lg`: 12px - Cards, dialog boxes.
- `radius.full`: 9999px - Circular avatars, pills.
- `elevation.0`: Flat, 1px border.
- `elevation.1`: 0 1px 3px rgba(0,0,0,0.08) - Resting cards.
- `elevation.2`: 0 4px 6px -1px rgba(0,0,0,0.1) - Dropdowns, popovers.
- `elevation.3`: 0 10px 15px -3px rgba(0,0,0,0.15) - Modal dialogs.

---

## 4. CSS Variable Compilation

Tokens compile into CSS Custom Properties for zero-runtime performance:

```css
:root {
  --color-surface-canvas: #F9FAFB;
  --color-surface-card: #FFFFFF;
  --color-text-primary: #111827;
  --color-action-destructive: #DC2626;
  --space-4: 16px;
  --radius-md: 8px;
}

[data-theme="dark"] {
  --color-surface-canvas: #0B0F19;
  --color-surface-card: #111827;
  --color-text-primary: #F9FAFB;
  --color-action-destructive: #EF4444;
}
```
