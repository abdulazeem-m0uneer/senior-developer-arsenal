# Mobile Security Checklist

Categories follow the OWASP MASVS control groups (STORAGE, CRYPTO, AUTH, NETWORK, PLATFORM, CODE, RESILIENCE, PRIVACY). Test procedures live in the OWASP MASTG at mas.owasp.org. Mark each row pass, fail, or not applicable with evidence.

---

## 1. Checklist by MASVS Category

### STORAGE: Data at Rest
- [ ] Tokens, refresh tokens, and keys live in iOS Keychain or Android Keystore-backed storage (expo-secure-store, react-native-keychain, flutter_secure_storage), never in AsyncStorage, MMKV, SharedPreferences, or plain files.
- [ ] Keychain items use the strictest accessibility that fits (after first unlock, this device only); no iCloud sync for secrets.
- [ ] Android backup rules exclude secrets and sensitive databases; check `allowBackup` and data-extraction rules.
- [ ] Personal data in local databases is minimised, encrypted where sensitive, and wiped on logout.
- [ ] No sensitive data in logs, analytics events, crash reports, push payloads, or clipboard; strip logs in release builds.
- [ ] Screenshots and app-switcher previews of sensitive screens are masked (secure flag on Android, blur on backgrounding on iOS).

### CRYPTO
- [ ] Use platform crypto APIs or vetted libraries; no custom algorithms, no hard-coded keys or IVs, no ECB.
- [ ] Keys are generated on device and bound to the Keystore or Keychain where possible.
- [ ] Randomness from a secure source only.

### AUTH: Authentication and Session
- [ ] Authorization is decided on the server for every request; the app only hides UI.
- [ ] Short-lived access tokens, rotating refresh tokens, server-side revocation, logout that revokes server-side.
- [ ] Refresh handled once per expiry (single in-flight refresh); reuse of a rotated refresh token invalidates the family.
- [ ] Biometric unlock gates a Keystore or Keychain key use, not just a boolean in app code.
- [ ] OAuth and OIDC use the system browser with PKCE and claimed HTTPS redirect links; no embedded WebView sign-in.
- [ ] Step-up authentication for sensitive actions, enforced by the server.

### NETWORK
- [ ] TLS only; no cleartext traffic exceptions (App Transport Security, Android network security config) in release.
- [ ] Never disable certificate or hostname validation, including in debug flags that could ship.
- [ ] Certificate pinning: see section 2 for the trade-off; pin the public key of an intermediate or keep a backup pin.
- [ ] Request signing or payload encryption envelopes, if used, are defence in depth only; they never replace TLS, server-side authorization, or input validation, and a key shipped in the app is not a secret.

### PLATFORM: Interaction with the OS and Other Apps
- [ ] Deep links and Android intents: treat every parameter as hostile; validate scheme, host, and values; require authentication before acting; prefer verified App Links and Universal Links over custom schemes.
- [ ] Exported Android components limited to what must be exported, with permissions; PendingIntents immutable.
- [ ] WebViews: JavaScript off unless needed, no `file://` access, restrict navigation to an allow-list of origins, no JS-to-native bridges exposed to remote content, disable debugging in release.
- [ ] Request the minimum runtime permissions, with a rationale shown before the prompt.
- [ ] Clipboard, share sheets, and custom keyboards: do not place secrets on the clipboard; mark sensitive inputs to bypass third-party keyboards and autofill logging.

### CODE: Code Quality and Supply Chain
- [ ] Dependencies pinned with lockfiles (`package-lock.json`, `pubspec.lock`, `Podfile.lock`, Gradle lock); audited in CI (`npm audit`, `dart pub outdated`, OSV scanning).
- [ ] Each native module and plugin reviewed for maintainer health, permissions it adds, and install scripts; prefer few, well-maintained packages.
- [ ] Release builds strip debug code, test endpoints, and dev menus; no secrets in the bundle (see section 3).
- [ ] Minimum OS and target SDK kept current.
- [ ] Input from deep links, push, and web content is validated before reaching native code.

### RESILIENCE: Reverse Engineering and Tampering
- [ ] Root, jailbreak, emulator, and hooking-framework detection used as a risk signal sent to the server, not a hard guarantee; attackers bypass it.
- [ ] Minification and obfuscation (R8/ProGuard, Hermes bytecode, Dart `--obfuscate` with split debug info) raise effort only; they do not protect secrets.
- [ ] Play Integrity and App Attest (or DeviceCheck) verdicts verified server-side for high-risk actions.
- [ ] Decide the resilience level by app risk (banking versus content app); do not pay UX cost without a threat.

### PRIVACY
- [ ] Collect only what is needed; data-safety and privacy-label answers match actual SDK behaviour.
- [ ] Consent and tracking prompts are honoured before SDKs start.
- [ ] Third-party SDK data flows documented; privacy manifests present for iOS SDKs.

---

## 2. Pinning Trade-offs

| Choice | Benefit | Risk |
| :--- | :--- | :--- |
| No pinning, system trust store | No rotation outage | Trust in every installed root; user-installed CAs on rooted or managed devices |
| Pin leaf certificate | Strongest binding | Every renewal breaks old app versions; outage until users update |
| Pin public key of intermediate, plus backup pin | Survives leaf renewal | Still breaks if CA chain changes without notice |
| Pin with remote-config kill switch | Recoverable | Kill switch itself must be authenticated, otherwise it is a downgrade path |

- Rotation plan before enabling: backup pin, expiry-aware rollout, monitoring of pinning failures, and a force-update path (see release pipeline).
- Pinning is not needed for most apps; add it where the data justifies the operational risk.

## 3. Secrets

- Anything in the JS bundle, APK, or IPA is recoverable; environment variables compiled in are public.
- Third-party API keys that must be client-side are scoped (bundle id, domain, quota) and rotatable; real secrets stay behind your backend.
- Use build-time injection for non-secret config only; keep signing keys and store credentials in CI secret stores.

## 4. Verification Evidence

- Static: inspect the built IPA and APK/AAB for strings, endpoints, and debug flags.
- Dynamic: proxy traffic with a test device and confirm pinning, cleartext absence, and token handling.
- Run the relevant MASTG tests for each category and record results.
- For code-level backend findings, hand off to `security-audit`; for design-time threats, `threat-model`.
