# STRIDE Catalogue

STRIDE (Microsoft): Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege. Use per element, per boundary crossing.

## Which Letters Apply to Which Element

| Element type | S | T | R | I | D | E |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| External entity / actor | x | | x | | | |
| Process (service, function, job) | x | x | x | x | x | x |
| Data store (DB, cache, bucket, queue) | | x | x* | x | x | |
| Data flow (network, IPC, message) | | x | | x | x | |
| Trust boundary crossing | x | x | | x | x | x |

*Repudiation applies to stores that hold audit or log data.

## Letter Prompts

| Letter | Ask | Typical mitigation family |
| :--- | :--- | :--- |
| S | Can the caller claim to be someone or something else? | Authentication, signed requests, mutual TLS |
| T | Can data or code be changed in transit, at rest, or by the client? | Integrity checks, server-side validation, signing, least-privilege writes |
| R | Can an actor deny an action, or can we not prove it? | Audit log with actor, time, and request id; append-only storage |
| I | Can data reach someone not entitled to it (response, log, error, backup, cache)? | Authorization, field filtering, encryption, log redaction |
| D | Can a caller exhaust CPU, memory, connections, quota, or money? | Limits, timeouts, quotas, backpressure, pagination caps |
| E | Can a caller do something above their role or tenant? | Server-side authz on every object and function, deny by default |

## Per-Boundary Questions

- What does the receiving side trust that the sender controls?
- Is identity re-established at this boundary, or inherited from a header?
- What is the maximum size, rate, and shape accepted?
- What happens on failure: fail closed, or fall through to a default role?

## API Catalogue

| Threat | STRIDE | Check | Implement via |
| :--- | :---: | :--- | :--- |
| BOLA / IDOR: object fetched by id without owner or tenant filter | I, E | Every lookup filters on session-derived owner or tenant | `security-audit`, `database-standards` |
| Function-level authz missing on admin or internal routes | E | Deny by default; role check per route | `security-audit`, `api-design` |
| Mass assignment: client sets role, owner, price, status | T, E | Explicit allow-list DTO per write route | `api-design`, `nodejs-backend-expert` |
| Request tampering: price, quantity, or id altered in body | T | Server recomputes derived values; never trust client totals | `payments-integrity` |
| Replay of a captured request or webhook | S, T | Nonce or timestamp window, idempotency key, signature | `provider-sdk`, `api-design` |
| Forged webhook or callback | S | Verify signature on the raw body before parsing | `provider-sdk` |
| SSRF: server fetches a caller-supplied URL | I, E | Allow-list hosts, block private and metadata ranges, no redirects by default | `security-audit` |
| Rate-limit abuse: credential stuffing, enumeration, scraping | D, S | Per-identity and per-IP limits, uniform error text, lockout backoff | `api-design` |
| Resource exhaustion: unbounded page size, upload, query depth | D | Caps on page size, body size, nesting, query cost | `api-design`, `nodejs-backend-expert` |
| Excessive data exposure: whole entity serialised | I | Response DTO per route; no internal fields | `api-design`, `data-privacy` |
| Verbose errors and stack traces | I | Problem-details body without internals; detail goes to logs | `api-design` |
| Sensitive data in logs, URLs, or analytics | I | Redact tokens and PII; no secrets in query strings | `data-privacy`, `observability` |
| Token theft or non-expiring token | S, E | Short expiry, rotation, revocation list, audience and issuer checks | `security-audit` |
| Tenant crossover in shared cache, queue, or job | I, E | Tenant id in every key and message; verify on consume | `shared-infra-changes` |
| Supply chain: malicious or vulnerable dependency, install script, CI action | T, E | Lockfile, pinned versions, audit gate in CI, no unpinned remote code | `dependency-upgrade`, `devops-ci` |
| Secret in repo, image, or CI log | I | Secret store, scanning, rotation plan | `security-audit`, `devops-ci` |
| Stale or shared admin credential, no audit trail | R, S | Per-person identity, audit log of privileged actions | `security-audit` |
| Third-party outage or compromise | D, T | Timeouts, circuit breaker, validate vendor payloads as untrusted | `provider-sdk` |

## Mobile and Client-Side Catalogue

Treat the client as attacker-controlled: it can be decompiled, proxied, rooted, and scripted.

| Threat | STRIDE | Check | Implement via |
| :--- | :---: | :--- | :--- |
| Token in plain local storage or app preferences | I, S | Platform secure storage (keychain, keystore); on web prefer HttpOnly cookie over script-readable storage | `fullstack-integration-master`, `security-audit` |
| Token or PII in device backup, screenshot, clipboard, or app switcher | I | Exclude from backup, mask sensitive screens, clear clipboard | `frontend-audit` |
| Secret or API key embedded in the binary or bundle | I | Assume extractable; keep secrets server-side, scope client keys | `security-audit` |
| Stolen refresh token reused from another device | S | Rotation with reuse detection, device binding where available, revoke on anomaly | `security-audit` |
| Man-in-the-middle on hostile network | I, T | TLS only; consider certificate pinning with a rotation plan | `fullstack-integration-master` |
| Client-side checks as the only control (price, role, feature flag, rate) | T, E | Duplicate every check on the server; client checks are UX only | `fullstack-integration-master` |
| Request envelope tampering or replay from a proxy | T, S | Signed or encrypted envelope plus nonce and timestamp; server verifies | `api-design` |
| Deep link or intent hijack carrying auth or action parameters | S, T | Validate parameters, require re-auth for sensitive actions, no tokens in links | `frontend-audit` |
| Outdated client with known flaws still accepted | E | Minimum supported version gate on the server | `api-design` |
| Offline cache holds data after logout | I | Wipe local stores on logout and token revoke | `frontend-audit` |
| XSS or injected markup in web views | T, I, E | Output encoding, CSP, no untrusted HTML in privileged web views | `frontend-audit` |

## Abuse Case Prompts

- Which asset would an attacker want most, and what is the cheapest path to it?
- How could a paying, legitimate user abuse the feature for gain (promo stacking, refund loops, data scraping)?
- What could an insider or a compromised vendor do with the access this design grants?
- What is the worst thing one stolen credential allows, and how soon would we notice?
