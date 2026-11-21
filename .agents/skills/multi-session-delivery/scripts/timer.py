#!/usr/bin/env python3
"""Durable fixed-time routines: validated systemd user units, a read-back of the next run, a pause file.

usage: timer.py make NAME --on-calendar SPEC --command CMD --timeout DUR [--deadline ISO] [--margin 30m]
                         [--dir DIR] [--state-dir DIR] [--persistent] [--workdir ABSPATH] [--python ABSPATH] [--force]
       timer.py check NAME [--deadline ISO] [--margin 30m] [--state-dir DIR]
       timer.py pause NAME | resume NAME [--state-dir DIR]
       timer.py launchd NAME --at HH:MM [--weekdays 1-5|1,3,5] --command CMD --timeout DUR [--dir DIR]
                         [--state-dir DIR] [--python ABSPATH] [--force]
       timer.py run --name NAME --timeout DUR [--state-dir DIR] -- CMD...

Exit: 0 ok, 1 refused or judged bad, 2 usage or I/O error (a missing systemd-analyze or systemctl is 2, never a pass).
Durations: 90s, 30m, 2h, 1h30m. State dir: ${XDG_STATE_HOME:-~/.local/state}/timers (the pause files live there).

Why each rule exists:
  - A timer, not a sleep inside a session: a closed session kills its own alarms.
  - TimeoutStartSec bounds a oneshot unit; RuntimeMaxSec is ignored by oneshot, so the job could hang forever.
  - OnCalendar is validated by `systemd-analyze calendar`, and `make` refuses a first run that is after the
    deadline or closer to it than --margin (default 30m): a job that late reports late.
  - `check` is the read-back: read the scheduler's own next run before promising a time.
  - pause/resume only create or remove NAME.paused (the service has ConditionPathExists=! on it). Stopping and
    starting a Persistent timer makes it fire a missed run at once, so a timer is never stopped to pause it.
  - launchd has no timeout and no full calendar: only fixed times, and the job runs through `run`, which
    times out the command (SIGTERM to its process group, SIGKILL after 10 s, exit 124).
`make` and `launchd` write files only; they never run systemctl or launchctl. The margin check judges the first
run only: later runs are not checked against the deadline.
--command is one portable command line for both backends. In ExecStart, `%` is written as `%%` and `$` as `$$`
so systemd expands nothing; a leading `-`, `@`, `+`, `!` or `:` keeps its systemd meaning (ignore failure, argv0,
privileges). A backslash anywhere (systemd expands C escapes, launchd does not) and a lone `;` word (systemd
separates commands there) are refused (exit 2), as is any control character (line break, tab, ...). launchd runs the words without a shell (no
VAR=x, no $HOME, no redirects); wrap those in a script. Use absolute paths: systemd does not search PATH for
ExecStart. `make` also runs `systemd-analyze --user verify` on the pair and refuses (exit 1) what systemd would
refuse (unbalanced quote, bare `-`, relative --workdir, ...).
launchd and the printed commands use this Python (a virtualenv one prints a warning because the job then
depends on that venv; --python ABSPATH pins another).
run: the command gets its own session. SIGTERM, SIGINT and SIGHUP to the wrapper (exit 128+signal) and the
timeout (exit 124) end its process group: SIGTERM, then SIGKILL after --grace seconds (default 10). After a normal
exit whatever is left in the group is SIGKILLed, as systemd does with a oneshot's cgroup. A child that calls
setsid escapes this, and a SIGKILLed wrapper cannot clean up. Exit 126: the command cannot be run; 127: not found.
check refuses (exit 1) a deadline that has already passed and a paused routine (NAME.paused exists in
--state-dir): its runs are skipped, so the promised time would not happen. NAME: no .service/.timer suffix, 200 characters at most.
run leaves SIGINT and SIGHUP ignored when its caller ignored them (nohup); an unreadable pause file is exit 2.
Tests: TIMER_NOW (ISO time) replaces the clock.
"""
import argparse
import math
import os
import plistlib
import re
import shlex
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

NAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9_.@-]*[A-Za-z0-9_-])?")
DURATION_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")
TS_RE = r"(?:[A-Za-z]{3}\s+)?(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)(?:\s+(\S+))?"
TOOL_TIMEOUT = 20
REFUSAL_PHRASES = ("fatal error", "refusing", "bad unit file setting")
MAX_SECONDS = 366 * 86400
MAX_NAME = 200


class Refused(Exception):
    """Exit 1: a judged-bad input or state."""


class UsageError(Exception):
    """Exit 2: bad usage or an I/O problem."""


def parse_duration(text):
    match = DURATION_RE.match(text or "")
    if not text or not match:
        raise ValueError(f"bad duration {text!r}: use 90s, 30m, 2h or 1h30m")
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise ValueError(f"bad duration {text!r}: must be above zero")
    if total > MAX_SECONDS:
        raise ValueError(f"bad duration {text!r}: at most 366 days")
    return total


def now():
    raw = os.environ.get("TIMER_NOW")
    if not raw:
        return datetime.now().astimezone()
    try:
        return to_aware(datetime.fromisoformat(raw))
    except ValueError:
        raise UsageError(f"bad TIMER_NOW {raw!r}") from None


def to_aware(moment):
    return moment if moment.tzinfo else moment.astimezone()


def parse_deadline(text):
    try:
        deadline = to_aware(datetime.fromisoformat(text))
        fmt(deadline)
    except ValueError:
        raise UsageError(f"bad --deadline {text!r}: use an ISO time such as 2030-01-01T17:00") from None
    except OverflowError:
        raise UsageError(f"bad --deadline {text!r}: out of range") from None
    return deadline


def valid_name(name):
    if not NAME_RE.fullmatch(name or ""):
        raise UsageError(f"bad NAME {name!r}: letters, digits, . _ @ - only, not starting with a symbol")
    if name.endswith((".service", ".timer")) or len(name) > MAX_NAME:
        raise UsageError(f"bad NAME {name!r}: no .service or .timer suffix, at most {MAX_NAME} characters")
    return name


def duration_arg(text):
    try:
        return parse_duration(text)
    except ValueError as error:
        raise UsageError(str(error)) from None


def state_dir(args):
    """Absolute, because systemd ignores a relative ConditionPathExists and launchd runs with cwd /."""
    if args.state_dir:
        raw = args.state_dir
    else:
        raw = str(Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "timers")
    return Path(os.path.abspath(one_line("--state-dir", raw)))


def run_tool(argv):
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=TOOL_TIMEOUT)
    except FileNotFoundError:
        raise UsageError(f"{argv[0]} not found: cannot verify the schedule, nothing was done") from None
    except subprocess.TimeoutExpired:
        raise UsageError(f"{argv[0]} did not answer within {TOOL_TIMEOUT}s") from None
    return done.returncode, done.stdout, done.stderr


def parse_stamp(date_time, zone):
    """A zone abbreviation names the offset: in the fall-back hour 01:30 happens twice (EDT, then EST)."""
    naive = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S")
    if zone == "UTC":
        return naive.replace(tzinfo=timezone.utc)
    for fold in (0, 1):
        candidate = naive.replace(fold=fold).astimezone()
        if candidate.tzname() == zone:
            return candidate
    return naive.astimezone()


def next_from_analyze(text):
    """The UTC line is exact; the local line has only a zone abbreviation, read as the local zone."""
    utc = re.search(r"\(in UTC\):\s+" + TS_RE, text)
    if utc:
        return parse_stamp(utc.group(1), "UTC")
    local = re.search(r"Next elapse:\s+" + TS_RE, text)
    return parse_stamp(local.group(1), local.group(2)) if local else None


