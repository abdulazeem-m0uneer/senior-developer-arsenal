#!/usr/bin/env python3
"""Generate lite/, a text-only edition of the arsenal for the plugin directory.

The plugin directory accepts hooks, scripts and some manifest and frontmatter fields only from Verified
organizations. lite/ carries the skills and subagents as Markdown alone, so it can be listed without them.
The full plugin at the repository root is not changed.

Usage:
  python3 scripts/build_lite.py           # write lite/
  python3 scripts/build_lite.py --check   # exit 1 if lite/ is stale
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".agents" / "skills"
OUT = ROOT / "lite"
NAME = "arsenal-lite"
REPO_URL = "https://github.com/abdulazeem-m0uneer/senior-developer-arsenal"

# Skills whose procedure is built around their bundled scripts or hooks; without them the skill does not work.
EXCLUDED_SKILLS = {
    "agent-memory", "autonomous-run", "ci-wait", "lessons-learned", "multi-session-delivery",
    "quality-gate", "repo-scan", "shared-infra-changes", "ship", "usage-stats",
}
# Subagent frontmatter keys the directory accepts from any organization.
AGENT_KEYS = ("name", "description", "model", "tools", "disallowedTools")
TEXT_SUFFIXES = {".md"}
ICON = ROOT / "assets" / "icon.png"  # square 1024 px PNG; the directory takes it as the listing icon
ICON_PATH = ".claude-plugin/icon.png"

SCRIPT_NOTE = (
    "> **Lite edition:** steps that run a bundled script (a `scripts/` or `templates/` path) need the full "
    f"arsenal ({REPO_URL}). Here, do that step by hand or skip it and say so.\n\n"
)


def frontmatter_end(text):
    """Index just past the closing `---` line of a leading frontmatter block."""
    match = re.match(r"---\n.*?\n---\n", text, re.S)
    if not match:
        raise ValueError("missing frontmatter")
    return match.end()


def needs_script_note(skill_dir):
    return (skill_dir / "scripts").is_dir() or (skill_dir / "templates").is_dir() or re.search(
        r"(scripts|templates)/[\w.-]+", (skill_dir / "SKILL.md").read_text(encoding="utf-8")) is not None


def skill_files(skill_dir):
    """SKILL.md and Markdown references only; never a script, template or file starting with #!."""
    out = {}
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    if needs_script_note(skill_dir):
        end = frontmatter_end(text)
        text = text[:end] + "\n" + SCRIPT_NOTE + text[end:].lstrip("\n")
    out[f"skills/{skill_dir.name}/SKILL.md"] = text
    references = skill_dir / "references"
    if references.is_dir():
        for path in sorted(references.rglob("*")):
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                body = path.read_text(encoding="utf-8")
                if not body.startswith("#!"):
                    out[f"skills/{skill_dir.name}/{path.relative_to(skill_dir).as_posix()}"] = body
    return out


def lite_agent(text):
    """The subagent with only the frontmatter keys the directory accepts."""
    end = frontmatter_end(text)
    kept = [line for line in text[4:end - 4].splitlines() if line.split(":", 1)[0] in AGENT_KEYS]
    return "---\n" + "\n".join(kept) + "\n---\n" + text[end:]


def readme(skills):
    listed = "\n".join(f"- `{name}`" for name in skills)
    return f"""# Senior Developer Arsenal (Lite)

Senior engineering skills and subagents for AI coding agents: investigation, code review, testing, security, \
databases, APIs, frontend, mobile, DevOps and more. Each skill is a step-by-step runbook with a verification \
protocol, so the agent proves its work instead of claiming it.

This is the text-only edition for the plugin directory. It has no hooks and no scripts. The full arsenal adds \
guards that block risky commands and unproven "done" claims, a lessons ledger that turns repeated mistakes into \
rules, and the ship, CI and multi-session skills. Install the full edition from {REPO_URL}.

## Skills ({len(skills)})

{listed}

## Subagents

Read-only specialists for review, security, testing, QA, databases, DevOps and each stack, in `agents/`.

## Privacy

This edition stores nothing and sends nothing. See {REPO_URL}/blob/master/PRIVACY.md for the full edition.

## License

MIT. See LICENSE.
"""


def generate():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    skills = sorted(path.name for path in SKILLS.iterdir()
                    if (path / "SKILL.md").is_file() and path.name not in EXCLUDED_SKILLS)
    out = {}
    for name in skills:
        out.update(skill_files(SKILLS / name))
    for path in sorted((ROOT / "agents").glob("*.md")):
        out[f"agents/{path.name}"] = lite_agent(path.read_text(encoding="utf-8"))
    out[".claude-plugin/plugin.json"] = json.dumps({
        "name": NAME, "version": version,
        "description": "Senior engineering skills and subagents (text-only edition): review, testing, "
                       "security, databases, APIs, frontend, mobile and DevOps runbooks.",
        "author": {"name": "Abdulazeem Mohammed"}, "license": "MIT",
        "homepage": REPO_URL, "repository": REPO_URL,
        "keywords": ["senior-engineering", "code-review", "testing", "security", "devops", "skills"],
        "icon": f"./{ICON_PATH}",
    }, indent=2) + "\n"
    out["README.md"] = readme(skills)
    out["LICENSE"] = (ROOT / "LICENSE").read_text(encoding="utf-8")
    out[ICON_PATH] = ICON.read_bytes()
    return out


def as_bytes(content):
    return content if isinstance(content, bytes) else content.encode("utf-8")


def stale(expected):
    existing = {p.relative_to(OUT).as_posix() for p in OUT.rglob("*") if p.is_file()} if OUT.exists() else set()
    changed = [rel for rel, content in expected.items()
               if not (OUT / rel).is_file() or (OUT / rel).read_bytes() != as_bytes(content)]
    return sorted((existing - set(expected)) | set(changed))


def write(expected):
    if OUT.exists():
        shutil.rmtree(OUT)
    for rel, content in expected.items():
        path = OUT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(as_bytes(content))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if lite/ is stale")
    args = parser.parse_args(argv)
    expected = generate()
    if args.check:
        paths = stale(expected)
        if paths:
            print("stale lite/ files (run python3 scripts/build_lite.py):", *paths, sep="\n  ", file=sys.stderr)
            return 1
        return 0
    write(expected)
    return 0


if __name__ == "__main__":
    sys.exit(main())
