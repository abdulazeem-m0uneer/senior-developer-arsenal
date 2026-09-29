# /ui-ux-audit Workflow

Run an objective anti-slop and accessibility audit on UI components, design tokens, and web/native views.

---

## Workflow Steps

1. **Target Identification**: Specify the component, template, or screen to audit.
2. **Execute 10 Anti-Slop Gates**:
   - Gate 1: Zero-Emoji Enforcement
   - Gate 2: Intent Token Alignment (Destructive = Danger)
   - Gate 3: Contrast Verification (WCAG 2.2 AA)
   - Gate 4: State Completeness (Default, Hover, Active, Focus, Disabled, Loading)
   - Gate 5: Target Sizing ($\ge 24$px desktop, $\ge 44$px touch, $\ge 48$px POS)
   - Gate 6: Responsive Overflow Check (no horizontal scroll at 280px)
   - Gate 7: Keyboard Navigation & Focus Trap (Tab, Escape)
   - Gate 8: Anti-AI Copy Tells (no em-dash, no marketing fluff)
   - Gate 9: Visual Hierarchy & Asymmetry
   - Gate 10: Token Compliance (no hardcoded hex)
3. **Structured Audit Matrix**: Output table (`Gate`, `Component`, `Status`, `Finding`, `Fix`).
4. **Surgical Diffs**: Provide minimal 2–5 line diffs for failed gates.
