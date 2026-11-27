#!/usr/bin/env python3
"""A CI rerun before the red run was reported, for guard_lessons' opt-in `rerun-after-red` rule (the CI half).

Usage: events = guard_ci_rerun.observe(command, text, parse, ok)   # track side: events to record for one gh command
       bad = guard_ci_rerun.refused(args, events)                  # judge side: True for a rerun or re-dispatch
Never raises: any error records nothing and refuses nothing.
Seen red: a `gh run view`, `gh run watch`, `gh run list` or `gh pr checks` output (stdout, or the error text when
the command exited non-zero) with a failed or cancelled line: an `X` line, a status column or a JSON conclusion; the
word "fail" inside a name or a log is not red, and --log output is not read. The run id comes from the line's actions
URL, a list row's id column, or the id argument of `gh run view`; without one the red is for any run ("*"). The
workflow name comes from the view header or the list row; without one it is unknown ("*").
Refused until a `lessons.py cause` note was recorded after that: `gh run rerun <id>` and the api rerun calls (with or
without --failed or --job) of a run seen red (or any rerun when the id is unknown), and `gh workflow run` of the
workflow seen red (any workflow when the red one is unknown). A newer green run of the workflow, or the run itself
going green, closes it. A rerun or dispatch that started (ok) re-opens it, so a second rerun needs a new note; after
an unknown ("*") red that re-opening applies only while that red is at most 2 hours old.
A red with no run id ("*") refuses a named run, and a red with no workflow name ("*") refuses a dispatch, only while
it is at most 2 hours old (the event's "time"; an event without one counts as fresh); a named run or workflow seen red
stays open until closed. A run never seen red passes. gh run view, watch and gh pr checks always pass.
A `gh pr checks` output also closes: a run id closes when every row of that id in that output is pass (or pass and
skipping), together with the workflow that run was seen red in; when every row of the whole output is pass or
skipping (with at least one pass), it also closes the "*" reds (runs and workflows), and a closed run closes the
"*" workflow it was seen red in only then. A row still pending or failing keeps its run open.
Standard library only.
"""
import re
import time

RED_LINE = re.compile(r'(?i)^\s*X\s|^\s*-\s.*\bcancel+ed\b|"(?:conclusion|status)"\s*:\s*"(?:failure|cancel+ed|timed_out|startup_failure)"')
RED_FIELDS = frozenset(("fail", "failure", "cancel", "cancelled", "canceled", "timed_out", "startup_failure"))
HEADER = re.compile(r"^\s*(X|✓|-|\*)\s+\S+\s+(.+?)\s+·\s+\d+")
JSON_WORKFLOW = re.compile(r'"workflowName"\s*:\s*"([^"]*)"')
RUN_URL = re.compile(r"/actions/runs/(\d+)")
API_RERUN = re.compile(r"actions/(?:runs/(\d+)|jobs/\d+)/rerun(?:-failed-jobs)?/?$")
API_DISPATCH = re.compile(r"actions/workflows/([^/]+)/dispatches/?$")
RUN_ID = re.compile(r"\d{5,}")
WITH_VALUE = frozenset(("-R", "--repo", "-j", "--job", "-b", "--branch", "--workflow", "-L", "--limit", "--json",
                        "-q", "--jq", "-t", "--template", "-f", "--field", "-F", "--raw-field", "-r", "--ref",
                        "-e", "--event", "-s", "--status", "-u", "--user", "-c", "--commit",
                        "-X", "--method", "-H", "--header", "--input"))
ANY = "*"
CHECK_STATES = frozenset(("pass", "skipping", "fail", "pending", "cancel"))  # gh pr checks' bucket column
PASSING = frozenset(("pass", "skipping"))
REPORTERS = (("run", "view"), ("run", "watch"), ("run", "list"), ("pr", "checks"))
MAX_LINES = 2000
UNKNOWN_RED_SECONDS = 2 * 3600
GH_WORD = re.compile(r"\bgh\b")


