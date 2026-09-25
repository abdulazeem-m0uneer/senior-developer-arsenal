# Senior Software Engineer Core Principles & Code Review Standards

This rule establishes senior-level engineering practices across all language stacks, system designs, and code reviews.

---

## 1. The Senior Engineering Mindset

1. **Systemic Thinking**: Look beyond the immediate function or file. Ask:
   - What happens under high load?
   - How does this interact with the database connection pool?
   - What happens if an external dependency times out or fails?
   - Is this change backwards-compatible with existing clients and data?
2. **Readability & Maintainability Over Cleverness**:
   - Code is read 10x more often than it is written.
   - Avoid cryptic one-liners, overly complex metaprogramming, or unnecessary abstractions.
   - Use intention-revealing names for variables, methods, and types.
3. **Defensive Boundaries**:
   - Never trust input from external clients, queries, or third-party APIs.
   - Validate and sanitize at boundaries. Internal domain code can then assume invariants hold true.

---

## 2. Code Review Standard Operating Procedure

When performing code reviews or reviewing code for PRs:

### A. Architecture & Design
- Does the code adhere to Single Responsibility and Separation of Concerns?
- Are dependencies injected rather than hard-coded?
- Does the implementation belong in this layer (Domain vs Application vs Infrastructure)?
- Is there any unnecessary coupling between modules?

### B. Correctness & Edge Cases
- Are null/undefined values handled safely?
- Are edge cases (empty lists, negative numbers, boundary dates, large payloads) covered?
- Is state mutable where it should be immutable?
- Are concurrent operations safe from race conditions and deadlocks?

### C. Security Audit Checklist
- **SQL / NoSQL Injection**: Are all database queries parameterized?
- **Authentication & Authorization**: Is every endpoint protected by appropriate roles/policies? Are object-level permissions (IDOR) verified?
- **Data Leakage**: Are sensitive fields (passwords, tokens, PII) excluded from logs, error responses, and serializations?
- **Mass Assignment**: Are DTOs used to whitelist acceptable input fields rather than binding raw request bodies directly to domain entities?
- **Rate Limiting & DoS**: Are expensive operations protected by timeouts, rate limits, and payload size bounds?

### D. Performance & Resource Management
- Are database calls made inside loops (N+1 query problem)?
- Are connection pools, file handles, HTTP clients, and streams properly disposed/closed?
- Are allocations kept minimal in hot paths (avoiding unnecessary string concatenations or large array copies)?

### E. Testing & Verification
- Are there unit tests for critical business rules?
- Are integration tests validating database interactions and external contracts?
- Are mock objects testing behavior, not implementation details?

---

## 3. Communication & Feedback Rubric

When providing feedback to engineers:
- **Categorize Issues**: Tag comments as `[Blocker]` (security, data loss, severe bug), `[Performance]`, `[Architecture]`, `[Minor/Nit]` (styling, formatting), or `[Question]` (clarification).
- **Explain the "Why"**: Always provide the architectural, security, or performance rationale behind requested changes.
- **Provide Actionable Alternatives**: Don't just point out a problem—demonstrate a concrete, idiomatic solution or pattern.
