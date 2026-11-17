"""Self-diagnosis of one session: where an arsenal skill should have fired and did not, and where the operating
core was not followed. Run as `usage_stats.py diagnose <transcript> | --session ID | --last [--dir D] [--json]`.

Findings, each with the turn's timestamp and a one-line fix:
  missed-skill     a user prompt holds one of a skill's multi-word trigger phrases (its SKILL.md `Triggers:`, whole
                   words, any case) and that skill was never invoked in the session, subagents included. Tagged
                   blocks (pasted content, system reminders) are ignored, and so is a prompt that matches 3 or more
                   skills: a brief that names many topics is not a request for each. Possibly missed, not proven.
  untested-change  source files were edited and no test file was, in the whole session
  unverified-done  the last assistant text claims done, fixed or passing after the last edit, and no check passed
                   after that edit
  unlearned-fail   a check failed, never passed again, and no lesson was recorded after it
Prompts, commands and paths are read in memory and never printed: a finding names the trigger phrase, the skill
and counts only. Reads the transcript and its subagents/ folder; writes nothing. Standard library only.
"""
import json
import re
from pathlib import Path

import skill_triggers
import usage_stats as stats

DONE_CLAIM = re.compile(r"\b(?:done|fixed|all (?:tests|checks) pass(?:ing|ed)?|tests? pass(?:es|ing|ed)?|"
                        r"ready to merge|complete[d]?)\b", re.I)
SKILL_DIR = stats.SKILLS
TAGGED = re.compile(r"<([a-zA-Z][\w-]*)\b[^>]*>.*?</\1>", re.S)  # pasted content, system reminders, IDE selections
MAX_SKILLS_PER_PROMPT = 2


class Session:
    """One pass over the transcript in order, keeping what the findings need."""

    def __init__(self):
        self.session = self.cwd = None
        self.prompts = []           # (timestamp, text)
        self.invoked = set()        # skill names, subagent use included
        self.edits = []             # (timestamp, kind)
        self.passes = []            # timestamps of passing checks
        self.failures = {}          # check key -> timestamp of its first failure that is still red
        self.lessons = []           # timestamps of recorded lessons
        self.claims = []            # (timestamp, assistant text)
        self.commands = {}

    def feed(self, raw):
        try:
            entry = json.loads(raw)
        except ValueError:
            return
        if not isinstance(entry, dict) or entry.get("isSidechain") is True:
            return
        self.session = self.session or entry.get("sessionId")
        self.cwd = self.cwd or entry.get("cwd")
        stamp = entry.get("timestamp") if isinstance(entry.get("timestamp"), str) else ""
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        content = message.get("content")
        if entry.get("type") == "user":
            self.user(entry, content, stamp)
        elif entry.get("type") == "assistant" and isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "tool_use":
                    self.tool_use(part, stamp)
                elif part.get("type") == "text" and isinstance(part.get("text"), str):
                    self.claims.append((stamp, part["text"]))

    def user(self, entry, content, stamp):
        if entry.get("isMeta") is True:
            return
        if isinstance(content, str):
            self.invoked.update(stats.COMMAND_NAME.findall(content))
            self.prompts.append((stamp, content))
            return
        if not isinstance(content, list):
            return
        text = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                text.append(part["text"])
            elif part.get("type") == "tool_result":
                self.tool_result(part, stamp)
        if text:
            joined = "\n".join(text)
            self.invoked.update(stats.COMMAND_NAME.findall(joined))
            self.prompts.append((stamp, joined))

    def tool_use(self, part, stamp):
        name, given = part.get("name"), part.get("input")
        given = given if isinstance(given, dict) else {}
        value = given.get("skill") if name == "Skill" else given.get("subagent_type") if name in ("Agent", "Task") else None
        if isinstance(value, str) and value.startswith(stats.SKILL_PREFIX):
            self.invoked.add(value[len(stats.SKILL_PREFIX):])
        elif name == "Bash" and isinstance(given.get("command"), str) and isinstance(part.get("id"), str):
            self.commands[part["id"]] = given["command"]
        elif name in stats.EDIT_TOOLS and stats.GUARD is not None and isinstance(given.get(stats.EDIT_TOOLS[name]), str):
            kind = stats.GUARD.kind(stats.relative(given[stats.EDIT_TOOLS[name]], self.cwd))
            if kind:
                self.edits.append((stamp, kind))

    def tool_result(self, part, stamp):
        command = self.commands.pop(part.get("tool_use_id"), None) if isinstance(part.get("tool_use_id"), str) else None
        if command is None or stats.GUARD is None:
            return
        guard = stats.GUARD
        if part.get("is_error") is True:
            for key in guard.check_keys(command):
                self.failures.setdefault(key, stamp)
            return
        passed = guard.check_keys(command, decisive=True)
        if passed:
            self.passes.append(stamp)
            for key in passed:
                self.failures.pop(key, None)
        if guard.LESSON_COMMAND.search(guard.bounded(command)) and stats.LESSON_OUTPUT.search(
                stats.text_of(part.get("content"))):
            self.lessons.append(stamp)

    def subagent(self, raw):
        """A subagent line: only its skill and subagent use counts, like usage_stats.Summary.feed_subagent."""
        if '"tool_use"' not in raw:
            return
        try:
            entry = json.loads(raw)
        except ValueError:
            return
        if not isinstance(entry, dict) or entry.get("type") != "assistant":
            return
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        for part in message.get("content") if isinstance(message.get("content"), list) else []:
            if isinstance(part, dict) and part.get("type") == "tool_use" and part.get("name") in ("Skill", "Agent", "Task"):
                self.tool_use(part, "")


