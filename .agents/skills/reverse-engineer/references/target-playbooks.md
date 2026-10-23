# Target Playbooks: Entry Points, Tools, and Gotchas by Target Type

Read the one section that matches the target in Step 3. Each section lists where the feature's code lives, which REA analyzer to run, what to list first, and the traps that produce confident wrong findings.

---

## 1. Electron / JavaScript Desktop

- **Where the code is**: `resources/app.asar` (or `app.asar.unpacked`); main process entry in `package.json#main`; preload scripts bridge renderer and main; renderer bundles are usually webpack or Vite output.
- **Run**: `npx -y rea-agents@latest analyze-javascript-application /abs/path/to/app --json`.
- **List first**: IPC channel names (`ipcMain.handle`, `ipcRenderer.invoke`, `contextBridge.exposeInMainWorld`), `protocol.registerSchemesAsPrivileged`, menu and shortcut registrations, and strings from the oracle cases.
- **Gotchas**:
  - Source maps may describe a different build than the bundle shipped; trust the bundle, use the map only for names.
  - Minified names are per-build; record the IPC channel string and the exported bridge name, not the minified identifier.
  - A feature may be implemented in a remote web view (the app loads a URL); then it is a website target with an Electron shell.
  - `asar` integrity checks and fuses on recent Electron versions are protections: observing them is fine, defeating them is on the stop list.

## 2. Website / Web App

- **Where the code is**: JavaScript bundles, service workers, WebAssembly modules, and the network.
- **Run**: Chrome-family browser with REA's website observation; save a HAR of the feature's exact user action; `inspect_wasm_artifact` for `.wasm`.
- **List first**: the request sequence for the oracle case (method, path, request and response shapes, status on failure), local storage and IndexedDB keys touched, feature flags in the initial payload.
- **Gotchas**:
  - Server-side behaviour is only observable through its responses; everything inside the server is assumed unless an API document confirms it.
  - Rate limits, CSRF tokens, and signed URLs are protections; record them as hops marked "not traced: gated" rather than reproducing a bypass.
  - A/B flags change behaviour between sessions; record the flag payload with the capture.

## 3. .NET Assembly

- **Where the code is**: `.dll` and `.exe` metadata, CIL method bodies, embedded resources; `appsettings.json` and `*.config` for defaults.
- **Run**: REA static .NET inspection (metadata plus CIL). Static only: no runtime hooking is provided.
- **List first**: public types and methods named after the oracle case, attributes (`[Route]`, `[Command]`, `[JsonProperty]`), string literals, and resource names.
- **Gotchas**:
  - Obfuscated assemblies rename members but keep string literals and attribute data; trace from those.
  - `async` methods compile to state machines; the method named in the UI is the stub, the body is in `<Name>d__N.MoveNext`.
  - Interface dispatch and dependency injection hide the concrete implementation; find the registration (`services.Add...`) before trusting a call target.

## 4. Android APK

- **Where the code is**: `classes*.dex` (JADX decompile), `AndroidManifest.xml`, `res/` and `assets/`, native `lib/*.so`.
- **Run**: REA Android analysis (JADX plus JDK, Apktool for resources); `inspect_apk_signature` for signing facts; `adb` only on a device the user owns.
- **List first**: the activity or fragment for the oracle case, intent filters, content providers, `WorkManager` and `JobScheduler` registrations, and the retrofit/okhttp interfaces.
- **Gotchas**:
  - Kotlin coroutines and R8 inlining scatter one feature across synthetic classes; trace by string and by the generated `$1` lambdas.
  - Logic may live in a `.so`; that becomes a native target.
  - Certificate pinning and root detection are protections: record, do not defeat.

## 5. Native Binary (PE, ELF, Mach-O)

- **Where the code is**: the main executable plus the dynamic libraries loaded at the oracle action.
- **Run**: Hopper, Ghidra, or IDA through REA (IDA via the native MCP bridge when licensed); `objdump` and Rizin for offline inspection.
- **List first**: imports (which system calls the feature must make: file, socket, crypto, registry), exported symbols, strings from the oracle case, and cross-references from those strings.
- **Gotchas**:
  - Decompiler pseudocode is a hypothesis: types, signedness, and struct layouts are inferred and often wrong; confirm a value by its runtime effect (a file written, a packet sent) before grading it proven.
  - Stripped binaries lose names; a cross-reference graph from a string is worth more than any guessed name.
  - Packed or encrypted sections are protections and stop the trace at that boundary.
  - Go, Rust, and IL2CPP binaries have their own symbol recovery in REA; use it before manual naming.

## 6. Data at Rest and in Flight

- SQLite snapshots: copy the file with the app closed, diff `before` and `after` the oracle action (`sqlite3 before.db .dump > a.sql`, same for after, then `diff`). Schema plus the changed rows are proven evidence of storage format.
- Saved captures: `tshark -r capture.pcapng -Y '<filter>'` for non-HTTP protocols; `capinfos` for the capture's bounds.
- Firmware: Binwalk or Unblob to carve, then each component is one of the targets above.
