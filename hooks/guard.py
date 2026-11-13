#!/usr/bin/env python3
"""Mechanical gates for "a test with every change", "record the lesson from a failure", destructive shell
commands and the limits of an unattended run (Claude Code plugin).

Usage (hook input is JSON on stdin):
  guard.py baseline  # SessionStart startup|resume|clear: record HEAD and the already-dirty paths; prints nothing
  guard.py track     # PostToolUseFailure / PostToolUse on Bash: record failed and passed checks and recorded lessons
  guard.py pre       # PreToolUse, every tool: deny past a run limit (guard_limits.py); ask or deny a destructive
                     # Bash command (guard_destructive.py)
  guard.py stop      # Stop: block once when source changed without a test, or a check failed, never passed
                     # again and no lesson followed; silent once a run limit is reached
Output: the Stop block {"decision":"block","reason":...} and the PreToolUse decision {"hookSpecificOutput":
{"hookEventName":"PreToolUse","permissionDecision":"deny"|"ask","permissionDecisionReason":...}}; with nothing
to enforce a hook prints nothing, so it costs no context. A destructive command is denied in a permission
mode where no human approves each call (bypassPermissions, dontAsk, auto) and asked about in the others
(default, acceptEdits, plan; what an unanswered ask does in a -p run is undocumented and unobserved).
A failed check is forgotten when the same check passes later in the session (red-first TDD). "The same
check" is the recognised tool and subcommand, or the script path, without wrappers (env, timeout, uv run),
directory prefix, interpreter and flags: `cd api && python3 -m pytest -x tests/a.py` and `pytest -q` are one
check, `python3 tests/a.py` and `python3 tests/b.py` are two. A command that runs several checks is cleared
when each of them has passed. So a narrower passing run clears a wider failed one: that costs a missed
question, never a wrong block.
The Stop gate cannot loop: it does nothing while stop_hook_active is true, and every
block is written to the state file before it is printed, so the same files and the same failures never
block twice (an explicit "no test applies" or "nothing learned" answer ends it). ARSENAL_GUARD=off disables
every gate here; ARSENAL_GUARD_DESTRUCTIVE=allow disables only the destructive-command check. Fails open: outside a git repository, when git fails or times out, without a session id, on any
exception, and whenever the diff could name work this session did not do: HEAD is no longer a descendant of
the baseline (checkout, rebase), a commit since the baseline is older than the session (pull, checkout of a
branch that was already ahead), or the stop runs in another working tree. Then it exits 0 silently.
A changed path is one added or modified since the baseline; deletions, pure renames and mode changes are not.
Observed on Claude Code 2.1.321, not documented: a Bash command with a non-zero exit arrives as
PostToolUseFailure (error "Exit code N", is_interrupt false) and never as PostToolUse, so failures are read
from that event only. A pass is recorded only when the check's exit status is the command's: a check followed
by a pipe, ||, ;, & or another command, or run with --version or --help, is not a pass (pytest | tail).
State: one JSON line per event in <snapshot file>.guard.jsonl, in the OS temp dir (see snapshot.py).
Time budget: baseline does at most four git reads and stop at most five, at 2 s each; track and pre run no
subprocess. pre runs before every tool call: measured at 51 to 53 ms a call on a busy Linux machine with
Python 3.14, where an empty interpreter takes 13 ms; the rest is importing and compiling, not the checks.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Plugin and repository: <root>/hooks beside <root>/.agents/skills. Installer: <dir>/arsenal-hooks beside <dir>/skills.
SKILLS = next((path for path in (ROOT / ".agents" / "skills", ROOT / "skills") if path.is_dir()), ROOT / "skills")
LESSONS = SKILLS / "lessons-learned" / "scripts" / "lessons.py"
sys.dont_write_bytecode = True  # importing the helper must not leave __pycache__ in the plugin
sys.path.insert(0, str(SKILLS / "handoff" / "scripts"))
try:
    import snapshot as hook  # hook input, session id, per-session file path, bounded git
    import guard_destructive
    import guard_limits
except Exception:  # a broken install must not break the session either
    sys.exit(0)

MAX_NAMED = 8
COMMAND_CHARS = 80
PACKAGE_RUNNERS = ("npm", "pnpm", "yarn", "bun")
UNATTENDED_MODES = frozenset(("bypassPermissions", "dontAsk", "auto"))  # no human approves each call
CODE_EXTENSIONS = frozenset(
    "py js jsx mjs cjs ts tsx mts cts vue svelte cs fs vb go rs java kt kts scala groovy rb php swift dart "
    "c h cc cpp cxx hpp m mm ex exs lua".split())
IGNORED_DIRS = frozenset(
    "dist vendor node_modules third_party generated __generated__ __pycache__ obj coverage migrations "
    ".git .venv venv .storybook .vscode .idea .husky".split())
ROOT_BUILD_DIRS = frozenset("build out target".split())  # deeper down these are ordinary package names
GENERATED_NAME = re.compile(r"\.(min\.(js|css)|d\.ts|g\.cs|designer\.cs|pb\.go|generated\.\w+)$|_pb2(_grpc)?\.py$", re.I)
CONFIG_NAME = re.compile(r"^\.|\.(config|stories)\.\w+$|^(setup|conf|noxfile)\.py$|^(gulp|grunt)file\.\w+$", re.I)
TEST_DIR = re.compile(r"^(__tests__|__mocks__|e2e|cypress|playwright|testdata)$|(^|[._-])[Tt]ests?([._-]|$)|[a-z]Tests?$")
ROOT_TEST_DIRS = frozenset("spec specs".split())  # deeper down "spec" is as often an API specification
TEST_NAME = re.compile(
    r"^(test_.*|tests?|conftest)\.\w+$|[._-](test|spec)s?\.\w+$|\.cy\.\w+$"
    r"|[a-z0-9](Tests?|Spec|IT)\.(cs|fs|vb|java|kt|scala|groovy|swift|php)$|[a-z0-9](Test|Spec)\.[jt]sx?$")
QUOTED = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")
OPTIONS = r"(?:\s+-[\w-]+(?:[=\s][^\s;&|-]\S*)?)*?"  # one way to read each option: no backtracking blow-up
INTERPRETER = r"(?:py(?:thon[\d.]*)?|bash|sh|zsh|node)"
# What may stand between the start of a shell command and the program it runs.
PREFIX = (r"(?:^|[;&|(\n])[^\S\n]*(?:(?:\w+=\S*|if|then|else|while|until|do|!|npx|bunx|time|sudo|env"
          r"|nice(?:\s+-n\s*\S+)?|timeout\s+\S+|uv\s+run|poetry\s+run|pipenv\s+run|bundle\s+exec|(?:pnpm|yarn)\s+(?:exec|dlx)"
          r"|docker(?:\s+|-)compose\s+(?:run|exec)" + OPTIONS + r"\s+\S+|py(?:thon[\d.]*)?\s+-m)\s+)*")
CHECK_COMMAND = re.compile(
    PREFIX + r"(?:\S*/)?(?P<check>"
    r"pytest|py\.test|unittest|tox|nox|vitest|jest|mocha|playwright|cypress|rspec|phpunit|ctest"
    r"|ruff(?!\s+(?:format|clean|server|rule|config|linter|version|help|analyze))(?:\s+check)?"
    r"|mypy|pyright|flake8|pylint|eslint|tsc|biome(?!\s+(?:format|init|migrate|search|explain))(?:\s+(?:check|lint|ci))?"
    r"|shellcheck|rubocop|golangci-lint"
    r"|pre-commit(?!\s+(?:install|uninstall|autoupdate|clean|gc|init-templatedir|migrate-config|sample-config|try-repo))(?:\s+run)?"
    r"|(?:npm|pnpm|yarn|bun)" + OPTIONS + r"(?:\s+workspace\s+\S+)?\s+(?:run\s+)?"
    r"(?:test|lint|build|check|typecheck|jest|vitest|eslint|tsc)\S*"
    r"|dotnet\s+(?:test|build)|go\s+(?:test|build|vet)|cargo\s+(?:test|build|check|clippy|nextest)"
    r"|swift\s+(?:test|build)|deno\s+(?:test|lint|check)|(?:php\s+)?artisan\s+test"
    r"|(?:mvn|mvnw|gradle|gradlew)\s[^;&|\n]*\b(?:test|build|verify|check|install|package)"
    r"|(?:make|rake|mix|just|rails)" + OPTIONS + r"\s+(?:test|check|lint|build)"
    r"|gh\s+(?:run\s+(?:watch|view)|pr\s+checks)"
    r"|" + INTERPRETER + r"\s+\S*(?<![A-Za-z])tests?(?![A-Za-z])\S*"  # a script in a test directory, or a test file
    r"|" + INTERPRETER + r"\s+\S+\s[^;&|\n]*--(?:check|validate)"
    r")(?=$|[\s;&|)])")
# lessons.py run as a command with the subcommand itself: not a word passed to "search", echo or grep, not --help.
LESSON_COMMAND = re.compile(
    PREFIX + r"(?:(?:\S*/)?py(?:thon[\d.]*)?(?:\s+-\S+)*\s+)?(?:\"[^\"\n]*lessons\.py\"|'[^'\n]*lessons\.py'|[^\s\"';&|]*lessons\.py)"
    r"(?:\s+--file[=\s](?:\"[^\"]*\"|'[^']*'|\S+))?\s+(?:add|bump)\b(?![^;&|\n]*\s(?:--help|-h)(?:\s|$))")


def kind(path):
    """'test', 'source' or None (docs, config, lockfiles, generated or vendored files) for a repo-relative path."""
    *dirs, name = path.split("/")
    if any(part.lower() in IGNORED_DIRS for part in dirs) or dirs[:1] and dirs[0].lower() in ROOT_BUILD_DIRS:
        return None
    if any(TEST_DIR.search(part) for part in dirs) or dirs[:1] and dirs[0].lower() in ROOT_TEST_DIRS:
        return "test"  # whatever the extension: fixtures, shell and data-driven tests are test changes too
    if name.rpartition(".")[2].lower() not in CODE_EXTENSIONS or "." not in name:
        return None
    if GENERATED_NAME.search(name) or CONFIG_NAME.search(name):
        return None
    return "test" if TEST_NAME.search(name) else "source"


REDIRECT_FD = re.compile(r"\d*>&\d*|&>>?")  # 2>&1 and &> are not a background or a separator
SEPARATOR = re.compile(r"\|\||&&|\||&|;|\n")
NOT_A_RUN = re.compile(r"(?:^|\s)(?:--version|--help|-V|-h|--collect-only|--co)(?=\s|$)")
SCAN_CHARS = 20000  # a longer command is read at its head and tail: the scan cost must not grow with hostile input


def bounded(command):
    return command if len(command) <= SCAN_CHARS else command[:SCAN_CHARS // 2] + "\n" + command[-SCAN_CHARS // 2:]


def decides_exit(text, end):
    """True when the exit status of the command's last step is the status of the check ending at `end`: nothing
    hides it behind a pipe, `||`, `;`, a background `&` or a later command, and it is not --version or --help."""
    rest = REDIRECT_FD.sub(" ", text[end:])
    separator = SEPARATOR.search(rest)
    if NOT_A_RUN.search(rest[:separator.start()] if separator else rest):
        return False
    if not separator or separator.group() == "&&":
        return True
    return separator.group() in (";", "\n") and not rest[separator.end():].strip()  # `pytest;` ends there; `&` never


def check_keys(command, decisive=False):
    """The checks a shell command runs, each named by tool and subcommand (or script path) without wrappers,
    directory, interpreter and flags, so the same check run with other flags or paths has the same name.
    decisive: only checks whose exit status decides the command's (see decides_exit)."""
    keys = set()
    text = QUOTED.sub("''", bounded(command))
    for match in CHECK_COMMAND.finditer(text):
        if decisive and not decides_exit(text, match.end()):
            continue
        words = re.sub(r"^" + INTERPRETER + r"\s+", "", match.group("check")).split()
        if words[0] in PACKAGE_RUNNERS and "run" in words:
            words.remove("run")  # npm run test is npm test
        if words[0] == "pre-commit" and "run" in words:
            words.remove("run")
        if words == ["ruff"]:
            words.append("check")
        keys.add(" ".join(w for w in words if not w.startswith("-") or w in ("--check", "--validate"))[:COMMAND_CHARS])
    return sorted(keys)


