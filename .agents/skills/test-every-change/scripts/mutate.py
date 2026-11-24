#!/usr/bin/env python3
"""Run mutation checks: each mutant in its own temporary copy of the repository's tracked files, always removed.

Usage: python3 mutate.py --mutants <mutants.json> [--timeout 300] -- <test command...>
  mutants.json: a non-empty list of {"file": <tracked path from the repository top>, "old": <text>, "new": <text>,
  "label": <name>}. "old" must occur exactly once in the file (line endings as stored: CRLF stays CRLF). The file
  must be a tracked regular UTF-8 file, never a symlink or a path outside the repository.
First the unmutated copy runs the test command once: when it fails there (a test that needs an untracked file,
node_modules or build output, which are not copied), nothing is judged and the run exits 2. Then, per mutant: the
tracked files (git ls-files; symlinks copied as links) go into a new temporary folder, the one replacement is made,
the command runs at the top of the copy (timeout per run, default 300 s), and the folder is deleted, also when the
command fails or times out, the mutant is malformed, or this script gets SIGTERM, SIGINT or SIGHUP. The command runs
in its own process group, and that group is killed on a timeout and on those signals, so no child outlives the run.
The checkout itself is never written by this script, and git run by the test command finds no repository above the
copy (inherited GIT_DIR, GIT_WORK_TREE and the like are removed from its environment). A tracked symlink whose target is absolute or climbs out of the repository still points there in the copy, so
a test that writes through it writes outside the copy. The folders go under $ARSENAL_MUTATION_DIR when it is set, else the system
temp folder.
Output: one line per mutant, "killed <label>" (the command failed or timed out) or "SURVIVED <label>".
Exit codes: 0 every mutant killed, 1 at least one survived, 2 usage error, bad input, a failing baseline or a git
or file error, 128+N stopped by signal N (its folder is removed first).
Standard library only.
"""
import argparse
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

PREFIX = "arsenal-mutant-"
STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
# variables that point git at a repository: inherited from a hook, they would aim the tests' git at the checkout
GIT_LOCATION = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR",
                "GIT_NAMESPACE", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_PREFIX")
POLL_SECONDS = 0.05


class BadInput(Exception):
    pass


def tracked_files(top):
    out = subprocess.run(["git", "ls-files", "-z"], cwd=top, capture_output=True, check=True).stdout
    return [os.fsdecode(name) for name in out.split(b"\0") if name]


def copy_tracked(top, names, target):
    for name in names:
        source, destination = os.path.join(top, name), os.path.join(target, name)
        if os.path.islink(source):
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            os.symlink(os.readlink(source), destination)
        elif os.path.isfile(source):  # a tracked file deleted in the checkout, or a submodule, is skipped
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copy2(source, destination)


def check_mutant(top, names, mutant):
    """The mutant's file as a tracked name; refuses paths outside the repository, untracked files and symlinks."""
    name = os.path.normpath(mutant["file"])
    if os.path.isabs(mutant["file"]) or name.startswith(os.pardir) or name not in set(map(os.path.normpath, names)):
        raise BadInput(f"{mutant['label']}: {mutant['file']} is not a tracked file of this repository")
    if os.path.islink(os.path.join(top, name)):
        raise BadInput(f"{mutant['label']}: {mutant['file']} is a symlink; mutate the file it points to")
    return name


def apply(target, name, mutant):
    path = os.path.join(target, name)
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            text = handle.read()
    except (OSError, ValueError) as error:
        raise BadInput(f"{mutant['label']}: cannot read {name} as UTF-8 ({error})") from error
    count = text.count(mutant["old"])
    if count != 1:
        raise BadInput(f"{mutant['label']}: the old text occurs {count} times in {name}, not once")
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text.replace(mutant["old"], mutant["new"]))


def kill_group(proc):
    """Kill the test command's own process group: it was started with start_new_session, so its group id is its pid,
    and the group lives on while a child of it runs. Called before the leader is reaped where os.waitid exists.
    Never a group id of 1 or less, and never this script's own group."""
    pid = proc.pid
    if not isinstance(pid, int) or pid <= 1 or pid == os.getpgrp():
        return
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):  # the group is already empty
        pass


def wait_unreaped(proc, timeout):
    """True when the command exited within the timeout. Where os.waitid exists the leader is left unreaped, so its
    pid (the group id) cannot be reused before kill_group; elsewhere Popen.wait reaps it first."""
    if not hasattr(os, "waitid"):
        try:
            proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False
    deadline = time.monotonic() + timeout
    while True:
        if os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_SECONDS)


