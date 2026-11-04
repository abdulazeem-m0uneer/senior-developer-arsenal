# Flutter Guide

Facts checked against docs.flutter.dev on 2026-11-04. Re-check version-specific claims before relying on them.

---

## 1. Platform Status (verify per project)

| Topic | Current state | Action |
| :--- | :--- | :--- |
| Impeller | Default renderer on iOS (no Skia switch) and on Android API 29+, with fallback to the legacy OpenGL renderer on older or non-Vulkan devices. Web uses Skia. | Profile with Impeller on; opt out only to isolate a rendering bug, then file an issue. |
| Desktop | Impeller is enabled by default on macOS, Linux, and Windows from 3.47; opt-out is slated for removal. | Test desktop targets on the default renderer. |
| Shader jank | Shaders precompile at engine build time, so shader warm-up workarounds are no longer the first fix. | Look for layout, build, or raster cost before suspecting shaders. |

---

## 2. Structure and State

- Feature-first: `lib/features/<name>/{data,domain,presentation}`; `lib/core` for networking, storage, theme, routing.
- Navigation: a declarative router (go_router) with typed routes; validate deep-link parameters in the route builder.
- State: Riverpod (providers, `AsyncValue` for loading, data, error) or Bloc/Cubit for event-driven flows; pick one per app.
- Keep widgets dumb: they read state and dispatch intents; repositories own data sources.
- Server state: repository with cache policy (memory, then local DB, then network); expose a Stream or `AsyncValue`; invalidate on mutation.
- Immutable models (freezed or records) and `json_serializable` or generated clients from OpenAPI for typed contracts.
- Render every `AsyncValue` state: loading, empty, error with retry, data.

## 3. Offline-First and Sync

- Local source: Drift or sqflite for relational data, Isar or Hive-like stores only if maintained and justified; secure storage is for secrets, not data.
- Outbox pattern as in React Native: queued mutations, idempotency keys, ordered replay, server dedupe.
- Run sync in a background mechanism the OS permits (WorkManager, BGTaskScheduler through a plugin); assume it can be delayed or skipped.
- Conflict rule per entity chosen before coding; use server timestamps or version numbers, never device clocks.
- Expose sync status in the UI and test with connectivity toggled mid-request and process death.

## 4. API Client Layer

- Dio (or http) wrapped in one client class; an interceptor attaches the token, refreshes once with a single in-flight future, and retries.
- Map transport errors to a sealed class (network, auth, validation, server) consumed by the UI.
- Set connect and receive timeouts; support cancellation tokens on screen exit.

---

## 5. Performance: Measure First

- Profile in profile mode on a physical device (`flutter run --profile`); debug mode is not representative and emulators lie about GPU.
- Open DevTools: Performance view for frame timeline (UI thread build/layout vs raster thread), CPU profiler for hot Dart code, Memory view for leaks and allocation, Widget rebuild counts via the Inspector.

| Symptom | Where to look | Fix |
| :--- | :--- | :--- |
| UI-thread frames over budget | Build or layout cost | Split large `build` methods, push state down, use `const` constructors, avoid work in `build` |
| Raster-thread frames over budget | Saveable layers, clips, opacity, blurs | Remove `saveLayer` triggers, avoid large `Opacity` and `ClipRRect` on animated content, use `RepaintBoundary` where it isolates repaint |
| Long list jank | Eager children | `ListView.builder` or slivers, fixed `itemExtent` when rows are uniform, keys for stateful rows |
| Freeze on parse or crypto | Main isolate | `Isolate.run` / `compute` for heavy parsing, image processing, or hashing |
| Large memory | Images | Decode at display size (`cacheWidth`, `cacheHeight`), dispose controllers and subscriptions |

- Rebuild control: `const` widgets, `select` on Riverpod providers, `BlocSelector`, `ValueListenableBuilder` scoped to the changing leaf.
- Do not call `setState` high in the tree; do not create futures or streams inside `build`.
- Animations: prefer implicit animations and `AnimatedBuilder` with a `child` argument so static subtrees are not rebuilt.
- Startup: defer heavy plugin initialisation until after the first frame, avoid blocking `main()`, and use deferred components or lazy routes only when measured startup justifies them.
- Check app size with the size-analysis build option before removing dependencies.

---

## 6. Testing

- Unit: pure Dart tests for domain and repositories; mock data sources with fakes.
- Widget: `flutter_test` with `pumpWidget`, find by semantics or key, `pump` with durations instead of real timers; override providers in a `ProviderScope`.
- Golden tests: reserve for a few design-system components, generate on one platform in CI, and review diffs by eye.
- Integration: `integration_test` package on real devices or a device farm; or Maestro for black-box flows.
- Matrix: lowest supported Android API and iOS version, one tablet or foldable if supported, plus text-scale and dark-mode runs.
- Run `flutter analyze` with strict lints and fail CI on warnings.
