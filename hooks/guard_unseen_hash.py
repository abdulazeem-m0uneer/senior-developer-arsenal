#!/usr/bin/env python3
"""Commit hashes in outbound text that nothing in the session showed, for guard_lessons' built-in `unseen-hash` rule.

Usage: found = guard_unseen_hash.unseen(texts, transcript_path, window_mb=None, agent_id=None, allow=None)
       # [] when all seen
       found = guard_unseen_hash.unseen_tokens(tokens, transcript_path, agent_id=None, partial=True)
       # the same check on tokens already picked (typed-sha's operands); partial=False: a timeout judges none
       text = guard_unseen_hash.named(found)  # "a1b2c3d, e4f5a6b and 2 more"
The texts are what a call sends (guard_calendar.outbound_texts with messages_only: gh comments, PRs and issues, the
message of a git commit or tag, the registry entry's `programs`, outbound MCP tools, the message of the built-in
SendMessage). A hash typed from memory is often wrong, so every commit-like token in them must have reached the
session from outside the model first. git's own operands (`git tag --contains <sha>`, `--fixup=<sha>`, a tag
target) and gh's `--match-head-commit <sha>` and `--target <sha>` are not judged: git and GitHub check those themselves.
What counts as a hash: 7 to 40 lowercase hex characters (git and gh print hashes in lowercase, so an uppercase hex
id such as a disk label in a path is not one) with at least one digit and one letter a-f ("deadbeef" and
"20261123" are words and dates, not hashes), not right after a `#` (a CSS color), not right after or before a
letter, digit or underscore (so not part of a longer hex run such as a SHA-256 or a 0x number); a `#` after it is
allowed, so `<sha>#L10` (a commit and a line anchor) is still checked. Not a segment of a UUID, not a binary
literal (0b1011) and not a word in NOT_HASHES (ed25519) or in the registry entry's "allow" list. A hash inside a
URL (.../commit/<sha>) is still checked: a commit link quotes a hash as much as the text does. Other ids that are
pure hex with a digit and a letter (a build id such as 2026a1b, a color without # such as ff00ff00, a number such
as 1e10000) are judged too: quote them from a tool output, write them in a form that is not bare hex, or add them
to "allow". In an MCP tool's input, the values of id fields (a key that is id or ends in _id, -id, Id or ids, such
as message_id or threadId; not sha or commit_sha) are not judged: they name a mail, task or page, and the service
checks them. A 32-character token (a UUID without dashes) also counts as seen when it was printed with its dashes.
Seen: the hash is a prefix of, or equal to, a hex run (any case) in a transcript entry the assistant did not write
(the hook input's "transcript_path", JSONL): a user entry's text (a prompt the person typed, a subagent's brief, a
message from another session, a task notification, the user's own shell output) and its tool_result blocks, a
"queue-operation" entry (a message queued while the agent was busy) and an "attachment" entry. A short hash of a
full one that was printed passes; a full hash when only its short form was printed is refused, because the rest of
it was never shown. Never seen: the assistant's text, thinking and tool_use inputs (the current call's and earlier
ones), request copies of them ("api-request-blob" entries), compaction summaries (the model wrote them), a line
that is a refusal by this rule (it quotes the hashes), and a hash that a git or gh error line rejects (a line
starting with fatal:, error:, gh:, GraphQL: or {"message": that says unknown revision, bad object, no commit found
and the like; git echoing a recalled hash does not confirm it, so that hash counts nowhere else in the same entry;
a commit subject that only uses such words is not an error line). A hash the agent prints on purpose (`echo
<hash>`, a file it wrote and read back) counts: the rule catches recall from memory, not deliberate evasion.
Subagents: the hook names the session transcript and adds agent_id; the agent's own entries are in
<session>/subagents/agent-<id>.jsonl, or one folder deeper for a workflow (subagents/workflows/<run>/). That file
is read instead; when it is not found within MAX_AGENT_DIRS folders, the call passes.
Cost: only the last `window_mb` MB of the transcript (default 16, also the most: the read and its lowercased copy hold
about twice the window in memory, and 16 absence searches of 16 MB with the read fit the budget, where 64 MB took
about 0.5 s) are read. First each distinct 7-character hash prefix is searched for once from the end of the window
(a C-level rfind: about 10 ms for 16 MB when it is absent, less when it was printed lately), and a hash whose
prefix appears nowhere is unseen with no parse, so the printed hashes never spend the budget before a hash
printed nowhere is judged. Then the lines holding a present prefix are parsed newest first, each
once, and the hex runs of the seen entries go into one sorted list that every hash is judged against (bisect), so
hashes that share lines or a prefix cost nothing more. Decision: per-prefix searches, not one scan that collects
every hex run. The searches grow with the number of distinct prefixes, but on a 16 MB window 16 absent ones took
about 0.10 s, a regex collecting every run about 0.20 s, and a translate-and-split pass about 0.11 s with a 66 MB
peak; a call with fewer hashes (the usual one or two) costs a fraction of either scan. A machine too slow for 16
full searches times the later ones out and they pass (see below). At most 16 distinct hashes per call
are checked (the rest pass). The whole check, the read included, stops after 0.2 s, and then only the hashes
already judged unseen are refused (the rest pass; one is enough to refuse the call). A missing, unreadable or
non-regular transcript, a timeout before any hash was judged unseen, or any other error passes the call: this guard
never refuses because it broke. A call with no hash reads nothing. Standard library and guard_calendar only.
"""
import bisect
import itertools
import json
import os
import re
import stat
import time

