---
name: provider-sdk
description: 'Integrates an outside provider (payments, SMS, maps, identity) as one package with the same calls in a mock mode and a live mode chosen by configuration: fixed file layout, one contract test through both modes, documented mock differences, the mock refused in production, hardened live calls. Use when the user asks to add, wrap, mock, or test a third-party API, or runs /provider-sdk. Triggers on: "integrate a provider", "third-party client", "mock the provider", "webhook signature", "/provider-sdk". Do not use for designing your API (use api-design) or ledger rules (use payments-integrity).'
---

# Provider SDK Integration Procedure

This skill guides the agent through wrapping one outside provider in one package whose calls behave the same in an in-process mock mode and a live mode, so that every environment without credentials still runs the real client code.

---

## 1. When to Use This Skill

Activate this skill when:
- A new outside service is about to be called: payments, SMS or email, maps and routing, identity verification, push, storage.
- Provider calls are scattered through business code, or tests and local development need the provider without credentials, network, or cost.
- A provider webhook must be received, verified, and made idempotent.
- The user runs the `/provider-sdk` slash command.

*Boundary*: For the shape of your own API, use `api-design`. For ledgers, double-charge protection, and reconciliation, use `payments-integrity`. For an end-to-end proof through the deployed API, use `smoke-test`. For upgrading the provider's official library, use `dependency-upgrade`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Answer the Pre-flight Questions
1. Does the provider offer a sandbox with test credentials? Then build **no mock**: every non-production environment uses the sandbox. Write only the client, the live transport, and the adapter.
2. Is the provider's document (API reference, integration guide, version) in hand? If not, **build nothing**: record the gap and ask for the document. A client built from guesses is a liability.
3. Which calls does the application send today? Only those get a method on the application's port; the package may hold every documented call.
4. Which calls are unsafe to repeat (charge, send, register)? Note the provider's idempotency mechanism for each, or its absence.

### Step 2: Lay Out the Package
Consult: [Package Layout, Contract Test & README Template](./references/package-layout.md)
1. Create one package with the fixed file names: transport types, client, wire schemas, codes, live transport, mock engine, testing helper, entry point.
2. Write each call once, in the client, over a transport function. The live transport and the mock are two carriers under the same client.
3. Every call answers one of three ways: success with a value, a refusal with the provider's code, or a thrown "unavailable" error that says nothing about the business outcome.
4. Keep the provider's field names and codes in the package; translate to the application's words only in the adapter.

### Step 3: Build the Mock From the Document
1. The mock engine takes method, path, and body and answers by the provider's documented rules, in the process: no server, container, or image.
2. Give it a control handle: set facts, move a clock, inject a fault, list received requests, reset.
3. Make outcomes reachable by the value typed in (a number ending in 2 is declined), so people can try the applications by hand.
4. Where the document is silent or contradicts itself, choose the lenient reading and list the choice in the README under "Where the mock differs". Never invent silently.

### Step 4: Prove Both Modes With One Contract Test
1. One test file runs the same calls through the mock mode and through the live client pointed at the mock engine served on a loopback port; the answers must be equal. That run exercises the live transport's URL building, headers, authentication, timeout, and error mapping without the internet.
2. If a sandbox exists, run the same contract against it on demand, never in the default test run.

### Step 5: Harden the Live Mode
Consult: [Live Mode Hardening](./references/live-mode-hardening.md)
1. Every request has a timeout; the transport itself never retries.
2. Retries belong to the caller and only for calls that are idempotent or carry an idempotency key.
3. Webhooks are verified by signature over the raw body, checked for freshness, and deduplicated by event id.
4. Credentials come from validated configuration and are never logged, echoed in errors, or stored in recorded requests.

### Step 6: Wire It Into the Application
1. Port (the application's words), adapter (maps answers; "unavailable" becomes a 503-class domain error), and a selector that picks the mode from configuration.
2. The selector refuses the mock when the environment is production, at startup, with a clear message; live mode refuses to start with a credential missing.
3. Unit-test both refusals. Add the configuration keys to the schema and regenerate the environment example.

---

## 3. Verification Protocol

```bash
npm test -w packages/<provider>            # Node.js: unit and contract tests of the package
dotnet test src/<Provider>.Sdk.Tests       # .NET
pytest packages/<provider>                 # Python
APP_ENV=production PROVIDER_MODE=mock <start command>; echo "exit $?"   # must fail at startup, non-zero
grep -rnE "api[_-]?key|secret|authorization" <log output> | head       # must print nothing from a test run
```

| Area | Finding | Risk | Severity | Fix |
| :--- | :--- | :--- | :---: | :--- |
| Selector | Mock selectable in production | Fake approvals or payments treated as real | `[Blocker]` | Refuse at startup; test the refusal |
| Transport | Charge call retried on timeout without idempotency key | Customer charged twice | `[Blocker]` | Remove the retry or send the key |
| Webhook | Signature computed over re-serialised JSON | Valid events rejected, or forgery accepted | `[Security]` | Verify over the raw bytes, constant-time compare |

---

## 4. ⚡ Token-Saving Execution Rule

- **Read Once, Cite Sections**: Note the provider document's section numbers on first read and cite them in comments; never reread the whole document.
- **Mirror One File**: When an earlier provider package exists, read its README and the one file being mirrored, not the package.
- **Package Tests While Building**: Run only the package's tests during work; the full gate once at the end.
