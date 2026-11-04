# Mobile Release Pipeline

Facts checked against docs.expo.dev, developer.android.com, and developer.apple.com on 2026-11-04. Store policies change; re-read them before each submission.

---

## 1. Signing and Identity

| Platform | Artefact | Rule |
| :--- | :--- | :--- |
| iOS | Distribution certificate, provisioning profile, bundle id, capabilities | Profiles must match certificate, bundle id, and entitlements; automate with EAS credentials, Fastlane match, or Xcode managed signing. Certificates expire; calendar the date. |
| Android | Upload key signs the bundle; Google holds the app signing key through Play App Signing | Enrol in Play App Signing; sign uploads with a separate upload key; if the upload key is lost or leaked, request an upload key reset. The app signing key cannot be retrieved. |
| Both | Keystore and certificate backups | Store in a secrets manager with two owners; never in the repo. |

- Android App Bundles are the Play format; Play builds and signs the APKs per device.
- To share one signing key across several stores, supply your own app signing key instead of letting Google generate it, and accept the custody risk.

## 2. Versioning

- User-facing version follows semver; build number (iOS `CFBundleVersion`, Android `versionCode`) increases monotonically on every upload and is never reused.
- Let CI assign build numbers (EAS remote versioning or a pipeline counter); do not commit them by hand.
- Tag the commit that produced each store build and keep source maps and symbols per build.
- Use `git-release` for tags and changelogs.

## 3. Build and Submit Tooling

- Expo: EAS Build for cloud builds with profiles (development, preview, production), EAS Submit to the stores, EAS Update for over-the-air JavaScript changes.
- Bare React Native or Flutter: Fastlane (`gym`, `pilot`/`deliver`, `supply`), or platform CLIs (`flutter build ipa`, `flutter build appbundle`), inside GitHub Actions or another runner; macOS runners are required for iOS.
- Cache dependencies and derived data; pin Xcode, JDK, Node, and Flutter versions per build.
- Pipeline stages: lint and tests, signed build, upload symbols and source maps, internal distribution, store submission. Secrets come from the CI secret store, injected at job time (see `devops-ci`).
- Preview builds for every merge to main via internal channels (TestFlight internal, Play internal testing, EAS internal distribution).

## 4. Over-the-Air Updates

- EAS Update delivers JavaScript, styling, and image changes without a new binary. It cannot change native code or dependencies, permissions, or the SDK version; those need a new build.
- A runtime version ties each update to compatible native code; change it whenever native code changes so incompatible binaries never receive the update.
- Store rules apply to OTA content: do not use updates to change the app's primary purpose or to download executable code that circumvents review. Re-read the current Apple and Google policy before relying on a specific allowance.
- Use channels and percentage rollouts; roll back by republishing the last good update.
- Flutter has no first-party equivalent; third-party code-push products exist, so check the same store rules and vendor maintenance before adoption.
- Sign updates (code signing) where the platform supports it, so a compromised update host cannot ship code.

## 5. Staged Rollout and Release Health

- iOS: phased release over seven days, pausable; Play: staged rollout by percentage, haltable.
- Rollout plan: internal, then 1 to 5 percent, then 20, 50, 100, with a halt criterion per step (crash-free sessions and ANR rate against baseline, key funnel metric, support volume).
- Crash reporting (Sentry, Firebase Crashlytics, or equivalent): upload dSYMs, mapping files, Hermes or Dart symbol files and source maps in CI, tied to release and build number.
- Watch release health for the first 24 to 48 hours; define who can pause and who decides.
- A server-side feature flag is the fastest rollback for behaviour; a native bug requires a hotfix build or an OTA fix if JS-only.

## 6. Force-Update and Compatibility

- Ship the force-update mechanism in the first release: a server-provided minimum supported version, a soft prompt for recommended versions, and a blocking screen for required ones.
- API versioning keeps old clients working for a defined support window; announce end of support in-app first.
- Use the stores' in-app update APIs where available, and always link to the store listing as fallback.
- Required before pinning, security fixes, and breaking API changes.

## 7. Store Review Checklist

- Metadata matches behaviour; screenshots current; demo account and reviewer notes supplied if login is required.
- Permission usage strings (iOS) and permission declarations (Android) are specific and justified.
- Account deletion available in-app and from the listing where the store requires it for apps with account creation.
- In-app purchases follow each store's payment rules for digital goods.
- Target API level meets the current Play requirement and the build uses the current required Xcode/SDK for the App Store; check the developer pages each year.
- Privacy: iOS privacy manifests for the app and bundled SDKs, including declared reasons for required-reason APIs, plus privacy nutrition labels; Play Data safety form and privacy policy URL. Answers must match actual collection by every SDK.
- Test the exact release binary on a clean device, not the debug build.
- Keep a rollback and hotfix path ready before pressing submit; store review time varies, so never schedule a launch against the review clock.