def operands(args):
    """The words of a gh command line that are not options or option values."""
    words, skip = [], False
    for arg in args:
        if skip:
            skip = False
        elif arg.startswith("-"):
            skip = arg in WITH_VALUE
        else:
            words.append(arg)
    return words


def workflow_key(name):
    """A workflow file, path or name reduced to lower-case letters and digits, so ci.yml and CI match."""
    base = str(name).rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9]", "", re.sub(r"(?i)\.ya?ml$", "", base).lower()) or ANY


def rerun_target(words):
    """The run a rerun call aims at (ANY when unknown), ("workflow", key) for a dispatch, or None."""
    if words[:2] == ["run", "rerun"]:
        return words[2] if len(words) > 2 else ANY
    if words[:2] == ["workflow", "run"]:
        return ("workflow", workflow_key(words[2]) if len(words) > 2 else ANY)
    if words[0] == "api" and len(words) > 1:
        rerun, dispatch = API_RERUN.search(words[1]), API_DISPATCH.search(words[1])
        if rerun:
            return rerun.group(1) or ANY
        if dispatch:
            return ("workflow", workflow_key(dispatch.group(1)))
    return None


def line_runs(line, fallback):
    ids = set(RUN_URL.findall(line))
    if not ids and fallback:
        ids = {fallback}
    if not ids:
        ids = {field for field in line.split("\t") if RUN_ID.fullmatch(field)}
    return ids or {ANY}


def line_workflow(line, view_name):
    """The workflow named on a line (header, list row, JSON), else the view's, else unknown."""
    header, listed, as_json = HEADER.match(line), None, JSON_WORKFLOW.search(line)
    fields = line.split("\t")
    for index, field in enumerate(fields):
        if index >= 3 and RUN_ID.fullmatch(field):
            listed = fields[index - 3]
            break
    name = header.group(2) if header else listed or (as_json.group(1) if as_json else view_name)
    return workflow_key(name) if name else ANY


def classify(line):
    """"red", "green" or None for one output line."""
    fields = {field.strip().lower() for field in line.split("\t")}
    if RED_LINE.search(line) or fields & RED_FIELDS:
        return "red"
    header, listed = HEADER.match(line), "success" in fields and any(RUN_ID.fullmatch(f) for f in fields)
    return "green" if (header and header.group(1) == "✓") or listed else None


def checks_greens(text):
    """The ci_green event a `gh pr checks` output earns: the run ids whose every row is pass or skipping (at least one
    pass), plus "*" runs and workflows when every row of the output is. None when nothing closes."""
    states = {}
    for line in str(text or "").splitlines()[:MAX_LINES]:
        fields = [field.strip().lower() for field in line.split("\t")]
        if len(fields) < 2 or fields[1] not in CHECK_STATES:
            continue
        for run in line_runs(line, ""):
            states.setdefault(run, set()).add(fields[1])
    closed = {run for run, seen in states.items() if run != ANY and seen <= PASSING and "pass" in seen}
    everything = all(seen <= PASSING for seen in states.values()) and any("pass" in seen for seen in states.values())
    if not closed and not everything:
        return None
    return {"event": "ci_green", "runs": sorted(closed | ({ANY} if everything else set())),
            "workflows": [ANY] if everything else [], "from_checks": True}


def sightings(text, fallback):
    """ci_red and ci_green events for one output, oldest line first (gh run list prints newest first)."""
    lines = str(text or "").splitlines()[:MAX_LINES]
    header = next((HEADER.match(line) for line in lines if HEADER.match(line)), None)
    view_name = header.group(2) if header else ""
    events = []
    for line in reversed(lines):
        kind = classify(line)
        if kind:
            events.append({"event": "ci_" + kind, "runs": sorted(line_runs(line, fallback)),
                           "workflows": [line_workflow(line, view_name)]})
    return events


