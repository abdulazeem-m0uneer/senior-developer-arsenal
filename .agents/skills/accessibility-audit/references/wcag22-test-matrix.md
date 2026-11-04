# WCAG 2.2 Test Matrix (human-check criteria)

Conformance target: Level A and AA of WCAG 2.2. Names and levels verified against W3C material on 2026-11-04. 4.1.1 Parsing was removed in 2.2: never cite it. AAA rows are marked and are not required for an AA claim.

Method codes: `A` automated (axe finds some instances, a human confirms), `K` keyboard, `SR` screen reader, `Z` zoom/reflow, `V` visual inspection, `M` manual measurement, `C` content review.

---

## 1. Perceivable

| SC | Level | Method | Practical test |
| :--- | :---: | :---: | :--- |
| 1.1.1 Non-text Content | A | A, SR | Axe finds missing `alt`; a human judges the text. Informative image: the alt says what the image conveys here. Decorative: `alt=""`. Functional (icon link): alt names the action. Charts: a text or table alternative exists nearby. |
| 1.2.1 to 1.2.5 Time-based media | A, AA | V, C | Prerecorded video has accurate captions (1.2.2) and audio description or a text alternative (1.2.3, 1.2.5). Live video has captions (1.2.4). Audio-only has a transcript (1.2.1). Check caption accuracy, speaker names, sound cues. |
| 1.3.1 Info and Relationships | A | SR, A | Headings, lists, tables, form groups, and required state exist in markup, not only in styling. Tab through a table with a screen reader: headers announced per cell. `fieldset`/`legend` for radio groups. |
| 1.3.2 Meaningful Sequence | A | K, SR | Reading order in the accessibility tree equals visual order. Disable CSS or read with the screen reader; CSS `order`, grid placement, and absolute positioning are the usual causes. |
| 1.3.3 Sensory Characteristics | A | C | No instruction relies only on shape, position, or colour ("the round button on the right"). |
| 1.3.4 Orientation | AA | V | Rotate device or emulate both orientations; nothing locked to one unless essential. |
| 1.3.5 Identify Input Purpose | AA | A, V | Fields collecting the user's own data carry the correct `autocomplete` token. Browser autofill fills them. |
| 1.4.1 Use of Color | A | V | Greyscale the page: links in text, errors, required, chart series, and status remain distinguishable without hue. |
| 1.4.2 Audio Control | A | K | Audio that plays over 3 seconds can be paused or its volume set independent of system volume. |
| 1.4.3 Contrast (Minimum) | AA | A, M | 4.5:1 text, 3:1 large text (>= 24px, or >= 18.66px bold). Axe misses text on images, gradients, and pseudo-elements: measure those with a picker in every state (hover, focus, disabled is exempt). |
| 1.4.4 Resize Text | AA | Z | Browser text zoom to 200% (not page zoom): no clipped, overlapping, or lost content or function. |
| 1.4.5 Images of Text | AA | V | Text rendered as an image only for logos or when unavoidable. |
| 1.4.10 Reflow | AA | Z | 320 CSS px wide (1280 px at 400% zoom) with no two-dimensional scrolling. Exempt: data tables, maps, diagrams, video, code editors. |
| 1.4.11 Non-text Contrast | AA | M | 3:1 for input borders, focus indicators, icon-only controls, selected/checked states, and chart marks versus neighbours. Measure each state. |
| 1.4.12 Text Spacing | AA | V | Apply the spacing bookmarklet or the CSS in section 5: line-height 1.5, paragraph 2x, letter 0.12em, word 0.16em. Nothing clipped or overlapped. |
| 1.4.13 Content on Hover or Focus | AA | K, V | Tooltips and popovers are dismissible (Esc) without moving pointer, hoverable, and persistent until dismissed or invalid. |

## 2. Operable

