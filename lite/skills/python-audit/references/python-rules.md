# Python Static Analysis & Asyncio Reference

Audit rules for modern Python 3.11+ services (FastAPI, SQLAlchemy 2.0, Pydantic v2).

---

## 1. Static Checks Commands

```bash
# 1. Linting & Formatting
ruff check .
ruff format --check .

# 2. Strict Type Checking
mypy --strict .

# 3. Test Suite Execution
pytest -v --asyncio-mode=auto
```

---

## 2. Common Asyncio & Typing Defects

- **Blocking Sync Calls in `async def`**: Using `time.sleep()`, `requests.get()`, or standard sync database drivers inside async routes.
  - *Fix*: Use `asyncio.sleep()`, `httpx.AsyncClient()`, or offload to thread pool: `await asyncio.to_thread(sync_func)`.
- **Unhandled `asyncio.CancelledError`**: Catching generic `Exception` without re-raising `CancelledError`.
  - *Fix*: Do not swallow `asyncio.CancelledError` during graceful shutdown.
- **SQLAlchemy Async N+1**: Lazy loading attributes across async boundaries causes `MissingGreenlet` errors.
  - *Fix*: Explicitly specify `selectinload()` or `joinedload()`.
