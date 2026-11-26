# Optional Mobile Scanners

Run a tool only when it is already installed; otherwise finish the checklist by hand and say which tool was not run. Scan only builds of the user's own app.

| Tool | Use when | Command |
| :--- | :--- | :--- |
| MobSF | Static scan of a release APK or IPA: hardcoded secrets, insecure storage, exported components, cleartext traffic | Start MobSF as its own install instructions describe (`mobsf` on port 8000), then upload the build and export the JSON report |
| QARK | Android-only static scan of source or APK when MobSF is unavailable | `qark --apk <app.apk>` |
| drozer | Probe exported activities, providers and services on a test device | `drozer console connect`, then `run app.package.attacksurface <package>` |

Map each scanner hit to a MASVS item in the checklist; a hit with no matching item is reported as hardening.
