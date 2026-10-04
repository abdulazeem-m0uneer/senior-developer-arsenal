#!/usr/bin/env python3
"""Detect a repository's stack and map it to arsenal skills, rules and subagents.

Usage: python scripts/detect_stack.py [path] [--json]
Exit codes: 0 on success, 2 when the path is not an existing directory.
"""
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "bin", "obj", "dist", "build", ".venv", "venv", "__pycache__", "vendor"}
MAX_FILES = 20000
MAX_READ_BYTES = 8_000_000
LONG_FILE_LINES = 1000
WORST_FILES = 10
SOURCE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".cs", ".py", ".sql", ".css", ".scss", ".html", ".vue", ".go", ".java")
MANIFEST_RE = re.compile(r"^(package\.json|pyproject\.toml|pipfile|setup\.(py|cfg)|requirements.*\.txt|.*\.csproj)$")
COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
DOCKERFILE_RE = re.compile(r"^dockerfile(\..+)?$|\.dockerfile$")
TEST_FILE_RE = re.compile(
    r"^(vitest|jest|playwright)\.config\.|^(pytest\.ini|conftest\.py)$|\.(test|spec)\.|^test_|tests\.cs$")
TEST_DIRS = ("test", "tests", "__tests__", "spec", "specs", "e2e")
DEP_SECTIONS = ("dependencies", "devDependencies", "peerDependencies")
FRONTEND_DEPS = {"react": "react", "next": "react", "@angular/core": "angular"}
NODE_BACKEND_DEPS = ("express", "fastify", "@nestjs/core", "koa", "hono", "@hapi/hapi")
NODE_DATA_DEPS = ("@prisma/client", "typeorm", "knex", "sequelize", "drizzle-orm", "pg", "mssql", "better-sqlite3")
NODE_TEST_DEPS = ("vitest", "jest", "mocha", "@playwright/test", "cypress")
PYTHON_FRAMEWORKS = ("fastapi", "sqlalchemy", "django", "flask")
ENGINE_HINTS = {
    "PostgreSQL": ("postgres", "npgsql", "psycopg", "asyncpg"),
    "MSSQL": ("mssql", "sqlserver", "pyodbc"),
    "SQLite": ("sqlite",),
}
KINDS = ("skills", "rules", "subagents")
# signal -> (label, skills, rules, subagents); names are space-separated and must exist in the arsenal.
RECOMMENDATIONS = {
    "node": ("Node.js project", "nodejs-backend-expert api-design perf-audit", "nodejs-standards", "node-specialist"),
    "frontend": ("Frontend (React / Angular)", "frontend-architecture-expert frontend-audit", "frontend-standards",
                 "frontend-architect"),
    "dotnet": ("C#/.NET", "csharp-dotnet-expert api-design perf-audit", "csharp-dotnet-standards", "dotnet-specialist"),
    "python": ("Python", "python-backend-expert python-audit", "python-standards", "python-specialist"),
    "database": ("SQL / database", "database-architect database-migration perf-audit", "database-standards",
                 "db-architect"),
    "fullstack": ("Fullstack (frontend + backend)", "fullstack-integration-master e2e-feature",
                  "fullstack-standards", "fullstack-architect"),
    "openapi": ("OpenAPI", "api-design fullstack-integration-master", "fullstack-standards", "fullstack-architect"),
    "styling": ("UI styling", "ui-ux-architect ui-ux-audit", "ui-ux-standards", "ui-ux-architect"),
    "docker": ("Docker", "devops-ci", "", "devops-engineer"),
    "ci": ("CI pipeline", "devops-ci git-release", "", "devops-engineer"),
    "tests": ("Tests present", "test-strategy qa-engineer", "", "test-engineer qa-engineer"),
    "git": ("Git repository", "git-workflow-master git-release", "git-standards", ""),
}
ALWAYS_APPLICABLE = (
    "code-review deep-review test-every-change definition-of-done investigate git-workflow-master security-audit",
    "senior-engineer-core defensive-epistemology token-conservation testing-standards",
    "code-reviewer epistemic-debugger security-auditor",
)


