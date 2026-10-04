# Test Layering & Test Doubles

Decision tables for choosing a test layer, a test double, and the right tool per stack.

---

## 1. Which Layer Proves It?

| Behaviour under test | Layer | Why |
| :--- | :--- | :--- |
| Pricing rule, validator, state transition, mapper | Unit | Pure logic; fast, exhaustive input tables |
| SQL query, ORM mapping, migration, unique constraint | Integration (real engine) | An in-memory substitute hides dialect, locking, and constraint behaviour |
| Route + auth + validation + serialization | Integration (in-process HTTP) | Exercises the real middleware pipeline without a browser |
| Outbound call to a third-party API | Integration with a stubbed HTTP boundary, plus a contract test | You do not own the provider; pin the contract instead |
| Sign-in, checkout, critical journey across pages | End-to-end | Only a browser proves the wiring; keep to a handful |
| Visual layout, focus order, accessibility | Component test or end-to-end with accessibility assertions | Needs a real DOM |

Rules:
- [ ] Test at the lowest layer that can fail for the defect in question.
- [ ] Do not re-test framework behaviour (ORM saves, router matches) in unit tests.
- [ ] An end-to-end test that only repeats an integration assertion should be deleted.
- [ ] If a unit needs more than three doubles, the design is too coupled; test it one layer up or refactor.

---

## 2. Test Double Taxonomy

| Double | Behaviour | Use for |
| :--- | :--- | :--- |
| Dummy | Passed, never used | Filling a required parameter |
| Stub | Returns canned answers | Driving a code path (dependency returns error, empty list) |
| Spy | Records calls, real or stubbed behaviour | Verifying an outbound side effect happened once |
| Mock | Pre-programmed expectations, fails on mismatch | Protocol-style interactions; use sparingly |
| Fake | Working lightweight implementation | In-memory repository, fake clock, fake message bus |

- [ ] Mock only at boundaries you own (ports, gateways). Never mock the type under test or value objects.
- [ ] Prefer fakes and stubs to interaction-verifying mocks; assert state and output first.
- [ ] Verify interactions only for commands with no observable return (email sent, event published).
- [ ] Keep doubles faithful: a stub that returns shapes the real dependency never returns creates false confidence.

---

## 3. Tooling per Stack

| Need | Vitest / Jest | xUnit (.NET) | pytest |
| :--- | :--- | :--- | :--- |
| Table-driven cases | `it.each([...])` | `[Theory]` + `[InlineData]` / `[MemberData]` | `@pytest.mark.parametrize` |
| Stub / spy | `vi.fn()`, `vi.spyOn(obj, 'm')` (`jest.fn()`, `jest.spyOn`) | NSubstitute `Substitute.For<T>()` or Moq `Mock<T>` | `monkeypatch.setattr`, `unittest.mock.patch(..., autospec=True)` |
| Module replacement | `vi.mock('./mod')` / `jest.mock('./mod')` | Constructor injection of an interface | `monkeypatch`, FastAPI `app.dependency_overrides` |
| Fake time | `vi.useFakeTimers()`, `vi.setSystemTime()`, `vi.advanceTimersByTimeAsync()` | Inject `TimeProvider`; `FakeTimeProvider.Advance()` | `freezegun.freeze_time` or `time-machine` |
| HTTP boundary stub | MSW (`setupServer`, `http.get`) | Custom `HttpMessageHandler` or WireMock.Net | `respx` (httpx), `responses` (requests) |
| In-process API test | `supertest(app)` or Fastify `app.inject()` | `WebApplicationFactory<Program>` + `CreateClient()` | `httpx.AsyncClient(transport=ASGITransport(app=app))` |
| Real database | Testcontainers (`@testcontainers/postgresql`) | `Testcontainers.PostgreSql` + `IAsyncLifetime` | `testcontainers` + session-scoped fixture |
| Shared setup | `beforeEach` / `afterEach` | Constructor + `IDisposable`, `IClassFixture<T>` | `@pytest.fixture` (function scope by default), `tmp_path` |

---

## 4. Structure Example (Vitest)

```ts
describe('applyDiscount', () => {
  it.each([
    { total: 100, pct: 10, expected: 90 },
    { total: 0, pct: 10, expected: 0 },
    { total: 100, pct: 0, expected: 100 },
    { total: 0.3, pct: 10, expected: 0.27 },
  ])('returns $expected for total=$total pct=$pct', ({ total, pct, expected }) => {
    expect(applyDiscount(total, pct)).toBeCloseTo(expected, 2);
  });

  it('rejects a percentage above 100', () => {
    expect(() => applyDiscount(100, 101)).toThrow(RangeError);
  });
});
```

---

## 5. Playwright Rules

- [ ] Locate by role or label: `page.getByRole('button', { name: 'Pay' })`, `getByLabel`, `getByTestId` as last resort. No CSS chains tied to layout.
- [ ] Use web-first assertions that auto-wait: `await expect(locator).toBeVisible()`, `toHaveText`, `toHaveURL`. Never `page.waitForTimeout()`.
- [ ] Isolate state: fresh browser context per test; authenticate once and reuse `storageState`.
- [ ] Stub third-party calls with `page.route(url, route => route.fulfill({ json }))`; hit your own backend for real.
- [ ] Seed data through the API or database, not through the UI.
- [ ] Configure `retries` in CI only and collect `trace: 'on-first-retry'`; a test that passes on retry is reported as flaky and must be triaged.