def read(transcript):
    session = Session()
    with Path(transcript).open(encoding="utf-8", errors="replace") as lines:
        for raw in lines:
            session.feed(raw)
    for path in stats.subagent_transcripts(Path(transcript)):
        try:
            with path.open(encoding="utf-8", errors="replace") as lines:
                for raw in lines:
                    session.subagent(raw)
        except OSError:
            continue
    return session


def findings(session, table):
    found = []
    reported = set()
    table = {skill: [phrase for phrase in phrases if not phrase.startswith("/") and len(phrase.split()) > 1]
             for skill, phrases in table.items()}
    for stamp, text in session.prompts:
        matched = skill_triggers.matching(TAGGED.sub(" ", text), table)
        if len(matched) > MAX_SKILLS_PER_PROMPT:
            continue
        for skill, phrase in matched.items():
            if skill not in session.invoked and skill not in reported:
                reported.add(skill)
                found.append({"time": stamp, "kind": "missed-skill", "skill": skill,
                              "detail": f'a prompt said "{phrase}" and {skill} was never invoked',
                              "fix": f"invoke /arsenal:{skill} for this kind of request"})
    sources = [stamp for stamp, kind in session.edits if kind == "source"]
    if sources and not any(kind == "test" for _, kind in session.edits):
        found.append({"time": sources[-1], "kind": "untested-change",
                      "detail": f"{len(sources)} source edits and no test edit in the session",
                      "fix": "add or update a test with the change (test-every-change), or state why none applies"})
    last_edit = max((stamp for stamp, _ in session.edits), default="")
    if last_edit:
        claims = [(stamp, text) for stamp, text in session.claims if stamp >= last_edit and DONE_CLAIM.search(text)]
        verified = any(stamp >= last_edit for stamp in session.passes)
        if claims and not verified:
            found.append({"time": claims[-1][0], "kind": "unverified-done",
                          "detail": "claimed done after the last edit with no passing check after it",
                          "fix": "run the tests after the last edit and report their result (definition-of-done)"})
    for key, stamp in sorted(session.failures.items(), key=lambda item: item[1]):
        if not any(lesson >= stamp for lesson in session.lessons):
            found.append({"time": stamp, "kind": "unlearned-fail", "detail": f"`{key}` failed and never passed again",
                          "fix": "fix it, or record the verified cause with lessons.py add (lessons-learned)"})
    return sorted(found, key=lambda item: item["time"])


def locate(transcript, session_id, last, directory):
    """The transcript to read, or raises ValueError with the reason."""
    if transcript:
        path = Path(transcript).expanduser()
        if not path.is_file():
            raise ValueError(f"no transcript at {path}")
        return path
    directory = Path(directory).expanduser()
    if not directory.is_dir():
        raise ValueError(f"not a directory: {directory}")
    candidates = list(stats.transcripts(directory))
    if session_id:
        match = [path for path in candidates if path.stem == session_id]
        if not match:
            raise ValueError(f"no transcript for session {session_id} under {directory}")
        return match[0]
    if last and candidates:
        return max(candidates, key=lambda path: path.stat().st_mtime)
    raise ValueError(f"no transcripts under {directory}" if last else "give a transcript, --session ID or --last")


def run(transcript, session_id, last, directory, as_json):
    try:
        path = locate(transcript, session_id, last, directory)
        session = read(path)
    except (OSError, ValueError) as error:
        print(error, file=__import__("sys").stderr)
        return 2
    found = findings(session, skill_triggers.triggers(SKILL_DIR))
    if as_json:
        print(json.dumps({"session": session.session, "findings": found}, indent=2))
        return 0
    print(f"## Diagnosis of session {session.session or path.stem}")
    if not found:
        print("- no missed skill and no operating-core gap found")
    for item in found:
        print(f"- {item['time'] or '?'} {item['kind']}: {item['detail']}. Fix: {item['fix']}")
    return 0
