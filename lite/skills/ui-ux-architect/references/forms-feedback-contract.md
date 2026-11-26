# Forms and Feedback Contract (WCAG 2.2 + interaction mechanics)

Adapted from nextlevelbuilder/ui-ux-pro-max-skill (MIT) ux-guidelines and quick-reference. Pairs with the WCAG 2.2 block in `.agents/rules/ui-ux-standards.md` §5.

---

## 1. Forms Contract

### Labels and inputs
- Visible `<label>` above or beside every input; placeholder is never the only label. Persistent helper text below complex inputs.
- `type="email|tel|url|number"` and `inputmode` so the correct mobile keyboard opens; `autocomplete` on every field the browser can fill (`name`, `email`, `street-address`, `one-time-code`).
- Required marked in text or asterisk with a legend; read-only styled and announced differently from disabled.
- Inputs look like inputs: a border at >= 3:1 or a filled surface with a clear focus state. Mobile input height >= 44px.
- Password fields have a show/hide toggle. Group related fields with `fieldset`/`legend`.
- Long forms autosave drafts; confirm before dismissing a sheet or modal with unsaved changes.

### Validation
- Validate on blur, not per keystroke; show the error only after the user leaves the field.
- Error below its field, linked with `aria-describedby`, flagged with `aria-invalid="true"`, stating cause and fix ("Enter a UK postcode like SW1A 1AA"), not "Invalid input". Error colour >= 4.5:1 and paired with an icon or text, never colour alone.
- After a failed submit with several errors: a focusable error summary at the top, each item linking to its field, inline errors retained; with no summary, focus the first invalid field. Summary and inline errors use `role="alert"` or an `aria-live` region.
- Submit: loading state inside the button (dimensions preserved), then success or error. Request timeout shows a message with Retry.

### Destructive and bulk actions
- Confirm before destructive actions; the confirm button uses the destructive variant (Gate 2) and is spatially separated from the primary.
- Offer undo for destructive or bulk actions ("Undo delete" toast, 5-10s) in preference to a confirm dialog where the action is reversible.

## 2. Feedback and Status

- Toasts: 3-5s auto-dismiss, `aria-live="polite"`, no focus steal; error toasts persist until dismissed and carry the recovery action.
- Live counts (cart, unread): one `role="status" aria-atomic="true"` region announcing a complete phrase ("3 items in cart"), never a bare number, never every badge as a competing live region.
- Empty states: one sentence naming what belongs here and the action that creates it, inside the frame the content will occupy (see app-screen-rules.md §6 for data screens).
- Multi-step flows: step indicator ("Step 2 of 4"), back navigation that preserves entered data.
- Offline and slow network: a visible state and a degraded mode (smaller images, fewer animations) rather than a frozen UI.

## 3. Compact Components (chips, badges, tags)

- Choose the control from its semantics: a filter chip is a `<button aria-pressed>`; a removable value has a labelled remove button; a status tag is static text.
- Chips never shrink their label: `flex: none; white-space: nowrap`. Wrap the collection before truncating; a "+n" overflow is an operable disclosure that reveals the hidden values, not a dead label.
- Essential labels stay available to pointer and keyboard users when truncation is unavoidable (tooltip plus `aria-label`, or expand on focus).
- Reserve a stable slot for counts and badges so an arriving number does not shift layout.

## 4. Layout Mechanics Often Missed

- `touch-action: manipulation` on tappable controls to remove the 300ms delay; `cursor: pointer` on every clickable element on web.
- Fixed nav and bottom bars reserve space for underlying content (`padding-bottom: calc(var(--bar-h) + env(safe-area-inset-bottom))`); scroll content is never hidden behind sticky bars.
- `min-height: 100dvh`, not `100vh`, for full-screen mobile layouts. `width=device-width, initial-scale=1`; never disable zoom.
- A named z-index scale (0 / 10 / 20 / 40 / 100 / 1000) as tokens; a parent with `z-index` creates a stacking context, so children cannot escape it.
- Reserve space for async content (`aspect-ratio` on media, fixed-height skeletons) so CLS stays under 0.1. `font-display: swap` with a metric-compatible fallback.
- No nested scroll regions that fight the main scroll; avoid horizontal swipe on main content.