@dataclass
class Repo:
    root: Path
    files: list
    truncated: bool
    manifests: dict
    node_deps: dict
    invalid_manifests: list

    def named(self, *names):
        return [f for f in self.files if basename(f) in names]

    def suffixed(self, *suffixes):
        return [f for f in self.files if f.lower().endswith(suffixes)]

    def matching(self, pattern):
        return [f for f in self.files if pattern.search(basename(f))]

    def in_dir(self, *dir_names):
        return [f for f in self.files if set(f.lower().split("/")[:-1]) & set(dir_names)]

    def with_dep(self, *deps):
        return sorted({self.node_deps[d] for d in deps if d in self.node_deps})

    def mentioning(self, *needles):
        return [path for path, text in self.manifests.items() if any(n in text for n in needles)]


def basename(path):
    return path.rsplit("/", 1)[-1].lower()


def walk(root):
    files = []
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            if len(files) >= MAX_FILES:
                return files, True
            files.append((Path(current) / name).relative_to(root).as_posix())
    return files, False


def read_bytes(path):
    try:
        with open(path, "rb") as handle:
            return handle.read(MAX_READ_BYTES)
    except OSError:
        return b""


def parse_node_deps(manifests):
    deps, invalid = {}, []
    for path in (p for p in manifests if basename(p) == "package.json"):
        try:
            sections = [json.loads(manifests[path]).get(section) for section in DEP_SECTIONS]
        except (ValueError, AttributeError):
            invalid.append(path)
            continue
        for section in sections:
            for name in section if isinstance(section, dict) else ():
                deps.setdefault(name, path)
    return deps, invalid


def load_repo(root):
    files, truncated = walk(root)
    manifest_paths = [f for f in files if MANIFEST_RE.match(basename(f)) or basename(f) in COMPOSE_NAMES]
    manifests = {f: read_bytes(root / f).decode("utf-8", errors="replace") for f in manifest_paths}
    node_deps, invalid = parse_node_deps(manifests)
    lowered = {path: text.lower() for path, text in manifests.items()}
    return Repo(root, files, truncated, lowered, node_deps, invalid)


def evidence(paths, tags=()):
    if not paths:
        return None
    more = f" (+{len(paths) - 1} more)" if len(paths) > 1 else ""
    note = f" [{', '.join(tags)}]" if tags else ""
    return f"{paths[0]}{more}{note}"


def detect_frontend(repo):
    frameworks = sorted({FRONTEND_DEPS[dep] for dep in FRONTEND_DEPS if dep in repo.node_deps})
    return evidence(repo.with_dep(*FRONTEND_DEPS) or repo.named("angular.json"), frameworks)


def detect_node(repo):
    backend = [dep for dep in NODE_BACKEND_DEPS if dep in repo.node_deps]
    if backend:
        return evidence(repo.with_dep(*backend), backend)
    if detect_frontend(repo):
        return None
    return evidence(repo.named("package.json", "tsconfig.json"), ["no web framework dependency found"])


def detect_dotnet(repo):
    return evidence(repo.suffixed(".csproj", ".sln"))


def detect_python(repo):
    manifests = [p for p in repo.manifests if p.lower().endswith((".toml", ".txt", ".py", ".cfg", "pipfile"))]
    frameworks = [name for name in PYTHON_FRAMEWORKS if repo.mentioning(name)]
    return evidence(manifests + repo.suffixed(".py"), frameworks)


def detect_database(repo):
    engines = [engine for engine, needles in ENGINE_HINTS.items() if repo.mentioning(*needles)]
    paths = (repo.suffixed(".sql", ".prisma") + repo.in_dir("migrations") + repo.with_dep(*NODE_DATA_DEPS)
             + repo.mentioning("sqlalchemy", "entityframeworkcore", "dapper", *sum(ENGINE_HINTS.values(), ())))
    return evidence(paths, engines)


def detect_fullstack(repo):
    frontend = detect_frontend(repo)
    backend = detect_node(repo) or detect_dotnet(repo) or detect_python(repo)
    return f"frontend: {frontend}; backend: {backend}" if frontend and backend else None


def detect_openapi(repo):
    return evidence(repo.matching(re.compile(r"^(openapi|swagger).*\.(json|ya?ml)$")))


def detect_styling(repo):
    tailwind = repo.matching(re.compile(r"^tailwind\.config\."))
    return evidence(tailwind + repo.suffixed(".css", ".scss", ".sass", ".less"), ["tailwind"] if tailwind else ())


def detect_docker(repo):
    return evidence(repo.matching(DOCKERFILE_RE) + repo.named(*COMPOSE_NAMES))


