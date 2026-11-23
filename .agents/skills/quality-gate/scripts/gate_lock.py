#!/usr/bin/env python3
"""Run the heavy pre-push gate one at a time per machine, and never be stuck behind a dead run.

usage: gate_lock.py run [--lock PATH] [--max-minutes 45] [--wait-minutes 0] [--grace-seconds 10] -- CMD...
       gate_lock.py status [--lock PATH] [--json]
       gate_lock.py git-lock [--repo DIR] [--older-than-minutes 10]

Why: several sessions push from one machine and each push runs a full test and lint gate. A lock keeps them
one at a time, but a run that was killed (terminal closed, OOM kill, crash) leaves a plain lock file behind
and every later push waits for nobody. Here a real OS lock (flock, msvcrt on Windows), which the kernel drops
when every process holding it is gone, decides while run lives. After run dies, the holder record beside it
decides only while the gate group it names (this host) still has live processes, or while a live gate of this
host recorded another lock file inode. Nothing else (age, an override) makes a lock stale.

Rules:
  * Kernel lock free and no live recorded gate group: take it. A leftover record is replaced with one line
    "cleared stale gate lock: pid N (dead|reused) started T: CMD". There is no age limit and no override.
  * Kernel lock held: busy, exit 5, with the holder from the record ("busy: held by pid N since T (cmd)", plus
    "running 73 min, over its 45 min limit" as a hint, and how to stop it: kill N), or, with no record,
    "held by a process that left no record ... find it with fuser <lock> or lsof <lock>".
  * CMD runs in its own process group and never inherits the lock fd: only run holds it, so a long-lived
    descendant (a server, a watcher, one that calls setsid) cannot keep the lock after run ends. The record
    names CMD's group; when run is gone (kill -9) but that group still has live processes, a new run is busy
    ("pid N is gone but its gate (process group G) still runs") and status says held. When CMD exits, the rest
    of its group is ended (SIGTERM, then SIGKILL after --grace-seconds, one line "stopped N leftover gate
    processes"). SIGTERM, SIGINT and SIGHUP sent to run are forwarded to the group and escalate to SIGKILL after
    the same grace. A hung gate is stopped by killing the pid the busy message prints. (POSIX; on Windows only
    the direct child is stopped.)

Commands:
  run -- CMD...   run CMD holding the lock; CMD's exit code is passed through (128 + N when it died of signal
                  N, 127 not found, 126 cannot be run). The record (JSON: pid, started, host, cwd, command,
                  lock_inode, max_minutes, and gate_group plus gate_leader_start once CMD has started) is
                  written when the lock is taken and removed when CMD ends, whatever its exit.
                  Busy: wait up to --wait-minutes (default 0, polling 1 s doubling to 10 s), then exit 5.
                  A failure while ending CMD's group or removing the record is reported on stderr and never
                  replaces CMD's exit code.
  status          "free", "held (pid N, age min, cmd)" or "held, no record (...)"; --json for tools. Exit 0.
  git-lock        report .git/index.lock, other .git/*.lock and refs/**/*.lock files (of the repository and of
                  its worktrees) older than --older-than-minutes (default 10), with the exact rm command.
                  It never deletes: git made the lock, and a human or the caller decides. Exit 1 when one is
                  found, 0 when none.

The lock file is never deleted by this tool. If someone else removes it during a run, a new run would lock a
new file; so every record carries the lock file's inode, and a run that finds a live gate (this host, another
pid) recorded under a different inode stays busy ("lock file was replaced while pid N runs") instead of
clearing it. Limit: a pid reused by an unrelated process after its lock file was also removed stays busy until
that pid ends or the holder record is deleted. A recorded gate group counts only when it is not run's own or
its parent's group and its leader (if alive) has the recorded start time, so a reused group id is not the gate.
A run killed between starting CMD and recording its group leaves CMD unguarded. A failed lock is retried 3 times,
50 ms apart, before it counts as held, so a racing `status` probe is not mistaken for a gate.

Lock path: --lock, else $ARSENAL_GATE_LOCK, else <cache dir>/arsenal/gate.lock (per user; the cache dir is
$XDG_CACHE_HOME or ~/.cache). The record is PATH.json. GATE_LOCK_NOW (ISO 8601 with offset) fixes the clock
for tests. Standard library only.
Exit: 0 ok, 1 git lock found, 2 usage error, unreadable clock or a lock file that cannot be opened or locked,
5 busy.
"""
import argparse
import contextlib
import datetime as dt
import errno
import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

