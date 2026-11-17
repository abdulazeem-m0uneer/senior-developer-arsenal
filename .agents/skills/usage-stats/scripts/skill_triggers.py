"""Trigger phrases of each arsenal skill, read from the `Triggers:` part of its SKILL.md description.

Imported by diagnose.py; not a command. Standard library only.
  triggers(skills_dir) -> {skill name: [phrase, ...]}   quoted phrases plus the /slash-command
  matching(text, table) -> {skill name: first phrase found}   case-insensitive, whole words only
"""
import re
from pathlib import Path

DESCRIPTION = re.compile(r"^description:\s*'((?:[^']|'')*)'\s*$", re.M)
TRIGGERS = re.compile(r"Triggers?:\s*(.*?)(?:\.\s+Not for\b|\.\s*$|$)", re.S)
QUOTED = re.compile(r'"([^"]{2,80})"')
SLASH = re.compile(r"(?<![\w/])/([a-z0-9]+(?:-[a-z0-9]+)*)")


def triggers(skills_dir):
    table = {}
    for skill_md in sorted(Path(skills_dir).glob("*/SKILL.md")):
        try:
            found = DESCRIPTION.search(skill_md.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        part = TRIGGERS.search(found.group(1).replace("''", "'")) if found else None
        if not part:
            continue
        phrases = QUOTED.findall(part.group(1)) + [f"/{name}" for name in SLASH.findall(part.group(1))]
        if phrases:
            table[skill_md.parent.name] = phrases
    return table


def pattern(phrase):
    words = r"\s+".join(re.escape(word) for word in phrase.split())
    start = "" if phrase.startswith("/") else r"(?<![\w-])"
    return re.compile(start + words + r"(?![\w-])", re.I)


def matching(text, table):
    found = {}
    for skill, phrases in table.items():
        for phrase in phrases:
            if pattern(phrase).search(text):
                found[skill] = phrase
                break
    return found
