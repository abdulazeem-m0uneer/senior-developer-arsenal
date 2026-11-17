#!/usr/bin/env python3
"""Name the arsenal skills that match a prompt, so the model invokes them first (Claude Code plugin).

Usage: skill_router.py   # UserPromptSubmit hook; hook input is JSON on stdin
Prints at most one line of additionalContext naming at most two skills, for example
  arsenal: matching skills for this request: arsenal:investigate, arsenal:test-every-change (invoke ...)
and nothing at all when no skill scores at or above THRESHOLD, for a slash command, for a prompt shorter than
MIN_WORDS words, when the suggestion equals the previous one of the same session, or with ARSENAL_ROUTER=off.

Scoring (case-insensitive, word-bounded, a trailing plural allowed):
  a trigger phrase from a skill's description ("Triggers: ...")   1 + its word count; one word: 3
  one bare word of a stack skill (*-expert: "React", "Python")   2, below THRESHOLD: naming a stack is not a task
  the skill's own name ("dead code", "code-review")              3
  a synonym rule of the core skills (SYNONYMS)                    4
  a change request (CHANGE_VERB, not a question, not docs-only)  3 for test-every-change
A "Not for <topic> (use <skill>)" clause whose topic words all appear in the prompt zeroes the skill that owns the
clause when that skill scored, and then adds 1 to the named skill if it scored too. A question (a question word
first, or a final "?") gets no change-request score: asking how something works is not a change.

Cost: the parsed trigger table is cached in the OS temp dir (beside the handoff snapshot when HANDOFF_SNAPSHOT is
set), keyed by the path, mtime and size of every SKILL.md, so a prompt costs one stat per skill and one small read.
Never blocks and never fails the session: any error prints nothing and exits 0. Standard library only.
"""
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Plugin and repository: <root>/hooks beside <root>/.agents/skills. Installer: <dir>/arsenal-hooks beside <dir>/skills.
SKILLS = next((path for path in (ROOT / ".agents" / "skills", ROOT / "skills") if path.is_dir()), ROOT / "skills")
PREFIX = "arsenal:"
THRESHOLD = 3
MAX_SKILLS = 2
MAX_CHARS = 160
MIN_WORDS = 4
SCAN_CHARS = 4000  # a pasted log is read at its head only
CACHE_VERSION = 2
CORE = ("investigate", "test-every-change", "refactor-legacy", "code-review", "definition-of-done")
DESCRIPTION = re.compile(r"^description:\s*(['\"])(.*)\1\s*$", re.M)
TRIGGERS = re.compile(r"Triggers?(?: on)?:(.*?)(?:\.\s*Not for\b|$)", re.S)
NOT_FOR = re.compile(r"\bNot for (.*)$", re.S)
NOT_FOR_ITEM = re.compile(r"(.+?)\s*\(use ([\w-]+)(?: or [\w-]+)?\)")
QUOTED_PHRASE = re.compile(r"\"([^\"]+)\"")
WORD = re.compile(r"[a-z0-9][a-z0-9+#.'-]*")
STOPWORDS = frozenset("a an the of or and to for in on with alone one its own your any that this".split())
QUESTION_WORDS = frozenset("what why how when where who which whose is are was were can could does do did should "
                           "would will".split())
CHANGE_VERB = re.compile(r"\b(?:fix|implement|add|change|update|refactor|rename|remove|delete|build|modify|migrate"
                         r"|patch|rewrite|extend|support|wire|port|replace)\b")
DOCS_ONLY = re.compile(r"\b(?:readme|docs?|documentation|changelog|release notes|runbook|comment|typo)\b")
SYNONYMS = {
    "investigate": re.compile(r"\b(?:bugs?|broken|crash(?:es|ed|ing)?|errors?|exceptions?|fail(?:s|ing|ed|ure)?"
                              r"|regressions?|not working|doesn'?t work|stack ?trace|root cause|flaky)\b"),
    "code-review": re.compile(r"\breview(?:ing)?\s+(?:(?:this|the|my|our|his|her|their)\s+)?"
                              r"(?:code|pr|pull request|diff|changes?|commits?|branch|patch)\b|\bcode review\b"
                              r"|\breview\b.*\bpr\s*#?\d+|\bpr\s*#?\d+\b.*\breview\b"),
    "refactor-legacy": re.compile(r"\brefactor\w*\b.*\b(?:untested|legacy|no tests|without tests)\b"
                                  r"|\b(?:untested|legacy)\b.*\brefactor\w*\b"),
    "definition-of-done": re.compile(r"\b(?:is (?:it|this|that) (?:done|finished|complete)|are we done|done yet"
                                     r"|ready to (?:merge|ship|release)|can (?:we|i) (?:merge|ship))\b"),
}


def hook_input():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def state_dir():
    override = os.environ.get("HANDOFF_SNAPSHOT")
    return Path(override).parent if override else Path(tempfile.gettempdir())


def phrase_pattern(phrase):
    """Word-bounded, case-insensitive, an optional plural; works for C#, .NET and Node.js too."""
    words = [re.escape(word) for word in phrase.lower().split()]
    if not words:
        return None
    return r"(?<![\w.#-])" + r"[\s-]+".join(words) + r"(?:e?s)?(?![\w#-])"


def topic_words(topic):
    return [word for word in WORD.findall(topic.lower()) if len(word) >= 3 and word not in STOPWORDS]


