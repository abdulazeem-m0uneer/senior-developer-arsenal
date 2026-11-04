# React Native Guide (Expo and Bare)

Facts checked against reactnative.dev and docs.expo.dev on 2026-11-04. Re-check version-specific claims before relying on them.

---

## 1. Platform Status (verify per project)

| Topic | Current state | Action |
| :--- | :--- | :--- |
| New Architecture | The only runtime option since React Native 0.82; legacy code is being removed release by release. | Do not plan new work on the bridge; replace libraries that lack New Architecture support. |
| Expo SDK | From SDK 55 the New Architecture is always on; SDK 53 and 54 allowed opt-out; Expo Go supports only the New Architecture. | Test on a development build, not only Expo Go. |
| Hermes | Hermes V1 is the default engine from 0.84. | Keep Hermes bytecode builds on; do not benchmark with a remote debugger attached. |
| iOS builds | Precompiled React Native binaries are the default from 0.84. | Build from source only to opt out of a default. |

- Read the release blog and upgrade helper for the exact version before migrating; support covers only recent minors.

---

## 2. Stack and Project Shape

- Default to Expo: development builds, config plugins, prebuild, EAS. Custom native code is allowed through config plugins or local modules without ejecting.
- Go bare only when a requirement cannot be met by a plugin, a local Expo module, or a TurboModule; record why in an ADR.
- Feature-first layout: `src/features/<name>/{screens,components,hooks,api,__tests__}`, plus `src/shared` for cross-feature primitives and `src/app` for providers and routes.
- Navigation: file-based routing (Expo Router) or React Navigation; both sit on native navigators. Keep screens thin: they compose hooks and components.
- Type every route parameter; validate deep-link params at the screen boundary.
- Keep native-module count low; each one is upgrade and supply-chain cost.

---

## 3. State and Server State

- TanStack Query owns server data: query keys per entity and filter, `staleTime` set per query, `gcTime` long enough for back navigation.
- Local UI state stays in the component; shared client state goes to a small store (Zustand or Context) holding only UI and session flags.
- Mutations: optimistic update with rollback snapshot, then invalidate; see `fullstack-integration-master` for the pattern.
- Persist the query cache only for data safe at rest; exclude tokens and personal data, and bust the cache on logout.
- Wire `onlineManager` to NetInfo and `focusManager` to app state so refetch follows connectivity and foregrounding.

## 4. Offline-First and Sync

- Local source: SQLite (expo-sqlite, op-sqlite) or an embedded database; use MMKV only for small key-value data, not tokens.
- Outbox table: mutation, payload, idempotency key, attempt count, status. Replay in order; the server must dedupe by key.
- Conflict rule per entity: server-authoritative, last-write-wins by server timestamp, or field-level merge. Never compare device clocks.
- Surface sync state in the UI (pending, failed, conflict) and give failures a retry or discard path.
- Test with airplane mode, flaky network throttling, and app kill during sync.

## 5. API Client Layer

- One module exports typed functions; screens never call `fetch` directly.
- Generate types from OpenAPI or a schema (see `e2e-type-safety`); validate untrusted responses at the boundary with a schema library.
- Central interceptor: attach token, refresh once on 401 with a single in-flight refresh promise, then retry; on refresh failure clear session and navigate to sign-in.
- Set timeouts and cancellation (`AbortController`); map errors to a small typed set (network, auth, validation, server) that the UI renders.
- Every screen defines loading (skeleton, not spinner-only), empty, error with retry, and stale-data states.

---

## 6. Performance: Measure First

| Symptom | Likely bound thread | Measure with | Typical fix |
| :--- | :--- | :--- | :--- |
| Touch lag, slow navigation | JS thread busy | React Native DevTools profiler, performance monitor | Defer work, split renders, move parsing off the hot path |
| Dropped frames while scrolling | UI thread or too many views | Platform profilers (Instruments, Android Studio / Perfetto) | Virtualise, simplify view depth, resize images |
| Slow cold start | JS bundle load, native init | Release build trace, startup marks | Lazy-load screens, trim imports, defer SDK init |
| Memory growth | Images, caches, listeners | Xcode memory graph, Android Profiler | Size images, clear subscriptions, bound caches |

- Profile release builds on a mid-range physical Android and an older iPhone; dev mode inflates costs.
- Lists: use FlatList with `keyExtractor`, stable `renderItem`, `getItemLayout` for fixed rows, tuned `windowSize` and `initialNumToRender`; consider FlashList for large or heterogeneous lists. Never nest a vertical list in a ScrollView of the same axis.
- Re-renders: memoise rows (`React.memo`) with stable props, `useCallback` only where it feeds a memoised child, colocate state, select narrow slices from stores. The React Compiler can automate memoisation where adopted; measure rather than assume.
- Animation: run on the UI thread (Reanimated worklets); avoid driving animation from React state.
- Images: serve the displayed size, use a caching image component (expo-image), modern formats, and placeholders.
- Large JSON: parse and transform on the server, paginate, or request only needed fields; avoid multi-megabyte `JSON.parse` on the JS thread and large objects crossing into native.
- Startup: lazy `require` heavy screens, inline requires or Expo Router lazy routes, initialise analytics after first render, keep the splash screen until data for the first screen is ready.
- JSI and TurboModules allow synchronous native calls; keep them short, since they block the JS thread.
- Check bundle composition with a bundle visualiser before removing dependencies.

---

## 7. Testing

- Unit and component: Jest with React Native Testing Library; query by role, text, or label as a user would; mock native modules at the boundary only.
- Server state in tests: a fresh `QueryClient` per test with retries off; mock the network (MSW) rather than hooks.
- E2E: Maestro (YAML flows, quick to author) or Detox (gray-box, synchronised with the app); cover sign-in, the core purchase or create flow, and offline recovery.
- Snapshots: only for small stable output such as serialisable data; large component snapshots get approved blindly and hide regressions.
- Matrix: lowest supported OS, latest OS, one small-screen and one large device each; pick from your analytics.
- Run E2E on release-like builds in CI against a seeded backend; keep the suite under about ten minutes.
