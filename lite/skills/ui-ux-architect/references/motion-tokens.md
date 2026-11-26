# Motion Tokens and Rules

Adapted from Leonxlnx/taste-skill (MIT) motion.md (measured on 99 Awwwards Sites of the Day) and nextlevelbuilder/ui-ux-pro-max-skill (MIT) ux-guidelines.csv.

The arsenal defines six interactive states but no durations, curves, or reduced-motion contract. These tokens make Gate 4 (state completeness) and the loading state measurable.

---

## 1. Four Questions Before Any Animation

1. **How often is it seen?** Once per visit (hero load, section reveal): may take its time. Many times (hover, menu, accordion): fast and small. Hundreds of times (typing, keyboard actions): no animation.
2. **What is it for?** Valid: shows where something came from; confirms an action; keeps a change from jarring; explains how the product works; is the one signature moment. "Looks nice" is valid only for the signature moment.
3. **Which curve?** Entering or leaving: ease-out (movement starts the instant the eye arrives). Moving between two on-screen places: ease-in-out. Colour/opacity on hover: plain `ease`. Constant travel (marquee, progress): `linear`. Ease-in makes interfaces feel slow; use it only for something leaving for good.
4. **How long?** See tokens. Leaving is quicker than arriving (~60-70%).

## 2. Tokens

```css
:root {
  --ease-out:    cubic-bezier(0.22, 1, 0.36, 1);        /* entrances, moving hovers, UI under 600ms */
  --ease-expo:   cubic-bezier(0.16, 1, 0.3, 1);         /* reveals >= 800ms, line rises, openings */
  --ease-in-out: cubic-bezier(0.76, 0, 0.24, 1);        /* wipes, panels, things that travel while visible */
  --ease-soft:   cubic-bezier(0.33, 1, 0.68, 1);        /* slow scale and drift on photographs */
  --ease-exit:   cubic-bezier(0.55, 0.055, 0.675, 0.19);/* leaving for good, short */
  --t-press:  140ms;   /* 100-160 */
  --t-hover:  180ms;   /* colour 180-200; a hover that moves something 300-400 */
  --t-ui:     240ms;   /* menus, popovers 150-250; dialogs, drawers 250-450 */
  --t-reveal: 800ms;   /* section and hero reveals 500-900 */
  --t-open:   1200ms;  /* picture openings, clip wipes 1100-1300 */
  --stagger-line: 90ms;   /* 75-120 between lines */
  --stagger-item: 70ms;   /* 50-100 between list items; 20-40 between characters, headings of 1-3 words only */
}
```

- Not adopted: `cubic-bezier(.4,0,.2,1)` (a framework default) and any overshoot/elastic curve on interface elements.
- Staggers: four steps at most in one sequence.
- Press feedback must land within 100ms of the tap; a late press state reads as a dead control.

## 3. Rules

1. **First frame.** Headline, supporting sentence, and hero picture are in the HTML and painted on the first frame. Load sequence starts without waiting for the load event, settles by 1.2s, four elements max. No preloader, no counter, no gate.
2. **Properties.** Animate `transform`, `opacity`, `clip-path` only. `width`, `height`, `top`, `left`, `margin`, `padding` force layout per frame. `grid-template-rows` for accordions is the accepted short exception. Press states must not shift layout bounds.
3. **Reveals.** Fire once, when the element's top is 85-90% down the viewport; rise 12-32px or from a line mask; nothing in view hidden longer than 900ms; nothing above the fold waits for scroll. Section parts enter heading, then text, then picture, staggered 60-90ms; never one fade for the whole block.
4. **One of each per page.** One signature move; one moving picture; one marquee at most. Hover lift on every card and fade-up on every section are the generated default.
5. **Scroll-linked travel** is linear and locked to the scrollbar; parallax under 8% of the element; scale between 0.94 and 1.15; built with scroll timelines inside `@supports`, static without. No scroll hijacking, no wheel capture, no custom cursor.
6. **Text stays readable.** Fills start at 45% ink; dims no lower than 40%; blur at most 8px and gone once settled; nothing moves across text being read; scramble and typewriter headlines are not used.
7. **State transitions animate, do not snap**: hover, active, expanded, collapsed, modal. Modals and sheets originate from their trigger (scale+fade or slide). Forward navigation moves left/up, back moves right/down; keep it consistent.
8. **Interruptible and cancellable.** A tap or gesture cancels an in-progress animation immediately; rapid state changes replace the prior transition and set the final state explicitly; never depend on `animationend` for correctness. Never block input during motion.
9. **Loops** pause off screen and when the tab is hidden; `will-change` only on an element about to animate, removed afterwards.
10. **Page to page**: view transitions, 480ms max, off under reduced motion.
11. **Hierarchy motion**: enter from below = deeper; exit upward = back. Crossfade for content replaced in the same container.

## 4. Reduced Motion Contract

```css
@media (prefers-reduced-motion: no-preference) {
  .reveal { opacity: 0; transform: translateY(16px); transition: opacity var(--t-reveal) var(--ease-expo), transform var(--t-reveal) var(--ease-expo); }
  .reveal.is-in { opacity: 1; transform: none; }
}
/* No reduce block needed: outside no-preference the element is already in its finished state. */
```

- Every hidden state lives inside `prefers-reduced-motion: no-preference`, so the reduced page is the finished page. Content never depends on script to appear.
- Reduce means fewer and gentler, not none: keep opacity and colour changes; drop travel, scale, parallax, autoplay; stop loops; render scroll scenes at their final state.
- Verify after the motion pass by screenshotting every viewport and looking for content that failed to appear (a blank band where a reveal did not fire caps usability at 5 in the critique).

## 5. Loading and Feedback Timing

- Match the indicator to the expected wait: under ~300ms, nothing; ~300ms-1s, a spinner inside the control (Gate 4 loading state, dimensions preserved); over ~1s, a skeleton at the real layout size with `aria-busy="true"`, no shimmer gradient, no layout shift on arrival.
- Toasts auto-dismiss in 3-5s, `aria-live="polite"`, never steal focus. Success confirmation is brief (checkmark, toast). Errors use `role="alert"` and include the recovery path.
- Exit animations at 60-70% of the matching entrance.