def is_check_command(command):
    """True when a shell command runs a test, build, lint, type check or CI check (quoted arguments are not read)."""
    return isinstance(command, str) and bool(check_keys(command))


def switched_off(name="ARSENAL_GUARD", value="off"):
    return os.environ.get(name, "").strip().lower() == value


def state_path(data):
    """The per-session event file, or None when nothing identifies the session."""
    if hook.session_id(data) or os.environ.get("HANDOFF_SNAPSHOT"):
        return hook.snapshot_path(data).with_suffix(".guard.jsonl")
    return None


def record(path, event, fresh=False):
    """Append one event line (O_APPEND, so parallel tool hooks cannot lose each other's lines); fresh restarts the file."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if fresh else os.O_APPEND) | getattr(os, "O_NOFOLLOW", 0)
    handle = os.open(path, flags, 0o600)
    try:
        os.write(handle, (json.dumps(event) + "\n").encode("utf-8"))
    finally:
        os.close(handle)


def load(path):
    """The recorded events, oldest first; a missing file or a damaged line reads as absent."""
    events = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return events
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def text_list(value):
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def git_fields(root, *args):
    """NUL-separated output fields of a git command run with -z (paths verbatim, never quoted); None on failure."""
    try:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=hook.GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return [os.fsdecode(field) for field in out.stdout.split(b"\0") if field] if out.returncode == 0 else None


def edited_since(root, sha):
    """Tracked paths added or modified since the commit; a rename counts (as its new path) only when also edited."""
    fields = git_fields(root, "-c", "core.fileMode=false", "diff", "--name-status", "-M", "-z", sha)
    if fields is None:
        return None
    paths, fields = set(), iter(fields)
    for status in fields:
        path = next(fields, "")
        if status[:1] in "RC":
            path = next(fields, "")  # old path first, then the new one
        if status[:1] in "AM" or (status[:1] == "R" and status != "R100"):
            paths.add(path)
    return paths


def changed_paths(root, sha):
    """Paths added or edited since the commit (staged or not) plus untracked ones; None when git cannot say."""
    tracked = edited_since(root, sha) if sha \
        else git_fields(root, "ls-files", "--cached", "-z")  # no commit yet: every indexed file is new
    untracked = git_fields(root, "ls-files", "--others", "--exclude-standard", "-z")
    return None if tracked is None or untracked is None else set(tracked) | set(untracked)


def repo_root(data):
    root, is_repo = hook.workspace(hook.working_dir(data))
    return root if is_repo else None


def baseline():
    data = hook.hook_input()
    path, root = state_path(data), repo_root(data)
    if not path or not root or data.get("source") == "compact":  # the baseline must survive compaction
        return
    head = hook.git(root, "rev-parse", "--verify", "HEAD")
    sha = head[0] if head else ""
    dirty = changed_paths(root, sha)
    if dirty is not None:
        calls, started = guard_limits.usage(load(path))  # a resumed session keeps what its run has used
        record(path, {"event": "baseline", "sha": sha, "dirty": sorted(dirty), "root": root, "time": int(time.time())},
               fresh=True)
        if calls:
            record(path, {"event": "run", "calls": calls, "time": started})


def track():
    data = hook.hook_input()
    path = state_path(data)
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not path or not isinstance(command, str):
        return
    checks = check_keys(command)
    if data.get("hook_event_name") == "PostToolUseFailure":
        if checks and data.get("is_interrupt") is not True:
            record(path, {"event": "fail", "command": " ".join(command.split())[:COMMAND_CHARS], "checks": checks})
        return
    if LESSON_COMMAND.search(bounded(command)):  # PostToolUse: the command exited 0
        record(path, {"event": "lesson"})
    checks = check_keys(command, decisive=True)  # a pass hidden by `| tail` or `|| true` proves nothing
    if checks:
        record(path, {"event": "pass", "checks": checks})


def decide(decision, text):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                             "permissionDecisionReason": text}}))


def run_limit(data, cwd, count):
    """(limits file, why the run must stop) for this session; ('', '') without a limits file. count records the call."""
    limits_file = guard_limits.find(cwd)
    if not limits_file:
        return "", ""
    path = state_path(data)
    why, damaged = guard_limits.status(limits_file, load(path) if path else [], time.time())
    if why and guard_limits.is_report_write(data, limits_file, damaged):
        return limits_file, ""
    if count and path and not why:
        record(path, {"event": "call", "time": int(time.time())})
    return limits_file, why


def pre():
    data = hook.hook_input()
    if switched_off():
        return
    cwd = hook.working_dir(data)
    limits_file, why = run_limit(data, cwd, count=True)
    if why:
        return decide("deny", f"arsenal run limit ({limits_file}): {why}. Start nothing new and make no further tool "
                              "calls: write the handoff or end report (Write or Edit of a .md file still works) and "
                              "end the turn. Only the operator lifts the limit, by editing or deleting that file.")
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if data.get("tool_name") != "Bash" or not isinstance(command, str) or switched_off("ARSENAL_GUARD_DESTRUCTIVE", "allow"):
        return
    danger = guard_destructive.destructive(command, cwd)
    if not danger:
        return
    if data.get("permission_mode") in UNATTENDED_MODES:
        return decide("deny", f"arsenal guard: {danger}. Denied because nobody approves each call in this "
                              "permission mode; if it is really needed, park it for the user.")
    decide("ask", f"arsenal guard: {danger}.")


def untested_sources(root, events):
    """Source files changed since the baseline, not yet asked about, when no test file changed with them."""
    base = next((event for event in events if event.get("event") == "baseline"), None)
    sha = base.get("sha") if base else None
    if not isinstance(sha, str) or base.get("root") != root or foreign_history(root, sha, base.get("time")):
        return []  # another working tree, or commits this session did not make: the diff would name their files
    changed = changed_paths(root, sha)
    if changed is None:
        return []
    changed -= set(text_list(base.get("dirty")))
    kinds = {path: kind(path) for path in changed}
    if "test" in kinds.values():
        return []
    asked = {path for event in events if event.get("event") == "asked" for path in text_list(event.get("files"))}
    return sorted(path for path, value in kinds.items() if value == "source" and path not in asked)


def foreign_history(root, sha, started):
    """True when HEAD does not descend from the baseline, or a commit since then predates the session."""
    if not sha:
        return False
    if hook.git(root, "merge-base", "--is-ancestor", sha, "HEAD") is None:
        return True
    stamps = hook.git(root, "log", "--format=%ct", f"{sha}..HEAD")
    return stamps is None or not isinstance(started, int) or any(not s.isdigit() or int(s) < started for s in stamps)


def open_failures(events):
    """Failed check commands whose check did not pass again, with no lesson recorded and no question asked since."""
    failed = []  # (command, the checks it ran that have not passed since)
    for event in events:
        if event.get("event") == "fail":
            failed.append((str(event.get("command", "")), set(text_list(event.get("checks")))))
        elif event.get("event") == "pass":
            green = set(text_list(event.get("checks")))
            failed = [(command, red - green) for command, red in failed if not red or red - green]
        elif event.get("event") == "lesson" or (event.get("event") == "asked" and event.get("failures")):
            failed = []
    return [command for command, _ in failed]


def reason(files, failed):
    parts = []
    if files:
        more = f" (+{len(files) - MAX_NAMED} more)" if len(files) > MAX_NAMED else ""
        parts.append(f"source changed this session with no test change: {', '.join(files[:MAX_NAMED])}{more}. "
                     "Add or update a test and run it, or tell the user in one sentence why no test applies.")
    if failed:
        parts.append(f"{len(failed)} test/build/lint command(s) failed this session (last: {failed[-1]}), did not pass "
                     "again, and no lesson was recorded. If a verified mistake of your own caused it, record it with the "
                     f"lessons-learned skill: python3 \"{LESSONS}\" add --tags a,b --mistake \"...\" --cause \"...\" "
                     "--rule \"...\" --check \"...\"; otherwise say nothing was learned.")
    return "arsenal guard (asked once): " + " Also: ".join(parts) + " Then stop again."


def stop():
    data = hook.hook_input()
    path = state_path(data)
    if not path or data.get("stop_hook_active") is True or switched_off():
        return
    if run_limit(data, hook.working_dir(data), count=False)[1]:
        return  # the run was told to stop: asking for more work now would contradict the limit
    root = repo_root(data)
    if not root:
        return
    events = load(path)
    files, failed = untested_sources(root, events), open_failures(events)
    if not files and not failed:
        return
    record(path, {"event": "asked", "files": files, "failures": bool(failed)})  # before printing: never ask twice
    print(json.dumps({"decision": "block", "reason": reason(files, failed)}))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        {"baseline": baseline, "track": track, "pre": pre, "stop": stop}.get(cmd, lambda: None)()
    except Exception:  # a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
