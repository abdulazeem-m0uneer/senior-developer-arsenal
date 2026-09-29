---
name: python-audit
description: Python quality, static type checking, and asyncio performance audit workflow.
---

# Python Code Quality & Concurrency Audit Workflow

Follow this procedure when inspecting or auditing Python codebases.

## Steps

1. **Static Analysis & Formatting**:
   - Run Ruff:
     ```bash
     ruff check .
     ruff format --check .
     ```

2. **Strict Type Verification**:
   - Run Mypy:
     ```bash
     mypy --strict .
     ```

3. **Concurrency & Asyncio Audit**:
   - Check `async def` functions for synchronous blocking calls (`time.sleep()`, `requests.get()`, synchronous DB/file I/O).
   - Verify `asyncio.TaskGroup` usage and proper `asyncio.CancelledError` handling.
   - Verify SQLAlchemy async queries use `selectinload()` / `joinedload()`.

4. **Security & Validation Checks**:
   - Check for unpickling of untrusted data (`pickle.loads`).
   - Check that Pydantic models forbid extra fields (`extra='forbid'`).

5. **Run Test Suite**:
   ```bash
   pytest -v --asyncio-mode=auto
   ```

6. **Output Report**:
   - Report findings in a dense table (`Location`, `Category`, `Issue`, `Recommendation`).
   - Provide surgical 2-5 line code fixes.
