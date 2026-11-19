#!/usr/bin/env python3
"""Check that the arsenal is installed and healthy, and print the exact repair command for each problem.

Usage (also `arsenal doctor` / `arsenal.ps1 doctor`):
  doctor.py [--project PATH] [--fix]
Checks: the Python version; the Claude Code plugin (installed, enabled, its cached version against this checkout's
VERSION, older cached versions no install uses); the plugin's and this checkout's hooks.json (parses, each script
it runs exists and compiles); every installer target whose files are partly present globally, or in --project, read
from dist/manifest.tsv; the global and project lessons ledgers; the lesson-guard registries, read by this hook and by
every installed plugin version (a version that would refuse every Bash command over an entry is a failure); whether the CodeGraph and Hindsight MCP servers are
configured (configured or not, never contacted).
Nothing is changed without --fix, and --fix only re-runs the installer for the targets with missing files. Older
plugin versions are reported, never deleted. A missing plugin is a warning: an installer-only setup is valid.
Exit codes: 0 no failures (warnings allowed), 1 at least one failure, 2 usage error. Standard library only.
"""
import argparse
import json
import os
import py_compile
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_PYTHON = (3, 9)
PLUGIN = "arsenal@senior-developer-arsenal"
MCP_PLUGINS = {"codegraph": "arsenal-codegraph@senior-developer-arsenal",
               "hindsight": "arsenal-hindsight@senior-developer-arsenal"}
SCRIPT_IN_COMMAND = re.compile(r"\"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"]+\.py)\"")
INSTALLED_KINDS = ("file", "dir")


class Report:
    def __init__(self):
        self.rows, self.missing = [], {}  # missing: (scope, project) -> set of targets

    def ok(self, text):
        self.rows.append(("ok", text, ""))

    def warn(self, text, repair=""):
        self.rows.append(("warn", text, repair))

    def fail(self, text, repair=""):
        self.rows.append(("fail", text, repair))

    def failed(self):
        return any(level == "fail" for level, _, _ in self.rows)

    def render(self):
        lines = [f"[{level}] {text}" + (f"\n       repair: {repair}" if repair else "") for level, text, repair in self.rows]
        counts = {level: sum(1 for row in self.rows if row[0] == level) for level in ("ok", "warn", "fail")}
        lines.append(f"{counts['ok']} ok, {counts['warn']} warnings, {counts['fail']} failures")
        return "\n".join(lines)


