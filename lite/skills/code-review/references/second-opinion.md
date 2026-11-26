# Second Opinion

Read in Step 4a of the code-review skill, before you run `scripts/second_opinion.py`.

## When to ask for one

| Ask | Skip |
| :--- | :--- |
| Money movement, auth or permissions, data migrations, concurrency, cryptography | Typos, renames, formatting, doc-only changes |
| A plan or design that is costly to reverse | A change already covered by a failing-then-passing test that pins the risk |
| Your own review found nothing on a large or risky diff | The diff holds secrets the redaction cannot safely remove: narrow the ref instead |

## What is sent, and what is not

- Only the diff against `<base>` (or the plan file). It never sends the repository, history or environment. Untracked files are not part of `git diff`: run `git add -N <file>` first to include a new file.
- The blocks of secret-looking files (environment files, certificate and key files, SSH private keys, names with a `key`, `secret` or `credential` segment) are dropped and named on stderr.
- Every remaining line that looks like a credential is replaced by `[redacted: <reason>]`.
- Material over `--max-bytes` (default 200,000) is refused, not truncated. A cut diff hides findings, so narrow the ref.
- `--dry-run` prints exactly what would be sent. Use it the first time in a repository.

## Weighing disagreement

1. A finding from the second CLI is a hypothesis. Open the cited `file:line` and reproduce the failure before you report it.
2. If it is reproduced, it joins your findings with its severity. Say in the review that the second opinion found it.
3. If it is refuted, drop it. Give the one-line reason in your notes, not in the review.
4. If both reviewers disagree on a severity, use the higher one only when the failure scenario is concrete (an input and a wrong output). Otherwise use the lower one and state the open question.
5. Never merge on the second opinion's "no findings" alone. It sees only the diff, not the tests that ran.

## Exit codes

| Code | Meaning | What to do |
| :--- | :--- | :--- |
| 0 | Review printed | Verify each finding (above) |
| 2 | Usage error, git error, nothing to review, or a refused file | Fix the ref or the path |
| 3 | No Codex or Gemini CLI installed | Say so in "Not Checked" and continue |
| 4 | Over `--max-bytes` | Review in smaller ranges |
| 5 | The CLI failed or timed out | Report it. Retry once at most with a larger `--timeout` |