def run_command(command, cwd, timeout):
    """'passed', 'failed' or 'timeout'; the command's whole process group is gone on return, also on a signal."""
    env = {key: value for key, value in os.environ.items() if key not in GIT_LOCATION}
    env["GIT_CEILING_DIRECTORIES"] = os.path.dirname(os.path.abspath(cwd))  # the copy has no .git
    proc = subprocess.Popen(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True, env=env)
    try:
        finished = wait_unreaped(proc, timeout)
    finally:
        kill_group(proc)
        proc.wait()
    if not finished:
        return "timeout"
    return "passed" if proc.returncode == 0 else "failed"


DEFER = {"on": False, "signal": None}  # while on, a stop signal is only recorded; see stop()


def defer(on):
    """Start or end a stretch where a stop signal waits; ending it raises the signal that came meanwhile. A flag,
    not only a signal mask: Python runs handlers in the main thread, and a mask set there does not hold back a
    signal another thread accepts."""
    DEFER["on"] = on
    if not on and DEFER["signal"] is not None:
        raise SystemExit(128 + DEFER["signal"])


def remove(target):
    """Delete the copy with a stop signal deferred: a signal that arrives now waits until the folder is gone."""
    defer(True)
    try:
        shutil.rmtree(target, ignore_errors=True)
        if os.path.lexists(target):
            print(f"mutate: warning: could not remove {target}; delete it by hand", file=sys.stderr)
    finally:
        defer(False)


def in_copy(top, names, command, timeout, mutant=None, name=None):
    defer(True)  # no stop between creating the folder and guarding it with the finally below
    target = tempfile.mkdtemp(prefix=PREFIX, dir=os.environ.get("ARSENAL_MUTATION_DIR") or None)
    try:
        defer(False)  # a stop that came during mkdtemp is raised here, inside the guard
        copy_tracked(top, names, target)
        if mutant is not None:
            apply(target, name, mutant)
        return run_command(command, target, timeout)
    finally:
        remove(target)


def load_mutants(path):
    try:
        with open(path, encoding="utf-8") as handle:
            mutants = json.load(handle)
    except (OSError, ValueError) as error:
        raise BadInput(f"cannot read {path}: {error}") from error
    keys = {"file", "old", "new", "label"}
    if not isinstance(mutants, list) or not mutants or not all(
            isinstance(m, dict) and keys <= set(m) and all(isinstance(m[k], str) for k in keys) for m in mutants):
        raise BadInput(f"{path} must be a non-empty list of objects with string file, old, new and label")
    return mutants


def stop(signum, _frame):
    for other in STOP_SIGNALS:  # a second signal must not cut the cleanup short
        signal.signal(other, signal.SIG_IGN)
    if DEFER["on"]:  # creating or removing a copy: finish that first, then exit (see defer)
        DEFER["signal"] = signum
        return
    raise SystemExit(128 + signum)  # unwinds through run_command's and in_copy's finally blocks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mutants", required=True)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.print_usage(sys.stderr)
        print("mutate: give the test command after --, and a timeout above 0", file=sys.stderr)
        return 2
    sys.stdout.reconfigure(errors="backslashreplace")  # a label of any text is printed, never crashed on
    for signum in STOP_SIGNALS:
        signal.signal(signum, stop)
    try:
        mutants = load_mutants(args.mutants)
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             check=True).stdout.strip()
        names = tracked_files(top)
        checked = [(mutant, check_mutant(top, names, mutant)) for mutant in mutants]
        baseline = in_copy(top, names, command, args.timeout)
        if baseline != "passed":
            raise BadInput(f"the tests fail without any mutant ({baseline}): a test may need a file that is not "
                           "tracked (node_modules, build output, a new untracked test); nothing was judged")
        survived = 0
        for mutant, name in checked:
            verdict = in_copy(top, names, command, args.timeout, mutant, name)
            survived += verdict == "passed"
            line = {"passed": "SURVIVED", "failed": "killed", "timeout": "killed"}[verdict]
            note = f" (timeout after {args.timeout:g} s)" if verdict == "timeout" else ""
            print(f"{line} {mutant['label']}{note}", flush=True)
    except BadInput as error:
        print(f"mutate: {error}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as error:
        print(f"mutate: git failed: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"mutate: {error}", file=sys.stderr)
        return 2
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
