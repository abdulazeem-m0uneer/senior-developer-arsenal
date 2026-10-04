# Audit Checklist & Severity Rubric

Walk every category for each entry point in scope, then score and report.

---

## 1. OWASP Top 10:2021 Checklist

- [ ] **A01 Broken Access Control**: Every route has an explicit authorization rule (deny by default). Object lookups filter on tenant or owner from the verified session (BOLA/IDOR). No role or tenant ID accepted from the request body. CORS origins are an explicit list, never a reflected `Origin` with credentials.
- [ ] **A02 Cryptographic Failures**: TLS enforced end to end; HSTS set. Passwords hashed with Argon2id (minimum 19 MiB memory, 2 iterations, parallelism 1) or bcrypt (cost 10 or higher). No MD5/SHA-1 for integrity or passwords. Keys and IVs never hardcoded; AES-GCM nonces never reused.
- [ ] **A03 Injection**: All SQL parameterized; no shell invocation with user input; output encoded for its context (HTML, attribute, URL, JSON). Regex applied to user input has bounded backtracking or a timeout.
- [ ] **A04 Insecure Design**: Rate limits on login, password reset, OTP, and expensive endpoints. Business invariants enforced server-side (price, quantity, state transitions). Reset and invite tokens are single-use and expire.
- [ ] **A05 Security Misconfiguration**: Debug endpoints, stack traces, and directory listings disabled in production. Default credentials removed. Security headers present (section 3). XML parsers reject DTDs.
- [ ] **A06 Vulnerable and Outdated Components**: Lockfiles committed; advisory scan clean or triaged; no abandoned packages on the critical path; base images patched.
- [ ] **A07 Identification and Authentication Failures**: JWT algorithm pinned, `exp` / `aud` / `iss` validated; session ID rotated on login; logout and password change invalidate sessions; MFA paths cannot be skipped by calling the next step directly.
- [ ] **A08 Software and Data Integrity Failures**: No deserialization of untrusted data into arbitrary types. CI actions and base images pinned (commit SHA, image digest). Webhook payloads verified with an HMAC signature and constant-time comparison.
- [ ] **A09 Security Logging and Monitoring Failures**: Authentication failures, access denials, and privilege changes logged with a correlation ID. No PII, tokens, or secrets in logs. Log injection prevented (structured JSON logging, no raw newlines).
- [ ] **A10 Server-Side Request Forgery**: Outbound URLs from user input pass scheme and host allow-lists, resolved-IP validation, and redirect controls.

Note: the 2025 edition reorders these and adds dedicated categories for software supply chain failures and mishandling of exceptional conditions; the checks above still cover them through A06, A08, and section 2.

---

## 2. Cross-Cutting Checks

- [ ] **Mass assignment**: request bodies bind to DTOs or schemas (Zod, FluentValidation, Pydantic with `extra="forbid"`), never to persistence entities.
- [ ] **Error handling**: failures close safe (deny on exception); error responses use a generic problem body with no stack trace, SQL, or internal host names.
- [ ] **File upload**: size limit, content-type sniffing by magic bytes, generated server-side filename, storage outside the web root, no execution permission.
- [ ] **Secrets**: loaded from environment or a secret manager; none in source, images, CI logs, or client bundles; rotation procedure exists for anything found in git history.
- [ ] **Supply chain**: install scripts reviewed; private package names protected against dependency confusion (scoped registry mapping); provenance or signature verification where available.
- [ ] **Timing**: all secret comparisons constant-time; login and reset flows respond identically for known and unknown accounts.

---

## 3. Required HTTP Hardening

| Control | Expected value |
| :--- | :--- |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `Content-Security-Policy` | No `unsafe-inline` / `unsafe-eval` for scripts; `frame-ancestors 'none'` unless framing is required |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` or stricter |
| Session cookie | `HttpOnly; Secure; SameSite=Lax` (or `Strict`); `__Host-` prefix where possible |
| `Cache-Control` on authenticated responses | `no-store` |

---

## 4. Severity Rubric (CVSS v3.1 base score)

| Band | Score | Typical finding |
| :--- | :---: | :--- |
| Critical | 9.0-10.0 | Unauthenticated RCE, SQL injection on a public route, authentication bypass |
| High | 7.0-8.9 | Cross-tenant IDOR, SSRF reaching cloud metadata, leaked production credential |
| Medium | 4.0-6.9 | Stored XSS behind login, missing rate limit on login, verbose error disclosure |
| Low | 0.1-3.9 | Missing hardening header, weak cookie flag on a non-session cookie |

State the vector string with each score, for example `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H` (9.8). Downgrade when exploitation needs a privileged account (`PR:H`) or local access (`AV:L`).

---

## 5. Finding Template

```markdown
### [CVSS 8.1 High] Cross-tenant invoice read (BOLA)
- **Location**: `src/invoices/invoice.controller.ts:57` -> `invoice.repository.ts:23`
- **Vector**: `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N`
- **Attack**: Authenticated user of tenant A requests `GET /invoices/{id}` with an ID owned by tenant B.
- **Root cause**: Lookup filters on primary key only.
- **Fix**: add `AND tenant_id = $2` bound to the session tenant; add a regression test asserting 404 for a foreign ID.
```
