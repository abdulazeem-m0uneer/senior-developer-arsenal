# Package Layout, Contract Test & README Template

The fixed file layout of a provider package, the three-way answer shape, the mock's control handle, the one contract test, and the README every package ships.

---

## 1. Pre-flight Decision Matrix

| Provider has a sandbox | Document in hand | Build |
| :---: | :---: | :--- |
| Yes | Yes | Client, live transport, adapter. **No mock**: non-production environments use the sandbox |
| Yes | No | Nothing yet. Ask for the document; a sandbox does not explain error codes or limits |
| No | Yes | The full package below, mock included |
| No | No | Nothing. Record the gap, ask the person who owns the provider relationship |

A mock on top of a sandbox is a second source of truth that will disagree with the first. Unit tests of the adapter may still stub the client.

---

## 2. File Layout

Same file names for every provider, so the second package is a copy of the first's shape. Shown for TypeScript; the roles carry over to any stack.

| File | Holds | Rule |
| :--- | :--- | :--- |
| `transport` | Request and reply types, the `Transport` function type, the `<Provider>Unavailable` error | The only seam between client and carrier |
| `client` | Every call, written once, over a transport | No `fetch`, no credentials, no mode check |
| `wire` | Request types and response schemas in the provider's field names | Validate every response; an unreadable body is "unavailable", not a crash |
| `codes` | The provider's result and error codes as constant lists, in the provider's spelling | Never renamed here; the adapter translates |
| `live-transport` | HTTP call, authentication, timeout, status handling | Never retries; never logs credentials |
| `mock/engine` | `(method, path, body) -> reply`, by the document's rules | One file per provider service beside it; state in one place |
| `testing` | The mock engine behind a loopback HTTP server | Exported separately; used only by tests |
| `index` | `create<Provider>(options)` by mode; `create<Provider>Mock()` returning client and handle | The only public entry |

In the application, outside the package:

| File | Holds |
| :--- | :--- |
| `port` | The interface in the application's own words; only the calls used today |
| `adapter` | Implements the port over the client; maps codes to domain results; turns "unavailable" into a retryable service error |
| `select` | Reads configuration, returns the port; refuses the mock in production |

Dependencies: a schema validator and the platform's HTTP client. Add the provider's official library only when it handles something hard (request signing, token refresh) that would otherwise be reimplemented.

---

## 3. One Answer Shape

```typescript
type Answer<T> =
  | { ok: true; value: T }                          // the provider's answer
  | { ok: false; code: ProviderCode; message: string }; // the provider refused, in its own code
// throws ProviderUnavailable                       // no answer that is the provider's
```

| Situation | Result | Why |
| :--- | :--- | :--- |
| 2xx with a valid body | `ok: true` | |
| Business refusal (declined, not found, invalid field) | `ok: false` with the provider's code | The caller branches on it; it is not an exception |
| Timeout, connection error, 5xx, gateway page, body that fails the schema | throw unavailable | It says nothing about the business outcome; the caller must not treat it as a refusal |
| 401 or 403 from the provider | throw unavailable | A credential problem is ours, never the customer's |

---

## 4. The Mock's Control Handle

```typescript
const { provider, mock } = createProviderMock({ now });
mock.setCustomer('cust_1001', { status: 'blocked' }); // set a fact
mock.advance({ days: 10 });                          // move the clock: expiries, windows
mock.failNext('timeout');                            // or 'unreachable', or { status, body }
mock.requests();                                     // every request received, secrets removed
mock.reset();
```

Outcomes by typed value, for manual trials with no code, are listed in the README:

| Input ending | Outcome |
| :---: | :--- |
| 0 | Success (default) |
| 1 | Refused: not found |
| 2 | Refused: declined |
| 9 | Unavailable (timeout) |

---

## 5. The Contract Test

One file, two carriers, identical expectations.

```typescript
const carriers = {
  mock: async () => createProviderMock({ now }),
  live: async () => {
    const served = await serveProviderMock({ now, credentials });   // loopback port, no internet
    return { provider: createProvider({ mode: 'live', url: served.url, ...credentials }), mock: served.mock };
  },
};

for (const [mode, make] of Object.entries(carriers)) {
  describe(`contract (${mode})`, () => {
    it('answers a success in the provider shape', async () => { /* same call, same expected value */ });
    it('answers a refusal with the provider code', async () => { /* mock.setCustomer(...) then call */ });
    it('throws unavailable on a timeout', async () => { /* mock.failNext('timeout') */ });
  });
}
```

- [ ] Every public call appears at least once with a success and once with a refusal.
- [ ] The live run asserts the wire: path, method, authentication header present, timeout honoured.
- [ ] The optional sandbox run reuses the same cases behind an explicit flag and is never part of the default run.

---

## 6. README Template

```markdown
# <provider> SDK. Source: <document title, version, date>. Modes: `mock` (this process, no network) and `live`.

## Use            (create call, one example, the three answers)
## Calls          (table: call, document section, what it does, safe to repeat?)
## The mock       (outcomes by typed value; the control handle)
## Where the mock differs
- **<topic>.** The document says <x> in section <n> and <y> in section <m>. The mock accepts both.
- **<topic>.** Not in the document. The mock answers <z>; to be settled by the first live call.
- **Not modelled:** <behaviour>, <behaviour>.
## Live mode      (configuration keys, timeout, what is unverified until a real call proves it)
```

"Where the mock differs" is mandatory and never empty: a mock with no known differences has not been compared with its document.
