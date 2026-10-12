---
name: legacy-parity
description: 'Runbook for rebuilding a legacy system while keeping its behaviour, and a frozen interface, the same: answer what the legacy does from source with file and line, pin it with characterisation tests, rebuild cleanly, audit differences as a table, and sync with the moving legacy branch. Use when the user asks what the legacy does, to check parity, or runs /legacy-parity. Triggers on: "what does the legacy do", "parity check", "same as legacy", "legacy sync", "/legacy-parity". Do not use for judging a design on its merits (use ui-ux-audit) or moving data (use database-migration).'
---

# Legacy Parity Procedure

This skill guides the agent through learning behaviour from a legacy system's source, rebuilding it cleanly with the same observable behaviour, auditing the differences, and keeping the rebuild in step while the legacy keeps moving.

---

## 1. When to Use This Skill

Activate this skill when:
- A specification or a decision needs the answer to "what does the legacy do here?", with evidence.
- Rebuilding a feature, endpoint, job, or screen whose behaviour or appearance must stay the same.
- Auditing a rebuilt screen or flow against its legacy original.
- The legacy branch moved and its changes must be carried into the new build.
- The user runs the `/legacy-parity` slash command.

*Boundary*: For reviewing a design on its own merits or proposing improvements, use `ui-ux-audit`. For moving the data itself, use `database-migration`. For recording why a deliberate difference was accepted, use `decision-log`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Fix the Ground Rules
1. Record the legacy source of truth: repository, branch, and the commit last synced. A parity claim without a commit is unverifiable.
2. Record what is frozen: behaviour only, or behaviour and interface (layout, colours, spacing, typography, icons, wording, motion).
3. Record who may approve a difference and where approved differences are written. Until one is written, the legacy wins.
4. Treat the legacy checkout as read-only. Nothing is fixed, formatted, or upgraded there.

### Step 2: Answer "What Does the Legacy Do Here?"
Consult: [Behaviour Answer Template](./references/behaviour-answer-template.md)
1. Search cheapest first: the code-search tool for symbols and call paths, text search for literals (a route, an error code, a setting name, a screen string), then read only the lines a search pointed to.
2. Answer in the fixed shape: what it does, where (`path:line` per claim), who can reach it, what was not found.
3. State numbers with their units and where they are set (constant, setting, default).
4. Never fill a gap with what is likely. A gap goes to the open questions with what was searched.

### Step 3: Pin the Behaviour, Then Rebuild Cleanly
1. Write characterisation tests from the legacy answer: inputs, outputs, side effects, error codes, ordering, and rounding, including behaviour that looks wrong.
2. Rebuild against those tests. The legacy logic is read to learn behaviour and is not ported: no copied functions, structure, or naming.
3. Where the interface is frozen, carry the visual layer over (layout, styles, assets, strings) and rebuild only the behaviour behind it.
4. Reuse from an earlier rebuild only where it already matches the legacy exactly; where they differ, the legacy wins.

### Step 4: Run the Parity Audit
Consult: [Parity Checklist & Difference Table](./references/parity-checklist.md)
1. Compare item by item, in every language, direction, and state (loading, empty, error, disabled) the legacy has.
2. Check nothing was added that the legacy lacks and nothing removed that it has.
3. Report each difference as a table row: location, legacy value, built value, and the fix that restores the legacy. Never propose a redesign.
4. Report accessibility problems and bugs found in the legacy in a separate table for the owner. Do not fix them silently: the fix is a difference and needs approval.

### Step 5: Sync with the Moving Legacy
1. At the start of legacy-dependent work, fetch the legacy branch and compare it with the last synced commit.
2. List what changed, grouped by feature, and mark each change: already covered, gap, or not applicable.
3. Carry each gap in through the normal workflow (specification, tests, review), not by copying the legacy commit.
4. Record one tracked task per sync, named with the commit range, listing what changed, what was carried, and what waits for an answer. Use `delivery-board-sync` for the board update.

---

## 3. Verification Protocol

```bash
git -C ../legacy fetch origin
git -C ../legacy log --oneline <last-synced>..origin/<branch>             # what moved since the last sync
git -C ../legacy diff --stat <last-synced>..origin/<branch> -- src/orders # narrowed to the feature
git -C ../legacy status --porcelain                                       # must print nothing: read-only
npm test -- characterisation                                              # or: dotnet test --filter Category=Characterisation, pytest -m characterisation
```

| Location | Check | Legacy | Built | Severity | Fix that restores legacy |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `src/orders/cancel.ts:41` | Behaviour | Cancel allowed until 30 min before start | Allowed until start | `[Blocker]` | Apply the 30 min cut-off (`legacy/orders/cancel.js:112`) |
| `src/pages/Orders.tsx:88` | Wording | "No orders yet" | "You have no orders" | `[Suggestion]` | Use the legacy string key |

---

## 4. ⚡ Token-Saving Execution Rule

- **Search, Then Read Lines**: Use the code-search tool first and open a legacy file only at the lines it pointed to; never read a legacy module whole.
- **Fixed Shapes Only**: Deliver the behaviour answer (under 40 lines, one code line per claim) or the difference tables, with no narrative around them.
- **Delta Sync**: On a sync, read only the commits after the last synced one, narrowed to the paths the rebuild covers.
