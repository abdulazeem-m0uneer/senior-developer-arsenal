# Senior Code Review Feedback Rubric & Template

Use this format to produce clear, constructive, and impactful review comments.

---

## 1. Finding Format Template

Every finding must provide:
1. **File and Line Reference**: Clear pointer to where the issue occurs.
2. **Category & Severity**:
   - `[Blocker]`: Critical defect, security flaw, or data corruption risk. Merging blocked.
   - `[Perf]`: Query degradation, event loop blocking, memory leak.
   - `[Arch]`: Boundary violation, improper abstraction, tight coupling.
   - `[Nit]`: Minor readability or idiomatic cleanup.
3. **The "Why"**: The underlying technical risk, performance penalty, or maintainability drawback.
4. **Actionable Solution / Code Diff**: Concrete replacement code demonstrating the fix.

---

## 2. Review Report Template

```markdown
# Senior Code Review Report

## Summary & Verdict
- **Verdict**: [ Approved | Approved with Suggestions | Changes Requested ]
- **Summary**: Concise 2-3 sentence overview of the changes and overall quality.

---

## Key Findings

### [Blocker] [Brief description of blocker]
- **Location**: `src/Services/PaymentService.cs:L45-L52`
- **Impact**: Risk of double-charging customer due to unhandled concurrency race condition.
- **Recommendation**: Wrap transaction in an optimistic lock or use a distributed lock key based on order ID.
```csharp
// Recommended Fix:
await using var tx = await dbContext.Database.BeginTransactionAsync(IsolationLevel.Serializable, ct);
```

### [Perf] [Brief description of performance issue]
- **Location**: `src/modules/orders/order.repository.ts:L88`
- **Impact**: Unindexed sequential scan on table `orders` with 1M+ rows.
- **Recommendation**: Create a composite index on `(user_id, created_at DESC)`.

### [Arch] [Layering or abstraction concern]
- **Location**: `src/Controllers/UsersController.cs:L30`
- **Impact**: Direct dependency on EF DbContext inside Presentation Controller bypassing Domain Service layer.

### [Nit] Minor cleanups
- `src/utils/date.ts`: Prefer native `Intl.DateTimeFormat` over ad-hoc string slicing.

---

## Verification & Testing Recommendations
- Add an integration test verifying that concurrent requests return HTTP 409 Conflict.
- Verify migration rollbacks cleanly on a staging database.
```
