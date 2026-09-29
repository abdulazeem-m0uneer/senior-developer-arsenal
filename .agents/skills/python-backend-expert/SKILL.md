---
name: python-backend-expert
description: Specialized Python engineering skill. Use when designing, building, refactoring, or optimizing modern Python services (FastAPI, Django, Flask), asyncio event loops, SQLAlchemy 2.0, or Pydantic data pipelines. Triggers on: "Python", "FastAPI", "SQLAlchemy", "Pydantic", "asyncio", "TaskGroup". Do not use for Node.js services (use nodejs-backend-expert) or .NET services (use csharp-dotnet-expert).
---

# Python Backend Engineering Skill

This skill guides the agent in building robust, type-safe, and high-performance Python services.

---

## 1. When to Use This Skill

Activate this skill when:
- Developing or refactoring FastAPI, Flask, or Django applications.
- Structuring asynchronous pipelines with `asyncio`, `TaskGroup`, or background workers (Celery/ARQ).
- Optimizing SQLAlchemy 2.0 async queries, sessions, and database migrations (Alembic).
- Implementing data validation and parsing using Pydantic v2.
- Running static type analysis (`mypy`), linting (`ruff`), and async unit tests (`pytest`).

*Boundary*: For Node.js/TypeScript services, use `nodejs-backend-expert`. For C# / .NET services, use `csharp-dotnet-expert`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Non-Blocking Asyncio Architecture
Consult: [Asyncio Performance & Concurrency Guide](./references/asyncio-perf.md)
1. Ensure all I/O is asynchronous (`httpx`, `asyncpg`, `aiofiles`).
2. Wrap synchronous CPU-heavy or legacy library calls in `asyncio.to_thread()`.
3. Use `asyncio.TaskGroup` for structured concurrency.

### Step 2: FastAPI & Pydantic v2 Architecture
Consult: [Pydantic v2 & FastAPI Architecture](./references/pydantic-fastapi.md)
1. Declare API payloads with Pydantic v2 models using `Field()` constraints.
2. Use `@asynccontextmanager` for application lifespan (database connection pool startup/shutdown).
3. Structure modular routers using `APIRouter` with dependency injection (`Depends()`).

---

## 3. Verification Protocol

Verify code quality and type safety:
```bash
# 1. Lint and format check
ruff check . && ruff format --check .

# 2. Strict type checking
mypy --strict .

# 3. Run test suite
pytest -v --asyncio-mode=auto
```
Report status in a single line: `✅ Ruff clean, Mypy strict passed, tests green`.

---

## 4. ⚡ Token-Saving Execution Rule

- **Targeted Code Output**: Output only the modified Python function, class, or Pydantic model. Never output entire unchanged files.
- **Terse Tool Reporting**: Summarize linting and test results in a single line.