def parse_skill(name, text):
    """{"triggers": [[pattern, score, probe]], "not_for": [[[words], target]]} from one SKILL.md.

    probe is the phrase's first word: a plain substring test that skips compiling a pattern that cannot match."""
    match = DESCRIPTION.search(text)
    description = match.group(2).replace("''", "'") if match else ""
    triggers = []
    found = TRIGGERS.search(description)
    for phrase in QUOTED_PHRASE.findall(found.group(1) if found else ""):
        pattern = phrase_pattern(phrase)
        if pattern:
            words = len(phrase.split())
            triggers.append([pattern, 1 + words if words > 1 else 2 if name.endswith("-expert") else 3,
                             phrase.lower().split()[0]])
    triggers.append([phrase_pattern(name.replace("-", " ")), 3, name.split("-")[0]])
    not_for = []
    clause = NOT_FOR.search(description)
    for topic, target in NOT_FOR_ITEM.findall(clause.group(1) if clause else ""):
        for part in re.split(r",\s*|\s+or\s+", topic):
            words = topic_words(part)
            if words and target != name:
                not_for.append([words, target])
    return {"triggers": triggers, "not_for": not_for}


def skill_files():
    try:
        return sorted(path for path in SKILLS.glob("*/SKILL.md") if path.is_file())
    except OSError:
        return []


def cache_key(files):
    digest = hashlib.sha256(f"{CACHE_VERSION}|{SKILLS}".encode())
    for path in files:
        stat = path.stat()
        digest.update(f"|{path}|{stat.st_mtime_ns}|{stat.st_size}".encode())
    return digest.hexdigest()


def load_table():
    """{skill: parsed}; read from the cache when every SKILL.md is unchanged, else parsed and cached again."""
    files = skill_files()
    if not files:
        return {}
    key = cache_key(files)
    cache = state_dir() / f"arsenal-router-{hashlib.sha256(str(SKILLS).encode()).hexdigest()[:12]}.json"
    try:
        stored = json.loads(cache.read_text(encoding="utf-8"))
        if stored.get("key") == key and isinstance(stored.get("skills"), dict):
            return stored["skills"]
    except (OSError, ValueError, AttributeError):
        pass
    table = {path.parent.name: parse_skill(path.parent.name, path.read_text(encoding="utf-8", errors="replace"))
             for path in files}
    try:  # mkstemp: a fresh name opened exclusively, so a planted link in a shared temp dir is never followed
        handle, temporary = tempfile.mkstemp(prefix=cache.name + ".", dir=cache.parent)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"key": key, "skills": table}, stream)
        os.replace(temporary, cache)  # atomic: a parallel prompt reads the old or the new table, never half
    except OSError:
        pass  # the cache is an optimisation; the table is still right
    return table


def is_question(text):
    words = WORD.findall(text)
    return text.rstrip().endswith("?") or (bool(words) and words[0] in QUESTION_WORDS)


def score(prompt, table):
    """[(skill, score)] for the skills at or above THRESHOLD, best first, at most MAX_SKILLS."""
    text = " ".join(prompt[:SCAN_CHARS].lower().split())
    scores = dict.fromkeys(table, 0)
    for name, skill in table.items():
        for pattern, points, probe in skill["triggers"]:
            if probe in text and re.search(pattern, text):
                scores[name] += points
    for name, pattern in SYNONYMS.items():
        if name in scores and pattern.search(text):
            scores[name] += 4
    if "test-every-change" in scores and not is_question(text) and CHANGE_VERB.search(text) \
            and not DOCS_ONLY.search(text):
        scores["test-every-change"] += 3
    words = set(WORD.findall(text)) | {word.rstrip("s") for word in WORD.findall(text)}
    zeroed, helped = set(), set()
    for name, skill in table.items():
        if not scores[name]:
            continue  # a clause only decides between skills that both matched something
        for topic, target in skill["not_for"]:
            if target in scores and all(word in words or word.rstrip("s") in words for word in topic):
                zeroed.add(name)
                helped.add(target)
    for name in zeroed:
        scores[name] = 0
    for name in helped - zeroed:
        if scores[name]:
            scores[name] += 1
    ranked = sorted(((name, points) for name, points in scores.items() if points >= THRESHOLD),
                    key=lambda item: (-item[1], CORE.index(item[0]) if item[0] in CORE else len(CORE), item[0]))
    return ranked[:MAX_SKILLS]


def suggestion(prompt, table):
    """The one context line for the prompt, or "" when nothing should be said."""
    if not isinstance(prompt, str):
        return ""
    stripped = prompt.strip()
    if not stripped or stripped.startswith("/") or len(stripped.split()) < MIN_WORDS:
        return ""
    ranked = score(stripped, table)
    if not ranked:
        return ""
    names = ", ".join(PREFIX + name for name, _ in ranked)
    line = f"arsenal: matching skills for this request: {names} (invoke with the Skill tool first)."
    return line if len(line) <= MAX_CHARS else f"arsenal: matching skills: {names}."[:MAX_CHARS]


def repeated(data, line):
    """True when this session's previous suggestion was the same line; records the line either way."""
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id", "")))
    if not session:
        return False
    path = state_dir() / f"arsenal-router-{session}.last"
    try:
        same = path.read_text(encoding="utf-8") == line
    except OSError:
        same = False
    try:
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            os.write(handle, line.encode("utf-8"))
        finally:
            os.close(handle)
    except OSError:
        pass  # a planted link or an unwritable temp dir: the suggestion may repeat, nothing else breaks
    return same


def main():
    try:
        if os.environ.get("ARSENAL_ROUTER", "").strip().lower() == "off":
            return 0
        data = hook_input()
        line = suggestion(data.get("prompt"), load_table())
        if line and not repeated(data, line):
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": line}}))
    except Exception:  # a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
