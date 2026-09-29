# The 10 Anti-Slop Verification Gates

Use this checklist to audit screens and components against production-grade design criteria. Each gate is an objective pass/fail condition.

---

## Gate 1: Zero-Emoji Enforcement
- **Requirement**: No Unicode emoji glyphs (e.g. 🚀, 💡, ⚠️, ❌, ✅, 🔍) in templates, SVG text, copy, or button labels.
- **Pass**: All icons use inline SVGs (e.g., Lucide, Heroicons) with `currentColor`, or concise text.
- **Fail**: Emoji used for status badges, search icons, alert indicators, or list bullets.

---

## Gate 2: Intent Token Alignment
- **Requirement**: Component variant must match its semantic action role.
- **Pass**:
  - Primary positive action: `color.action.primary`.
  - Destructive / high-risk action (Delete, Revoke, Ban, Cancel Subscription): `color.action.destructive` (danger).
  - Secondary / dismissive action: Neutral outline or ghost (`color.action.neutral`).
- **Fail**: A blue "Delete Item" button, a red "Save" button, or saturated primary backgrounds on non-affirmative actions.

---

## Gate 3: Contrast Ratio Verification (WCAG 2.2 AA)
- **Requirement**:
  - Normal text ($< 18$pt / $< 24$px): Contrast $\ge 4.5:1$ against underlying surface.
  - Large text ($\ge 18$pt / $\ge 24$px or $\ge 14$pt bold): Contrast $\ge 3:1$.
  - Essential graphical boundaries (input borders, active tab lines): Contrast $\ge 3:1$.
- **Pass**: Real computed contrast passes threshold for both resting AND hover/active states.
- **Fail**: Low-contrast placeholder text ($< 4.5:1$), washed-out badges, or text disappearing on hover.

---

## Gate 4: State Completeness
- **Requirement**: All 6 interactive states defined for every control.
- **Pass**: Explicit styles for:
  1. Default/Rest
  2. Hover
  3. Active/Pressed
  4. Focus-Visible (2px solid outline with 2px offset)
  5. Disabled (`aria-disabled="true"`, muted opacity, pointer-events guarded)
  6. Loading (spinner/skeleton inside fixed-dimension container, full opacity)
- **Fail**: `outline: none` without focus ring; button text shifting layout during loading; disabled state lacking ARIA.

---

## Gate 5: Target Sizing (WCAG 2.5.8 & Ergonomics)
- **Requirement**:
  - Desktop standard: $\ge 24\times 24$px bounding box.
  - Mobile & Touch: $\ge 44\times 44$px bounding box.
  - POS / Kiosk / Touchscreens: $\ge 48\times 48$px with $\ge 8$px spacing buffer.
- **Pass**: Hit area expands beyond visual icon if necessary via padding.
- **Fail**: 16px icon button without padding causing missed clicks on touch screens.

---

## Gate 6: Responsive Overflow & Fluidity
- **Requirement**: Zero horizontal overflow or clipped text at narrow viewport widths (280px, 320px, 375px, 414px).
- **Pass**: Layout wraps gracefully, grid collapses to single column, long strings truncate with ellipsis (`text-overflow: ellipsis`) or wrap.
- **Fail**: Horizontal scrollbar on body at $\le 360$px; fixed pixel container widths (`width: 500px`).

---

## Gate 7: Focus Trap & Keyboard Navigation
- **Requirement**:
  - Tab and Shift+Tab traverse focusable elements in logical visual order.
  - Escape closes modals, drawers, and popovers.
  - Focus is trapped within open modal dialogs (`aria-modal="true"`).
  - Dismissing a modal restores focus to the triggering element.
- **Pass**: Full keyboard operability verified without a mouse.
- **Fail**: Tab leaves modal to background elements; focus lost to document body on close.

---

## Gate 8: Anti-AI Copywriting & Microcopy
- **Requirement**: Clean, concrete, human-sounding interface copy.
- **Pass**: Short, unambiguous action labels ("Export CSV", "Remove Member", "Save Changes").
- **Fail**:
  - Em-dashes (`—`) in headers or descriptions.
  - Marketing buzzwords ("elevate your workflow", "unlock potential", "seamless integration", "supercharge").
  - Triads ("Fast, secure, and intuitive").
  - Generic metadata labels ("SECTION 01", "FEATURE CARD", "TITLE GOES HERE").

---

## Gate 9: Visual Hierarchy & Asymmetric Rhythm
- **Requirement**: Deliberate rhythm and focal points across cards and metrics.
- **Pass**:
  - Hero metric displayed $\ge 2.5\times$ body size with prominent visual weight.
  - Varied card widths / heights in bento arrangements.
  - Restrained elevation: 1px subtle borders or soft layered shadows.
- **Fail**: 3 or 4 identical square cards with identical typography, icons, and equal visual prominence.

---

## Gate 10: Token Compliance & Theme Parity
- **Requirement**: Zero hardcoded hex colors or arbitrary pixel margins in component CSS.
- **Pass**: All styles consume design tokens (`var(--color-...)`, `var(--space-...)`, or Tailwind token classes).
- **Fail**: Hardcoded `#2563EB`, `#1F2937`, or `margin: 17px` found in component styling.
