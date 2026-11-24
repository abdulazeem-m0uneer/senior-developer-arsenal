"""Check the lesson-guard registries against this hook and every installed hook version.

Imported by lessons.py (`guards`, and the session-start header) and by scripts/doctor.py; not a command.
Standard library only. Hooks before 1.10.0 refuse every Bash command while the registry holds an entry they cannot
read; from 1.10.0 a hook skips such an entry, and skips quietly an entry whose "min_version" is newer than itself.
min_version therefore protects only hooks from 1.10.0 on: an entry for a newer rule must still be checked against
any older version a session may run. Installed versions are the folders under $ARSENAL_CACHE (default
~/.claude/plugins/cache/senior-developer-arsenal/arsenal), where the Claude Code plugin runs from; each is asked with
its own guard_lessons.py, in a separate process.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECK_SECONDS = 10
VERSION_DIR = re.compile(r"\d{1,6}\.\d{1,6}\.\d{1,6}", re.ASCII)
# Runs inside one installed version, with its own read_registry: {"problems": [...], "effect": ...}. effect is
# "refuses" for a RegistryError (that version's hook refuses every Bash command), "fails-open" for any other fault
# (its hook swallows the error and runs no lesson guard), else "none".
PROBE = """
import json, sys
sys.path.insert(0, sys.argv[1])
problems, effect = [], "none"
try:
    import guard_lessons as g
    for path in sys.argv[2:]:
        try:
            found = g.read_registry(path)
            if isinstance(found, tuple):
                problems += found[1]
        except g.RegistryError as error:
            problems.append(f"{error} (this version refuses every Bash command while this is in the file)")
            effect = "refuses"
        except Exception as error:
            problems.append(f"{type(error).__name__}: {error} (this version runs no lesson guard while this is in "
                            "the file)")
            effect = "refuses" if effect == "refuses" else "fails-open"
except Exception as error:
    problems.append(f"could not load this version's guard: {type(error).__name__}: {error}")
print(json.dumps({"problems": problems, "effect": effect}))
"""


def hooks_dir():
    """The folder holding guard_lessons.py next to this skill: <plugin>/hooks or <install>/arsenal-hooks."""
    for candidate in (HERE.parents[3] / "hooks", HERE.parents[2] / "arsenal-hooks"):
        if (candidate / "guard_lessons.py").is_file():
            return candidate
    return None


def current_module():
    folder = hooks_dir()
    if folder is None:
        return None
    if str(folder) not in sys.path:
        sys.path.append(str(folder))  # appended: the skill's own modules stay first
    sys.dont_write_bytecode = True
    import guard_lessons
    return guard_lessons


def registry_paths(cwd, home=None, project=None):
    """The registries the hook reads in cwd (the global one under home, else ~; project, when given, is the search
    start instead of $CLAUDE_PROJECT_DIR and cwd); [] without the hook."""
    module = current_module()
    return module.registry_paths(str(cwd), str(home) if home else None, str(project) if project else None) \
        if module else []


def guarded_lessons(cwd):
    """Lesson ids the hook applies a registry guard for in cwd (enabled entries it can read; a rule it does not
    know or a min_version above it is skipped, as the hook skips it); empty when the hook is not installed."""
    module = current_module()
    if module is None:
        return set()
    return {entry["lesson"] for _name, entry, _match in module.rules(str(cwd))
            if isinstance(entry.get("lesson"), str) and entry["lesson"]}


def current_problems(cwd):
    """Problems this hook reports for the registries in cwd; [] when the hook is not installed beside the skill."""
    module = current_module()
    return module.registry_problems(str(cwd)) if module else []


def default_cache(home=None):
    return Path(os.environ.get("ARSENAL_CACHE")
                or Path(home or Path.home()) / ".claude/plugins/cache/senior-developer-arsenal/arsenal")


def links_to_sibling(path, cache):
    """True for a version folder that `arsenal repoint` made a symlink to another version: it runs that version's code."""
    return path.is_symlink() and path.resolve().parent == cache.resolve()


def installed_versions(cache=None):
    """[(version, hooks folder)] of the cached plugin versions that have guard_lessons.py, oldest first."""
    cache = Path(cache) if cache else default_cache()
    if not cache.is_dir():
        return []
    found = [(path.name, path / "hooks") for path in cache.iterdir()
             if VERSION_DIR.fullmatch(path.name) and (path / "hooks" / "guard_lessons.py").is_file()
             and not links_to_sibling(path, cache)]
    return sorted(found, key=lambda item: tuple(int(part) for part in item[0].split(".")))


def version_problems(hooks, paths):
    """(problems, effect) as one installed version reports them: effect is "none", "refuses" or "fails-open"; a
    version that cannot be asked is a problem with effect "none"."""
    try:
        done = subprocess.run([sys.executable, "-I", "-B", "-c", PROBE, str(hooks), *map(str, paths)],
                              capture_output=True, text=True, timeout=CHECK_SECONDS)
    except subprocess.TimeoutExpired:
        return [f"could not check: no answer within {CHECK_SECONDS}s"], "none"
    except OSError as error:
        return [f"could not check: {error}"], "none"
    try:
        result = json.loads(done.stdout)
        effect = result["effect"] if result["effect"] in ("refuses", "fails-open") else "none"
        return [str(problem) for problem in result["problems"]], effect
    except (ValueError, KeyError, TypeError):
        last = done.stderr.strip().splitlines()[-1] if done.stderr.strip() else f"exit {done.returncode}"
        return [f"could not check: {last}"], "none"


PLUGIN = "arsenal@senior-developer-arsenal"


def referenced_versions(home=None):
    """The versions Claude Code's installed_plugins.json points an install at ($ARSENAL_INSTALLED_PLUGINS, else
    <home>/.claude/plugins/installed_plugins.json); None when it cannot be read, so every cached version counts."""
    path = Path(os.environ.get("ARSENAL_INSTALLED_PLUGINS")
                or Path(home or Path.home()) / ".claude/plugins/installed_plugins.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data["plugins"].get(PLUGIN) or []
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    if not isinstance(entries, list):
        return None  # malformed: count every version rather than wave them through
    versions = set()
    for entry in entries:
        if isinstance(entry, dict):
            name = Path(str(entry.get("installPath") or "")).name or str(entry.get("version") or "")
            if VERSION_DIR.fullmatch(name):
                versions.add(name)
    return versions


def report(paths, cache=None, referenced=None):
    """[(label, problems, effect, counts)]: this hook first (it skips bad entries: effect "none"), then each cached
    version, oldest first. counts is False for a cached version no install references (referenced is the set from
    referenced_versions; None counts them all): a session started before an update may still run one, so it is
    reported, but it does not decide."""
    module = current_module()
    mine = [problem for path in paths for problem in module.read_registry(str(path))[1]] if module else []
    rows = [("this hook", mine, "none", True)]
    for version, hooks in installed_versions(cache):
        counts = referenced is None or version in referenced
        label = f"installed {version}" if counts else f"cached {version} (no install references it)"
        rows.append((label, *version_problems(hooks, paths), counts))
    return rows