EXIT_FOUND = 1
EXIT_BAD = 2
EXIT_BUSY = 5
BACKOFF_CAP = 10
LOCK_RETRIES = 3  # a failed lock is retried this often, 50 ms apart, before it counts as held
REOPEN_TRIES = 5
CONTENDED = (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, getattr(errno, "EDEADLK", errno.EAGAIN))
NO_RECORD = ("held by a process that left no record (likely a background process left by the last gate): "
             "find it with `fuser {lock}` or `lsof {lock}`")


class GateError(Exception):
    """Exit 2: usage, unreadable clock, a lock file that cannot be opened or locked."""


def clock():
    value = os.environ.get("GATE_LOCK_NOW")
    if not value:
        return dt.datetime.now().astimezone()
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        raise GateError(f"GATE_LOCK_NOW is not ISO 8601: {value!r}") from None
    return parsed if parsed.tzinfo else parsed.astimezone()


def pid_alive(pid):
    """True when the process exists (PermissionError: it exists, owned by someone else)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.windll.kernel32.GetLastError() == 5  # access denied: alive
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OverflowError:
        return False
    return True


def backoff(attempt):
    return min(BACKOFF_CAP, 2 ** attempt)


def lock_path(option):
    if option:
        return Path(option)
    if os.environ.get("ARSENAL_GATE_LOCK"):
        return Path(os.environ["ARSENAL_GATE_LOCK"])
    cache = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(cache) / "arsenal" / "gate.lock"


def _try_lock(handle):
    """True when taken, False when another process holds it; any other OSError propagates."""
    try:
        if fcntl:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except OSError as exc:
        if exc.errno in CONTENDED:
            return False
        raise


def settle():
    time.sleep(0.05)


def lock_with_retry(handle):
    """_try_lock, retried briefly: a competing probe (status, a racing run) holds the lock for microseconds."""
    for attempt in range(LOCK_RETRIES + 1):
        if attempt:
            settle()
        if _try_lock(handle):
            return True
    return False


def same_inode(handle, path):
    try:
        return os.fstat(handle.fileno()).st_ino == os.stat(path).st_ino \
            and os.fstat(handle.fileno()).st_dev == os.stat(path).st_dev
    except FileNotFoundError:
        return False


def read_record(path):
    """The holder record, None when absent, or the string 'corrupt'."""
    try:
        data = json.loads(Path(f"{path}.json").read_text(encoding="utf-8"))
        if not (isinstance(data, dict) and isinstance(data["pid"], int) and isinstance(data["max_minutes"], (int, float))
                and isinstance(data["host"], str) and isinstance(data["command"], str)):
            return "corrupt"
        started = dt.datetime.fromisoformat(data["started"])
        data["_started"] = started if started.tzinfo else started.astimezone()
        return data
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        return "corrupt"


def age_info(rec):
    """(age in whole minutes, text 'running N min, over its M min limit' or '')."""
    seconds = (clock() - rec["_started"]).total_seconds()
    age = int(seconds // 60)
    over = f"running {age} min, over its {rec['max_minutes']:g} min limit" if seconds > rec["max_minutes"] * 60 else ""
    return age, over


def same_host(rec):
    return rec["host"] == socket.gethostname()


def busy_message(path, rec):
    if not isinstance(rec, dict):
        return "busy: " + NO_RECORD.format(lock=path)
    text = f"busy: held by pid {rec['pid']} since {rec['started']} ({rec['command']})"
    if not same_host(rec):
        return text + f" on host {rec['host']}"
    over = age_info(rec)[1]
    if over:
        text += f", {over}"
    if pid_alive(rec["pid"]):
        return text + f"; to stop it: kill {rec['pid']}"
    return text + (f"; pid {rec['pid']} is gone and another process holds the lock (gated commands never get it): "
                   f"find it with `fuser {path}`")


def replaced_message(rec, path):
    return (f"busy: lock file was replaced while pid {rec['pid']} runs (held since {rec['started']}: {rec['command']}); "
            f"stop it with `kill {rec['pid']}`, or if that pid is not the gate, delete the holder record {path}.json")


def stale_message(rec):
    if not isinstance(rec, dict):
        return "cleared stale gate lock: unreadable holder record"
    why = "reused" if same_host(rec) and pid_alive(rec["pid"]) else "dead"
    return f"cleared stale gate lock: pid {rec['pid']} ({why}) started {rec['started']}: {rec['command']}"


def _write_record(path, args, handle, group=None):
    st = os.fstat(handle.fileno())
    rec = {"pid": os.getpid(), "started": clock().isoformat(), "host": socket.gethostname(), "cwd": os.getcwd(),
           "command": shlex.join(args.cmd), "lock_inode": [st.st_dev, st.st_ino],
           "max_minutes": int(args.max_minutes) if float(args.max_minutes).is_integer() else args.max_minutes}
    if group:
        rec["gate_group"], rec["gate_leader_start"] = group, process_start(group)
    tmp = Path(f"{path}.json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(rec), encoding="utf-8")
    os.replace(tmp, f"{path}.json")


def open_locked(path):
    """(handle, got): the lock file opened and locked, and verified to be the file now at path."""
    for _ in range(REOPEN_TRIES):
        handle = open(path, "a+b")
        if not lock_with_retry(handle):
            return handle, False
        if same_inode(handle, path):
            return handle, True
        handle.close()  # removed or replaced between open and lock: lock the current file instead
    raise GateError(f"{path} keeps being replaced; nothing was locked")


def process_start(pid):
    """The process's start time as an opaque token; None when it is gone or unreadable. Tells a reused id apart."""
    try:
        return "proc:" + Path(f"/proc/{pid}/stat").read_text(encoding="ascii").rsplit(")", 1)[1].split()[19]
    except (OSError, ValueError, IndexError):
        pass
    try:
        done = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    started = done.stdout[:200].strip()
    return "ps:" + started if done.returncode == 0 and started else None


