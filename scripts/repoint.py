#!/usr/bin/env python3
"""Make running Claude Code sessions use the newest installed arsenal plugin version, without a restart.

Usage (also `arsenal repoint` / `arsenal.ps1 repoint`):
  repoint.py [--dry-run] [--undo]
A session fixes CLAUDE_PLUGIN_ROOT at start to <cache>/<version> and runs every hook as a new process that reads its
files from that folder. So an older version folder that becomes a symlink to the newest version makes the session run
the new hook code from its next hook call. The cache is $ARSENAL_CACHE, else ~/.claude/plugins/cache/
senior-developer-arsenal/arsenal; installs are read from $ARSENAL_INSTALLED_PLUGINS, else
~/.claude/plugins/installed_plugins.json.
Target: the newest version an install references (any scope) that exists in the cache as a real folder; never a
version no install references. Each older real version folder is moved aside to .<version>.repointed-<UTC stamp>
(kept: --undo needs it; delete by hand when no session needs it), and a relative symlink to the target takes its
place. The link is created under a temporary name first, so the version path is missing only between two adjacent
rename calls (microseconds); a failure in either rolls the folder back. A version is skipped, never changed, when a
script its hooks.json runs, or a skill or agent it provides, is missing in the target: a running session keeps the
old hook event list (hook command-line arguments are not verified). Every run first recovers after a killed run:
a missing version is restored from its newest backup and stray temporary links are removed.
An existing link to an older version is re-pointed atomically. --undo restores the newest backup beside each linked
version. --dry-run prints the plan and changes nothing. On Windows creating a symlink needs Developer Mode or
administrator rights; without it the version is reported as failed and left unchanged.
Exit codes: 0 done or nothing to do, 1 some version skipped or failed, 2 usage error or no installed version.
Standard library only.
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doctor import PLUGIN, read_json, version_key  # noqa: E402

VERSION_DIR = re.compile(r"\d{1,6}\.\d{1,6}\.\d{1,6}", re.ASCII)
PLUGIN_ROOT_WORD = "CLAUDE_PLUGIN_ROOT"
PLUGIN_PATH = re.compile(r"\$(?:\{CLAUDE_PLUGIN_ROOT\}|CLAUDE_PLUGIN_ROOT(?![A-Za-z0-9_]))/([^\s\"'`;&|<>)]+)")
STRAY_NAME = re.compile(r"\.(\d{1,6}\.\d{1,6}\.\d{1,6})\.(?:link|repointed)-", re.ASCII)
LIMITS = (
    "limits: running sessions keep the skill and agent lists and the hook event list they loaded at start (a new "
    "skill is not listed until restart, though its files are readable); the next hook call runs the new code; tools "
    "a session already imported in process are not affected (hooks are separate processes); hook command-line "
    "arguments are not verified (only that each script an old hooks.json runs, and each skill and agent, exists in "
    "the newest version).",
)


def cache_dir(home):
    return Path(os.environ.get("ARSENAL_CACHE")
                or home / ".claude" / "plugins" / "cache" / "senior-developer-arsenal" / "arsenal")


def installed_file(home):
    return Path(os.environ.get("ARSENAL_INSTALLED_PLUGINS") or home / ".claude" / "plugins" / "installed_plugins.json")


def referenced_names(home):
    """Version folder names the installs reference. Raises ValueError when the file does not parse."""
    registry = read_json(installed_file(home)) or {}
    entries = (registry.get("plugins") or {}).get(PLUGIN) or []
    names = set()
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("installPath"), str):
            name = Path(entry["installPath"]).name
            if VERSION_DIR.fullmatch(name):
                names.add(name)
    return names


def hook_paths(root):
    """(paths under the plugin root that root's hooks.json commands use, problem): problem is None, or why they
    cannot be verified (hooks.json unreadable, or a command uses CLAUDE_PLUGIN_ROOT in a form not parsed)."""
    try:
        config = read_json(root / "hooks" / "hooks.json")
    except ValueError:
        config = None
    if config is None:
        return set(), f"cannot read {root.name}/hooks/hooks.json"
    found, stack = set(), [config]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, str) and PLUGIN_ROOT_WORD in item:
            paths = PLUGIN_PATH.findall(item)
            if not paths:
                return set(), "cannot verify its hooks: a command uses CLAUDE_PLUGIN_ROOT in a form this tool does not parse"
            found.update(paths)
    return found, None


def listed(root, key, default):
    """The paths plugin.json names under key (a string or a list), else default."""
    try:
        value = (read_json(root / ".claude-plugin" / "plugin.json") or {}).get(key, default)
    except (ValueError, AttributeError):
        value = default
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):  # null, a number or an object: not a path list, use the default
        return [default]
    return [item for item in value if isinstance(item, str)]


def components(root):
    """{"skill name", "agent name"} the plugin at root provides: skill folders and agent files."""
    found = set()
    for entry in listed(root, "skills", "./.agents/skills/"):
        folder = root / entry
        found.update(f"skill {p.name}" for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")) \
            if folder.is_dir() else ()
    for entry in listed(root, "agents", "./agents/"):
        path = root / entry
        files = path.glob("*.md") if path.is_dir() else [path] if path.suffix == ".md" and path.is_file() else []
        found.update(f"agent {p.stem}" for p in files)
    return found


def incompatibility(old_root, target):
    """Why a session started on old_root could break if it ran target's files, or None."""
    needed, problem = hook_paths(old_root)
    if problem:
        return problem
    missing = sorted(item for item in needed if not (target / item).exists())
    if missing:
        return f"its hooks run {', '.join(missing)}, missing in {target.name}"
    gone = sorted(components(old_root) - components(target))
    if gone:
        return f"its skills or agents missing in {target.name}: {', '.join(gone)}"
    return None


def backups(cache, version):
    """Backups of version beside it, oldest first (the stamp sorts)."""
    return sorted(path for path in cache.glob(f".{version}.repointed-*") if path.is_dir() and not path.is_symlink())


def make_link(cache, name, target_name, stamp):
    """A relative symlink to target_name under a temporary name; returns its path."""
    temp = cache / f".{name}.link-{stamp}"
    os.symlink(target_name, temp, target_is_directory=True)
    return temp


def forget(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def repoint_one(cache, version, target_name, stamp, dry_run):
    """(ok, line) for one older version."""
    path = cache / version
    if path.is_symlink():
        current = os.readlink(path)
        if path.resolve() == (cache / target_name).resolve():
            return True, f"{version}: already points to {target_name}"
        if not VERSION_DIR.fullmatch(Path(current).name) or not (cache / Path(current).name).is_dir():
            return False, f"{version}: skipped: symlink to {current}, not a cached version"
        old_root = (backups(cache, version) or [cache / Path(current).name])[-1]
    else:
        old_root = path
    reason = incompatibility(old_root, cache / target_name)
    if reason:
        return False, f"{version}: skipped: {reason}"
    if dry_run:
        return True, f"{version}: would repoint to {target_name}"
    try:
        link = make_link(cache, version, target_name, stamp)
    except OSError as error:
        return False, f"{version}: failed: cannot create a symlink ({error}); nothing changed"
    if path.is_symlink():
        try:
            os.replace(link, path)
        except OSError as error:
            forget(link)
            return False, f"{version}: failed: {error}; link unchanged"
        return True, f"{version}: repointed to {target_name} (was {current})"
    backup = cache / f".{version}.repointed-{stamp}"
    renamed = False
    try:
        os.rename(path, backup)  # the version path is missing from here until the replace below
        renamed = True
        os.replace(link, path)
    except BaseException as error:  # a kill signal in the gap must not leave the version missing
        forget(link)
        lost = None
        if renamed and not path.is_symlink():
            try:
                os.rename(backup, path)
            except OSError as restore_error:
                lost = restore_error
        if not isinstance(error, OSError):
            raise
        if lost:
            return False, (f"{version}: failed: {error}; ROLLBACK FAILED ({lost}): restore by hand with "
                           f"mv {backup} {path}")
        return False, f"{version}: failed: {error}; " + ("rolled back" if renamed else "folder unchanged")
    return True, f"{version}: repointed to {target_name} (backup {backup.name})"


def undo_one(cache, version, dry_run):
    """(ok, line) for one version path."""
    path = cache / version
    if not path.is_symlink():
        return True, ""
    found = backups(cache, version)
    if not found:
        return True, f"{version}: left: symlink without a backup"
    backup, current = found[-1], os.readlink(path)
    if dry_run:
        return True, f"{version}: would restore {backup.name}"
    forget(path)  # the version path is missing from here until the rename below
    try:
        os.rename(backup, path)
    except BaseException as error:
        lost = None
        try:
            os.symlink(current, path, target_is_directory=True)
        except OSError as restore_error:
            lost = restore_error
        if not isinstance(error, OSError):
            raise
        if lost:
            return False, (f"{version}: failed: {error}; ROLLBACK FAILED ({lost}): recreate with "
                           f"ln -s {current} {path}")
        return False, f"{version}: failed: {error}; link unchanged"
    return True, f"{version}: restored {backup.name}"


def recover(cache, dry_run):
    """[(ok, line)] after a kill between a rename and its replace: restore a missing version from its newest
    backup (the safe direction) and remove temporary links left beside a version that is present."""
    results = []
    for version in sorted({m.group(1) for p in cache.iterdir() if (m := STRAY_NAME.match(p.name))}, key=version_key):
        if not os.path.lexists(cache / version):
            found = backups(cache, version)
            if not found:
                results.append((False, f"{version}: missing and no backup beside it"))
                continue
            if dry_run:
                results.append((True, f"{version}: would recover from {found[-1].name}"))
            else:
                try:
                    os.rename(found[-1], cache / version)
                except OSError as error:
                    results.append((False, f"{version}: failed to recover from {found[-1].name}: {error}"))
                    continue
                results.append((True, f"{version}: recovered from {found[-1].name}"))
        for stray in sorted(cache.glob(f".{version}.link-*")):
            if stray.is_symlink():
                if not dry_run:
                    forget(stray)
                results.append((True, f"{version}: {'would remove' if dry_run else 'removed'} stray link {stray.name}"))
    return results


def run(home, dry_run=False, undo=False, out=print):
    """Exit code."""
    cache = cache_dir(home)
    try:
        names = referenced_names(home)
    except ValueError as error:
        out(f"error: {error}")
        return 2
    recovered = recover(cache, dry_run) if cache.is_dir() else []
    real = {path.name for path in cache.iterdir() if path.is_dir() and not path.is_symlink()} if cache.is_dir() else set()
    candidates = sorted(names & real, key=version_key)
    if not candidates:
        for _, line in recovered:
            out(line)
        out(f"error: no version referenced by {installed_file(home)} exists as a folder in {cache}")
        return 2
    target = candidates[-1]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    versions = sorted((path.name for path in cache.iterdir()
                       if VERSION_DIR.fullmatch(path.name) and path.name != target
                       and (undo or version_key(path.name) < version_key(target))), key=version_key)
    step = (lambda v: undo_one(cache, v, dry_run)) if undo else (lambda v: repoint_one(cache, v, target, stamp, dry_run))
    results = recovered + [step(v) for v in versions]
    lines = [line for _, line in results if line]
    out(f"cache: {cache}" if undo else f"target: {target}")
    for line in lines or ["nothing to do: no older cached version"]:
        out(line)
    for line in LIMITS:
        out(line)
    return 0 if all(ok for ok, _ in results) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Point older cached plugin versions at the newest installed one.")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    parser.add_argument("--undo", action="store_true", help="restore the backups beside linked versions")
    args = parser.parse_args(argv)
    return run(Path.home(), args.dry_run, args.undo)


if __name__ == "__main__":
    sys.exit(main())
