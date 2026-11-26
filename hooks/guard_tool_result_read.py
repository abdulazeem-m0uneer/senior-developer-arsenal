#!/usr/bin/env python3
"""A Read of a persisted oversized tool result, for guard_lessons' opt-in `tool-result-read` rule.

Usage: text = guard_tool_result_read.problem(tool_name, tool_input, entry)   # None, or the refusal text
Never raises: any error passes the call.
When a tool result is too large the harness saves it to a file and prints its path; reading that file puts the whole
overflow into the context anyway. Judged: a Read whose file_path is inside a "tool-results" directory under
~/.claude/projects/<project>/<session>/ (~ expanded, .. resolved, a relative path taken from the working directory,
a bounded read with offset or limit included), or matches a glob of the entry's "paths" list (~ and $HOME expanded; a
glob with a / matches as a path suffix, one without names the file's basename). Other files under
~/.claude/projects/ (memory files, transcripts) pass. Not seen: a symlink into such a directory, a Bash cat or head,
a persisted path outside ~/.claude/projects/ that no "paths" glob names.
Standard library only.
"""
import fnmatch
import os
import posixpath

REASON = ("{path} is a persisted oversized tool result: reading it loads the whole overflow into the context. "
          "Narrow the query at the source instead (a filter, a smaller query, or a fetch with an extraction prompt).")
RESULTS_DIRECTORY = "tool-results"


def inside_results(path):
    """Whether the resolved path is <project>/<session>/tool-results/<file> under the projects folder."""
    prefix = posixpath.join(posixpath.normpath(os.path.expanduser("~")), ".claude", "projects") + "/"
    parts = path[len(prefix):].split("/")
    return path.startswith(prefix) and len(parts) >= 4 and parts[2] == RESULTS_DIRECTORY


def resolve(raw):
    """~ expanded, relative paths taken from the working directory, .. and a leading // collapsed."""
    return "/" + posixpath.abspath(os.path.expanduser(raw)).lstrip("/")


def expand_home(pattern):
    home = os.path.expanduser("~")
    return os.path.expanduser(pattern.replace("${HOME}", home).replace("$HOME", home))


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) or (not pattern.startswith("/") and fnmatch.fnmatchcase(
        path, "*/" + pattern)) for pattern in patterns)


def problem(tool_name, tool_input, entry):
    try:
        if tool_name != "Read" or not isinstance(tool_input, dict):
            return None
        raw = tool_input.get("file_path")
        if not isinstance(raw, str) or not raw.strip():
            return None
        path = resolve(raw)
        patterns = entry.get("paths") if isinstance(entry, dict) else None
        patterns = [expand_home(item) for item in patterns if isinstance(item, str) and item] if isinstance(patterns, list) else []
        return REASON.format(path=raw) if inside_results(path) or matches(path, patterns) else None
    except Exception:  # a guard never blocks work by failing
        return None
