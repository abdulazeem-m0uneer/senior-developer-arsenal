---
name: python-audit
description: 'Python quality, static type checking, and asyncio performance audit workflow. Use when the user asks to lint Python, run mypy strict checks, audit asyncio event loops, or runs /python-audit. Triggers on: "python audit", "lint python", "mypy check", "asyncio audit", "/python-audit". Do not use for Node.js or .NET code (use code-review).'
---

# Python Quality & Asyncio Audit Skill

Follow this procedure when inspecting, linting, and profiling Python codebases.

---

## 1. When to Use This Skill

Activate this skill when:
- Auditing Python 3.11+ services (FastAPI, Flask, Django) for static typing and linting violations.
- Checking `async def` code paths for synchronous blocking calls or improper task cancellation.
- The user runs the `/python-audit` slash command.

*Boundary*: For Node.js/TypeScript or C# codebases, use `code-review` or `perf-audit`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Static Linter & Strict Type Execution
Consult: [Python Static Analysis Reference](./references/python-rules.md)
1. Run Ruff linter and formatter checks:
   ```bash
   ruff check .
   ruff format --check .
   ```
2. Run Mypy in strict mode:
   ```bash
   mypy --strict .
   ```

### Step 2: Concurrency & Asyncio Inspection
1. Audit all `async def` functions for blocking calls (`time.sleep`, `requests.get`, sync file operations).
2. Ensure structured concurrency using `asyncio.TaskGroup` over unstructured background tasks.
3. Check for proper handling of `asyncio.CancelledError`.

### Step 3: Pydantic & SQLAlchemy Audit
1. Verify Pydantic v2 schemas forbid unknown fields (`extra='forbid'`) on sensitive endpoints.
2. Verify SQLAlchemy queries eagerly load related entities via `selectinload` or `joinedload`.

---

## 3. Verification Protocol

1. Execute test suite: `pytest -v --asyncio-mode=auto`.
2. Output findings table:

| Location | Category | Severity | Issue | Surgical Fix |
| :--- | :--- | :---: | :--- | :--- |
| `service.py:34` | Concurrency | `🚨 [Blocker]` | `time.sleep` in async route | `await asyncio.sleep(1)` |
| `schema.py:12` | Security | `💡 [Suggestion]` | Missing `extra='forbid'` | Add `model_config = ConfigDict(extra='forbid')` |

---

## 4. ⚡ Token-Saving Execution Rule

- Provide only the findings table and 2–5 line surgical code fixes.
- Never reprint entire unchanged Python modules.
