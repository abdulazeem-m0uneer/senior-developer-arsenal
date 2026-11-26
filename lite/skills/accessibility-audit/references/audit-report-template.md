# Accessibility Audit Report Template

Write the report to the location the project guide names for audit output (default `docs/audits/a11y-<yyyy-mm-dd>.md`). Keep findings dense: one block or table row per defect, no narrative padding.

---

## 1. Header

- **Target**: product, build or commit, environment URL.
- **Standard**: WCAG 2.2 Level AA (list any extra target, e.g. AAA focus criteria adopted by policy).
- **Date and auditor**.
- **Page set and states**: each page or screen, with the states tested (empty, loading, error, success, logged in/out, dialog open, mobile width).
- **Test matrix**: pairing, version (NVDA 20xx.x + Firefox xx; VoiceOver macOS xx + Safari xx; VoiceOver iOS xx + Safari; TalkBack xx + Chrome xx), axe-core version, viewport sizes, input methods.
- **Not tested** and why (stated, never silent).

## 2. Summary table

| Principle | Pass | Fail | Not applicable | Not tested |
| :--- | :---: | :---: | :---: | :---: |
| Perceivable | | | | |
| Operable | | | | |
| Understandable | | | | |
| Robust | | | | |

Counts of findings: blocker / major / minor. One sentence on the dominant failure pattern (for example "custom widgets lack state exposure").

## 3. Severity

- **blocker**: a user group cannot complete a core task (sign in, search, buy, submit) or is trapped. Fix before release.
- **major**: task is possible but needs a workaround, is confusing, or harms many users; fails an A or AA criterion with a workable path. Fix this cycle.
- **minor**: inconvenience, redundancy, or a best-practice gap; fails a criterion only in a narrow case. Schedule.

Severity is about user impact, not about how many axe nodes matched.

## 4. Finding format

Use one block per defect. Deduplicate: one defect repeated on N elements is one finding with a count and a selector list.

```
### A11Y-<nn> <short title>
- SC: <number> <name> (Level A|AA)
- Severity: blocker | major | minor
- Location: <page/screen>, <component>, <selector or file:line>
- Evidence: steps (1..n); observed (verbatim announcement, measured ratio, screenshot path); expected
- Tools: <axe rule id | manual keyboard | NVDA+Firefox | VoiceOver+Safari | TalkBack+Chrome>
- User impact: who is affected and what they cannot do
- Fix: <surgical change, 2-5 lines or the attribute to add>
- Retest: <how to confirm; regression test name>
```

Example:

```
### A11Y-07 Checkout error not announced
- SC: 3.3.1 Error Identification (A); 4.1.3 Status Messages (AA)
- Severity: major
- Location: /checkout, card number field, components/CardField.tsx:48
- Evidence: 1) NVDA+Firefox, submit with empty card number. 2) Observed: silence; focus stays on the Pay button. 3) Expected: focus on error summary, or field announced with "invalid entry" and the message.
- Tools: NVDA+Firefox, VoiceOver+Safari (same)
- User impact: screen reader users do not learn the payment failed.
- Fix: render the message in an element with id, set aria-invalid="true" and aria-describedby on the input, move focus to the first invalid field on submit.
- Retest: e2e "checkout empty card shows described error"
```

## 5. Conformance statement shape

```
Conformance statement
Product / version: <...>        Standard: WCAG 2.2 Level AA        Date: <...>
Scope: <pages, flows, states, platforms included> ; Excluded: <what and why>
Method: automated (axe-core <v>), keyboard-only, screen readers (<list with versions>), zoom/reflow, contrast measurement.
Result: one of
  - Conforms: no open Level A or AA failures in scope.
  - Partially conforms: <n> open failures, listed in section <x>; all blockers closed.
  - Does not conform: <n> blockers open.
Known limitations: <list with finding ids and target fix dates>
Contact / feedback route: <address or form>
```

Rules: conformance is claimed per page or per complete process, never per component. State the evaluated set and the date; a claim without scope is worthless. Automated results alone never support "Conforms". Third-party content outside the author's control is listed under limitations.

## 6. Regression guard

Add after fixes land, in the same change (see `test-every-change`, `quality-gate`):

```ts
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

for (const path of ['/', '/login', '/checkout']) {
  test(`a11y ${path}`, async ({ page }) => {
    await page.goto(path);
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .analyze();
    expect(results.violations).toEqual([]);
  });
}
```

- Add one test per key state (dialog open, error shown) by driving the page to that state before `analyze()`.
- Add keyboard assertions axe cannot make: dialog traps and restores focus, skip link works, focused element is not covered (`toBeInViewport` plus a bounding-box check against the sticky header).
- Known exceptions go in a reviewed allow-list with the finding id and expiry date, not in blanket `disableRules`.
- Run in the same command locally and in CI (`quality-gate`). A new violation fails the build. Manual screen reader passes repeat at each release or when a widget changes.

## 7. Open items

| Id | Item | Owner | Blocks | Working rule until answered |
| :--- | :--- | :--- | :--- | :--- |
