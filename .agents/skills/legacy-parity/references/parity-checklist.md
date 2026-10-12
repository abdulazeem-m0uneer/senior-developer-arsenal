# Parity Checklist & Difference Table

What to compare, how to report differences, what goes to the owner instead of being fixed, and the record of a legacy sync.

---

## 1. Interface Parity Checklist

Used when the interface is frozen: a difference from the legacy is the defect, whether or not it looks better.

| # | Check | Compare |
| :---: | :--- | :--- |
| 1 | Layout and order | Sections, fields, columns, and actions in the same order and position |
| 2 | Colours | Every colour against the documented design values; no raw value that is not listed |
| 3 | Typography | Family, size, weight, line height |
| 4 | Spacing and shape | Padding, gaps, sizes, radius, shadows |
| 5 | Icons and images | Same asset, same size, same alignment |
| 6 | Wording | Every string in every supported language, exactly as the legacy words it |
| 7 | Direction | Correct in right-to-left and left-to-right where the legacy supports both |
| 8 | States | Loading, empty, error, disabled, read-only, validation messages |
| 9 | Formats | Dates, times (12 or 24 hour), numbers, currency, units as the legacy shows them |
| 10 | Motion | Transitions, durations, and what triggers them |
| 11 | Additions and removals | Nothing present that the legacy lacks; nothing missing that it has |
| 12 | Source hygiene | Built code uses design tokens and translation keys, not literals or inline styles |

For check 12, search the built code for raw colours, literal strings, and inline styles. Each hit is a candidate: read it before reporting.

---

## 2. Behaviour Parity Checklist

| # | Check | Compare |
| :---: | :--- | :--- |
| B1 | Inputs accepted and refused | Validation rules, limits, required fields, trimming and case handling |
| B2 | Outputs | Fields, types, null versus absent, ordering, pagination defaults |
| B3 | Errors | Status code, error code, message key for each refusal |
| B4 | Side effects | Records written, messages sent, jobs queued, and their order |
| B5 | Permissions | Who may call it, and whose data they see |
| B6 | Numbers | Limits, time-outs, rounding, time zone of day boundaries |
| B7 | Failure behaviour | What stays changed when a later step fails |
| B8 | Background behaviour | Scheduled jobs, retries, expiry |

Each row is proven by a characterisation test or a recorded legacy response, not by reading both implementations and agreeing with oneself.

---

## 3. Difference Table

One row per difference. No prose between rows.

| # | Location (`file:line`) | Check | Legacy value (with `path:line`) | Built value | Severity | Fix that restores legacy |
| :---: | :--- | :---: | :--- | :--- | :---: | :--- |
| 1 | `src/pages/Invoices.tsx:64` | 1 | Columns: number, date, customer, total (`views/invoices.html:22`) | Total before customer | `[Blocker]` | Reorder columns |
| 2 | `src/pages/Invoices.tsx:91` | 8 | Empty state shows illustration and "No invoices yet" | Blank table | `[Blocker]` | Add the legacy empty state |
| 3 | `src/theme/tokens.ts:14` | 2 | Primary `#1F4E79` | `#1D4ED8` | `[Architecture]` | Use the documented token |
| 4 | `src/invoices/list.ts:30` | B2 | Sorted by date descending, 25 per page | Sorted by id, 20 per page | `[Blocker]` | Match sort and page size |

Severity for parity work:

| Tag | Meaning here |
| :--- | :--- |
| `[Blocker]` | A user or client of the system would notice or be affected: behaviour, layout, wording, state |
| `[Security]` | The rebuild exposes more than the legacy did (a wider permission, an extra field) |
| `[Architecture]` | Looks the same today but is built to drift (literal instead of token, copied logic) |
| `[Suggestion]` | Difference with no visible effect; fix when touching the file |

After the table, list **Not checked** with the reason (no device, no screenshot, legacy not runnable, state not reproducible). An unchecked item is never reported as matching.

---

## 4. For the Owner (Reported, Not Fixed)

Problems found in the legacy itself. Fixing one changes approved behaviour or appearance, so each needs a written decision first.

| # | Legacy location | Problem | Kind | Effect of keeping it | Effect of fixing it |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 1 | `views/invoices.html:40` | Grey text on white, contrast 2.9:1 | Accessibility | Fails WCAG AA for body text | Colour differs from the approved design |
| 2 | `server/bookings/cancel.js:71` | Refund failure leaves booking cancelled with no refund | Bug | Customers lose money silently | Behaviour differs; needs a retry rule |
| 3 | `server/auth/session.js:18` | Session never expires | Security | Stolen token works for ever | Users are signed out after the new limit |

- A security fault that is exploitable now is escalated the same day through `security-audit`; it does not wait for the parity report.
- An approved fix is recorded as a deliberate difference with its decision reference, and the characterisation test is updated in the same change.

---

## 5. Exceptions to "Legacy Wins"

A difference is allowed only when one of these is written down and approved by the named owner:

| Exception | Example | Still required |
| :--- | :--- | :--- |
| Feature removed from scope | A product line not carried over | Entry point handled as the owner decided (hidden or disabled) |
| New feature with no legacy counterpart | A screen the legacy never had | Built only from existing components and values |
| Legal or platform requirement | Store policy, consent wording | The requirement cited |
| Approved defect fix | Rows from section 4 | Decision reference and updated tests |

Anything else is restored to the legacy.

---

## 6. Sync Record

One tracked task per sync, titled with the commit range.

```markdown
Legacy sync <old-commit>..<new-commit> (<branch>, <date>)

| Legacy change (commit) | Area | Status | Carried in as |
| :--- | :--- | :--- | :--- |
| Add cancellation fee setting (a1b2c3d) | Bookings | Gap | Spec row + task, pull request link |
| Fix typo in invoice footer (d4e5f6a) | Invoices | Gap | String updated, pull request link |
| Refactor logger (0f9e8d7) | Internal | Not applicable | none |
| New export endpoint (7c6b5a4) | Reports | Waiting | Open question: who may call it? |

Last synced commit is now: <new-commit>
```

- Status is one of: covered, gap, not applicable, waiting. "Waiting" names the open question.
- The legacy process is not adopted with its changes: each gap goes through the rebuild's own specification, tests, and review.
- If the branch did not move, record nothing; if it moved and nothing applies, still record the range so the next sync starts from the right commit.
