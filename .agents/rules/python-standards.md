# Modern Python Senior Engineering Standards

These rules enforce robust, high-performance, and type-safe Python (3.11+) backend development across **FastAPI**, **Django**, **Flask**, **SQLAlchemy 2.0**, and **asyncio**.

---

## 1. Type Hints & Code Modernization

- **Strict Type Annotations**:
  - Use `from __future__ import annotations` at the top of every module.
  - Type-hint all function signatures (arguments and returns). Avoid `Any`; use `typing.TypeVar`, `typing.Self`, or `object` with isinstance narrowing.
- **Data Validation & Modeling**:
  - Prefer **Pydantic v2** (`BaseModel`, `Field`) for API schemas and configuration settings (`BaseSettings`).
  - Use Python standard library `@dataclass(slots=True, frozen=True)` for internal immutable value objects.

---

## 2. Asynchronous Event Loop & Concurrency (`asyncio`)

- **Zero Blocking in `async def`**:
  - Never use blocking synchronous calls (`time.sleep()`, `requests.get()`, `open()`, synchronous DB drivers) in async route handlers or tasks.
  - Use `asyncio.sleep()`, `httpx.AsyncClient()`, `aiofiles`, or offload blocking sync code via `asyncio.to_thread(func, *args)`.
- **Task Management**:
  - Always clean up tasks with `asyncio.TaskGroup()` (Python 3.11+) to guarantee exception propagation and prevent orphaned tasks.
  - Catch `asyncio.CancelledError` properly when performing cleanup; never swallow it silently.

---

## 3. Data Access: SQLAlchemy 2.0 & PostgreSQL

- **SQLAlchemy 2.0 Async Paradigm**:
  - Use `AsyncSession` with modern `select()` syntax. Never use legacy 1.x query methods (`session.query()`).
  - Prevent N+1 query and `MissingGreenlet` errors by explicitly declaring eager loading strategies:
    - Use `selectinload()` for 1-to-many collections.
    - Use `joinedload()` for 1-to-1 or many-to-1 foreign keys.
- **Connection Hygiene**:
  - Use `asyncpg` or `psycopg3` (async) for PostgreSQL drivers.
  - Pool settings: Set `pool_size`, `max_overflow`, and `pool_pre_ping=True` to detect dropped TCP connections.

---

## 4. Quality, Tooling & Security

- **Package Management & Tooling**:
  - Prefer `uv` for ultra-fast dependency resolution and virtual environments.
  - Enforce formatting and linting via **Ruff** (`ruff check`, `ruff format`).
  - Typecheck via `mypy --strict`.
- **Security Guardrails**:
  - Never unpickle untrusted data (`pickle.loads`). Use JSON or Protocol Buffers.
  - Strip unknown fields in Pydantic schemas: `model_config = ConfigDict(extra='forbid')`.
  - Always parameterize database queries.

---

## 5. ⚡ Token-Saving Output Rule
- Output only the modified function, Pydantic model, or route handler. Never dump whole modules or generic `requirements.txt` files.
- Report `pytest` or `ruff` results as a single status line (`✅ Ruff & 16 Pytest tests passed`).
