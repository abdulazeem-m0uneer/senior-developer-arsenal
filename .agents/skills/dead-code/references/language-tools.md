# Dead-Code Tools by Language

Read in Step 2 of the dead-code skill. Prefer the project's own pinned version (`npx`, `uv run`, `dotnet tool run`); ask before installing anything globally.

| Language | Command | Finds |
| :--- | :--- | :--- |
| TypeScript / JavaScript | `npx knip` | unused files, exports, types, dependencies |
| Python | `vulture . --min-confidence 80` | unused functions, classes, variables |
| Python | `ruff check --select F401,F841 .` | unused imports (F401) and local variables (F841) |
| C# | `dotnet build -warnaserror:IDE0051,IDE0052,CS0168` (enable `EnforceCodeStyleInBuild`) | unused private members (IDE0051), unread private members (IDE0052), unused variables (CS0168) |
| Go | `staticcheck -checks U1000 ./...` | unused identifiers |
| Go | `deadcode ./...` (`golang.org/x/tools/cmd/deadcode`) | functions unreachable from `main` |
| Rust | `cargo build` (read the `dead_code` warnings) | unused functions, fields, variants |
| Rust | `cargo +nightly udeps` | unused dependencies |
| Java / Kotlin | `detekt` with `UnusedPrivateMember` enabled | unused private members |
| PHP | `vendor/bin/phpstan analyse` with a dead-code detector extension (`shipmonk/dead-code-detector`) | unused classes, methods, constants |
| Ruby | `debride .` | methods never called |
| Swift | `periphery scan` | unused declarations |
| Dart / Flutter | `dart analyze` | `unused_element`, `unused_import`, `unused_local_variable` |
| CSS | `npx purgecss --css <css> --content <templates>` | selectors no template uses |
| Unused dependencies | `npx knip` (JS), `deptry .` (Python), `cargo +nightly udeps` (Rust) | declared but never imported packages |

## Without a Tool

1. CodeGraph: ask `codegraph_explore` for the symbols of the area; a symbol with no callers and no references is a candidate.
2. Fallback: `python3 <skill-dir>/scripts/dead_code.py --diff <base>` checks a diff (commented-out code, debugger leftovers, names defined once, imports orphaned by removed calls) in any language, with git only.

## Known False Positives

| Tool | Reports as unused | Why it is alive |
| :--- | :--- | :--- |
| `vulture` | Django or FastAPI views, Celery tasks, pytest fixtures | registered by decorator or by name |
| `knip` | files loaded by a framework convention (Next.js `app/`, Storybook) | add them to the knip `entry` config |
| `staticcheck U1000` | methods that satisfy an interface through reflection | add a compile-time interface assertion |
| IDE0051 | members used only by a serializer or `[JsonInclude]` | serialization reads them |
