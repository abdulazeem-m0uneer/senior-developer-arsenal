"""Pick which lessons a session start shows: the most recurrent, then those matching the files in play.

Imported by lessons.py; not a command. Standard library only.
Time budget: at most STDIN_WAIT for the hook input, then two git reads, each cut off after GIT_TIMEOUT seconds; with
no git, ranking falls back to recency.
"""
import contextlib
import json
import os
import re
import subprocess
import sys
import threading

GIT_TIMEOUT = 1.5
STDIN_WAIT = 0.5
GIT_READS = (("status", "--porcelain"), ("log", "-5", "--name-only", "--pretty=format:"))
PATHS_MAX = 300
KEEP_RECURRENT = 3
TAG_WEIGHT = 3
# File extension -> the tags a lesson about that stack usually carries.
EXTENSION_TAGS = {
    "py": ("python",), "js": ("node", "javascript"), "ts": ("node", "typescript"), "tsx": ("react", "typescript"),
    "jsx": ("react", "javascript"), "cs": ("csharp", "dotnet"), "sql": ("database",), "yml": ("yaml", "ci"),
    "yaml": ("yml", "ci"), "sh": ("shell", "bash"), "tf": ("terraform",), "md": ("docs",)}


def read_stdin():
    """Hook input, waiting at most STDIN_WAIT: a stdin that is left open with nothing on it must not hang the hook."""
    if sys.stdin is None or sys.stdin.isatty():
        return ""
    try:
        descriptor = sys.stdin.fileno()
    except (OSError, ValueError):  # replaced by an in-memory stream
        return sys.stdin.read()
    chunks = []

    def pump():
        with contextlib.suppress(OSError):
            while chunk := os.read(descriptor, 65536):
                chunks.append(chunk)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    reader.join(STDIN_WAIT)
    return b"".join(chunks).decode("utf-8", "replace")


def session_cwd():
    """The session's working directory from the hook's stdin JSON; this process's own when absent."""
    try:
        data = json.loads(read_stdin() or "{}")
        cwd = data.get("cwd") if isinstance(data, dict) else None
    except (OSError, ValueError):
        cwd = None
    return cwd if isinstance(cwd, str) and os.path.isdir(cwd) else os.getcwd()


def changed_paths(cwd):
    """Paths changed in the working tree and in the last commits; empty when git is missing, slow, or not a repo."""
    paths = []
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    for read in GIT_READS:
        try:
            done = subprocess.run(["git", "-C", cwd, *read], capture_output=True, text=True, errors="replace",
                                  timeout=GIT_TIMEOUT, env=env, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            break
        if done.returncode != 0:
            break
        paths.extend(done.stdout.splitlines()[:PATHS_MAX])
    return paths


def path_tokens(paths):
    tokens = set()
    for word in re.findall(r"[a-z0-9]+", " ".join(paths).lower()):
        if len(word) >= 3 or word in EXTENSION_TAGS:
            tokens.add(word)
            tokens.update(EXTENSION_TAGS.get(word, ()))
    return tokens


def score(lesson, tokens):
    tags = {tag for tag in lesson["tags"].split(",") if tag}
    text = f"{lesson['mistake']} {lesson['rule']} {lesson['check']}".lower()
    words = {word for word in re.findall(r"[a-z0-9]+", text) if len(word) >= 3}
    return TAG_WEIGHT * len(tags & tokens) + len(words & tokens)


def rank(lessons, tokens):
    """The KEEP_RECURRENT most repeated lessons first, then by overlap with the paths, newest first on a tie."""
    repeated = sorted((lesson for lesson in lessons if lesson["hits"] > 1), key=lambda lesson: -lesson["hits"])
    first = repeated[:KEEP_RECURRENT]
    rest = [(score(lesson, tokens), lesson["date"], index, lesson)
            for index, lesson in enumerate(lessons) if not any(lesson is kept for kept in first)]
    rest.sort(key=lambda item: item[:3], reverse=True)
    return first + [item[3] for item in rest]


def fit(lines, budget):
    """Indexes of the lines that fit the character budget, taken in order."""
    kept, used = [], 0
    for index, line in enumerate(lines):
        if used + len(line) + 1 <= budget:
            kept.append(index)
            used += len(line) + 1
    return kept