def read_json(path):
    """The parsed file, None when it is missing, or raises ValueError with the reason."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from error


def version_key(text):
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3])


def check_python(report):
    found = sys.version_info[:3]
    shown = ".".join(map(str, found))
    if found[:2] >= MIN_PYTHON:
        report.ok(f"python {shown}")
    else:
        report.fail(f"python {shown} is older than {'.'.join(map(str, MIN_PYTHON))}", "install Python 3.9 or newer")


def check_hooks(report, root, label):
    """hooks.json under root parses, and each Python script it runs exists and compiles."""
    path = root / "hooks" / "hooks.json"
    try:
        config = read_json(path)
    except ValueError as error:
        report.fail(f"{label} hooks.json does not parse: {error}", "reinstall the plugin or restore hooks/hooks.json")
        return
    if config is None:
        report.fail(f"{label} has no hooks/hooks.json", "reinstall the plugin")
        return
    scripts = sorted(set(SCRIPT_IN_COMMAND.findall(json.dumps(config).replace('\\"', '"'))))
    broken = []
    with tempfile.TemporaryDirectory() as scratch:
        for index, script in enumerate(scripts):
            target = root / script
            try:
                py_compile.compile(str(target), cfile=os.path.join(scratch, f"{index}.pyc"), doraise=True)
            except (py_compile.PyCompileError, OSError) as error:
                broken.append(f"{script} ({'missing' if not target.is_file() else type(error).__name__})")
    if broken:
        report.fail(f"{label} hook scripts broken: {', '.join(broken)}", "reinstall the plugin")
    else:
        report.ok(f"{label} hooks.json parses; {len(scripts)} hook scripts compile")


def check_plugin(report, home, expected):
    plugins_dir = home / ".claude" / "plugins"
    try:
        registry = read_json(plugins_dir / "installed_plugins.json") or {}
        settings = read_json(home / ".claude" / "settings.json") or {}
    except ValueError as error:
        report.fail(f"Claude Code settings do not parse: {error}", "fix the JSON by hand; Claude Code rewrites it")
        return
    installs = (registry.get("plugins") or {}).get(PLUGIN) or []
    installs = [entry for entry in installs if isinstance(entry, dict)]
    if not installs:
        report.warn("Claude Code plugin not installed (fine for an installer-only setup)",
                    "in Claude Code: /plugin marketplace add <this repository>, then /plugin install " + PLUGIN)
        return
    enabled = (settings.get("enabledPlugins") or {}).get(PLUGIN)
    if enabled is False:
        report.warn("Claude Code plugin installed but disabled", f"in Claude Code: /plugin enable {PLUGIN}")
    in_use = {Path(entry["installPath"]).name for entry in installs if isinstance(entry.get("installPath"), str)}
    newest = max(in_use, key=version_key, default="")
    if expected and newest and version_key(newest) < version_key(expected):
        report.warn(f"Claude Code plugin {newest} is older than this checkout ({expected})",
                    "in Claude Code: /plugin marketplace update senior-developer-arsenal, then update the plugin")
    else:
        report.ok(f"Claude Code plugin {newest or '?'} installed ({len(installs)} scopes)")
    cache = plugins_dir / "cache" / "senior-developer-arsenal" / "arsenal"
    stale = sorted((path.name for path in cache.iterdir() if path.is_dir() and path.name not in in_use),
                   key=version_key) if cache.is_dir() else []
    if stale:
        report.warn(f"older plugin versions no install uses: {', '.join(stale)} (not deleted)",
                    f"after closing Claude Code: rm -r {' '.join(shlex.quote(str(cache / name)) for name in stale)}")
    if newest:
        check_hooks(report, cache / newest, f"plugin {newest}")


def manifest_rows(scope):
    try:
        lines = (ROOT / "dist" / "manifest.tsv").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = [line.split("\t") for line in lines[1:]]
    return [row for row in rows if len(row) >= 6 and row[1] == scope and row[2] in INSTALLED_KINDS]


def check_targets(report, base, scope, project=None):
    """Targets with some but not all of their manifest files under base: a partial or damaged install. A target
    counts as installed only by the paths no other target shares (several agents share ~/.agents/skills)."""
    by_target, users = {}, {}
    for row in manifest_rows(scope):
        by_target.setdefault(row[0], []).append(base / row[5])
        users.setdefault(row[5], set()).add(row[0])
    where = "globally" if scope == "global" else f"in {project}"
    installed = 0
    for target, paths in sorted(by_target.items()):
        own = [path for path in paths if users[str(path.relative_to(base))] == {target}]
        if not any(path.exists() for path in own):
            continue  # not installed, or nothing but shared paths: no way to tell, so no claim
        installed += 1
        missing = [path for path in paths if not path.exists()]
        if missing:
            report.missing.setdefault((scope, project), set()).add(target)
            report.fail(f"{target} installed {where} but {len(missing)} of {len(paths)} files are missing "
                        f"(first: {missing[0]})", installer_command(scope, project, [target]))
        else:
            report.ok(f"{target} installed {where}: {len(paths)} files")
    if not installed:
        report.warn(f"no installer target found {where}",
                    installer_command(scope, project, ["<target>"]) + " (only if you use agents beyond the plugin)")


def installer_command(scope, project, targets):
    where = "--global" if scope == "global" else f"--project {shlex.quote(str(project))}"
    if os.name == "nt":
        where = "-Global" if scope == "global" else f"-Project {project}"
        return f"./install.ps1 {where} -Target {','.join(targets)}"
    return f"./install.sh {where} --target {','.join(targets)}"


def check_ledger(report, path, label):
    sys.path.insert(0, str(ROOT / ".agents" / "skills" / "lessons-learned" / "scripts"))
    try:
        import lessons
    except Exception as error:  # a broken skill is itself a finding, not a crash
        report.fail(f"lessons.py cannot load: {error}", "reinstall the arsenal")
        return
    if not path.is_file():
        report.ok(f"{label} lessons ledger: none yet ({path})")
        return
    try:
        ledger = lessons.Ledger(path)
    except OSError as error:
        report.fail(f"{label} lessons ledger unreadable: {error}", f"check the permissions of {path}")
        return
    if ledger.undecodable or ledger.stray:
        problem = "is not UTF-8" if ledger.undecodable else f"has {len(ledger.stray)} unparsable lines"
        report.fail(f"{label} lessons ledger {path} {problem}",
                    f"python3 {shlex.quote(str(Path(lessons.__file__)))} --file {shlex.quote(str(path))} check")
    else:
        report.ok(f"{label} lessons ledger parses: {len(ledger.lessons)} lessons")


def check_mcp(report, home):
    try:
        config = read_json(home / ".claude.json") or {}
        settings = read_json(home / ".claude" / "settings.json") or {}
    except ValueError as error:
        report.warn(f"MCP configuration unreadable: {error}")
        return
    servers = {name.lower() for name in (config.get("mcpServers") or {})}
    for project in (config.get("projects") or {}).values():
        if isinstance(project, dict):
            servers |= {name.lower() for name in (project.get("mcpServers") or {})}
    enabled = settings.get("enabledPlugins") or {}
    for name, plugin in MCP_PLUGINS.items():
        if any(name in server for server in servers) or enabled.get(plugin) is True:
            report.ok(f"{name} MCP server configured")
        else:
            report.warn(f"{name} MCP server not configured (optional)",
                        f"./install.sh --global --target claude --{name} or /plugin install {plugin}")


def check_registry(report, home, project):
    """The lesson-guard registries as this hook and each installed plugin version reads them."""
    sys.path.insert(0, str(ROOT / ".agents" / "skills" / "lessons-learned" / "scripts"))
    try:
        import guard_registry
    except ImportError as error:
        report.warn(f"lesson-guard registry not checked: {error}", "reinstall from a complete checkout")
        return
    paths = guard_registry.registry_paths(project or Path.cwd(), home, project)  # found as the hook finds them
    if not paths:
        report.ok("no lesson-guard registry")
        return
    found = guard_registry.report(paths, guard_registry.default_cache(home), guard_registry.referenced_versions(home))
    problems = list(dict.fromkeys(f"{label}: {problem}" for label, items, _, _ in found for problem in items))
    effects = {effect for _, _, effect, counts in found if counts}  # an unreferenced cache only warns
    stale = {effect for _, _, effect, counts in found if not counts} & {"refuses", "fails-open"}
    repair = f"python3 {ROOT / '.agents/skills/lessons-learned/scripts/lessons.py'} guards; fix or add min_version"
    if effects & {"refuses", "fails-open"}:
        what = " and ".join(text for effect, text in (("refuses", "refuse every Bash command"),
                                                      ("fails-open", "run no lesson guard")) if effect in effects)
        report.fail(f"lesson-guard registry: an installed version would {what} ({'; '.join(problems)})", repair)
    elif stale:
        report.warn("lesson-guard registry: a cached version no install references would refuse every Bash command "
                    "or run no lesson guard; a session started before the last update may still run it: restart it "
                    f"({'; '.join(problems)})", repair)
    elif problems:
        report.warn(f"lesson-guard registry: {len(problems)} entr{'y' if len(problems) == 1 else 'ies'} skipped "
                    f"({'; '.join(problems)})", repair)
    else:
        report.ok(f"lesson-guard registry readable by this hook and {len(found) - 1} installed version(s)")


def diagnose(home, project):
    report = Report()
    check_python(report)
    try:
        expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        expected = ""
    check_hooks(report, ROOT, "this checkout's")
    check_plugin(report, home, expected)
    check_targets(report, home, "global")
    if project:
        check_targets(report, project, "project", project)
    lessons_global = Path(os.environ.get("LESSONS_GLOBAL_FILE") or home / ".agents" / "lessons.md")
    check_ledger(report, lessons_global, "global")
    check_ledger(report, (project or Path.cwd()) / ".agents" / "lessons.md", "project")
    check_registry(report, home, project)
    check_mcp(report, home)
    return report


def fix(report):
    """Re-run the installer for the targets with missing files only. Returns the worst exit code."""
    installer = os.environ.get("ARSENAL_DOCTOR_INSTALLER") or str(ROOT / ("install.ps1" if os.name == "nt" else "install.sh"))
    worst = 0
    for (scope, project), targets in sorted(report.missing.items(), key=str):
        where = ["--global"] if scope == "global" else ["--project", str(project)]
        command = ["bash", installer, *where, "--target", ",".join(sorted(targets))]
        if os.name == "nt":
            where = ["-Global"] if scope == "global" else ["-Project", str(project)]
            command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", installer, *where,
                       "-Target", ",".join(sorted(targets))]
        print(f"fix: {' '.join(shlex.quote(part) for part in command)}")
        try:
            worst = max(worst, subprocess.run(command, timeout=600).returncode)
        except (OSError, subprocess.SubprocessError) as error:
            print(f"fix failed: {error}", file=sys.stderr)
            worst = 1
    if not report.missing:
        print("fix: nothing the installer can repair")
    return worst


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check the arsenal installation and print repairs.")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args(argv)
    if args.project is not None and not args.project.is_dir():
        parser.error(f"--project {args.project} is not a directory")
    project = args.project.resolve() if args.project else None
    report = diagnose(Path.home(), project)
    print(report.render())
    if args.fix:
        if fix(report):
            return 1
        report = diagnose(Path.home(), project)  # judge the result, not the installer's exit code alone
        print("after fix:")
        print(report.render())
    return 1 if report.failed() else 0


if __name__ == "__main__":
    sys.exit(main())