from guard_calendar import string_values

DEFAULT_WINDOW_MB = 16
MAX_WINDOW_MB = 16  # 16 absence searches of the window and its read must fit BUDGET_SECONDS
MAX_HASHES = 16
MAX_AGENT_DIRS = 256  # workflow run folders searched for a subagent transcript
BUDGET_SECONDS = 0.2
SHOWN = 3  # hashes named in the refusal
PREFIX = 7  # the shortest hash: every hash's search needle
HASH = re.compile(r"(?<![0-9A-Za-z_#])[0-9a-f]{7,40}(?![0-9A-Za-z_])")
NOT_HASHES = frozenset(("ed25519",))  # hex-shaped words people write in commit messages
BINARY = re.compile(r"0b[01]+")
UUID = re.compile(r"(?<![0-9A-Za-z_-])[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}(?![0-9A-Za-z_-])")
HEX_RUN = re.compile(r"[0-9a-f]{7,}")  # on lowercased text: each match is a maximal run
REJECTION = re.compile(r"unknown revision|bad object|bad revision|not a valid object name|ambiguous argument|"
                       r"could not resolve|could not parse|did not match any|no commit found|not a commit|"
                       r"invalid object|no such commit|needed a single revision|malformed object name")  # lowercased
ERROR_LINE = re.compile(r'\s*(?:(?:fatal|error|gh|graphql):|\{"message":)')  # how git and gh print an error
AGENT_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
REFUSAL = re.compile(r"arsenal lesson guard \S+ \(unseen-hash\): ")  # guard.refusal_text, lowercased


class OutOfTime(Exception):
    """The check ran past its budget; the call passes."""


def hashes(texts, allow=None):
    """The distinct commit-like tokens in the texts, in order, at most MAX_HASHES. allow: words that are not hashes
    (the registry entry's "allow"), in any case."""
    skip = NOT_HASHES | {word.lower() for word in allow or ()}
    found = {}
    for text in texts:
        for match in HASH.finditer(UUID.sub(" ", text)):
            token = match.group()
            if re.search(r"\d", token) and re.search(r"[a-f]", token) and token not in skip \
                    and not BINARY.fullmatch(token):
                found[token] = None
    return list(found)[:MAX_HASHES]


def window_bytes(window_mb):
    valid = isinstance(window_mb, (int, float)) and not isinstance(window_mb, bool) and 0 < window_mb <= MAX_WINDOW_MB
    return int((window_mb if valid else DEFAULT_WINDOW_MB) * 1024 * 1024)


def read_tail(path, size):
    """The last `size` bytes of a regular file, lowercased; a line cut at the start does not parse and is skipped."""
    if not stat.S_ISREG(os.stat(path).st_mode):  # a FIFO or device would block or never end
        raise OSError("not a regular file")
    with open(path, "rb") as handle:
        total = os.fstat(handle.fileno()).st_size
        handle.seek(max(0, total - size))
        return handle.read(size).lower()


def seen_texts(entry):
    """The text of an entry the assistant did not write; [] for its own entries and request copies of them."""
    kind = entry.get("type")
    if kind == "queue-operation":
        return list(string_values(entry.get("content")))
    if kind == "attachment":
        return list(string_values(entry.get("attachment")))
    if kind != "user" or entry.get("iscompactsummary"):  # the window is lowercased: isCompactSummary
        return []
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [content]
    texts = []
    for block in content if isinstance(content, list) else []:
        block_type = block.get("type") if isinstance(block, dict) else None
        inner = block.get("text") if block_type == "text" else \
            block.get("content") if block_type == "tool_result" else None
        parts = inner if isinstance(inner, list) else [inner]  # a tool result: a string or a list of text blocks
        texts += [part.get("text") if isinstance(part, dict) else part for part in parts]
    return [text for text in texts if isinstance(text, str)]