| SC | Level | Method | Practical test |
| :--- | :---: | :---: | :--- |
| 2.1.1 Keyboard | A | K | Every function works with keyboard alone. Custom controls: Enter/Space for buttons, arrows per the ARIA pattern. Drag, hover-only menus, and click-only `div`s fail. |
| 2.1.2 No Keyboard Trap | A | K | Focus can always leave. Modal traps are legal only if Esc or a close control releases them and focus returns to the trigger. Check embedded iframes and editors. |
| 2.1.4 Character Key Shortcuts | A | K | Single-key shortcuts can be turned off, remapped, or only fire while their component has focus. Test with a dictation user in mind. |
| 2.2.1 Timing Adjustable | A | K | Session or form timeout warns, and the user can extend or turn off. |
| 2.2.2 Pause, Stop, Hide | A | V | Carousels, tickers, animations over 5 seconds, and auto-updating feeds have a pause control. |
| 2.3.1 Three Flashes | A | V | No content flashes more than 3 times per second. |
| 2.4.1 Bypass Blocks | A | K | First Tab stop is a working skip link (visible on focus) landing on `main`. Landmarks also satisfy it. |
| 2.4.2 Page Titled | A | SR | Unique, descriptive `<title>` per page and per SPA route; the route change is announced. |
| 2.4.3 Focus Order | A | K | Tab order follows meaning. After opening a dialog, focus enters it; after closing, it returns. After SPA navigation focus moves to the new heading or `main`, not stays on the clicked link. |
| 2.4.4 Link Purpose (In Context) | A | SR | Open the links list: each reads sensibly from its text plus surrounding context. Repeated "Read more" needs a distinguishing accessible name. |
| 2.4.5 Multiple Ways | AA | V | At least two ways to find a page (search, nav, sitemap), unless it is a step in a process. |
| 2.4.6 Headings and Labels | AA | SR | Headings and labels describe their topic or purpose. Heading list reads as an outline. |
| 2.4.7 Focus Visible | AA | K | Every focusable element shows a visible indicator in every theme, including on dark surfaces. |
| 2.4.11 Focus Not Obscured (Minimum) | AA | K, Z | Tab to every control at 100% and 200%/400% zoom with sticky headers, cookie banners, and chat widgets present: the focused item is not entirely hidden. 2.4.12 (Enhanced, AAA) requires no overlap at all. 2.4.13 Focus Appearance is AAA. |
| 2.5.1 Pointer Gestures | A | V | Pinch, swipe, and path-based gestures have a single-pointer alternative (buttons). |
| 2.5.2 Pointer Cancellation | A | V | Actions fire on pointer up, can be aborted by moving off, or undone. |
| 2.5.3 Label in Name | A | SR, A | The accessible name contains the visible label text, in order. Voice control "click Search" must work. |
| 2.5.4 Motion Actuation | A | V | Shake or tilt functions have a button alternative and can be disabled. |
| 2.5.7 Dragging Movements | AA | K, V | Each drag (reorder, slider, resize, map pan, upload zone) has a single-pointer non-drag path. |
| 2.5.8 Target Size (Minimum) | AA | M | Pointer targets >= 24x24 CSS px, or 24 px circles centred on the target do not intersect another target. Exceptions: inline links in text, user-agent controls, equivalent control elsewhere. Axe `target-size` flags candidates; confirm. |

## 3. Understandable

| SC | Level | Method | Practical test |
| :--- | :---: | :---: | :--- |
| 3.1.1 / 3.1.2 Language of Page / of Parts | A / AA | A, SR | `lang` on `html`; foreign phrases carry `lang` so the synthesiser switches voice. |
| 3.2.1 / 3.2.2 On Focus / On Input | A | K | Focusing or changing a field never submits or navigates unannounced (auto-submitting selects fail). |
| 3.2.3 / 3.2.4 Consistent Navigation / Identification | AA | V | Navigation order and the name/icon of repeated functions match across pages. |
| 3.2.6 Consistent Help | A | V | Help, contact, chat, or self-service links sit in the same relative place on every page where they appear. |
| 3.3.1 Error Identification | A | SR | Submit empty: the field and the error are named in text and programmatically linked (`aria-describedby`, `aria-invalid`). |
| 3.3.2 Labels or Instructions | A | SR | Visible persistent label; format hints and required state announced with the field. |
| 3.3.3 Error Suggestion | AA | C | Errors state the fix, not only the failure. |
| 3.3.4 Error Prevention (Legal, Financial, Data) | AA | K | Money, legal, and data-deleting submissions are reversible, checked, or confirmed. |
| 3.3.7 Redundant Entry | A | K | Walk a multi-step flow: information already given is prefilled or selectable ("same as shipping"). Exceptions: security re-entry, essential, no longer valid. |
| 3.3.8 Accessible Authentication (Minimum) | AA | K | Login allows paste and password managers (`autocomplete`, no `onpaste` blocking). No puzzle, transcription, or memory test without an alternative. Object or personal-content recognition CAPTCHA needs an alternative. 3.3.9 (Enhanced) is AAA. |

## 4. Robust

| SC | Level | Method | Practical test |
| :--- | :---: | :---: | :--- |
| 4.1.2 Name, Role, Value | A | SR, A | Custom widgets announce name, role, and state/value, and changes announce too (expanded, selected, checked, current). See `screen-reader-scripts.md` section 5. |
| 4.1.3 Status Messages | AA | SR | Toasts, result counts, save confirmations, and inline validation announce without taking focus (`role="status"`, `role="alert"`, live region present in DOM before the text changes). |

## 5. Text spacing CSS (1.4.12 test)

```css
* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }
p { margin-bottom: 2em !important; }
```

## 6. Result vocabulary

- `Pass`, `Fail`, `Not applicable` (state why: no video, no auth), `Not tested` (state why). A criterion is never silently skipped.
