# UI/UX Audit Matrix Template

Template for reporting objective anti-slop and accessibility gate results.

---

## Audit Matrix Format

```markdown
### UI/UX Anti-Slop Audit Report

| Gate | Target Element | Status | Severity | Finding | Surgical Fix |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `1. Zero-Emoji` | `NotificationBadge.tsx:14` | ❌ FAIL | `🚨 Blocker` | Used ⚠️ emoji for warning badge | Replace with Lucide `<AlertTriangle className="w-4 h-4 text-warning" />` |
| `2. Intent Tokens` | `DeleteModal.tsx:45` | ❌ FAIL | `🚨 Blocker` | Delete button uses primary blue | Set `variant="destructive"` / `bg-danger` |
| `3. WCAG Contrast` | `CardSubtitle.css:8` | ❌ FAIL | `⚡ Issue` | 3.2:1 contrast on `#F9FAFB` | Update to `text.secondary` (`#4B5563`, 5.4:1) |
| `4. Complete States` | `Button.tsx:22` | ❌ FAIL | `⚡ Issue` | Missing `:focus-visible` ring | Add `focus-visible:ring-2 focus-visible:ring-offset-2` |
| `5. Target Sizing` | `CloseIcon.tsx:9` | ❌ FAIL | `⚡ Issue` | Click target is 16x16px | Add padding to reach 44x44px target |
| `6. Overflow 280px` | `Navbar.tsx:30` | ✅ PASS | - | Fluid flex-wrap without scrollbar | - |
| `7. Focus Trap` | `Drawer.tsx:50` | ✅ PASS | - | Focus trapped, Escape closes | - |
| `8. Anti-AI Copy` | `Hero.tsx:12` | ❌ FAIL | `💡 Nit` | Found em-dash "—" in headline | Replace with period or comma |
| `9. Hierarchy` | `Dashboard.tsx:80` | ✅ PASS | - | Hero metric 3.2x body size | - |
| `10. Token Parity` | `Sidebar.css:15` | ❌ FAIL | `💡 Nit` | Hardcoded `#1e293b` | Replace with `var(--color-surface-subtle)` |
```
