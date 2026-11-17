"""Subagent cost guard for hooks/guard.py pre: deny an arsenal subagent call that asks for a dearer model than it is
built for.

Usage: reason = guard_models.refusal(tool_input, root)   # "" when the call is allowed
An Agent or Task call with subagent_type "arsenal:<name>" and a model above the subagent's tier is refused:
  fast       (recommended_model "fast", generated model: haiku)    allows haiku
  balanced   (recommended_model "balanced", generated model: sonnet) allows haiku and sonnet
  pro, inherit                                                      no limit
Requested models rank haiku < sonnet < opus = fable; an unknown or absent model is allowed. The tier comes from
<root>/.agents/subagents/subagent-definitions.json, read at call time; when that file is missing or malformed,
from the `model:` frontmatter of <root>/agents/<name>.md; when neither says, the call is allowed (fails open).
Measured on one user's machine over 7 days: arsenal:node-specialist, built for sonnet, ran 390 times for 14.4 B
tokens, most of its turns on Opus because callers passed model opus or fable. Standard library only.
"""
import json
import os
import re

RANK = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 2}
CEILING = {"fast": "haiku", "balanced": "sonnet"}  # tiers without an entry have no limit
FRONTMATTER_TIER = {"haiku": "fast", "sonnet": "balanced"}
NAME = re.compile(r"^arsenal:([a-z0-9]+(?:-[a-z0-9]+)*)$")
MAX_BYTES = 512 * 1024


def tier_from_definitions(root, name):
    """The recommended_model of the named subagent; None when the file is missing, malformed or does not list it."""
    try:
        with open(os.path.join(root, ".agents", "subagents", "subagent-definitions.json"), "rb") as handle:
            data = json.loads(handle.read(MAX_BYTES).decode("utf-8"))
    except (OSError, ValueError):
        return None
    entries = data.get("subagents") if isinstance(data, dict) else None
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and entry.get("name") == name:
            tier = entry.get("recommended_model")
            return tier if isinstance(tier, str) else None
    return None


def tier_from_agent_file(root, name):
    """The tier the generated agents/<name>.md runs on, from its model frontmatter; None when it does not say."""
    try:
        with open(os.path.join(root, "agents", f"{name}.md"), encoding="utf-8") as handle:
            head = handle.read(4096)
    except (OSError, ValueError):
        return None
    match = re.search(r"^model:\s*[\"']?([\w.-]+)", head.split("\n---", 1)[0], re.M)
    return FRONTMATTER_TIER.get(match.group(1).lower()) if match else None


def refusal(tool_input, root):
    if not isinstance(tool_input, dict):
        return ""
    match = NAME.match(str(tool_input.get("subagent_type") or ""))
    requested = str(tool_input.get("model") or "").strip().lower()
    if not match or requested not in RANK:
        return ""
    name = match.group(1)
    tier = tier_from_definitions(root, name) or tier_from_agent_file(root, name)
    ceiling = CEILING.get(tier or "")
    if not ceiling or RANK[requested] <= RANK[ceiling]:
        return ""
    return (f"arsenal subagent cost guard: arsenal:{name} is built to run on {ceiling}, and model \"{requested}\" was "
            "requested. Call it again without the model parameter to use its default, or set "
            "ARSENAL_SUBAGENT_MODEL=any to allow overrides.")
