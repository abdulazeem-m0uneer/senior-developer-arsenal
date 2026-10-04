#!/usr/bin/env python3
"""Parse every frontmatter block and generated config with strict parsers.

Requires PyYAML. Cursor `.mdc` rules are skipped: Cursor's format uses unquoted
globs such as `**/*.ts`, which is not valid YAML by design.
"""
import json
import sys
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    return text[4:text.index("\n---\n", 4)]


def main():
    checked = 0
    markdown = [*ROOT.glob("dist/**/*.md"), *ROOT.glob(".agents/skills/*/SKILL.md"), *ROOT.glob(".agents/rules/*.md")]
    for path in markdown:
        block = frontmatter(path)
        if block is not None and not isinstance(yaml.safe_load(block), dict):
            print(f"error: {path.relative_to(ROOT)}: frontmatter is not a mapping", file=sys.stderr)
            return 1
        checked += 1
    for path in ROOT.glob("dist/**/*.toml"):
        text = path.read_text(encoding="utf-8")
        # MCP snippets are table bodies; agent files are whole documents.
        tomllib.loads(text)
        checked += 1
    json_files = [*ROOT.glob("dist/**/*.json"), *ROOT.glob("plugins/**/*.json"),
                  *ROOT.glob(".claude-plugin/*.json"), *ROOT.glob(".agents/**/*.json")]
    for path in json_files:
        json.loads(path.read_text(encoding="utf-8"))
        checked += 1
    print(f"parsed {checked} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
