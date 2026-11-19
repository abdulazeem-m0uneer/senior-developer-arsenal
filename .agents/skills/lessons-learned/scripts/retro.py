"""A short Markdown retrospective for `lessons.py retro`: git history, the lessons ledgers, the failure evidence
file and the lesson-guard hit log over the last N days. Imported by lessons.py; not a command. Standard library only.

  report(sources, unguarded, days, today, cwd) -> Markdown text
A lesson counts in the window when its date (set when it is added and again on every repeat) is one of the last
N calendar days, today included: hits 1 is new, hits above 1 repeated this window. git reads the last MAX_COMMITS
commits and keeps those committed in the last N x 24 hours (not `--since`, which stops at the first older commit, so
one rebased or cherry-picked commit with an old date would hide every newer one). A missing repository, an empty one, a missing ledger or evidence file each print a line, never an error.
"""
import json
import os
import re
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import guard_hits

GIT_TIMEOUT = 5
MAX_COMMITS = 2000
TOP_FILES = 3
EXEMPT = re.compile(r"^exempt@\d+: ")  # a written exemption (lessons.py exempt)
CONVENTIONAL = re.compile(r"^(\w+)(?:\([^)]*\))?!?:")
FIELD, RECORD = "\x1f", "\x1e"


def git_activity(cwd, days, now=None):
    """{"commits": [(hash, subject, kind)], "files": Counter, "fixed": {file: [hash]}}; None outside a repository."""
    cutoff = (time.time() if now is None else now) - days * 86400
    try:
        out = subprocess.run(["git", "-c", "core.quotePath=false", "log", f"--max-count={MAX_COMMITS}", "--no-merges",
                              f"--format={RECORD}%h{FIELD}%ct{FIELD}%s", "--name-only"], cwd=cwd, capture_output=True,
                             text=True, timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=cwd, capture_output=True,
                                text=True, timeout=GIT_TIMEOUT)
        return {"commits": [], "files": Counter(), "fixed": {}} if inside.returncode == 0 else None
    activity = {"commits": [], "files": Counter(), "fixed": defaultdict(list)}
    for record in out.stdout.split(RECORD)[1:]:
        head, _, names = record.partition("\n")
        sha, _, rest = head.partition(FIELD)
        stamp, _, subject = rest.partition(FIELD)
        if not stamp.isdigit() or int(stamp) < cutoff:
            continue
        kind = commit_kind(subject)
        activity["commits"].append((sha, subject, kind))
        for name in filter(None, (line.strip() for line in names.split("\n"))):
            activity["files"][name] += 1
            if kind == "fix":
                activity["fixed"][name].append(sha)
    return activity


def commit_kind(subject):
    if subject.lower().startswith("revert"):
        return "revert"
    match = CONVENTIONAL.match(subject)
    kind = match.group(1).lower() if match else "other"
    return kind if kind in ("feat", "fix", "revert") else "other"


