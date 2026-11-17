#!/usr/bin/env python3
"""Scan AI-agent configuration (hooks, MCP servers, permissions, settings) for ways it can be turned against you.

Usage:
  python3 agent_config_scan.py [--user] [--json] [ROOT]   # ROOT: the project directory (default: current)
Prints `<severity> <rule> <file>:<line> <where>` per finding (or JSON). A secret is named by its key path,
never by its value. Exit codes: 1 when any finding is high, 0 otherwise, 2 usage error (ROOT missing).

Files: .claude/settings.json and settings.local.json, .mcp.json, hooks.json files (up to three directories deep),
.cursor/mcp.json and hooks.json, .codex/config.toml and hooks.json, .gemini/settings.json, .vscode/mcp.json,
.agents/hooks.json. --user adds ~/.claude/settings.json, ~/.claude.json, ~/.codex/config.toml,
~/.gemini/settings.json and ~/.cursor/mcp.json.

Rules:
  high    remote-exec      a command that pipes a download into a shell (curl|sh, wget -O- | bash, iex (iwr ...))
  high    secret           a plaintext credential (the repo's one detector: lessons-learned ledger_store.find_secret)
  high    bypass-default   permissions.defaultMode bypassPermissions; Codex sandbox_mode danger-full-access
  medium  broad-allow      an allow rule for every command or for a shell, network or interpreter wildcard
  medium  unpinned-mcp     an MCP server started by npx -y / uvx with no pinned version (or @latest)
  medium  insecure-mcp     an MCP server URL over http:// to a host other than localhost
  medium  temp-path-hook   a hook command that runs or writes in a world-writable temp path
  medium  no-approval      Codex approval_policy never
  low     all-project-mcp  enableAllProjectMcpServers: true (every server a repository ships starts unasked)
  low     unparseable      a config file that is not valid JSON or TOML
Standard library only (tomllib needs Python 3.11).
"""
import argparse
import json
import os
import re
import sys
from collections import namedtuple
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python < 3.11: TOML files are reported as unparseable
    tomllib = None

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lessons-learned" / "scripts"))
try:
    from ledger_store import find_secret
except Exception:  # noqa: BLE001 - the secret rule is skipped, never the scan
    find_secret = None

Finding = namedtuple("Finding", "severity rule path line where")

PROJECT_FILES = (".claude/settings.json", ".claude/settings.local.json", ".mcp.json", ".cursor/mcp.json",
                 ".cursor/hooks.json", ".codex/config.toml", ".codex/hooks.json", ".gemini/settings.json",
                 ".vscode/mcp.json", ".agents/hooks.json")
USER_FILES = (".claude/settings.json", ".claude.json", ".codex/config.toml", ".gemini/settings.json",
              ".cursor/mcp.json")
SKIP_DIRS = frozenset("node_modules .git dist build vendor .venv venv target".split())
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

REMOTE_EXEC = re.compile(
    r"\b(?:curl|wget|fetch)\b[^|;&\n]*\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b"
    r"|\b(?:ba|z)?sh\s+<\(\s*(?:curl|wget)\b"
    r"|\b(?:ba|z)?sh\s+-c\s+[\"']?\$\(\s*(?:curl|wget)\b"
    r"|\biex\b\s*\(?\s*(?:\(\s*)?(?:iwr|irm|Invoke-WebRequest|Invoke-RestMethod|New-Object\s+Net\.WebClient)", re.I)
BROAD_TOOLS = "curl|wget|sh|bash|zsh|sudo|rm|python|python3|node|ssh|scp|nc|eval|pwsh|powershell"
BROAD_ALLOW = re.compile(rf"^(?:\*|Bash|Bash\(\s*\*?\s*(?::\s*\*)?\s*\)|Bash\(\s*(?:{BROAD_TOOLS})\s*(?::\s*\*|\s+\*)\s*\))$")
TEMP_PATH = re.compile(r"(?:^|[\s;&|'\"=(])(?:/tmp/|/var/tmp/|/dev/shm/|\$\{?TMPDIR\}?|%TEMP%|%TMP%)")
PINNED = re.compile(r"^(?:@[\w.-]+/)?[\w.-]+(?:@(?!latest\b)[\w.^~<>=*-]*\d[\w.^~-]*|==[\w.]+)$")
IDENTIFIER_KEY = re.compile(r"(?:^|[._-])(?:id|uuid|guid)$|[a-z0-9](?:Id|ID|Uuid|UUID)$|^(?:uuid|guid)$", re.I)
LOCAL_HOST = re.compile(r"^http://(?:localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(?::\d+)?(?:/|$)", re.I)


def config_files(root, user):
    """(display name, path) for every config file that exists."""
    found = []
    for name in PROJECT_FILES:
        found.append((name, root / name))
    for directory, dirs, names in os.walk(root):
        rel = Path(directory).relative_to(root)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS] if len(rel.parts) < 3 else []
        if "hooks.json" in names:
            name = (rel / "hooks.json").as_posix()
            if name not in PROJECT_FILES:
                found.append((name, Path(directory) / "hooks.json"))
    if user:
        home = Path(os.path.expanduser("~"))
        found += [(f"~/{name}", home / name) for name in USER_FILES]
    return [(name, path) for name, path in found if path.is_file()]


def load(path):
    """(data, text) or (None, text) when the file does not parse."""
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        if path.suffix == ".toml":
            return (tomllib.loads(text) if tomllib else None), text
        return json.loads(text), text
    except (ValueError, TypeError):
        return None, text


