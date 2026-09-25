# Antigravity Gemini Workspace Configuration

This project serves as the global or template repository for senior software engineering workflows across C#, Node.js, PostgreSQL, MSSQL, SQLite, and Git.

## Active Rules & Skills
- Load all rules in `.agents/rules/` when operating on code files in this repository or any target repository using these tools.
- Refer to skills located in `.agents/skills/` for execution runbooks and checklists.
- Follow the subagent definitions in `.agents/subagents/` when delegating tasks.

## Code Standards Reminder
- Write idiomatic, modern, production-grade code (.NET 8/9 C#, TypeScript Strict ESM).
- Treat database queries and schema changes with utmost scrutiny (concurrency, non-blocking indexing, lock contention).
- Always include defensive unit/integration test patterns when authoring or reviewing code.

## ⚠️ Mandatory Token Conservation
- Be extremely frugal with token usage. Omit conversational pleasantries, chit-chat, and apologetic text.
- Never output full files when partial diffs or targeted snippets suffice.
- Use dense tables and bullet points with concise severity classifications.