def next_from_show(value):
    value = value.strip()
    if not value or value == "n/a" or value == "0":
        return None
    stamp = re.match(TS_RE, value)
    if stamp:
        return parse_stamp(stamp.group(1), stamp.group(2))
    if value.isdigit():
        try:
            return datetime.fromtimestamp(int(value) / 1_000_000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            raise UsageError(f"the next run {value!r} from systemctl is out of range") from None
    raise UsageError(f"cannot read the next run from systemctl: {value!r}")


def judge_margin(next_run, deadline, margin_seconds):
    if not deadline:
        return
    gap = deadline - next_run
    detail = f"next run {fmt(next_run)}, deadline {fmt(deadline)}, gap {gap}"
    if gap < timedelta(0):
        raise Refused(f"the next run is after the deadline: {detail}")
    if gap < timedelta(seconds=margin_seconds):
        raise Refused(f"the next run is less than the margin ({margin_seconds}s) before the deadline: {detail}")


def fmt(moment):
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def until(moment):
    minutes = max(0, int((moment - now()).total_seconds() // 60))
    return f"{minutes // 60}h {minutes % 60}m"


def write_files(files, force):
    """files: {Path: bytes}. Checks every file before writing any, writes each atomically (temp + replace),
    and puts the old pair back when a later write fails, so a pair is never left half done."""
    try:
        old = {}
        for path, data in files.items():
            if path.is_symlink():
                raise Refused(f"{path} is a symlink: refusing to write through it")
            if path.exists():
                if not path.is_file():
                    raise UsageError(f"{path} exists and is not a file")
                old[path] = path.read_bytes()
                if old[path] != data and not force:
                    raise Refused(f"{path} exists and differs: pass --force to overwrite")
        done = []
        try:
            for path, data in files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                replace_atomically(path, data)
                done.append(path)
        except OSError as error:
            stuck = []
            for path in done:
                try:
                    if path in old:
                        replace_atomically(path, old[path])
                    else:
                        path.unlink(missing_ok=True)
                except OSError:
                    stuck.append(str(path))
            if stuck:
                raise UsageError(f"rollback failed for {', '.join(stuck)}; units are half written "
                                 f"(original error: {error})") from None
            raise
    except OSError as error:
        raise UsageError(f"cannot write units: {error}") from None


def replace_atomically(path, data):
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def encodable(label, value):
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise UsageError(f"{label} is not valid UTF-8") from None
    return value


def one_line(label, value):
    """Systemd joins a line ending in a backslash with the next one, so that is refused with line breaks."""
    encodable(label, value)
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise UsageError(f"{label} must not contain a line break or other control character")
    if value.endswith("\\"):
        raise UsageError(f"{label} must not end with a backslash (systemd would continue the line)")
    return value


def portable_command(command):
    """One command line both backends read the same way (see the header)."""
    one_line("--command", command)
    if not command.strip():
        raise UsageError("--command is empty")
    if "\\" in command:
        raise UsageError("--command must not contain a backslash (systemd expands C escapes, launchd does not)")
    if ";" in command.split():
        raise UsageError("--command must not contain a lone ';' word (systemd separates commands there)")
    return command


def interpreter(args, err):
    if args.python:
        if not os.path.isabs(one_line("--python", args.python)):
            raise UsageError("--python must be an absolute path")
        return args.python
    if sys.prefix != sys.base_prefix:
        err(f"warning: {sys.executable} is inside a virtualenv; the job depends on it. Pass --python ABSPATH to pin another.")
    return sys.executable


def verify_units(name, files):
    """Ask systemd itself; only lines about this pair count, so warnings about other units are ignored."""
    try:
        with tempfile.TemporaryDirectory() as scratch:
            paths = []
            for filename, data in files.items():
                path = Path(scratch) / filename
                path.write_bytes(data)
                paths.append(str(path))
            _, stdout, stderr = run_tool(["systemd-analyze", "--user", "verify", *paths])
    except OSError as error:
        raise UsageError(f"cannot verify the units: {error}") from None
    bad = [line.strip() for line in (stdout + "\n" + stderr).splitlines()
           if (f"{name}.service" in line or f"{name}.timer" in line)
           and any(phrase in line.lower() for phrase in REFUSAL_PHRASES)]
    if bad:
        raise Refused("systemd would refuse these units: " + " | ".join(bad))


def escape_specifiers(text):
    return text.replace("%", "%%")


def state_flags(args):
    return ["--state-dir", str(state_dir(args))] if args.state_dir else []


def is_paused(path):
    try:
        os.stat(path)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise UsageError(f"cannot read pause file {path}: {error}") from None
    return True


def cmd_make(args, out, err):
    name, timeout = valid_name(args.name), duration_arg(args.timeout)
    spec, command = one_line("--on-calendar", args.on_calendar), portable_command(args.command)
    paused = state_dir(args) / f"{name}.paused"
    workdir = one_line("--workdir", args.workdir) if args.workdir else None
    if workdir and not workdir.startswith(("/", "~")):
        raise UsageError("--workdir must be an absolute path")
    python = interpreter(args, err)
    margin = duration_arg(args.margin)
    deadline = parse_deadline(args.deadline) if args.deadline else None
    if spec.startswith("-") or not spec.strip():
        raise UsageError(f"bad --on-calendar {spec!r}")
    code, stdout, stderr = run_tool(["systemd-analyze", "calendar", "--iterations=1", spec])
    if code != 0:
        raise Refused(f"OnCalendar {spec!r} was rejected by systemd-analyze: {(stderr or stdout).strip()}")
    next_run = next_from_analyze(stdout)
    if not next_run:
        raise Refused(f"OnCalendar {spec!r} has no next run")
    judge_margin(next_run, deadline, margin)
    service = ["[Unit]", f"Description={name}", f"ConditionPathExists=!{escape_specifiers(str(paused))}", "",
               "[Service]", "Type=oneshot", f"TimeoutStartSec={timeout}s"]
    if workdir:
        service.append(f"WorkingDirectory={escape_specifiers(workdir)}")
    service.append(f"ExecStart={escape_specifiers(command).replace('$', '$$')}")
    timer = ["[Unit]", f"Description={name} timer", "", "[Timer]", f"OnCalendar={spec}", "AccuracySec=1s"]
    if args.persistent:
        timer.append("Persistent=true")
    timer += ["", "[Install]", "WantedBy=timers.target"]
    unit_dir = Path(encodable("--dir", args.dir)) if args.dir else Path.home() / ".config" / "systemd" / "user"
    units = {f"{name}.service": ("\n".join(service) + "\n").encode(), f"{name}.timer": ("\n".join(timer) + "\n").encode()}
    verify_units(name, units)
    write_files({unit_dir / filename: data for filename, data in units.items()}, args.force)
    out(f"wrote {unit_dir}/{name}.service and {name}.timer; first run {fmt(next_run)}")
    out(f"enable: systemctl --user daemon-reload && systemctl --user enable --now {name}.timer")
    tool = [python, str(Path(__file__).resolve())]
    deadline_flag = ["--deadline", args.deadline] if args.deadline else []
    out(f"state dir: {state_dir(args)} (pause file {paused})")
    out("check:  " + shlex.join([*tool, "check", name, *deadline_flag, *state_flags(args)]))
    out("pause:  " + shlex.join([*tool, "pause", name, *state_flags(args)]))
    return 0


def cmd_check(args, out, err):
    name, margin = valid_name(args.name), duration_arg(args.margin)
    deadline = parse_deadline(args.deadline) if args.deadline else None
    if deadline and deadline <= now():
        raise Refused(f"the deadline {fmt(deadline)} has already passed")
    pause = state_dir(args) / f"{name}.paused"
    if is_paused(pause):
        raise Refused(f"{name} paused (pause file {pause}): its runs are skipped until resume")
    code, stdout, stderr = run_tool(["systemctl", "--user", "show", f"{name}.timer",
                                     "-p", "NextElapseUSecRealtime", "-p", "ActiveState"])
    if code != 0:
        raise UsageError(f"systemctl show {name}.timer failed: {stderr.strip()}")
    props = dict(line.split("=", 1) for line in stdout.splitlines() if "=" in line)
    state = props.get("ActiveState", "").strip()
    if state != "active":
        raise Refused(f"{name}.timer is not active (state: {state or 'unknown'})")
    next_run = next_from_show(props.get("NextElapseUSecRealtime", ""))
    if not next_run:
        raise Refused(f"{name}.timer has no next run")
    judge_margin(next_run, deadline, margin)
    out(f"{name} next {fmt(next_run)} (in {until(next_run)})")
    return 0


def cmd_pause(args, out, err):
    path = state_dir(args) / f"{valid_name(args.name)}.paused"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    except OSError as error:
        raise UsageError(f"cannot write {path}: {error}") from None
    out(f"paused {args.name} (the timer keeps running; its runs are skipped)")
    return 0


def cmd_resume(args, out, err):
    path = state_dir(args) / f"{valid_name(args.name)}.paused"
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        raise UsageError(f"cannot remove {path}: {error}") from None
    out(f"resumed {args.name}")
    return 0


def parse_at(text):
    match = re.fullmatch(r"(\d\d):(\d\d)", text or "")
    if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
        raise UsageError(f"bad --at {text!r}: launchd runs fixed times only, as HH:MM (00:00 to 23:59)")
    return int(match.group(1)), int(match.group(2))


def parse_weekdays(text):
    days = []
    for part in text.split(","):
        bounds = re.fullmatch(r"([0-7])(?:-([0-7]))?", part)
        if not bounds:
            raise UsageError(f"bad --weekdays {text!r}: use 1-5 or 1,3,5 (0 or 7 is Sunday)")
        low, high = int(bounds.group(1)), int(bounds.group(2) or bounds.group(1))
        if high < low:
            raise UsageError(f"bad --weekdays {text!r}: range {part} runs backwards")
        days += range(low, high + 1)
    return list(dict.fromkeys(day % 7 for day in days))


def cmd_launchd(args, out, err):
    name, timeout = valid_name(args.name), duration_arg(args.timeout)
    hour, minute = parse_at(args.at)
    if args.weekdays is None:
        schedule = {"Hour": hour, "Minute": minute}
    else:
        schedule = [{"Weekday": day, "Hour": hour, "Minute": minute} for day in parse_weekdays(args.weekdays)]
    try:
        words = shlex.split(portable_command(args.command))
    except ValueError as error:
        raise UsageError(f"bad --command: {error}") from None
    if not words:
        raise UsageError("--command is empty")
    program = [interpreter(args, err), str(Path(__file__).resolve()), "run", "--name", name, "--timeout", args.timeout,
               "--state-dir", str(state_dir(args)), "--", *words]
    plist = {"Label": name, "ProgramArguments": program, "StartCalendarInterval": schedule}
    target = (Path(encodable("--dir", args.dir)) if args.dir else Path.home() / "Library" / "LaunchAgents") / f"{name}.plist"
    write_files({target: plistlib.dumps(plist)}, args.force)
    out(f"wrote {target} (timeout {timeout}s enforced by the run wrapper)")
    out("enable: " + shlex.join(["launchctl", "load", str(target)]))
    return 0


def protected_groups():
    """Our own process group and our parent's: signalling either would kill the caller's session."""
    groups = {os.getpgrp()}
    try:
        groups.add(os.getpgid(os.getppid()))
    except OSError:
        pass
    return groups


def kill_group(pgid, sig):
    """killpg that never reaches beyond the child's group: killpg(1) is kill(-1), every process we may signal."""
    if isinstance(pgid, bool) or not isinstance(pgid, int) or pgid <= 1 or pgid in protected_groups():
        raise ValueError(f"refusing to signal process group {pgid!r}")
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def stop_group(child, grace):
    """TERM the whole process group, KILL it after the grace period, and reap the child."""
    kill_group(child.pid, signal.SIGTERM)
    try:
        child.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    kill_group(child.pid, signal.SIGKILL)
    child.wait()


class Interrupted(Exception):
    def __init__(self, signum):
        super().__init__(signum)
        self.signum = signum


def raise_interrupted(signum, _frame):
    raise Interrupted(signum)


def cmd_run(args, out, err):
    name, timeout = valid_name(args.name), duration_arg(args.timeout)
    if not math.isfinite(args.grace) or args.grace < 0:
        raise UsageError("--grace must be a finite number of seconds, 0 or more")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise UsageError("run needs a command after --")
    if is_paused(state_dir(args) / f"{name}.paused"):
        out(f"paused: {name} skipped")
        return 0
    handled = [sig for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
               if sig == signal.SIGTERM or signal.getsignal(sig) != signal.SIG_IGN]  # nohup's ignored signals stay ignored
    previous = {sig: signal.signal(sig, raise_interrupted) for sig in handled}
    child = None
    try:
        try:
            child = subprocess.Popen(command, start_new_session=True)
        except OSError as error:
            err(f"error: cannot start {command[0]!r}: {error}")
            return 127 if isinstance(error, FileNotFoundError) else 126
        code = child.wait(timeout=timeout)
        kill_group(child.pid, signal.SIGKILL)  # what the command left behind, as systemd does for a oneshot
        return 128 - code if code < 0 else code
    except subprocess.TimeoutExpired:
        err(f"{name}: timed out after {timeout}s, process group killed")
        return 124
    except Interrupted as stop:
        err(f"{name}: interrupted by signal {stop.signum}, process group killed")
        return 128 + stop.signum
    finally:
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)  # no second signal may cut the cleanup short
        if child is not None and child.poll() is None:
            stop_group(child, args.grace)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def build_parser():
    parser = argparse.ArgumentParser(prog="timer.py", add_help=False)
    sub = parser.add_subparsers(dest="cmd")

    def add(name, positional=True):
        p = sub.add_parser(name, add_help=False)
        if positional:
            p.add_argument("name")
        p.add_argument("--state-dir")
        return p

    def deadline_opts(p):
        p.add_argument("--deadline")
        p.add_argument("--margin", default="30m")

    make = add("make")
    make.add_argument("--on-calendar", required=True)
    make.add_argument("--command", required=True)
    make.add_argument("--timeout", required=True)
    make.add_argument("--dir")
    make.add_argument("--persistent", action="store_true")
    make.add_argument("--workdir")
    make.add_argument("--python")
    make.add_argument("--force", action="store_true")
    deadline_opts(make)
    deadline_opts(add("check"))
    add("pause")
    add("resume")
    launchd = add("launchd")
    launchd.add_argument("--at", required=True)
    launchd.add_argument("--weekdays")
    launchd.add_argument("--python")
    launchd.add_argument("--command", required=True)
    launchd.add_argument("--timeout", required=True)
    launchd.add_argument("--dir")
    launchd.add_argument("--force", action="store_true")
    run = add("run", positional=False)
    run.add_argument("--name", required=True)
    run.add_argument("--timeout", required=True)
    run.add_argument("--grace", type=float, default=10.0, help=argparse.SUPPRESS)
    run.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv=None, out=print, err=lambda s: print(s, file=sys.stderr)):
    parser = build_parser()
    parser.error = lambda message: (_ for _ in ()).throw(UsageError(message))
    for action in parser._subparsers._group_actions:
        for sub in action.choices.values():
            sub.error = parser.error
    handlers = {"make": cmd_make, "check": cmd_check, "pause": cmd_pause, "resume": cmd_resume,
                "launchd": cmd_launchd, "run": cmd_run}
    try:
        args = parser.parse_args(argv)
        if args.cmd not in handlers:
            raise UsageError("usage: timer.py make|check|pause|resume|launchd|run (see the header of timer.py)")
        return handlers[args.cmd](args, out, err)
    except Refused as error:
        err(f"refused: {error}")
        return 1
    except UsageError as error:
        err(f"error: {error}")
        return 2
    except OSError as error:
        err(f"error: {error}")
        return 2
    except OverflowError as error:
        err(f"error: a time or duration is out of range ({error})")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
