# Evidence Log, Confidence Rubric, and Final Report

Read this at Step 4 for the row format and grading rules, and at Step 6 for the report shape. The evidence log is the working artifact; the report is written from it, never the other way round.

---

## 1. Evidence Log

Header (written at Step 1, before any analysis):

```markdown
# Evidence Log: <feature> in <application> <version> (<build hash or file hash>)
Authorization: <line from the gate>   License: <clause>   Purpose: <one of the accepted purposes>
Feature action: <user action> → <observable result>
Done means: <explanation | rebuild in <stack> at <path> | both>
Analyzer: <REA tool / provider>   REA version: <from `rea --help`>
```

One row per hop, in call order, one chain per oracle case:

| # | Location | Hop | Evidence kind | Confidence | Note |
| :- | :--- | :--- | :--- | :---: | :--- |
| 1 | `path:line` or `module!function+0x1a` | what this hop does, one clause | static / runtime / capture / storage / doc | proven / probable / assumed | why this grade; what would change it |

Rules for rows:
- **Location** is exact enough to reopen: file and line for source or bundles, module and offset for native, method token for CIL, request index for a HAR.
- **Hop** describes behaviour ("reads `recent.sqlite`, orders by `last_opened` desc, limit 20"), not code ("calls `f` then `g`").
- **Evidence kind** names the independent sources; two kinds that agree are what make a row proven.
- A gap is a row with location `—`, kind `none`, grade `assumed`, and a note listing what was searched.

---

## 2. Confidence Rubric

| Grade | Requires | Typical sources | May appear in |
| :--- | :--- | :--- | :--- |
| **proven** | Two independent evidence kinds that agree | static read + HAR; static read + SQLite diff; two static views (CIL and strings) that agree; runtime trace + capture | spec lines without a caveat |
| **probable** | One evidence kind | pseudocode alone; a single static read; a single capture; vendor documentation | spec lines with a `// probable: row N` marker |
| **assumed** | No direct evidence; inferred from UI, naming, or convention | "the button is labelled Sync so it syncs"; a function named `validate` | Unknowns section only; never in the spec as behaviour |

Downgrades are mandatory: a failing oracle test downgrades every row it contradicts; a target version change downgrades every probable row to assumed until re-traced.

What pseudocode cannot prove on its own: types and signedness, struct layout, error-path ordering, which of several callers runs at the oracle action, anything the decompiler marked as unreachable or merged.

---

## 3. Behaviour Spec (bridge artifact)

```markdown
## Behaviour Spec: <feature>
Inputs: <name: type/format, where it comes from>
Output: <what the user sees; data returned; file or rows written>
Formats: <wire shape; storage schema; encodings; units>
Ordering and limits: <sort keys; page sizes; timeouts; retries>
Error paths: <condition → observed behaviour>
Not specified (assumed rows): <list>
Rows cited: <row numbers per line above>
```

---

## 4. Final Report (fixed shape)

```markdown
# Reverse-Engineering Report: <feature> in <application> <version>

## 1. Executive Summary
One sentence on how the feature works. One sentence on what was proven versus probable. Effort spent and whether the rebuild is done.

## 2. Target Profile
Type, version, build hash, technologies seen, analyzer and provider used, REA version.

## 3. Feature Trace
The chain per oracle case as a list of hops (`row #: location → behaviour [grade]`). No code.

## 4. Evidence Log
The table from section 1, complete.

## 5. Reconstruction
Where the rebuild lives, the behaviour spec, the architecture in five lines or fewer, and the markers for probable rows.

## 6. Verification Results
| Oracle case | Input | Expected | Original | Rebuild | Pass |
Plus the test command.

## 7. Implementation Plan
Ordered steps to integrate into the user's project, each with its test and its risk.

## 8. Unknowns and Limitations
Every assumed row, what was searched, what evidence would resolve it, and what a version update is most likely to break.
```

Keep the report under 150 lines; the evidence log table carries the detail.