def gate_still_runs(rec):
    """The recorded gate's process group (this host) still has live processes, though nobody holds the lock."""
    group = rec.get("gate_group") if isinstance(rec, dict) else None
    if not (os.name != "nt" and isinstance(group, int) and not isinstance(group, bool) and group > 1
            and group not in protected_groups() and same_host(rec)):
        return False
    leader = process_start(group)  # the kernel never reuses an id while its group has members
    if leader is not None and rec.get("gate_leader_start") not in (None, leader):
        return False
    return group_count(group) > 0


def orphan_message(rec, path):
    return (f"busy: pid {rec['pid']} is gone but its gate (process group {rec['gate_group']}) still runs "
            f"(since {rec['started']}: {rec['command']}); stop it with `kill -- -{rec['gate_group']}`, "
            f"or if that group is not the gate, delete the holder record {path}.json")


def holder_outlived_its_lock_file(rec, handle):
    """A live gate of this host recorded another lock inode: its lock file was removed or replaced."""
    st = os.fstat(handle.fileno())
    return (same_host(rec) and rec["pid"] != os.getpid() and pid_alive(rec["pid"])
            and rec.get("lock_inode") not in (None, [st.st_dev, st.st_ino]))


def try_acquire(path, args, err):
    """(handle, None) when the kernel lock is taken, (None, message) when it is held by someone else."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        handle, got = open_locked(path)
    except OSError as exc:
        raise GateError(f"cannot open or lock {path}: {exc}") from None
    try:
        if not got:
            handle.close()
            return None, busy_message(path, read_record(path))
        rec = read_record(path)
        if isinstance(rec, dict) and holder_outlived_its_lock_file(rec, handle):
            handle.close()
            return None, replaced_message(rec, path)
        if gate_still_runs(rec):
            handle.close()
            return None, orphan_message(rec, path)
        if rec is not None:
            err(stale_message(rec))
        _write_record(path, args, handle)
        return handle, None
    except OSError as exc:
        handle.close()
        raise GateError(f"cannot lock or record in {path}: {exc}") from None


def lock_is_free(path):
    """Probe the kernel lock without keeping it (a missing lock file is free)."""
    if not Path(path).exists():
        return True
    try:
        with open(path, "a+b") as handle:
            return lock_with_retry(handle)
    except OSError as exc:
        raise GateError(f"cannot open or lock {path}: {exc}") from None


def release(path, handle, err):
    """Remove our record, then drop the lock. Never raises: the command's exit code must survive."""
    try:
        rec = read_record(path)
        if isinstance(rec, dict) and rec["pid"] == os.getpid():
            Path(f"{path}.json").unlink(missing_ok=True)
    except OSError as exc:
        err(f"gate_lock.py: could not remove the holder record: {exc}")
    finally:
        handle.close()


