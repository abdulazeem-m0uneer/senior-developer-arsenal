# Screen Reader Test Scripts

Pairings to test: NVDA + Firefox (Windows), VoiceOver + Safari (macOS), VoiceOver + Safari (iOS), TalkBack + Chrome (Android). JAWS + Chrome is optional: use it when users or contract require it. Pairings matter: results differ per browser.

Announcement wording differs by screen reader, version, and verbosity settings. Compare the elements (name, role, state, value, position), not exact phrasing. Record the observed text verbatim in the finding.

---

## 1. Setup

- Use a recent stable build and note versions in the report. Reset verbosity to defaults. Test with the display on; do not rely on the speech viewer alone, but enable it to capture text (NVDA: Tools > Speech viewer).
- Use a clean browser profile with no extensions. Close other audio.
- NVDA modifier is Insert (or CapsLock if configured); VoiceOver modifier `VO` is Control+Option on macOS.
- Stop speech: NVDA `Ctrl`; VoiceOver macOS `Ctrl`.

## 2. Command cheat sheet

| Task | NVDA + Firefox | VoiceOver macOS + Safari | VoiceOver iOS | TalkBack + Chrome |
| :--- | :--- | :--- | :--- | :--- |
| Read all from here | `Insert+Down` (or numpad `+`) | `VO+A` | Two-finger swipe up | Reading controls, or from top with the TalkBack menu "Read from top" |
| Next / previous item | `Down` / `Up` in browse mode | `VO+Right` / `VO+Left` | Swipe right / left | Swipe right / left |
| Next heading | `H` (`Shift+H` back) | `VO+Cmd+H` | Rotor set to Headings, swipe down / up | Reading controls set to Headings, swipe down / up |
| Landmarks | `D` next landmark | `VO+U`, choose Landmarks | Rotor: Landmarks | No landmark granularity listed in Google's reading-controls help: verify structure through headings and controls |
| Links | `K` next link | `VO+U`, Links list | Rotor: Links | Reading controls: Links |
| Form fields | `F` next form field | `VO+U`, Form Controls | Rotor: Form Controls | Reading controls: Controls |
| Tables | `T` next table; `Ctrl+Alt+Arrows` between cells | `VO+Arrows` inside the table; `VO+U`, Tables | Rotor: Tables (where offered) | Reading controls: Rows / Columns granularity |
| Element list | `Insert+F7` (headings, links, landmarks) | `VO+U` rotor | Rotor | TalkBack menu |
| Activate | `Enter` / `Space` | `VO+Space` | Double-tap | Double-tap |
| Read current line | `Insert+Up` | `VO+L` | Focus item | Focus item |
| Toggle browse / focus mode | `Insert+Space` | not applicable | not applicable | not applicable |
| Open reading controls / menu | not applicable | not applicable | Two-finger twist = rotor | Reading controls: one-finger swipe up then down (or three-finger swipe up/down). Menu: three-finger tap |

Notes:
- Safari on macOS: by default `Tab` skips non-form items. For keyboard testing enable "Press Tab to highlight each item on a webpage" in Safari settings, or use `Option+Tab`.
- NVDA browse mode reads the page like a document; focus mode passes keys to a widget. NVDA switches automatically for form fields and `application` roles. A widget that needs a manual `Insert+Space` to work has a role problem.
- TalkBack gestures vary by Android and TalkBack version; if a gesture does not respond, open Settings > Accessibility > TalkBack > Settings > Customize gestures and note the mapping used.

## 3. Page orientation script (every page)

1. Load the page. Expect the page title announced first, then the main heading on load or route change.
2. Landmarks: navigate all. Expect banner, navigation (named if more than one), main (exactly one), contentinfo. Fail on content outside landmarks or two unnamed navigations.
3. Headings: list all. Expect one `h1`, no skipped levels, text reads as an outline.
4. Links: list all. Fail on duplicates with different targets and on "click here", "more", or bare URLs.
5. Forms: step through each field. Expect label, role, required, invalid, value, and hint in one announcement.
6. Tables: enter a table. Expect caption or name, row/column count, and header text with each cell. Layout tables announce none.
7. Images: pass every image. Informative: meaningful alt; decorative: silent.
8. Read all: listen for hidden text read twice, icon font glyphs read as private-use characters, and "graphic"/"image" noise.

