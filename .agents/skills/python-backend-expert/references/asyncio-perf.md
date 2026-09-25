# Asyncio Performance & Concurrency Reference

Guidelines for maintaining low latency, zero event-loop blocking, and leak-free memory in modern Python async services.

---

## 1. Structured Concurrency with `TaskGroup` (Python 3.11+)

Always prefer `asyncio.TaskGroup` over `asyncio.gather()`. If any child task fails, remaining tasks are safely cancelled:

```python
import asyncio
from typing import Any

async def fetch_user_dashboard(user_id: str) -> dict[str, Any]:
    async with asyncio.TaskGroup() as tg:
        orders_task = tg.create_task(get_user_orders(user_id))
        profile_task = tg.create_task(get_user_profile(user_id))
        metrics_task = tg.create_task(get_user_metrics(user_id))

    # All tasks guaranteed completed or cancelled on exception
    return {
        "orders": orders_task.result(),
        "profile": profile_task.result(),
        "metrics": metrics_task.result(),
    }
```

---

## 2. Offloading Blocking Operations

Never block the primary event loop with synchronous file I/O or heavy computations:

```python
import asyncio
import hashlib

def _heavy_hashing(payload: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", payload, b"salt", 200_000).hex()

async def compute_hash_safe(payload: bytes) -> str:
    # Runs the synchronous function in the default thread pool executor
    return await asyncio.to_thread(_heavy_hashing, payload)
```

---

## 3. SQLAlchemy 2.0 Async Session Pattern

```python
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select
from sqlalchemy.orm import selectinload

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost:5432/pos_db",
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```
