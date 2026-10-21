# Delegation Patterns: When a Helper Agent Is Worth It

Adapted from JuliusBrussee/caveman, skill `cavecrew` (Apache-2.0).

---

## 1. The Real Cost of a Helper

A helper agent's reply is pasted into the caller's context verbatim. A helper that answers in two thousand tokens of prose charges the caller two thousand tokens, every time. Across twenty delegations in one session that is the difference between finishing and running out of context. The win from delegation is not parallelism first; it is that the helper's *reads* stay in its own context and only a compressed *answer* comes back. A helper is worth it when you would want its result in a third of the tokens it would take you to produce inline.

Rule of thumb: structured answer wanted, delegate to a helper with an output contract. Prose, judgement, or architecture commentary wanted, do it in the main thread or use a reviewer that is allowed to write prose.

---

## 2. Three Roles, One Table

| Task | Who | Reason |
| :--- | :--- | :--- |
| "Where is X defined, what calls Y, list uses of Z" | locator helper (read-only, cheap model) | returns `path:line` rows; its reads never reach the caller |
| Same, but suggestions or architecture commentary also wanted | main thread | prose is the deliverable; a contract would strip it |
| Surgical edit, at most two files, scope already known | builder helper (write tools, no sub-helpers) | returns a change line and a verify line |
| New feature, three or more files, cross-cutting refactor | main thread | the builder would answer `too-big` and the turn is wasted |
| Review a diff, branch, or file for defects | reviewer helper (read-only) | returns findings only, sorted by file and line |
| Deep review with rationale and alternatives | main thread or a prose-capable reviewer | findings-only output cannot carry rationale |
| A one-line answer already known | main thread | a delegation costs more than the answer |

---

## 3. Output Contracts

A helper is only cheap if its reply shape is fixed and parseable. The caller relies on these shapes and nothing else:

**Locator**
```text
<heading>:
- path:line — `symbol` — short note
totals: <counts>
```
or the single line `no relevant locations found`. Always path first, line attached, symbols in backticks, so the caller can match `path:\d+` without reading prose.

**Builder**
```text
<path:line-range> — <change in ten words or fewer>
verified: <re-read OK | mismatch at path:line>
```
or exactly one terminal token as the first word: `too-big`, `needs-confirm`, `ambiguous`, `regressed`. The caller branches on the first token.

**Reviewer**
```text
path:line: <severity>: <problem>. <fix>.
totals: <n blocker> <n high> <n medium> <n low>
```
or `No issues.` Findings sorted by file then line.

Helpers drop the compressed shape for security warnings, irreversible-action confirmations, and any line that could be misread as a fragment; they resume the shape afterwards. Output that a human will read directly is paraphrased by the caller; contract output is for the caller.

---

## 4. Chaining Patterns

- **Locate, fix, verify** (the common case): locator returns sites; main thread picks one or two and hands exact paths to the builder; reviewer audits the diff.
- **Parallel scout** (broad investigation): two or three locators in one message, each with a different angle (definitions, callers, tests); aggregate in the main thread.
- **Single-shot edit** (site already known): skip the locator; hand `path:line` to the builder directly.

---

## 5. Mistakes That Waste a Turn

- Sending a builder to a file you have not located. It burns tokens re-discovering what the locator would have returned in ten lines.
- Chaining locator to builder for a five-file refactor. The builder returns `too-big`.
- Asking a findings-only reviewer for "general feedback". It has no channel for opinions.
- Expecting prose from a contract helper, or reading its reply to the user unparaphrased.
- Spawning one helper per file. One helper with a wide brief and a fixed contract beats ten narrow ones; measure context use before launching a fleet.

---
