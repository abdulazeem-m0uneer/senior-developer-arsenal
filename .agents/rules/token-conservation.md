# Token Conservation & Context Engineering Protocol

This rule enforces strict token economy across all agent responses, code generations, code reviews, and reasoning steps. The user is strictly focused on minimizing token consumption while maintaining senior engineering rigor.

---

## 1. Zero Conversational Fluff

- **Eliminate Preambles & Pleasantries**: Never output introductory filler (e.g., "Certainly!", "Sure thing", "I would be happy to help", "As a senior engineer...").
- **Direct Action**: Start responses immediately with the finding, execution command, or code diff.
- **Omit Conversational Outros**: Do not conclude with generic sign-offs (e.g., "Let me know if you need anything else!").

---

## 2. Surgical Code Output & Minimal Diffs

- **No Full-File Dumps**: Never re-print entire files (especially unchanged files or files over 50 lines).
- **Targeted Diffs**: Show only the changed function, block, or statement with minimal surrounding context (1–3 lines).
- **Symbolic References**: Use file path and line pointers (`file.ts:L45-L52`) rather than copy-pasting the existing code block before modifying it.
- **No Echoing Artifacts**: When creating or modifying a file with filesystem tools, do not repeat the full file contents in the conversational text. Summarize the change in 1–2 bullet points and provide the clickable file link.

---

## 3. High Information Density

- **Format in Compact Tables & Keyed Lists**: Use dense markdown formats instead of multi-paragraph prose:
  - Format: `[Severity] path/file:L10 - Issue: <brief issue> -> Fix: <brief fix>`
- **Progressive Disclosure**:
  - Do NOT preload or quote reference manuals (`references/*.md`) unless strictly requested or needed for a complex decision.
  - Rely on index pointers and on-demand reading.

---

## 4. Terse Verification & Reporting

- **Test & Build Results**: Report build/test outcomes in a single status line:
  - `✅ Build passed (0 errors, 0 warnings). 14/14 tests green.`
  - Do not paste hundreds of lines of successful build logs. Only print relevant error lines when a build or test fails.
- **Concise Reasoning**: Keep chain-of-thought and explanations dense, technical, and free of redundant restatements.
