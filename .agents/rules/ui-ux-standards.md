# Senior UI/UX & Design System Standards

Authoritative rules for architecting accessible, production-grade design systems, DTCG tokens, and user interfaces across React, Angular, Web, and Native.

---

## 1. Decision Hierarchy

Prioritize design decisions strictly in this order:
1. **User Needs**: Does this enable task completion without friction?
2. **Accessibility (POUR)**: Perceivable, Operable, Understandable, Robust. Non-negotiable.
3. **Consistency**: Adherence to design tokens and established component contracts.
4. **Aesthetics & Taste**: Visual hierarchy, intentional typography, restrained depth.
5. **Developer Experience**: Modularity, composability, clean token mapping.

> **Taste never overrides Accessibility**: A brand color that fails WCAG contrast must be adjusted. Beautiful but inaccessible is broken.

---

## 2. DTCG Token Hierarchy (3 Tiers)

All design values follow the **Design Tokens Community Group (DTCG)** architecture:
- **Primitives** (`color.blue.600`, `space.4`): Raw values. Never consume directly in component code.
- **Semantic Aliases** (`surface.canvas`, `text.primary`, `action.destructive`): Purpose-driven mappings.
- **Component Tokens** (`button.primary.bg`, `card.border`): Scoped to specific component slots.

### Token by Intent
- Match token meaning to action role.
- **Destructive Actions** (Delete, Revoke, Remove) must resolve to `action.destructive` / danger variant in every surface (trigger button and confirm modal alike). A blue "Delete" button is a critical defect.
- **Secondary Actions** are neutral (outline or ghost, dark text, no saturated fill).

---

## 3. The Anti-Slop Directives (Banned AI Tells)

Break statistical AI defaults to deliver deliberate, human-caliber software:

| Slop Default (Banned) | Why It Fails | The Senior Engineer Move |
| :--- | :--- | :--- |
| **Emoji in UI** (e.g. 🚀, ⚠️, 🔍) | Reads as amateur toy; renders inconsistently across OS | Real SVG icons (Lucide) with `currentColor`, or plain text. |
| **Em-Dashes in Copy** (`—`) | Dead giveaway of LLM text generation | Use periods, commas, or concise two-sentence splits. |
| **Marketing Buzzwords** ("elevate", "unlock", "supercharge", "seamless") | Hollow filler with zero technical substance | Use concrete, factual benefit verbs ("Export", "Filter", "Sync"). |
| **Superlative Triads** ("Fast, secure, and beautiful") | LLM cadence tell; meaningless abstraction | Name one specific verifiable metric or remove. |
| **Fake Section Labels** ("SECTION 01", "FEATURE") | Clutters layout with non-informational noise | Clear descriptive headlines or no label at all. |
| **3 Equal Stat Cards** | Monotonous rhythm; no visual focal point | Asymmetric bento grid; hero metric $\ge 2.5\times$ body size. |
| **Pure `#000` on `#fff`** | High-glare, harsh ocular fatigue | Off-black (`#111827`) on warm/cool white surface (`#F9FAFB`). |
| **Generic Drop Shadows** | Muddy, dated box-shadow on every card | 1px subtle borders (`border.subtle`) or layered elevation tokens. |
| **Rainbow Accents** | Chaotic, undisciplined visual noise | 1 primary brand color, 1 accent max. Neutrals carry 80% of layout. |

---

## 4. State-Complete Component Contract

Every interactive control (button, input, select, card, menu item) must explicitly define all **6 states**:
1. **Default / Rest**: Semantic surface, border, and readable label.
2. **Hover**: Intentional luminance shift ($\Delta L \approx 4\text{--}8\%$), subtle border emphasis.
3. **Active / Pressed**: Scale down ($0.98\text{--}0.99$), deepened background.
4. **Focus-Visible**: 2px outline with 2px offset (`outline-offset: 2px`). Never set `outline: none` without replacement.
5. **Disabled**: Muted opacity ($0.4\text{--}0.5$), `pointer-events: none` or `cursor: not-allowed`, `aria-disabled="true"`.
6. **Loading**: Maintain full container opacity, preserve layout dimensions, display inline spinner or skeleton. Never dim like disabled.

---

## 5. WCAG 2.2 AA / AAA Ergonomics & Touch Sizing

- **Contrast Ratios**:
  - Normal text ($< 18$pt / $< 24$px): $\ge 4.5:1$ (AA) or $\ge 7:1$ (AAA).
  - Large text ($\ge 18$pt or $\ge 14$pt bold): $\ge 3:1$ (AA).
  - Graphical objects and user interface boundaries (inputs, buttons): $\ge 3:1$ against adjacent background.
- **Target Sizing**:
  - Minimum clickable target: $\ge 24\times 24$px (WCAG 2.5.8).
  - Touch/mobile targets: $\ge 44\times 44$px.
  - POS / Kiosk / Touchscreens: $\ge 48\times 48$px with $\ge 8$px spacing to prevent mis-taps.
- **Form Semantics**:
  - Every `<input>` must be explicitly associated with a `<label>` via `for`/`id` or `aria-labelledby`.
  - Accessible names (`aria-label`) mandatory on all icon-only buttons.
  - Error messages linked to input via `aria-describedby` and flagged with `aria-invalid="true"`.

---

## 6. ⚡ Token-Saving Output Protocol

- Output only the specific component template, CSS/Tailwind classes, or token snippet.
- Never output unchanged surrounding page markup or generic full-file stylesheets.
