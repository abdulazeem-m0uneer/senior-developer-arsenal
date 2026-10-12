# Behaviour Answer Template

The fixed shape for answering "what does the legacy do here?", the search order, a worked example, and how an answer becomes characterisation tests.

---

## 1. The Shape

Four headings, in this order, and nothing else. Under 40 lines. At most one line of code per claim.

```markdown
**Legacy at:** <repository>@<short commit> (<branch>)

**What the legacy does:**
1. <behaviour in a plain sentence; one step per line when it is a flow>
2. <numbers with unit and where they are set: constant, setting, default>

**Where:**
- claim 1: `path/to/file.ext:line`
- claim 2: `path/to/other.ext:line`

**Who can reach it:** <app, screen or route, role or permission; only when it matters to the question>

**Not found:** <what was looked for, with the search used, and not found>
```

Rules:
- Every claim has a `path:line`. A claim without one is removed or moved to "Not found".
- Report behaviour, never a recommendation. How the new system should be built is not part of the answer.
- Describe what the code does, not what its comments, names, or documents say it does. Where they disagree, say so.
- "Not found" is never empty by default: write "nothing missing for this question" only after looking.
- Dead code is reported as dead: say what would have to call it and that nothing does.

---

## 2. Search Order

| Order | Tool | Good for | Stop when |
| :---: | :--- | :--- | :--- |
| 1 | Code-search tool (symbols, callers, call paths) | "Where is this decided?", "what calls this?" | The deciding function and its callers are known |
| 2 | Text search for a literal | Route paths, error codes, setting names, screen strings, table names | The literal is found or shown absent |
| 3 | Read at the pointed lines | The exact condition, number, or order of effects | The claim can be written with a line number |
| 4 | Configuration and seed data | Values not in code: feature flags, defaults, role tables | The effective value is known, with where it is set |
| 5 | Database constraints and triggers | Behaviour enforced below the application | Checked or listed under "Not found" |

Places behaviour hides, to check before writing "Not found": middleware and interceptors, scheduled jobs, database triggers and defaults, client-side validation the server does not repeat, feature flags, per-tenant settings, and error handlers that swallow a failure.

---

## 3. Worked Example

Question: "Until when can a customer cancel a booking, and what is refunded?"

```markdown
**Legacy at:** legacy-platform@3f9c21a (release)

**What the legacy does:**
1. A booking can be cancelled by its customer while its status is `confirmed` or `pending`.
2. Cancellation is refused when the start is less than 30 minutes away; the limit is the constant
   `CANCEL_CUTOFF_MINUTES = 30`, not a setting.
3. More than 24 hours before the start the full amount is refunded; inside 24 hours, 50%, rounded
   down to the minor unit.
4. The refund is requested after the status is saved; a gateway failure is logged and the booking
   stays `cancelled` with no refund and no retry.
5. Staff can cancel at any time from the admin screen; the cut-off is not applied to them.

**Where:**
- 1: `server/bookings/cancel.js:38`
- 2: `server/bookings/cancel.js:52`, `server/config/constants.js:17`
- 3: `server/bookings/refund-policy.js:21-34`
- 4: `server/bookings/cancel.js:71-80`
- 5: `server/admin/bookings.js:140`

**Who can reach it:** customer app, booking details screen (`POST /bookings/:id/cancel`, role
`customer`, own bookings only); admin console, booking page (role `staff`).

**Not found:** a notification to the supplier on cancellation (searched `cancel` in
`server/notifications/` and the job folder); any audit record of who cancelled.
```

Claim 4 is a legacy bug. It is reported as behaviour here and listed in the "for the owner" table of the audit; whether the rebuild keeps it is the owner's decision, recorded with `decision-log`.

---

## 4. From Answer to Characterisation Tests

One test per numbered claim, named after the behaviour, citing the legacy line it pins.

```typescript
describe("cancel booking (characterises legacy server/bookings/cancel.js@3f9c21a)", () => {
  it("refuses cancellation 29 minutes before start", async () => {
    const booking = await aBooking({ status: "confirmed", startsInMinutes: 29 });
    await expect(cancel(booking.id, asCustomer(booking))).rejects.toMatchObject({ code: "cancel.too_late" });
  });

  it("allows cancellation exactly 30 minutes before start", async () => {
    const booking = await aBooking({ status: "confirmed", startsInMinutes: 30 });
    await expect(cancel(booking.id, asCustomer(booking))).resolves.toMatchObject({ status: "cancelled" });
  });

  it("refunds 50% rounded down inside 24 hours", async () => {
    const booking = await aBooking({ amountMinor: 2501, startsInMinutes: 600 });
    expect((await cancel(booking.id, asCustomer(booking))).refundMinor).toBe(1250);
  });
});
```

| Pin this | Because the rebuild usually gets it wrong |
| :--- | :--- |
| Boundaries (exactly at the limit, one unit either side) | `<` versus `<=` is invisible in a description |
| Rounding mode and the unit it is applied in | Half-up versus floor shifts money by one minor unit |
| Order of side effects and what happens when the second fails | Partial outcomes are the legacy's real contract |
| Error codes, status codes, and message keys | Clients switch on them |
| Sort order, pagination defaults, time zone of "today" | Never specified, always noticed |
| Who is exempt (staff, system jobs) | Exemptions live in a different file |

Where the legacy can still run, record its real responses for a fixed set of requests and replay them against the rebuild (golden-master comparison); normalise ids and timestamps before comparing.