## 4. Live regions and route changes

- Trigger a toast. Expect the message read once without focus moving. Polite regions wait; `role="alert"` interrupts. Fail if the message is silent or read twice.
- Add a result count after filtering ("12 results"). Expect a complete phrase, once per change.
- SPA navigation: expect the new title or heading announced and focus on a sensible start (heading or `main` with `tabindex="-1"`). Silence after a route change is a failure of 2.4.2, 2.4.3, or 4.1.3 depending on the cause.
- A live region inserted together with its text is often not announced: the container must exist before the text changes.

## 5. Widget scripts and expected announcements

Format per widget: action, then the elements expected in speech.

**Modal dialog**
1. Activate the trigger. Expect: dialog role, dialog name (from heading or `aria-labelledby`), then first focused control. Focus moves inside.
2. `Tab` through. Focus stays inside (or leaves only to browser chrome). Background is unreachable by virtual cursor (`aria-modal` plus inert background).
3. `Esc`. Expect dialog closes and focus returns to the trigger, announced as the trigger button.

**Tabs**
1. `Tab` to the tab list. Expect: tab name, "tab", "selected", position ("1 of 3"), tab list name if set.
2. Arrow keys move between tabs; the panel content is reached with `Tab` from the active tab. Unselected tabs announce "not selected" or nothing; selected state must differ in speech.

**Combobox / autocomplete**
1. Focus the input. Expect: label, "combo box" (or "edit, has autocomplete"), "collapsed" or "expanded" state.
2. Type. Expect the popup state to change and a result count or first option announced via live region without focus leaving the input.
3. `Down`: expect the option name, "option", position ("2 of 8"), "selected". `Enter` sets the value and the new value is read. `Esc` closes without losing typed text.

**Menu button / menu**
1. Focus the button. Expect: name, "menu button" or "button", "collapsed", "has popup".
2. `Enter` or `Down`: expect "expanded", focus on the first item, role "menu item", position. Arrows move; `Esc` closes and returns focus to the button. Navigation menus built as disclosure patterns are not `role="menu"`: do not penalise a disclosure that is correctly exposed as a button with expanded state.

**Accordion / disclosure**
- Expect: button name, "collapsed" or "expanded"; state flips on activation. The panel text follows in reading order.

**Toast / snackbar**
- Expect the message announced once, no focus change. An action in the toast must be reachable by keyboard before it disappears, or an equivalent exists elsewhere.

**Form error**
1. Submit invalid. Expect either focus on an error summary ("alert" or heading plus links) or focus on the first invalid field.
2. At the field: label, "invalid entry" (or "invalid data"), the error text via description, required state.
3. Correct the field. Expect the error to clear and, for blur validation, no premature announcement while typing.

**Checkbox / switch / radio**
- Expect name, role (checkbox, switch, radio button), state (checked/not checked, on/off), group name and position for radios.

## 6. Mobile native apps (brief)

- iOS: UIKit/SwiftUI `accessibilityLabel`, `accessibilityTraits`, `accessibilityValue`, `accessibilityHint`; test with VoiceOver, Voice Control, Dynamic Type at the largest accessibility size, Reduce Motion, Bold Text, and Switch Control.
- Android: `contentDescription`, `stateDescription`, `Role`, `semantics` in Compose; test with TalkBack, Switch Access, font size and display size at maximum, and `Remove animations`.
- Map web criteria to platform checks: target size (44pt iOS and 48dp Android are platform guidance, WCAG minimum is 24 CSS px for web), text scaling replaces zoom, orientation lock, custom actions replace dragging alternatives, live announcements via `UIAccessibility.post` or `announceForAccessibility`/live-region semantics.
- Test on physical devices; emulators miss gesture and speech behaviour.
