# Shortcut Debt Ledger & Lean Findings

## 1. Shortcut Ledger

The `minimal-change` rule marks every deliberate limit as `shortcut: <ceiling>, <upgrade trigger>`. The ledger collects them so a deferral cannot quietly become permanent.

```bash
git grep --no-index --exclude-standard -nE '(#|//|/\*|--|<!--) ?shortcut:'      # add the stack's comment prefixes
git blame -L<line>,<line> --porcelain <file> | grep -E '^(author|author-time)'   # owner and age per row, on request
```

The comment prefix keeps prose that merely mentions the word out of the ledger; skip hits that are not deferrals (a keyboard shortcut). A user-named marker (`TODO`, `HACK`) is grepped instead when asked.

Output, one row per marker, grouped by file:

```text
<file>:<line>, <what was simplified>. ceiling: <limit named>. upgrade: <trigger named>.
```

A marker that names no ceiling or no trigger is tagged `no-trigger`; those rot silently. End with `<N> markers, <M> with no trigger.` or `No shortcut debt.` Reads only; writes a ledger file (`docs/SHORTCUT-DEBT.md`) only when asked.

---

## 2. Lean Findings (what should not exist)

| Kind | Sign | Fix |
| :--- | :--- | :--- |
| Delete | dead code, unused option, flag, or config, speculative feature | remove; grep the whole tree first, including tests, fixtures, config, string and dynamic references |
| Reuse | two helpers doing one job | keep one, name the path |
| Stdlib / platform | a dependency or helper doing what the standard library or platform already does | replace; drop the dependency |
| YAGNI | interface with one implementation, factory with one product, pass-through wrapper, config nobody sets | inline |
| Merge | near-copies that must change together | one unit |
| Split | one function or class doing several unrelated jobs | split by job; never by line count; never into helpers that exist only to shorten a function |

Lean findings sit below correctness, safety, scale, tests, and speed. They still count: every extra line is read, tested, and fixed later. Report `Lean: -<N> lines, -<M> dependencies possible.` when any exist.

---

## 3. Scale Findings Need a Load

Find the expected load before judging scale: README, deploy config, replica count, queue consumers. One person running a script and a thousand concurrent users make different code wrong. Scale findings: check-then-write races, work repeated by every process, lists or caches that only grow, a query per item, O(n^2) on real input sizes, per-process state that must be shared. Name the load assumed in the report.

---

## 4. Finding Shape for a Non-Specialist Reader

When the audience may never have seen the code, every finding carries four short parts and a plain-English title:

```text
3. Orders land on the wrong day (billing/close_day.py:40-52)
   What this is: at midnight this job closes the day and bills that day's orders.
   Problem: "today" comes from the server clock in UTC; an order at 00:30 in Berlin bills the day before.
   Fix: compute the day once in the shop's time zone. One line.
   If we skip it: late orders carry the wrong date and accounting corrects them by hand.
```

No finding without a concrete case (`this input leads to this wrong result`); no `consider`, no style taste, no vague worries. Number findings across all severity groups so the user can say `fix 2 and 5`. Cap at 20 and state how many smaller ones were left out. Close with `Verdict:` (ship, or what to fix first), the lean line, and `Not checked:`.

Adapted from Ponytail by DietrichGebert (MIT).
