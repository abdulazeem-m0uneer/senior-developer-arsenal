# Antigravity Gemini Workspace Configuration

This project serves as the global or template repository for senior software engineering workflows across C#, Node.js, PostgreSQL, MSSQL, SQLite, and Git.

## Active Rules & Skills
- Load all rules in `.agents/rules/` when operating on code files in this repository or any target repository using these tools.
- Refer to skills located in `.agents/skills/` for execution runbooks and checklists.
- Follow the subagent definitions in `.agents/subagents/` when delegating tasks.

## Code Standards Reminder
- Write idiomatic, modern, production-grade code (.NET 8/9 C#, TypeScript Strict ESM, Python 3.11+ FastAPI/SQLAlchemy 2.0, React 18/19 RSC, Angular 17/18/19 Signals).
- Enforce end-to-end type safety, optimistic UI rollback safety, and non-blocking database queries.
- Treat database queries and schema changes with utmost scrutiny (concurrency, non-blocking indexing, lock contention).
- Always include defensive unit/integration test patterns when authoring or reviewing code.

## ⚠️ Mandatory Token Conservation & Defensive Epistemology
- Be extremely frugal with token usage. Omit conversational pleasantries, chit-chat, and brown-nosing ("You're absolutely right").
- **Rule 0**: On failure, STOP immediately. Do not silently retry. Output raw error, hypothesis, and confirm before touching anything.
- **Prediction Protocol**: Declare expected outcome (`EXPECT`) before non-trivial tool actions. If reality diverges, debug your mental model, not reality.
- Never output full files when partial diffs or targeted snippets suffice.
- Use dense tables and bullet points with concise severity classifications.

