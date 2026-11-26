# Strangler Fig Playbook

Incremental replacement after Martin Fowler's strangler fig pattern: grow the new code around the old and retire the old piece by piece.

## 1. When to Use It

| Situation | Choice |
| :--- | :--- |
| Change fits in one function or class | Tiny steps with pins (SKILL Steps 5 and 6) |
| Unit is large, in production, and cannot be frozen | Strangler fig |
| Old and new must run side by side for weeks | Strangler fig with a flag |
| Everything is replaced and downtime is acceptable | Consider a rewrite (section 6) |

## 2. Procedure

1. **Slice**: divide the unit by something observable (route, use case, tenant, message type). Each slice must be routable alone.
2. **Insert a routing layer**: a proxy, facade, or dispatcher in front of the old code. First release routes everything to old and changes nothing. Pin it.
3. **Branch by abstraction**: when the old code is called in-process, put an interface in front of it; callers use the interface; old implementation behind it.
4. **Build the new slice** behind the same interface or route, with its tests written from the characterization pins.
5. **Gate with a feature flag**: per slice, default off, switchable without a deploy, scoped to a tenant, percentage, or internal users.
6. **Shadow or parallel run**: send each request to both; return the old result; log differences. Run on real traffic before any cutover.
7. **Triage differences**: each is a new bug, an old bug, or acceptable noise (masked ids, timestamps). Fix new bugs; record old bugs with `decision-log`; mask noise in the comparator.
8. **Cut over per slice**: raise the flag by steps (internal, small percent, all). Watch error rate, latency, and the difference log at each step.
9. **Keep rollback live**: flipping the flag back restores the old path in one action. Rehearse it once before the first cutover.
10. **Retire**: after the slice runs clean for the agreed period, remove its flag, its old code, and its comparator in a separate commit. Repeat for the next slice.
11. **Finish**: delete the routing layer if it has no other purpose. An old path left behind with no traffic is debt; schedule its deletion with a date.

## 3. Comparator Rules

- Compare the observable result: response body, status, side effects written, messages sent.
- Shadow calls must not duplicate side effects: stub writes, emails, charges, and queue publishes on the new path, or route them to a sandbox.
- Normalise before comparing: sort collections, round numbers at the documented place, mask ids and timestamps.
- Log inputs with each difference so it can be replayed in a test; scrub personal data per `data-privacy`.
- Cutover needs a stated threshold (for example zero unexplained differences over N requests), written before the run.

## 4. Data Shared by Old and New

- Both paths read the same store when possible; avoid a copy that can drift.
- A schema change goes expand, migrate, contract, with `database-migration`; the old path must keep working until its slice is retired.
- Writes by the new path must remain readable by the old one until rollback is no longer needed.

## 5. Tracking

| Per slice | Record |
| :--- | :--- |
| Name and owner | Who decides cutover |
| Flag name and state | off, shadow, percent, all, retired |
| Difference count | Open, fixed, accepted |
| Rollback | How, and last rehearsed on |
| Old code deleted on | Date and commit |

## 6. When to Give Up and Rewrite

Rewrite (or `legacy-parity` rebuild) only when most of these hold:
- No seam is reachable at acceptable cost, and outside-in pins cannot cover the behaviour.
- The platform or language is unsupported, with no security patches.
- The code is small enough that the rebuild is shorter than the safe-step path, and its behaviour is fully written down.
- The business can accept the freeze or parallel-run cost.
- An owner approved the rewrite in writing, recorded in `decision-log`.

If only "the code is ugly" holds, do not rewrite: keep the small steps.
