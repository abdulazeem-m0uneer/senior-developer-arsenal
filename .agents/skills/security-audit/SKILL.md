---
name: security-audit
description: 'Application security audit runbook covering OWASP Top 10, injection, authn/authz flaws (IDOR/BOLA), secrets leakage, dependency and supply-chain risk, SSRF, unsafe deserialization, and timing attacks across Node.js/TypeScript, C#/.NET, Python, and SQL. Use when the user asks for a security audit, threat review, vulnerability hunt, or pre-release hardening pass. Triggers on: "security audit", "find vulnerabilities", "OWASP", "check for IDOR", "/security-audit". Do not use for general pull request quality review (use code-review) or latency profiling (use perf-audit).'
---

# Application Security Audit Procedure

This skill guides the agent through a source-to-sink security audit of Node.js/TypeScript, C#/.NET, Python, and SQL codebases, producing CVSS-rated findings with hardened remediation code.

---

## 1. When to Use This Skill

Activate this skill when:
- Auditing a service, module, or endpoint set for exploitable vulnerabilities before release or after an incident.
- Hunting a specific class of flaw: injection, IDOR/BOLA, SSRF, unsafe deserialization, weak token handling, leaked secrets.
- Assessing third-party dependency and supply-chain exposure.
- The user runs the `/security-audit` slash command or asks for a threat or vulnerability review.

*Boundary*: For a general diff review where security is one dimension among correctness, performance, and architecture, use `code-review`. For latency or resource profiling, use `perf-audit`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Map the Attack Surface
1. Enumerate every entry point: HTTP routes, GraphQL resolvers, queue consumers, webhooks, scheduled jobs, file uploads, CLI arguments.
2. For each entry point record: authentication requirement, authorization rule, and which inputs are attacker-controlled (body, query, headers, path, uploaded files, URLs to fetch).
3. Mark trust boundaries: public internet, tenant-to-tenant, service-to-service, admin plane.

### Step 2: Sweep for Dangerous Sinks
Use your search tool with the patterns in [Vulnerability Patterns by Language](./references/vulnerability-patterns.md), then trace each hit back to its source:
- **Injection**: string-built SQL, shell execution, dynamic evaluation, template rendering, ReDoS-prone regex on user input.
- **Deserialization & Parsing**: `pickle`, `BinaryFormatter`, polymorphic JSON type handling, unsafe YAML loaders, XML with DTDs enabled.
- **SSRF & Path Traversal**: outbound requests or file paths built from request data without an allow-list.
- Report a sink only when attacker-controlled data reaches it without validation or encoding; otherwise note it as hardening.

### Step 3: Authentication, Authorization & Session Review
1. **BOLA / IDOR**: every lookup by ID must also filter on tenant ID or owner ID taken from the verified session, never from the request body.
2. **Tokens**: JWT signature algorithm pinned, `exp`, `aud`, and `iss` validated; refresh tokens rotated and revocable.
3. **Cookies**: `HttpOnly`, `Secure`, `SameSite=Lax` or `Strict`; state-changing routes protected against CSRF.
4. **Comparisons**: secrets, signatures, and reset tokens compared with `crypto.timingSafeEqual`, `CryptographicOperations.FixedTimeEquals`, or `hmac.compare_digest`.
5. **Data exposure**: response DTOs strip password hashes, salts, internal flags; logs never contain PII, tokens, or raw secrets.

### Step 4: Secrets & Supply Chain
```bash
gitleaks detect --source . --redact                        # secrets in git history
npm audit --omit=dev                                       # Node.js advisories
dotnet list package --vulnerable --include-transitive      # NuGet advisories
pip-audit -r requirements.txt                              # Python advisories
```
Confirm lockfiles are committed, installs are reproducible (`npm ci`, `dotnet restore --locked-mode`, `pip install --require-hashes`), and no install script pulls unpinned remote code.

### Step 5: Rate and Report
Score each finding and fill the report using the [Audit Checklist & Severity Rubric](./references/audit-checklist.md). Every finding needs: attack vector, preconditions, impact, and a surgical fix.

---

## 3. Verification Protocol

Before delivering the report:
1. Each finding has a concrete source-to-sink path (`file:line` of the input and of the sink) and a plausible exploit request or payload.
2. Each proposed fix was checked against the existing tests (`npm test`, `dotnet test`, or `pytest`) and the scanners in Step 4 were re-run.
3. Output the findings table, ordered by CVSS descending:

| CVSS | Vulnerability | Location | Fix |
| :---: | :--- | :--- | :--- |
| 9.1 Critical | SQL injection via interpolated `FromSqlRaw` | `src/Orders/OrderRepository.cs:42` | Switch to `FromSqlInterpolated` |
| 7.5 High | IDOR: invoice fetched by ID without tenant filter | `src/invoices/invoice.service.ts:88` | Add `tenantId` from session to the `WHERE` clause |

---

## 4. ⚡ Token-Saving Execution Rule

- **Zero Fluff**: Start directly with the vulnerability table; no audit introduction.
- **Surgical Remediations**: Provide 2-5 line fixes only. Never reprint unchanged files.
- **Targeted Reads**: Open only the files your search tool flagged, at the flagged lines.
