---
name: ui-ux-audit
description: Senior UI/UX and design audit workflow. Evaluates screens and components against 10 anti-slop gates, DTCG token compliance, state completeness, and WCAG 2.2 AA.
---

# UI/UX & Design Audit Workflow

Follow this procedure when auditing or reviewing user interfaces, components, or design tokens.

---

## Steps

### 1. Scope & Component Extraction
Identify target UI templates, CSS stylesheets, and design token definitions. Isolate interactive elements (buttons, inputs, modals, cards).

### 2. Execute the 10 Anti-Slop Gates
Evaluate the target UI against the 10 objective gates:
1. **Zero-Emoji**: Check for any Unicode emoji glyphs used as UI icons or status badges.
2. **Intent Tokens**: Verify destructive buttons use danger tokens, not primary/blue.
3. **Contrast Ratios**: Check text and icon contrast against surfaces ($\ge 4.5:1$ body, $\ge 3:1$ large).
4. **State Completeness**: Verify Default, Hover, Active, Focus-Visible, Disabled, Loading.
5. **Target Sizing**: Verify touch/click targets meet $\ge 24\times 24$px ($\ge 44$px for touch, $\ge 48$px for POS).
6. **Responsive Overflow**: Check for horizontal scrollbars or clipping at 280px–360px widths.
7. **Keyboard & Focus**: Verify Tab order, modal focus trap, and Escape key dismissal.
8. **Anti-AI Copy**: Check for em-dashes (`—`), marketing buzzwords, and superlative triads.
9. **Visual Hierarchy**: Verify hero metrics lead ($\ge 2.5\times$), layout avoids 3 equal cards.
10. **Token Compliance**: Flag any hardcoded hex values or inline styling.

### 3. Generate Structured Audit Matrix
Output results in a dense Markdown table:

| Gate | Target Component | Status | Finding | Surgical Recommendation |
| :--- | :--- | :---: | :--- | :--- |
| `Intent` | `DeleteAccountModal` | ❌ FAIL | Delete button uses primary blue | Switch to `action.destructive` / danger variant |
| `Target Size` | `MobileNavToggle` | ❌ FAIL | Height is 20px | Add padding to reach $\ge 44\times 44$px hit box |
| `Contrast` | `BadgeStatus` | ✅ PASS | 4.8:1 contrast on canvas | Complies with WCAG 2.2 AA |

### 4. Provide Surgical Diffs
Supply 2–5 line unified diffs for any failing gates. Never output entire unchanged component files.
