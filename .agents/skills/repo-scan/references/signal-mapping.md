# Signal Mapping & Refinement

The mapping the detector applies, what each signal is detected from, and how to refine the result by reading key files.

---

## 1. Signal to Recommendation Map

| Signal | Detected from | Skills | Rules | Subagents |
| :--- | :--- | :--- | :--- | :--- |
| Node.js project | `package.json` with `express`, `fastify`, `@nestjs/core`, `koa`, `hono`, or `@hapi/hapi`; otherwise `package.json` / `tsconfig.json` with no frontend framework | `nodejs-backend-expert`, `api-design`, `perf-audit` | `nodejs-standards` | `node-specialist` |
| Frontend (React / Angular) | `react`, `next`, or `@angular/core` dependency; `angular.json` | `frontend-architecture-expert`, `frontend-audit` | `frontend-standards` | `frontend-architect` |
| C#/.NET | `*.csproj`, `*.sln` | `csharp-dotnet-expert`, `api-design`, `perf-audit` | `csharp-dotnet-standards` | `dotnet-specialist` |
| Python | `pyproject.toml`, `requirements*.txt`, `Pipfile`, `setup.py`, `setup.cfg`, `*.py`; tags `fastapi`, `sqlalchemy`, `django`, `flask` | `python-backend-expert`, `python-audit` | `python-standards` | `python-specialist` |
| SQL / database | `*.sql`, `*.prisma`, a `migrations` directory (any case, covers EF Core), ORM or driver dependencies, engine names in manifests and compose files | `database-architect`, `database-migration`, `perf-audit` | `database-standards` | `db-architect` |
| Fullstack (frontend + backend) | Frontend signal plus a Node.js, .NET, or Python signal | `fullstack-integration-master`, `e2e-feature` | `fullstack-standards` | `fullstack-architect` |
| OpenAPI | `openapi*` or `swagger*` with `.json`, `.yaml`, `.yml` | `api-design`, `fullstack-integration-master` | `fullstack-standards` | `fullstack-architect` |
| UI styling | `*.css`, `*.scss`, `*.sass`, `*.less`, `tailwind.config.*` | `ui-ux-architect`, `ui-ux-audit` | `ui-ux-standards` | `ui-ux-architect` |
| Docker | `Dockerfile`, `Dockerfile.*`, `*.dockerfile`, compose files | `devops-ci` | - | `devops-engineer` |
| CI pipeline | `.github/workflows/`, `.circleci/`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `Jenkinsfile` | `devops-ci`, `git-release` | - | `devops-engineer` |
| Tests present | Vitest / Jest / Playwright config, `pytest.ini`, `conftest.py`, `*.test.*`, `*.spec.*`, `test_*`, `*Tests.cs`, test dependencies, test directories | `test-strategy`, `qa-engineer` | - | `test-engineer`, `qa-engineer` |
| Git repository | `.git` at the scanned root | `git-workflow-master`, `git-release` | `git-standards` | - |

Always applicable, whatever is detected:

| Kind | Names |
| :--- | :--- |
| Skills | `code-review`, `deep-review`, `test-every-change`, `definition-of-done`, `investigate`, `git-workflow-master`, `security-audit` |
| Rules | `senior-engineer-core`, `defensive-epistemology`, `token-conservation`, `testing-standards` |
| Subagents | `code-reviewer`, `epistemic-debugger`, `security-auditor` |

---

## 2. Skills the Detector Does Not Map

Recommend these from the refinement reads, not from file markers:

| Skill | Recommend when |
| :--- | :--- |
| `architecture-design-adr` | Several services or bounded contexts, or a pending structural decision is visible in the docs or issues |
| `codegraph` | A code-graph index is configured for the repository, or the codebase is large enough that symbol queries beat text search |
| `agent-memory` | A long-term memory server is configured for the agent |
| `create-skill` | The repository has recurring workflows that no existing skill covers |

---

## 3. Refinement Reads

| Signal | Open | Confirm or correct |
| :--- | :--- | :--- |
| Node.js project | The manifest that was cited; the `scripts` block; one server entry point | Real backend versus tooling-only package; framework and version; test and lint commands |
| Frontend | The manifest; the app root component or router | Framework version; server-rendered or client-only; state and data libraries |
| C#/.NET | One `*.csproj` per project type | Target framework; web API versus library; EF Core or Dapper present |
| Python | `pyproject.toml` or requirements; the application entry point | Application versus helper scripts only; async stack; framework |
| SQL / database | One migration; the connection or ORM config | Actual engine (PostgreSQL, MSSQL, SQLite); migration tool; whether engine tags were incidental |
| Fullstack | How the frontend calls the backend | Shared types or generated client; same repository or only co-located |
| OpenAPI | The spec header | Version; hand-written or generated; whether clients are generated from it |
| Docker / CI | The Dockerfile and one pipeline file | What is built, tested, and deployed; missing test or lint stage |
| Tests present | The test config and one test file | Runner, real coverage versus a placeholder, the single command that runs the suite |

Corrections to apply:
- [ ] Python detected only from a few helper scripts: keep `python-standards` off the primary list; note it as incidental.
- [ ] Node.js detected with the note "no web framework dependency found": check whether it is a library, CLI, or tooling manifest before recommending backend skills.
- [ ] Database detected only from an engine name in a compose file: confirm the application uses it.
- [ ] Monorepo: report signals per package or service, with the path prefix as evidence.
- [ ] Tests detected from a directory name only: open one file to confirm that real tests exist.

---

## 4. Gap Handling

| Gap reported | Meaning | Close with |
| :--- | :--- | :--- |
| No tests found | No test config, dependency, file, or directory | `test-every-change` (bootstrap a runner), then `test-strategy` |
| No CI pipeline found | No workflow or pipeline definition | `devops-ci` |
| Not a git repository root | `.git` missing at the scanned path | Re-run at the repository root, or initialize version control |
| Unparseable manifest | `package.json` is not valid JSON or not an object | Fix the manifest, re-run the detector |
| Traversal capped | More than 20000 files after skipping dependency and build folders | Scan one service directory at a time |
| Files over 1000 lines | Ten largest source files above the limit, with line counts | Split by responsibility under characterization tests (`test-every-change`), verify with `definition-of-done` |

---

## 5. JSON Report Shape

```text
path               scanned root (absolute)
files_scanned      number of files visited
detected[]         signal, label, evidence, skills[], rules[], subagents[]
always_applicable  skills[], rules[], subagents[]
gaps[]             one sentence per gap
long_files[]       path, lines (largest first, at most 10)
```