def observe(command, text, parse, ok):
    """The events to record after a gh command: ci_red and ci_green for output, ci_rerun for a rerun or dispatch that ran."""
    try:
        if not GH_WORD.search(command):
            return []
        events = []
        for cmd in parse(command):
            words = operands(cmd.args) if cmd.name == "gh" else []
            if len(words) < 2:
                continue
            target = rerun_target(words) if ok else None
            if tuple(words[:2]) in REPORTERS:
                if any(arg.startswith("--log") for arg in cmd.args):
                    continue
                fallback = words[2] if words[0] == "run" and len(words) > 2 and RUN_ID.fullmatch(words[2]) else ""
                events += sightings(text, fallback)
                green = checks_greens(text) if words[0] == "pr" else None
                events += [green] if green else []
            elif isinstance(target, tuple):
                events.append({"event": "ci_rerun", "runs": [], "workflow": target[1]})
            elif target:
                events.append({"event": "ci_rerun", "runs": [target]})
        return events
    except Exception:
        return []


def red(events, now=None):
    """(open_runs, open_workflows): runs and workflows seen red that no cause note, green run or newer pass closed.
    A rerun or dispatch re-opens its target after an unknown ("*") red only while that red is at most 2 hours old."""
    now = time.time() if now is None else now
    runs_fresh = unknown_red_is_fresh(events, now)
    flows_fresh = unknown_red_is_fresh(events, now, "workflows")
    open_runs, seen, open_wf, seen_wf, wf_of = set(), set(), set(), set(), {}
    for event in events:
        kind, runs, workflows = event.get("event"), set(event.get("runs") or ()), set(event.get("workflows") or ())
        if kind == "ci_red":
            open_runs |= runs
            seen |= runs
            open_wf |= workflows
            seen_wf |= workflows
            for run in runs:
                wf_of.setdefault(run, set()).update(workflows)
        elif kind == "ci_green":
            if event.get("from_checks"):
                still_red = set().union(*(wf_of.get(run, set()) for run in open_runs - runs))
                for run in runs:  # an unknown workflow closes only with the whole output (which names "*" itself)
                    workflows = workflows | (wf_of.get(run, set()) - ({ANY} - workflows) - still_red)
            open_runs -= runs
            seen -= runs
            open_wf -= workflows
            seen_wf -= workflows
        elif kind == "ci_rerun" and event.get("workflow"):
            flow = event["workflow"]
            if flow == ANY or flow in seen_wf or (ANY in seen_wf and flows_fresh):
                open_wf |= seen_wf if flow == ANY else {flow}
        elif kind == "ci_rerun" and ((runs - {ANY}) & seen or (ANY in seen and runs_fresh)):
            open_runs |= runs
            for run in runs:
                open_wf |= wf_of.get(run, seen_wf if run == ANY else set())
        elif kind == "cause":
            open_runs.clear()
            open_wf.clear()
    return open_runs, open_wf


def unknown_red_is_fresh(events, now, field="runs"):
    """True when the latest red seen without a run id (field "runs") or workflow name (field "workflows") is at most
    2 hours old (an event with no time counts as fresh); False when no such red was seen."""
    stamps = [event.get("time") for event in events if event.get("event") == "ci_red" and ANY in (event.get(field) or ())]
    if not stamps:
        return False
    return not isinstance(stamps[-1], (int, float)) or now - stamps[-1] <= UNKNOWN_RED_SECONDS


def refused(args, events, now=None):
    """True for a rerun of a run seen red, or a dispatch of the workflow seen red, while no cause note covers it."""
    try:
        words = operands(args)
        if len(words) < 2 or not events:
            return False
        target = rerun_target(words)
        now = time.time() if now is None else now
        open_runs, open_wf = red(events, now)
        if isinstance(target, tuple):
            if target[1] == ANY:
                return bool(open_wf)
            unknown = ANY in open_wf and unknown_red_is_fresh(events, now, "workflows")
            return target[1] in open_wf or unknown
        if target:
            unknown = ANY in open_runs and unknown_red_is_fresh(events, now)
            return bool(open_runs) and (target == ANY or target in open_runs or unknown)
        return False
    except Exception:
        return False