class Transcript:
    """One lowercased transcript window and the hex runs found so far in the seen entries' lines."""

    def __init__(self, data, deadline, clock):
        self.data, self.deadline, self.clock = data, deadline, clock
        self.parsed, self.runs, self.search_end = set(), [], {}  # runs: sorted, distinct

    def tick(self):
        if self.clock() > self.deadline:
            raise OutOfTime()

    def line(self, pos):
        start = self.data.rfind(b"\n", 0, pos) + 1
        end = self.data.find(b"\n", pos)
        return start, len(self.data) if end < 0 else end

    def line_runs(self, start, end):
        """The hex runs the entry on this line shows, less the ones a git or gh error rejects anywhere in it
        (`git rev-parse <sha>` echoes the hash on its own line before the error)."""
        self.tick()
        try:
            entry = json.loads(self.data[start:end])
        except ValueError:  # a line cut by the window or a partial write
            return set()
        lines = [line for text in (seen_texts(entry) if isinstance(entry, dict) else []) for line in text.splitlines()
                 if not REFUSAL.search(line)]
        rejected = {run for line in lines if ERROR_LINE.match(line) and REJECTION.search(line)
                    for run in HEX_RUN.findall(line)}
        dashless = {match.group().replace("-", "") for line in lines for match in UUID.finditer(line)}
        return ({run for line in lines for run in HEX_RUN.findall(line)} | dashless) - rejected

    def known(self, token):
        """True when a run found so far starts with the token: the first run not below it is the only candidate."""
        index = bisect.bisect_left(self.runs, token)
        return index < len(self.runs) and self.runs[index].startswith(token)

    def absent(self, token):
        """True when the token's first PREFIX characters appear nowhere in the window, so nothing showed it; one
        search from the end, which also marks where seen() starts for that prefix."""
        needle = token[:PREFIX].encode()
        if needle not in self.search_end:
            self.tick()
            self.search_end[needle] = self.data.rfind(needle) + PREFIX  # PREFIX - 1 when absent: nothing before
        return self.search_end[needle] < PREFIX

    def seen(self, token):
        """True when a seen entry in the window printed this hash or a longer one it starts. The lines holding the
        token's first PREFIX characters are parsed newest first (a quoted hash was most often shown lately), each
        line once for every token, and the search stops at the first line that shows it; the next token with the
        same prefix resumes there."""
        needle = token[:PREFIX].encode()
        end = self.search_end.get(needle, len(self.data))
        while not self.known(token):
            self.tick()
            pos = self.data.rfind(needle, 0, end)
            if pos < 0:
                end = 0
                break
            start, line_end = self.line(pos)
            end = start  # the next search looks only before this line
            if start not in self.parsed:
                self.parsed.add(start)
                for run in self.line_runs(start, line_end):
                    index = bisect.bisect_left(self.runs, run)
                    if index == len(self.runs) or self.runs[index] != run:
                        self.runs.insert(index, run)
        self.search_end[needle] = end
        return self.known(token)


def agent_transcript(transcript_path, agent_id):
    """The subagent's own transcript beside the session's, or None when it is not found within the bounds."""
    if not isinstance(agent_id, str) or not AGENT_ID.fullmatch(agent_id):
        return None
    name = f"agent-{agent_id}.jsonl"
    if os.path.basename(transcript_path) == name:  # the hook already names the agent's own file
        return transcript_path
    root = os.path.join(os.path.splitext(transcript_path)[0], "subagents")
    folders = [root]
    try:
        with os.scandir(os.path.join(root, "workflows")) as runs:
            folders += [run.path for run in itertools.islice(runs, MAX_AGENT_DIRS)]
    except OSError:  # no workflow has run in this session
        pass
    return next((path for path in (os.path.join(folder, name) for folder in folders) if os.path.isfile(path)), None)


def unseen(texts, transcript_path, window_mb=None, clock=time.monotonic, budget=BUDGET_SECONDS, agent_id=None,
           allow=None):
    """The hashes in the texts that no seen entry of the transcript window showed; [] on any failure, and only the
    ones judged before the budget ran out on a timeout. agent_id: the hook input's, when the call runs inside a
    subagent (its own transcript is read). allow: words that are not hashes."""
    try:
        wanted = hashes(texts or [], allow)
    except Exception:  # fail open: a broken check never refuses a call
        return []
    return unseen_tokens(wanted, transcript_path, window_mb, clock, budget, agent_id)


def unseen_tokens(wanted, transcript_path, window_mb=None, clock=time.monotonic, budget=BUDGET_SECONDS, agent_id=None,
                  partial=True):
    """The tokens (lowercase hex, 7 to 40 characters) that no seen entry of the transcript window showed, judged as
    unseen() judges a hash; [] on any failure. On a timeout, the ones already judged unseen with partial, else []."""
    found = set()
    try:
        if not wanted or not isinstance(transcript_path, str) or not transcript_path:
            return []
        deadline = clock() + budget
        if agent_id:  # inside a subagent; absent or empty in the main session
            transcript_path = agent_transcript(transcript_path, agent_id)
            if transcript_path is None:
                return []
        transcript = Transcript(read_tail(transcript_path, window_bytes(window_mb)), deadline, clock)
        # hashes printed nowhere first: parsing the lines of the printed ones must not spend their budget
        for token in wanted:
            if transcript.absent(token):
                found.add(token)
        for token in wanted:
            if token not in found and not transcript.seen(token):
                found.add(token)
    except OutOfTime:  # a hash judged unseen stays unseen; the ones not judged yet pass
        if not partial:
            return []
    except Exception:  # fail open: a broken check never refuses a call
        return []
    return [token for token in wanted if token in found]


def named(found):
    """The unseen hashes for the refusal: the first SHOWN, then how many more."""
    return ", ".join(found[:SHOWN]) + (f" and {len(found) - SHOWN} more" if len(found) > SHOWN else "")
