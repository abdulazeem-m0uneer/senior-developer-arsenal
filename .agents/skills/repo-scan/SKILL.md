---
name: repo-scan
description: 'Scans the repository the arsenal is installed into and reports which arsenal skills, rules, and subagents apply, using a bundled stack-detection script refined by reading a few key files. Detects Node.js, React, Angular, .NET, Python, SQL, Docker, CI, tests, OpenAPI, and UI styling, and lists gaps (no tests, no CI, files over 1000 lines). Use when starting work in a new or unfamiliar repository or when the user asks which skills to use. Triggers on: "scan this repo", "which skills apply", "detect the stack", "/repo-scan". Do not use for reviewing code quality (use deep-review).'
---

# Repository Scan & Skill Applicability Procedure

This skill guides the agent through detecting the stack of a target repository and turning it into a short, evidence-backed list of the arsenal skills, rules, and subagents worth activating there.

---

## 1. When to Use This Skill

Activate this skill when:
- The arsenal has just been installed into a repository and nobody has mapped it to the codebase yet.
- Starting the first session in an unfamiliar repository, before choosing a specialized skill.
- The stack changed (new service, new frontend, new database) and the applicable set needs refreshing.
- The user asks "which skills apply here?" or runs the `/repo-scan` slash command.

*Boundary*: This skill only identifies what applies. For judging the code itself use `deep-review` or `code-review`; for architecture decisions use `architecture-design-adr`; for closing the gaps it reports use `test-every-change` and `devops-ci`.

---

## 2. Step-by-Step Execution Runbook

### Step 1: Run the Detector
Run this skill's `scripts/detect_stack.py` from your shell, passing the root of the target repository. Resolve the script path relative to the directory that contains this file. It needs Python 3.9+ and no packages.
```bash
python scripts/detect_stack.py <repo-path>            # human-readable table
python scripts/detect_stack.py <repo-path> --json     # same report as JSON
```
Exit status `0` means the report is complete; `2` means the path is not an existing directory. The script skips dependency and build folders and stops after 20000 files; a capped run is flagged under gaps.

### Step 2: Read the Report
The report has three parts:
- **Detected signals**: one row per signal with the evidence path and the recommended skills, rules, and subagents.
- **Always applicable**: the baseline set that applies to every repository.
- **Gaps**: no tests, no CI pipeline, not a git root, unparseable manifests, and the ten largest source files above 1000 lines.

### Step 3: Refine by Reading Key Files
The script matches marker files and dependency names only. Confirm or correct each row with a few targeted reads, following [Signal Mapping & Refinement](./references/signal-mapping.md):
1. Open the evidence file of each detected signal with your file-read tool and confirm the signal is real (a production dependency, not a leftover or a sample).
2. Read the top-level manifest, the project README, and one entry point per service to find what the script cannot see: framework versions, monorepo layout, the database engine in use, the test command.
3. Remove recommendations whose evidence turns out to be incidental; add ones the refinement table calls for.
4. Do not read whole directories. Stop once each row is confirmed, corrected, or removed.

### Step 4: Report the Applicable Set
Deliver the table from the Verification Protocol: what applies, why (evidence path), and in which order to use it. List gaps as actions with the skill that closes each one. Recommend only names that exist in the installed arsenal.

---

## 3. Verification Protocol

1. The script ran with exit status `0` and its output is the basis of the report; no stack claim is made from memory or from the repository name.
2. Every recommended skill, rule, and subagent carries an evidence path that was opened and confirmed.
3. Every recommended name exists in the installed arsenal; unknown names are dropped.
4. Output the applicability table:

| Signal | Evidence | Confirmed | Skills | Rules | Subagents |
| :--- | :--- | :---: | :--- | :--- | :--- |
| Node.js project | `package.json` (fastify 5) | yes | `nodejs-backend-expert`, `api-design` | `nodejs-standards` | `node-specialist` |
| SQL / database | `prisma/schema.prisma` (PostgreSQL) | yes | `database-architect`, `database-migration` | `database-standards` | `db-architect` |
| Docker | `Dockerfile` | yes | `devops-ci` | - | `devops-engineer` |

| Gap | Evidence | Close with |
| :--- | :--- | :--- |
| No CI pipeline | no workflow or pipeline file found | `devops-ci` |
| File over 1000 lines | `src/orders/order.service.ts` (1840 lines) | split by responsibility, then `test-every-change` |

---

## 4. ⚡ Token-Saving Execution Rule

- **Script Before Reading**: Never explore the tree by hand before running the detector.
- **Targeted Reads Only**: Open the evidence files and the few key files in Step 3; no directory dumps.
- **Tables Only**: Report the two tables above; no stack description in prose.