def detect_ci(repo):
    workflows = [f for f in repo.files if f.startswith((".github/workflows/", ".circleci/"))]
    return evidence(workflows + repo.named(".gitlab-ci.yml", "azure-pipelines.yml", "jenkinsfile"))


def detect_tests(repo):
    return evidence(repo.matching(TEST_FILE_RE) + repo.with_dep(*NODE_TEST_DEPS)
                    + repo.mentioning("pytest", "xunit", "nunit") + repo.in_dir(*TEST_DIRS))


def detect_git(repo):
    return ".git" if (repo.root / ".git").exists() else None


DETECTORS = {
    "node": detect_node, "frontend": detect_frontend, "dotnet": detect_dotnet, "python": detect_python,
    "database": detect_database, "fullstack": detect_fullstack, "openapi": detect_openapi,
    "styling": detect_styling, "docker": detect_docker, "ci": detect_ci, "tests": detect_tests, "git": detect_git,
}


def detect_signals(repo):
    detected = []
    for key, detector in DETECTORS.items():
        found = detector(repo)
        if found:
            label, *names = RECOMMENDATIONS[key]
            row = {"signal": key, "label": label, "evidence": found}
            row.update({kind: value.split() for kind, value in zip(KINDS, names)})
            detected.append(row)
    return detected


def find_long_files(repo):
    candidates = [f for f in repo.suffixed(*SOURCE_SUFFIXES) if ".min." not in basename(f)]
    counted = ((read_bytes(repo.root / f).count(b"\n"), f) for f in candidates)
    longest = sorted((item for item in counted if item[0] > LONG_FILE_LINES), key=lambda item: (-item[0], item[1]))
    return [{"path": path, "lines": lines} for lines, path in longest[:WORST_FILES]]


def find_gaps(repo, signals):
    gaps = []
    if "tests" not in signals:
        gaps.append("No tests found (no test config, dependency, file or directory): apply test-every-change.")
    if "ci" not in signals:
        gaps.append("No CI pipeline found: apply devops-ci.")
    if "git" not in signals:
        gaps.append("Not a git repository root: git skills and rules need one.")
    gaps.extend(f"Unparseable {path}: Node.js detection is incomplete." for path in repo.invalid_manifests)
    if repo.truncated:
        gaps.append(f"Traversal capped at {MAX_FILES} files: results are partial.")
    return gaps


def build_report(root):
    repo = load_repo(root)
    detected = detect_signals(repo)
    return {
        "path": str(root),
        "files_scanned": len(repo.files),
        "detected": detected,
        "always_applicable": {kind: names.split() for kind, names in zip(KINDS, ALWAYS_APPLICABLE)},
        "gaps": find_gaps(repo, {row["signal"] for row in detected}),
        "long_files": find_long_files(repo),
    }


def render_table(headers, rows):
    widths = [max(len(cell) for cell in column) for column in zip(headers, *rows)]
    lines = [headers, ["-" * width for width in widths], *rows]
    return "\n".join(" | ".join(cell.ljust(width) for cell, width in zip(line, widths)).rstrip() for line in lines)


def render_text(report):
    rows = [[row["label"], row["evidence"], *(", ".join(row[kind]) or "-" for kind in KINDS)]
            for row in report["detected"]]
    out = [f"Repository: {report['path']} ({report['files_scanned']} files scanned)", "", "DETECTED SIGNALS"]
    out.append(render_table(["Signal", "Evidence", "Skills", "Rules", "Subagents"], rows) if rows else "(none)")
    out += ["", "ALWAYS APPLICABLE"]
    out += [f"{kind}: {', '.join(names)}" for kind, names in report["always_applicable"].items()]
    out += ["", "GAPS"] + [f"- {gap}" for gap in report["gaps"]]
    if report["long_files"]:
        out.append(f"- Files over {LONG_FILE_LINES} lines (worst {WORST_FILES}):")
        out += [f"    {item['lines']:>6}  {item['path']}" for item in report["long_files"]]
    if not report["gaps"] and not report["long_files"]:
        out.append("(none)")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Detect a repository stack and recommend arsenal skills.")
    parser.add_argument("path", nargs="?", default=".", help="repository to scan (default: current directory)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    if not Path(args.path).is_dir():
        print(f"error: not an existing directory: {args.path}", file=sys.stderr)
        return 2
    report = build_report(Path(args.path).resolve())
    print(json.dumps(report, indent=2) if args.json else render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
