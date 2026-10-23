---
name: reverse-engineer
description: 'Evidence-driven runbook for understanding how one feature of a third-party application works (native binary, Electron, .NET, APK, website) with the REA MCP server, then rebuilding it clean-room in the user''s own stack with tests that prove parity. Every claim carries a file, function or address and a confidence grade; authorization and license limits gate the work. Use when the user asks how an app implements something, to trace or decompile a feature, to build similar functionality, or runs /reverse-engineer. Triggers on: "how does X do", "reverse engineer", "decompile", "trace the feature", "build the same as", "REA", "/reverse-engineer". Do not use for the user''s own legacy code (use legacy-parity), production bugs (use investigate), or anything that bypasses licensing, DRM, authentication or paywalls (refuse).'
---

# Feature Reverse-Engineering Procedure

This skill guides the agent through learning how a feature works in software the user is authorized to examine, grading every finding by the evidence behind it, and rebuilding the behaviour as original code that passes the same tests as the original.

---

## 1. When to Use This Skill

Activate this skill when:
- The user wants to know how a specific feature of an application works, with evidence from its code or runtime.
- The user wants comparable functionality in their own project, built from understanding rather than copied code.
- A finding from decompiled or observed behaviour must be graded as proven, probable, or assumed.
- The user runs the `/reverse-engineer` slash command.

*Boundary*: For the user's own legacy source, use `legacy-parity`. For a defect in the user's own system, use `investigate`. Requests to defeat licensing, DRM, authentication, paywalls, or to extract secrets or user data are refused, whatever the stated purpose.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Gate and Scope
Consult: [Legal Boundaries](./references/legal-boundaries.md) when the target is commercial, the feature touches auth, payment, licensing or DRM, or the user wants the result shipped.
1. Record the target (name, version, build hash), how the user is authorized to examine it, and the license terms that apply. Without an authorization line the work stops here.
2. Pin the feature to one user action and its observable result ("press ⌘K → palette lists recent pages"). One feature per run; a second feature is a second run.
3. Define done: an explanation, or a rebuild in the user's stack, or both. Record the stack and where the rebuild lives.
4. Run `rea update` (or `npx rea-agents@latest setup`) so findings come from the current analyzers. Done when the authorization line, the pinned action, and the definition of done are written at the top of the evidence log.

### Step 2: Observe Before Reading
1. Exercise the feature from the outside first: screenshots, a HAR capture, log lines, a file-system diff, a SQLite snapshot before and after. Outside observation is the oracle the rebuild is tested against and is the only evidence that never lies about intent.
2. Turn each observation into an oracle case: input, action, observed output, side effect. Done when at least three oracle cases exist, including one failure or edge path.

### Step 3: Map the Surface
Consult: [Target Playbooks](./references/target-playbooks.md) for the entry points, tools and gotchas of the target type.
1. Pick the analyzer by target type: `analyze-javascript-application` for Electron and web bundles, static CIL inspection for .NET, JADX via REA for APKs, Hopper, Ghidra or IDA for native code, Chrome plus HAR for websites.
2. List modules, imports, exported symbols, strings, file paths, and IPC channel or route names. Keep the strings that match the oracle cases; drop the rest.
3. Done when every oracle case maps to at least one candidate entry point (file, function, or address).

### Step 4: Trace the Call Chain
Consult: [Evidence Log and Report](./references/evidence-and-report-template.md) for the row format and confidence rubric.
1. Start from the entry point of one oracle case and follow calls downward: renderer → preload → IPC → main process; activity → service → native; route → handler → storage. Record one evidence-log row per hop with location, what it does, the evidence kind, and the confidence grade.
2. Grade by evidence, never by plausibility: **proven** needs two independent kinds (static plus runtime, or two static views that agree); **probable** has one kind; **assumed** has none and lives in the Unknowns list. Pseudocode alone is probable: decompilers invent names, flatten branches, and lose types.
3. Record the data formats, storage locations, network calls, and error handling the chain touches. A chain is complete when the last hop produces the oracle case's output; a gap is a row marked assumed, never a guess written as a hop.
4. Done when every oracle case has a chain with no assumed row on its happy path, or the gaps are listed with what was searched.

### Step 5: Rebuild Clean-Room
1. Write a behaviour spec from the evidence log: inputs, outputs, formats, ordering, limits, error paths. The spec is the only bridge; decompiled output, pseudocode, assets, names, strings, and branding stay on the analysis side.
2. Implement from the spec in the user's stack with the user's conventions (`minimal-change`, `test-every-change`). Simpler than the original is fine when the oracle cases still pass.
3. Mark every place the spec rests on a probable or assumed row with a comment naming the row, so the next version update knows what to re-check.
4. Done when the implementation compiles and every spec line maps to code or to a documented omission.

### Step 6: Verify Against the Oracle
Consult: [Verification Checklist](./references/verification-checklist.md) before declaring parity.
1. Encode the oracle cases from Step 2 as tests that run against the rebuild; run the same inputs against the original where it can be driven.
2. A failing case sends the work back to Step 4, not to the test. Downgrade the rows the failure contradicts.
3. Done when all oracle cases pass, the drift check (target version and hash recorded, probable rows flagged) is in place, and the report is written in the fixed shape.

---

## 3. Verification Protocol

```bash
rea --help && rea update                                               # analyzers current
npx -y rea-agents@latest analyze-javascript-application /abs/app --json  # Electron / web bundle surface map
npm test -- reverse-engineer                                           # or: dotnet test --filter Category=Oracle, pytest -m oracle
```

| # | Location | Hop | Evidence | Confidence | Note |
| :- | :--- | :--- | :--- | :---: | :--- |
| 1 | `renderer/palette.js:212` | `openPalette()` sends `ipc:recent` | static + HAR | proven | matches oracle case 1 |
| 2 | `main/recent.js:58` | reads `recent.sqlite`, orders by `last_opened` | static | probable | ordering not confirmed at runtime |
| 3 | — | cache invalidation on rename | none | assumed | searched `rename`, `invalidate`; nothing found |

---

## 4. ⚡ Token-Saving Execution Rule

- **Oracle First, Code Second**: Never open the analyzer before the oracle cases exist; they bound what must be read.
- **Rows, Not Narrative**: Findings are evidence-log rows and the fixed report; no prose walkthrough of the decompilation.
- **Read at the Pointer**: Open a decompiled function only at the address a cross-reference or string pointed to; never page through a module.
- **Stop on the Gate**: Missing authorization, or a feature behind licensing, DRM, auth, or a paywall, ends the run in one sentence.
