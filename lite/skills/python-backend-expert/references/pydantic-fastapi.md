# Pydantic v2 & FastAPI Architecture Reference

Guidelines for writing type-safe, resilient APIs with FastAPI and Pydantic v2.

---

## 1. Lifespan Context Manager Pattern

Use `lifespan` instead of deprecated `on_event("startup")` / `on_event("shutdown")`:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from database import engine

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup: Initialize connections / cache warm-up
    print("Application starting, validating database connection...")
    async with engine.begin() as conn:
        await conn.execute("SELECT 1")
    yield
    # Shutdown: Cleanly dispose connection pools
    print("Application shutting down, disposing engine...")
    await engine.dispose()

app = FastAPI(title="POS API", lifespan=lifespan)
```

---

## 2. Pydantic v2 Schema Modeling

```python
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from uuid import UUID
from datetime import datetime

class CreateProductRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=2, max_length=100)
    sku: str = Field(..., pattern=r"^[A-Z0-9_-]+$")
    price: float = Field(..., gt=0.0)
    category_id: UUID

class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    sku: str
    price: float
    created_at: datetime
```

---

## 3. Dependency Injection with `Depends`

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db_session

router = APIRouter(prefix="/products", tags=["products"])

@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: CreateProductRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ProductResponse:
    # Service logic here
    return await product_service.create(session, payload)
```