def in_window(when, today, days):
    try:
        moment = datetime.strptime(when, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False
    return today - timedelta(days=days) < moment <= today


def evidence_counts(today, days):
    """Lesson id -> failures that preceded it, from the evidence file, in the window; empty when there is none."""
    path = Path(os.environ.get("LESSONS_EVIDENCE_FILE") or Path.home() / ".agents" / "lessons-evidence.jsonl")
    found = Counter()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return found
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and isinstance(entry.get("lesson"), str) \
                and in_window(str(entry.get("time", ""))[:10], today, days):
            found[entry["lesson"]] += len(entry.get("failures") or [])
    return found


def report(sources, unguarded, days, today, cwd):
    lessons = [lesson for source in sources for lesson in source.lessons]
    new = [lesson for lesson in lessons if lesson["hits"] == 1 and in_window(lesson["date"], today, days)]
    repeated = sorted((lesson for lesson in lessons if lesson["hits"] > 1 and in_window(lesson["date"], today, days)),
                      key=lambda lesson: -lesson["hits"])
    unguarded_ids = {lesson["id"] for _, lesson in unguarded}
    hits, _ = guard_hits.counts(days * 86400)
    evidence = evidence_counts(today, days)
    git = git_activity(cwd, days)
    start = today - timedelta(days=days - 1)
    lines = [f"## Retro: {start.isoformat()} to {today.isoformat()} ({days} days)", "", "### What went well"]
    if git is None:
        lines.append("- not a git repository: no commit history read")
    elif not git["commits"]:
        lines.append("- no commits in the window")
    else:
        kinds = Counter(kind for _, _, kind in git["commits"])
        lines.append(f"- {len(git['commits'])} commits: {kinds['feat']} feat, {kinds['fix']} fix, "
                     f"{kinds['revert']} revert, {kinds['other']} other")
    if hits:
        stopped = ", ".join(f"{lesson} x{count}" for (lesson, _), count in hits.most_common(5))
        lines.append(f"- lesson guards stopped {sum(hits.values())} repeats on this machine: {stopped}")
    promoted = [lesson for lesson in lessons if lesson["promoted"] and not EXEMPT.match(lesson["promoted"])
                and in_window(lesson["date"], today, days)]
    for lesson in promoted:
        lines.append(f"- {lesson['id']} is enforced by {lesson['promoted']}")
    if new:
        lines.append(f"- {len(new)} new lessons recorded: {', '.join(lesson['id'] for lesson in new)}")
    if not any(source.path.is_file() for source in sources):
        lines.append("- no lessons ledger found")
    lines += ["", "### What repeated"]
    for lesson in repeated[:5]:
        mark = " (no guard yet)" if lesson["id"] in unguarded_ids else ""
        failures = f", {evidence[lesson['id']]} failed commands before it" if evidence[lesson["id"]] else ""
        lines.append(f"- {lesson['id']} x{lesson['hits']}{mark}{failures}: {lesson['rule']}")
    hot = sorted(((name, shas) for name, shas in (git or {}).get("fixed", {}).items() if len(shas) > 1),
                 key=lambda item: -len(item[1]))[:TOP_FILES]
    for name, shas in hot:
        lines.append(f"- {name} fixed {len(shas)} times: {', '.join(shas)}")
    reverts = [(sha, subject) for sha, subject, kind in (git or {}).get("commits", []) if kind == "revert"]
    for sha, subject in reverts:
        lines.append(f"- revert {sha}: {subject}")
    if not (repeated or hot or reverts):
        lines.append("- nothing repeated in the window")
    lines += ["", "### Repeats without a guard"]
    for _, lesson in unguarded[:10]:
        lines.append(f"- {lesson['id']} x{lesson['hits']} (last {lesson['date']}): {lesson['rule']}")
    if len(unguarded) > 10:
        lines.append(f"- and {len(unguarded) - 10} more: `lessons.py unguarded`")
    exempt = [lesson for lesson in lessons if EXEMPT.match(lesson["promoted"]) and lesson["id"] not in unguarded_ids]
    if not unguarded:
        lines.append("- none: every repeat has a guard" + (f" or an exemption ({len(exempt)})" if exempt else ""))
    elif exempt:
        lines.append(f"- {len(exempt)} exempted on purpose: {', '.join(lesson['id'] for lesson in exempt)}")
    lines += ["", "### Top 3 actions"] + [f"{index}. {action}" for index, action in
                                          enumerate(actions(unguarded, hot, reverts, new)[:3], 1)]
    return "\n".join(lines)


def actions(unguarded, hot, reverts, new):
    """Ranked actions, each tied to a lesson id or a commit."""
    found = [f"Guard {lesson['id']} (x{lesson['hits']}): `lessons.py promote {lesson['id']} --guard <test|lint|hook>`"
             for _, lesson in unguarded]
    found += [f"Add a test around {name}: fixed in {', '.join(shas)}" for name, shas in hot]
    found += [f"Root-cause revert {sha} ({subject}) and record the lesson" for sha, subject in reverts]
    found += [f"Check next week that {lesson['id']} holds: {lesson['rule']}" for lesson in new]
    return found or ["Nothing to act on: keep recording verified mistakes as lessons"]
