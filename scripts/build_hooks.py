#!/usr/bin/env python3
"""Hook configs for the agents that are not the Claude Code plugin, generated from hooks/hooks.json.

Used by scripts/build.py (not run on its own). hooks/hooks.json stays the one source of truth: the steps of
each ported event are read from it, written to dist/hooks/steps.json for hooks/agent_hook.py, and one
config per target (dist/hooks/<target>.json) names that adapter under the target's own event names and
file format. `{{ARSENAL_HOOKS}}` in a command is replaced by the installed hook directory when
scripts/hooks_merge.py merges the config. A target appears here only when its documentation defines the
config file, the event and the output contract (docs/TARGETS.md records which were run live). Not ported:
Claude Code through the installer (the plugin already carries the hooks, and a settings.json copy of a
plugin handler runs a second time), OpenCode (JavaScript plugin API, no command hooks, no stop event) and
Windsurf (its hook documentation now describes another product's file). Standard library only.
"""
import json
import re

HOOK_SOURCE = "hooks/hooks.json"
HOOK_DIR = "arsenal-hooks"
ADAPTER = "agent_hook.py"
PLACEHOLDER = "{{ARSENAL_HOOKS}}"
STEPS_PATH = "dist/hooks/steps.json"
HOOK_NAME = "senior-developer-arsenal"
PORTED_EVENTS = ("SessionStart", "Stop")
# snapshot.py show only re-injects what its PreCompact pair wrote, and compaction is not ported.
UNPORTED_SCRIPTS = (".agents/skills/handoff/scripts/snapshot.py",)
STEP_RE = re.compile(r'^python3 "\$\{CLAUDE_PLUGIN_ROOT\}/(?P<script>[^"]+)"(?P<args>(?: [\w-]+)*) \|\| python ')

# target -> (event names, global config, project config), destinations relative to $HOME or the project.
HOOK_TARGETS = {
    "codex": ({"SessionStart": "SessionStart", "Stop": "Stop"}, ".codex/hooks.json", ".codex/hooks.json"),
    "gemini": ({"SessionStart": "SessionStart", "Stop": "AfterAgent"},
               ".gemini/settings.json", ".gemini/settings.json"),
    "cursor": ({"SessionStart": "sessionStart", "Stop": "stop"}, ".cursor/hooks.json", ".cursor/hooks.json"),
    "copilot": ({"SessionStart": "sessionStart", "Stop": "agentStop"},
                ".copilot/hooks/arsenal.json", ".github/hooks/arsenal.json"),
    "antigravity": ({"SessionStart": "SessionStart", "Stop": "Stop"},
                    ".gemini/config/hooks.json", ".agents/hooks.json"),
}


def installed_path(script):
    """A hooks.json script path as the adapter sees it: hook scripts beside it, skills in ../skills."""
    if script.startswith("hooks/"):
        return script[len("hooks/"):]
    if script.startswith(".agents/skills/"):
        return "../skills/" + script[len(".agents/skills/"):]
    raise ValueError(f"{HOOK_SOURCE}: '{script}' is outside hooks/ and .agents/skills/, so it is not installed")


def load_steps(root):
    """{event: [{script, args, timeout}]} for the ported events, in hooks.json order."""
    hooks = json.loads((root / HOOK_SOURCE).read_text(encoding="utf-8"))["hooks"]
    steps = {}
    for event in PORTED_EVENTS:
        handlers = [handler for group in hooks[event] for handler in group["hooks"]]
        steps[event] = []
        for handler in handlers:
            match = STEP_RE.match(handler["command"])
            if not match:
                raise ValueError(f"{HOOK_SOURCE}: {event} command is not in the python3-or-python form: "
                                 f"{handler['command']}")
            if match["script"] not in UNPORTED_SCRIPTS:
                steps[event].append({"script": installed_path(match["script"]), "args": match["args"].split(),
                                     "timeout": handler["timeout"]})
        if not steps[event]:
            raise ValueError(f"{HOOK_SOURCE}: no portable step for {event}")
    return steps


def command(target, event, launcher="python3"):
    return f'{launcher} "{PLACEHOLDER}/{ADAPTER}" {target} {event}'


def render_config(target, steps):
    """The JSON text hooks_merge.py merges into the target's hook config."""
    names = HOOK_TARGETS[target][0]
    events = {}
    for event, name in names.items():
        seconds = sum(step["timeout"] for step in steps[event])
        shell = f"{command(target, event)} || {command(target, event, 'python')}"
        if target == "codex":
            handler = {"hooks": [{"type": "command", "command": shell, "timeout": seconds}]}
        elif target == "gemini":  # timeout in milliseconds; the name is what /hooks disable takes
            handler = {"hooks": [{"name": f"arsenal-{event}", "type": "command", "command": shell,
                                  "timeout": seconds * 1000}]}
        elif target == "cursor":
            handler = {"command": shell, "timeout": seconds}
        elif target == "copilot":
            handler = {"type": "command", "bash": shell, "powershell": command(target, event, "python"),
                       "timeoutSec": seconds}
        else:
            handler = {"type": "command", "command": shell, "timeout": seconds}
        events[name] = [handler]
    if target == "antigravity":
        config = {HOOK_NAME: events}
    elif target in ("cursor", "copilot"):
        config = {"version": 1, "hooks": events}
    else:
        config = {"hooks": events}
    return json.dumps(config, indent=2) + "\n"


def outputs(steps):
    """{repo-relative path: text} of the generated hook files."""
    out = {STEPS_PATH: json.dumps(steps, indent=2) + "\n"}
    for target in HOOK_TARGETS:
        out[f"dist/hooks/{target}.json"] = render_config(target, steps)
    return out


def hook_dir(target, scope):
    """Installed hook directory: always the sibling of the target's skills directory."""
    return f".gemini/config/{HOOK_DIR}" if (target, scope) == ("antigravity", "global") else f".agents/{HOOK_DIR}"


def manifest_rows(root, target, scope):
    """(kind, name, source, destination, extra) rows: the scripts as files, then the config to merge."""
    if target not in HOOK_TARGETS:
        return []
    directory = hook_dir(target, scope)
    names = sorted(path.name for path in (root / "hooks").glob("*.py")) + ["core.md"]
    rows = [("file", name, f"hooks/{name}", f"{directory}/{name}", "-") for name in names]
    rows.append(("file", "steps.json", STEPS_PATH, f"{directory}/steps.json", "-"))
    _, global_config, project_config = HOOK_TARGETS[target]
    rows.append(("hooks", "hooks", f"dist/hooks/{target}.json",
                 global_config if scope == "global" else project_config, directory))
    return rows