def protected_groups():
    """Our own process group and our parent's: signalling either would kill the caller's session."""
    groups = {os.getpgrp()}
    try:
        groups.add(os.getpgid(os.getppid()))
    except OSError:
        pass
    return groups


def killpg(pgid, sig):
    """os.killpg that never reaches beyond the gate's group: killpg(1) is kill(-1), every process we may signal."""
    if isinstance(pgid, bool) or not isinstance(pgid, int) or pgid <= 1 or pgid in protected_groups():
        raise ValueError(f"refusing to signal process group {pgid!r}")
    os.killpg(pgid, sig)


def group_count(pgid):
    """Live (not zombie) processes in the group. Without a usable ps (busybox, failure) probe the group: 1 or 0."""
    try:
        done = subprocess.run(["ps", "-eo", "pgid=,stat="], capture_output=True, text=True, timeout=10)
        rows = [line.split() for line in done.stdout.splitlines()]
        rows = [row for row in rows if len(row) == 2 and row[0].isdigit()]
        if done.returncode == 0 and rows:
            return sum(1 for pg, stat in rows if pg == str(pgid) and not stat.startswith("Z"))
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        os.killpg(pgid, 0)  # signal 0 only probes; it sends nothing
        return 1
    except OSError:
        return 0


def end_group(pgid, grace, err):
    """SIGTERM the group, wait up to grace seconds, SIGKILL it. One line when anything had to be stopped."""
    left = group_count(pgid)
    if not left:
        return
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 5)):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            killpg(pgid, sig)
        deadline = time.monotonic() + wait
        while group_count(pgid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if not group_count(pgid):
            break
    err(f"stopped {left} leftover gate process{'' if left == 1 else 'es'}")


FORWARDED = tuple(getattr(signal, name) for name in ("SIGTERM", "SIGINT", "SIGHUP") if hasattr(signal, name))


def run_command(cmd, record_group, grace, err):
    """Run cmd in its own process group, without the lock fd; returns its exit code (128 + N for signal N)."""
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    child, kill_at = None, []

    def forward(signum, frame):
        if child is None:
            raise SystemExit(128 + signum)
        if os.name == "nt":
            child.terminate()
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            killpg(child.pid, signum)
        kill_at[:] = kill_at or [time.monotonic() + grace]

    previous = {sig: signal.signal(sig, forward) for sig in FORWARDED}
    try:
        child = subprocess.Popen(cmd, **kwargs)
        if os.name != "nt":
            try:
                record_group(child.pid)
            except OSError as exc:  # the gate still runs; only the kill -9 guard is lost
                err(f"gate_lock.py: could not record the gate's process group: {exc}")
        while True:
            try:
                code = child.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if kill_at and time.monotonic() >= kill_at[0]:
                    with contextlib.suppress(ProcessLookupError, PermissionError):
                        killpg(child.pid, signal.SIGKILL)
        return 128 - code if code < 0 else code
    finally:
        try:
            if child is not None and os.name != "nt":
                end_group(child.pid, grace, err)
        except Exception as exc:  # never replace cmd's exit code
            err(f"gate_lock.py: could not end the gate's leftover processes: {exc}")
        for sig, old in previous.items():
            signal.signal(sig, old)


def cmd_run(args, out, err):
    if not args.cmd:
        raise GateError("run needs a command after --")
    path = lock_path(args.lock)
    deadline = clock() + dt.timedelta(minutes=args.wait_minutes)
    attempt = 0
    while True:
        handle, busy = try_acquire(path, args, err)
        if busy is None:
            break
        if clock() >= deadline:
            err(busy)
            return EXIT_BUSY
        time.sleep(backoff(attempt))
        attempt += 1
    try:
        return run_command(args.cmd, lambda group: _write_record(path, args, handle, group), args.grace_seconds, err)
    except FileNotFoundError:
        err(f"gate_lock.py: command not found: {args.cmd[0]}")
        return 127
    except PermissionError:
        err(f"gate_lock.py: cannot run: {args.cmd[0]}")
        return 126
    except OSError as error:  # exec format error, argument list too long, a path through a file...
        err(f"gate_lock.py: cannot run: {args.cmd[0]}: {error.strerror or error}")
        return 126
    finally:
        release(path, handle, err)


def cmd_status(args, out, err):
    path = lock_path(args.lock)
    if lock_is_free(path) and not gate_still_runs(read_record(path)):
        out(json.dumps({"state": "free"}) if args.json else "free")
        return 0
    rec = read_record(path)
    if not isinstance(rec, dict):
        text = "held, no record (" + NO_RECORD.format(lock=path) + ")"
        out(json.dumps({"state": "held", "record": False}) if args.json else text)
        return 0
    age, over = age_info(rec)
    text = f"held (pid {rec['pid']}, {age} min, {rec['command']})" + (f", {over}" if over else "")
    info = {"state": "held", "record": True, "pid": rec["pid"], "started": rec["started"], "host": rec["host"],
            "cwd": rec.get("cwd", ""), "command": rec["command"], "max_minutes": rec["max_minutes"],
            "age_minutes": age, "over_limit": bool(over), "pid_alive": same_host(rec) and pid_alive(rec["pid"])}
    out(json.dumps(info) if args.json else text)
    return 0


def _git_dir(repo, flag):
    done = subprocess.run(["git", "-C", str(repo), "rev-parse", flag], capture_output=True, text=True)
    if done.returncode:
        raise GateError(f"{repo} is not a git repository: {done.stderr.strip()}")
    return (Path(repo) / done.stdout.strip()).resolve()


def cmd_git_lock(args, out, err):
    own, common = _git_dir(args.repo, "--absolute-git-dir"), _git_dir(args.repo, "--git-common-dir")
    found = {p.resolve() for d in {own, common} for p in
             [d / "index.lock", d / "HEAD.lock", d / "packed-refs.lock", d / "config.lock"]}
    found |= {p.resolve() for p in (common / "worktrees").glob("*/index.lock")}
    found |= {p.resolve() for p in (common / "refs").rglob("*.lock")}
    now = clock().timestamp()
    old = sorted((p, int((now - p.stat().st_mtime) // 60)) for p in found if p.is_file())
    old = [(p, age) for p, age in old if age >= args.older_than_minutes]
    if not old:
        out("no stale git locks")
        return 0
    out(f"git locks older than {args.older_than_minutes:g} min (check no git process runs, then remove):")
    for p, age in old:
        out(f"{p}: {age} min old")
        out(f"  {'del' if os.name == 'nt' else 'rm -f'} {p if os.name == 'nt' else shlex.quote(str(p))}")
    return EXIT_FOUND


def build_parser():
    parser = argparse.ArgumentParser(prog="gate_lock.py")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--lock")
    run.add_argument("--max-minutes", type=float, default=45)
    run.add_argument("--wait-minutes", type=float, default=0)
    run.add_argument("--grace-seconds", type=float, default=10)
    run.add_argument("cmd", nargs=argparse.REMAINDER)
    status = sub.add_parser("status")
    status.add_argument("--lock")
    status.add_argument("--json", action="store_true")
    git = sub.add_parser("git-lock")
    git.add_argument("--repo", default=".")
    git.add_argument("--older-than-minutes", type=float, default=10)
    return parser


def main(argv=None, out=print, err=lambda m: print(m, file=sys.stderr)):
    try:
        args = build_parser().parse_args(argv)
        if args.command == "run" and args.cmd[:1] == ["--"]:
            args.cmd = args.cmd[1:]
        return {"run": cmd_run, "status": cmd_status, "git-lock": cmd_git_lock}[args.command](args, out, err)
    except GateError as exc:
        err(f"gate_lock.py: {exc}")
        return EXIT_BAD


if __name__ == "__main__":
    sys.exit(main())
