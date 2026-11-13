---
name: mobile-expert
description: 'Use for any React Native, Expo, or Flutter task: slow or janky screens, lists, startup, app architecture, navigation, state, offline sync, security hardening, testing, or store releases. Runbook: project shape, typed API client, performance measured before tuning, MASVS-aligned security, and signing-to-staged-rollout releases. Triggers on: "React Native", "Expo", "Flutter", "mobile app", "EAS Build", "certificate pinning", "App Store release", /mobile-expert. Not for visual design (use ui-ux-architect), accessibility (use accessibility-audit), design-time threats (use threat-model), or CI (use devops-ci).'
---

# Mobile Engineering Procedure

This skill guides the agent through architecture, performance, security, testing, and release of React Native (Expo and bare) and Flutter apps, measuring on real devices before changing anything.

---

## 1. When to Use This Skill

Activate this skill when:
- Choosing between Expo, bare React Native, and Flutter, or shaping a new app's folders, navigation, and state.
- Designing offline-first behaviour, sync, conflict handling, or a typed API client for a mobile app.
- A screen janks, startup is slow, a list stutters, or memory climbs on a device.
- Reviewing token storage, TLS and pinning, deep links, WebViews, or native-module risk.
- Setting up signing, store submission, over-the-air updates, staged rollout, or force-update.
- The user runs the `/mobile-expert` slash command.

*Boundary*: For visual design and screen audits, use `ui-ux-architect` and `ui-ux-audit`. For accessibility conformance, use `accessibility-audit`. For design-time threat analysis, use `threat-model`; for code-level security review of the codebase and backend, use `security-audit`. For API contracts, use `api-design`. For CI pipelines in general, use `devops-ci`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Choose Stack and Project Shape
Consult: [React Native Guide](./references/react-native-guide.md) and [Flutter Guide](./references/flutter-guide.md)
1. Record constraints first: team language skills, native-module needs, offline needs, target OS versions, release cadence, existing web code to share.
2. Default to Expo (with development builds and config plugins) for React Native; go bare only for a native requirement Expo cannot express. Choose Flutter when one rendering engine and pixel-identical UI matter more than reusing a JS or web team.
3. Organise by feature, not by type: each feature owns its screens, hooks or providers, API calls, and tests.

### Step 2: Data, State, and Offline
1. Separate server state (TanStack Query in React Native, Riverpod or Bloc in Flutter) from UI state; never copy server data into a global store.
2. Put a typed API client behind one module, generated from the contract when one exists. Every screen renders loading, empty, error, and stale states.
3. For offline-first, write to a local store first, queue mutations with idempotency keys, and define the conflict rule per entity (last-write-wins, field merge, or server-authoritative) before coding sync.

### Step 3: Measure, Then Optimise
Consult: [React Native Guide](./references/react-native-guide.md) or [Flutter Guide](./references/flutter-guide.md)
1. Reproduce on a mid-range physical device in a release or profile build; debug builds and simulators mislead.
2. Identify the bound thread (JS or UI in React Native; build, raster, or main isolate in Flutter) before choosing a fix.
3. Change one thing, re-measure, and keep the numbers in the report.

### Step 4: Apply the Security Checklist
Consult: [Mobile Security Checklist](./references/mobile-security-checklist.md)
1. Walk the checklist by MASVS category; mark each item pass, fail, or not applicable with evidence.
2. Treat client-side controls (pinning, root detection, obfuscation, request envelopes) as defence in depth; authorization and validation stay on the server.

### Step 5: Test on the Right Layers
1. Unit and component tests for logic and screens, a small E2E suite for the critical journeys, and a device and OS matrix drawn from your own analytics.
2. Prefer behaviour assertions over snapshots; see the guides for tooling.

### Step 6: Build the Release Pipeline
Consult: [Release Pipeline](./references/release-pipeline.md)
1. Automate signed builds, store upload, and crash-reporting symbol upload in CI.
2. Ship through staged rollout with a halt criterion; define the force-update path before the first release.

---

## 3. Verification Protocol

1. Run the typecheck, linter, and unit tests (`npx tsc --noEmit && npx jest`, or `flutter analyze && flutter test`).
2. Build a release artifact for each platform and install it on a physical device; run the critical journeys, including airplane mode and token expiry.
3. Confirm no secret, token, or personal data appears in the bundle, logs, or crash reports.
4. Report findings in this table:

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Security | Refresh token stored in AsyncStorage | Readable on rooted device or backup | `[Blocker]` | Move to Keychain/Keystore-backed storage |
| Performance | `FlatList` rows re-render on every keystroke | Dropped frames on mid-range Android | `[Architecture]` | Memoise rows, stable `keyExtractor`, move state down |
| Release | No halt criterion for staged rollout | Bad build reaches all users | `[Suggestion]` | Define crash-free threshold and pause step |

---

## 4. Negative Triggers

- Do not use for visual design, spacing, or token work (use `ui-ux-architect` or `ui-ux-audit`).
- Do not use for WCAG or screen-reader conformance (use `accessibility-audit`).
- Do not use for threat modelling before design is fixed (use `threat-model`) or backend vulnerability hunts (use `security-audit`).
- Do not use for REST or GraphQL contract design (use `api-design`) or generic pipeline authoring (use `devops-ci`).

---

## 5. ⚡ Token Conservation Directive

- **Targeted Reads**: Open only the feature folder, config file, or log excerpt under investigation; never dump a lockfile or native project tree.
- **Numbers, Not Narrative**: Report profiler results as before and after rows in a table.
- **Snippets Only**: Output the changed hook, widget, or config block, never the whole screen.
