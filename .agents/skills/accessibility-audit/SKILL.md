---
name: accessibility-audit
description: 'WCAG 2.2 AA conformance audit of a running page, app, or screen: scoped page and state set, automated axe pass, keyboard-only pass, screen reader scripts (NVDA+Firefox, VoiceOver+Safari macOS and iOS, TalkBack+Chrome), zoom/reflow, contrast, motion, target size, forms and authentication, media, then evidence-based findings, a conformance statement, and a Playwright+axe regression guard. Use when the user asks for an accessibility audit, a WCAG conformance check, a screen reader test, a VPAT/ACR input, or runs /accessibility-audit. Triggers on: "accessibility audit", "a11y audit", "WCAG audit", "screen reader test", "keyboard audit", "/accessibility-audit". Do not use for design gates and token compliance (use ui-ux-audit) or render performance (use frontend-audit).'
---

# Accessibility Audit Procedure

This skill guides the agent through a WCAG 2.2 Level AA conformance audit of a running interface, producing reproducible evidence per finding rather than a lint report.

---

## 1. When to Use This Skill

Activate this skill when:
- A page, flow, or app screen needs a conformance check against WCAG 2.2 A and AA before release or procurement.
- A user reports a screen reader, keyboard, zoom, or voice-control problem that needs reproduction.
- An accessibility statement or conformance report must be written or refreshed.
- A fixed finding needs a regression guard in CI.
- The user runs the `/accessibility-audit` slash command.

*Boundary*: Design gates, tokens, anti-slop, and state completeness stay with `ui-ux-audit`; this skill tests behaviour in a running build. Re-render and bundle cost go to `frontend-audit`. Functional acceptance and sign-off go to `qa-engineer`. Component construction rules are in `ui-ux-architect`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Scope the Page Set and States
1. List the pages, flows, and states in scope: the primary task flows (sign in, search, buy, submit), the templates behind them, and every state a user can reach (empty, loading, error, success, dialog open, logged out). Sample templates, not every URL.
2. Record the environment, build, viewports, browsers, and the screen reader pairings. State what is excluded and why.
3. Obtain a stable test account and seeded data; an audit on a build that changes underneath is not reproducible.

### Step 2: Automated Pass
Consult: [WCAG 2.2 Test Matrix](./references/wcag22-test-matrix.md)
1. Run axe-core against each page and state, with tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa` (`npx @axe-core/cli <url> --tags wcag22aa`, or `@axe-core/playwright` for states behind interaction).
2. Automated tools detect only a minority of WCAG failures. A clean axe run proves nothing about keyboard flow, announcements, reading order, alt-text quality, or captions. Triage each hit (true failure, false positive, needs review) and dedupe by cause.

### Step 3: Keyboard-Only Pass
1. Unplug the pointer. From page load: first Tab stop is a working skip link; Tab and Shift+Tab visit every control in a meaningful order (2.4.3) with a visible indicator (2.4.7).
2. With sticky headers, banners, and chat widgets present, confirm the focused control is not covered (2.4.11), also at 200% and 400% zoom.
3. Exercise every widget with its expected keys (Enter, Space, arrows, Esc, Home/End). Confirm no trap (2.1.2), dialogs return focus to the trigger, single-key shortcuts can be disabled (2.1.4), hover content is dismissible (1.4.13), and every drag has a non-drag path (2.5.7).

### Step 4: Screen Reader Pass
Consult: [Screen Reader Scripts](./references/screen-reader-scripts.md)
1. Run the orientation script (title, landmarks, headings, links, forms, tables, images) on each template with NVDA+Firefox, then VoiceOver+Safari (macOS and iOS), then TalkBack+Chrome. JAWS is optional.
2. Run the widget scripts for each dialog, tab set, combobox, menu, toast, and form error present. Compare name, role, state, and value, not exact phrasing. Capture observed announcements verbatim.
3. Test live regions and route changes (4.1.3, 2.4.2). Test the same flow on at least two pairings; a defect in one pairing is still a finding when the markup is wrong.

### Step 5: Visual and Input Checks
Consult: [WCAG 2.2 Test Matrix](./references/wcag22-test-matrix.md)
1. Reflow at 320 CSS px and 400% zoom (1.4.10); text zoom 200% (1.4.4); text spacing overrides (1.4.12); portrait and landscape (1.3.4).
2. Contrast measured for text (1.4.3) and non-text (1.4.11) in every state, including focus, hover, error, and over images.
3. Motion: `prefers-reduced-motion` honoured, auto-moving content pausable (2.2.2), no flashing (2.3.1). Target size 24x24 CSS px or spacing exception (2.5.8).
4. Forms and authentication: labels, errors, redundant entry (3.3.7), accessible authentication with paste and password managers (3.3.8), consistent help (3.2.6). Media: captions, transcripts, audio description (1.2.x).
5. Native mobile: apply the iOS and Android notes in the screen reader reference; test on devices.

### Step 6: Write Findings, Statement, and Guard
Consult: [Audit Report Template](./references/audit-report-template.md)
1. One finding per defect: success criterion, level, location, evidence (steps, observed versus expected), user impact, severity (blocker, major, minor), fix. Never cite 4.1.1 (removed in 2.2).
2. Write the conformance statement scoped to the tested set and date. Automated results alone never support "Conforms".
3. For each fixed finding add the regression guard (Playwright + axe plus keyboard assertions) in the same change, via `test-every-change`; wire it into the same command CI runs via `quality-gate`.

---

## 3. Verification Protocol

| Check | Pass condition |
| :--- | :--- |
| Coverage | Every in-scope page and state has a result per applicable criterion: Pass, Fail, Not applicable, or Not tested with a reason |
| Evidence | Each Fail has reproducible steps and a verbatim observation; no finding rests on axe output alone for a human-check criterion |
| Pairings | Report names screen reader, browser, and OS versions actually used |
| Citations | Every cited SC number, name, and level matches WCAG 2.2; no 4.1.1; AAA criteria (2.4.12, 2.4.13, 3.3.9) not presented as AA |
| Guard | `npx playwright test a11y` passes locally and in CI; a deliberately broken label makes it fail |

---

## 4. Negative Triggers

- Do NOT use for token, contrast-by-design, anti-slop, or state-completeness review (use `ui-ux-audit`).
- Do NOT use for re-render churn, memoization, or bundle size (use `frontend-audit`).
- Do NOT use for general functional acceptance or release sign-off (use `qa-engineer`).
- Do NOT claim legal compliance (ADA, EAA, Section 508); report WCAG results only and leave legal conclusions to the owner.

---

## 5. ⚡ Token Conservation Directive

- **Findings Only**: Report failures and the evidence for each; list passes as counts, never as prose.
- **Dedupe by Cause**: One finding with a selector list instead of one per element.
- **Targeted Reads**: Grep for the component or attribute; never load whole pages or the full axe JSON, filter violations to rule id, impact, and target.
- **References on Demand**: Open a reference only for the step you are executing.
