---
name: dead-code
description: 'Find and remove unused functions, imports, exports, dependencies and commented-out code, each verified first. Use for dead or unused code.'
---

> **Lite edition:** steps that run a bundled script (a `scripts/` or `templates/` path) need the full arsenal (https://github.com/abdulazeem-m0uneer/senior-developer-arsenal). Here, do that step by hand or skip it and say so.

<!-- routing (read by the skill router, not loaded into the skill listing): Dead-code sweep: unused functions, imports, exports, dependencies and commented-out code, verified before removal. Triggers: "dead code", "unused code", "unused imports", "unused exports", "remove dead code", /dead-code. Not for untested code (use refactor-legacy). -->

# Dead Code Sweep Procedure

This skill finds dead code with the stack's own tool, proves each candidate is unreachable before removing it, and removes it in small batches with the tests green after each one. The Stop hook already checks every session's own diff (`scripts/dead_code.py`); this skill is the repository-wide sweep.

---

## 1. When to Use This Skill

Activate this skill when:
- The user asks for unused code, imports, exports, dependencies or commented-out code to be found or removed.
- The Stop hook named dead code and the cleanup is wider than the lines it listed.
- A feature was removed and its leftovers need hunting down.
- The user runs the `/dead-code` slash command.

*Boundary*: For changing code that has no tests, use `refactor-legacy` first. For reviewing a diff, use `code-review`. For upgrading or removing a dependency version, use `dependency-upgrade`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Detect the Stack
1. List the languages and package managers from the manifests (`package.json`, `pyproject.toml`, `*.csproj`, `go.mod`, `Cargo.toml`, `pom.xml`, `composer.json`, `Gemfile`, `pubspec.yaml`).
2. Record the test and lint commands; run them once for a baseline. Done when the baseline result is written down.

### Step 2: Collect Candidates
Consult: [Language Tools](./references/language-tools.md) for the exact command per language.
1. Run the language tool when it is installed (never install a global tool without asking; a project dev dependency through the lockfile is fine).
2. When no tool is installed, list symbols with zero callers through CodeGraph (`codegraph_explore`).
3. When CodeGraph is unavailable too, run `python3 <skill-dir>/scripts/dead_code.py --diff <base>` (exit 1 findings, 0 clean, 2 error).
Done when every candidate is listed as `file:line name kind`.

### Step 3: Verify Each Candidate
A tool's "unused" is a hypothesis. Rule each candidate out against:
1. Reflection, dependency-injection registration, plugin or entry-point lists.
2. Serialization: fields read by a JSON, ORM or protobuf mapper.
3. Framework conventions: routes, handlers, migrations, jobs, lifecycle hooks, test fixtures.
4. References outside code: `git grep -w <name>` across config, templates, scripts, docs and SQL.
5. Public package API: anything exported by a published package.
Done when each candidate is either confirmed dead or kept with a one-line reason.

### Step 4: Remove in Small Batches
1. Remove one batch (one module or one kind), run the tests and lint, and commit per batch.
2. A red run means a candidate was alive: restore it, move it to keep-with-reason, and continue.
3. Never remove the exported API of a published package without asking the user: other repositories may call it.
Done when every confirmed candidate is gone and the suite is green.

---

## 3. Verification Protocol

1. Every removal maps to a candidate verified in Step 3.
2. The full test and lint suites pass after the last batch.
3. Output the table:

| File:line | Name | Kind | Verdict | Evidence |
| :--- | :--- | :--- | :--- | :--- |
| `src/util.ts:40` | `formatLegacy` | unused export | removed | `knip`, no `git grep` hit outside the file |
| `app/jobs.py:12` | `nightly_sync` | unused function | kept | registered by name in `scheduler.yaml` |

---

## 4. ⚡ Token-Saving Execution Rule

- **Table, No Narration**: Report the table and the suite result line only.
- **Diffs Only**: Show removed lines as diffs, never whole files.
- **Batch Tool Output**: Read only the candidate lines of a tool's report, not its full log.