def walk(value, path=()):
    """(key path, value) for every scalar, list items included."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk(item, path + (str(key),))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, path + (str(index),))
    else:
        yield path, value


def line_of(text, value):
    """The first line holding the value as written in the file (JSON-escaped first); 1 when it is not found."""
    for needle in (json.dumps(value)[1:-1] if isinstance(value, str) else json.dumps(value), str(value)):
        index = text.find(needle) if needle else -1
        if index >= 0:
            return text.count("\n", 0, index) + 1
    return 1


def under(path, *names):
    return any(part in names for part in path)


def server_entries(data):
    """(name, server dict) for every MCP server, whatever the agent calls the section."""
    for section in ("mcpServers", "mcp_servers", "servers"):
        servers = data.get(section) if isinstance(data, dict) else None
        if isinstance(servers, dict):
            for name, server in servers.items():
                if isinstance(server, dict):
                    yield section, str(name), server
    projects = data.get("projects") if isinstance(data, dict) else None  # ~/.claude.json keeps per-project servers
    if isinstance(projects, dict):
        for project in projects.values():
            yield from server_entries(project) if isinstance(project, dict) else ()


def mcp_findings(name, text, data):
    found = []
    for section, server_name, server in server_entries(data):
        where = f"{section}.{server_name}"
        command = str(server.get("command", ""))
        args = [str(arg) for arg in server.get("args", []) if isinstance(arg, (str, int, float))]
        launcher = Path(command).name.lower()
        if launcher in ("npx", "npx.cmd", "uvx", "pnpx", "bunx") or (launcher in ("pnpm", "npm") and args[:1] == ["dlx"]):
            packages = [arg for arg in args if not arg.startswith("-") and arg != "dlx"]
            if packages and not PINNED.match(packages[0]):
                found.append(Finding("medium", "unpinned-mcp", name, line_of(text, packages[0]), where))
        url = str(server.get("url", server.get("serverUrl", "")))
        if url.lower().startswith("http://") and not LOCAL_HOST.match(url):
            found.append(Finding("medium", "insecure-mcp", name, line_of(text, url), where))
    return found


def setting_findings(name, text, data):
    found = []
    if not isinstance(data, dict):
        return found
    permissions = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
    if permissions.get("defaultMode") == "bypassPermissions" or data.get("defaultMode") == "bypassPermissions":
        found.append(Finding("high", "bypass-default", name, line_of(text, "bypassPermissions"),
                             "permissions.defaultMode"))
    for rule in permissions.get("allow", []) if isinstance(permissions.get("allow"), list) else []:
        if isinstance(rule, str) and BROAD_ALLOW.match(rule.strip()):
            found.append(Finding("medium", "broad-allow", name, line_of(text, rule), f"permissions.allow {rule}"))
    if data.get("sandbox_mode") == "danger-full-access":
        found.append(Finding("high", "bypass-default", name, line_of(text, "danger-full-access"), "sandbox_mode"))
    if data.get("approval_policy") == "never":
        found.append(Finding("medium", "no-approval", name, line_of(text, "never"), "approval_policy"))
    if data.get("enableAllProjectMcpServers") is True:
        found.append(Finding("low", "all-project-mcp", name, line_of(text, "enableAllProjectMcpServers"),
                             "enableAllProjectMcpServers"))
    return found


def value_findings(name, text, data):
    found = []
    for path, value in walk(data):
        if not isinstance(value, str):
            continue
        where = ".".join(path)
        if REMOTE_EXEC.search(value):
            found.append(Finding("high", "remote-exec", name, line_of(text, value), where))
        if under(path, "hooks", "statusLine") and path[-1] == "command" and TEMP_PATH.search(value):
            found.append(Finding("medium", "temp-path-hook", name, line_of(text, value), where))
        if find_secret and path[-1:] != ("command",) and is_secret(path[-1] if path else "", value):
            found.append(Finding("high", "secret", name, line_of(text, value), where))
    return found


def is_secret(key, value):
    """A credential by the repo's detector; an identifier (machineID, userId, uuid) is random but not secret."""
    reason = find_secret(f"{key}: {value}")
    return bool(reason) and not (reason.startswith("a long random string") and IDENTIFIER_KEY.search(key))


def scan(root, user=False):
    found = []
    for name, path in config_files(root, user):
        try:
            data, text = load(path)
        except OSError:
            continue
        if data is None:
            found.append(Finding("low", "unparseable", name, 1, "not valid JSON or TOML"))
            continue
        found += setting_findings(name, text, data) + mcp_findings(name, text, data) + value_findings(name, text, data)
    return sorted(set(found), key=lambda f: (SEVERITY_ORDER[f.severity], f.path, f.line, f.rule))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scan agent configuration for risky settings.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--user", action="store_true", help="also scan the user-level configs in the home directory")
    parser.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    root = Path(args.root)
    if not root.is_dir():
        print(f"agent_config_scan: no such directory: {args.root}", file=sys.stderr)
        return 2
    if find_secret is None:
        print("agent_config_scan: lessons-learned/scripts/ledger_store.py not found: the secret rule is skipped",
              file=sys.stderr)
    found = scan(root.resolve(), args.user)
    if args.json:
        print(json.dumps([item._asdict() for item in found], indent=2))
    else:
        for item in found:
            print(f"{item.severity} {item.rule} {item.path}:{item.line} {item.where}")
    return 1 if any(item.severity == "high" for item in found) else 0


if __name__ == "__main__":
    sys.exit(main())
