#!/usr/bin/env python3
"""Confirm a payment by the gateway's status API until the status is final; never guess.

Reference implementation of the rule: act only on a final status read from the gateway, matched on
our own reference, amount and currency. Port the loop to the project's language, or run this CLI.

Usage: python3 confirm_status.py --fetch-cmd 'status-cmd {ref}' --reference REF --amount-minor N
           --currency CUR --success S [--success S ...] --failure F [--failure F ...] [--deadline 10m]
           [--fetch-timeout 30]
The fetch command prints one JSON object (at most 1 MB): status, amount_minor, currency, reference.
{ref} becomes one argv word (no shell); the template must not start with {ref}, so the reference
never picks the program. A reference starting with '-' is refused (exit 2): it could be read as an
option by the fetch command. POSIX only (process groups).
Fetch outcomes: the command's own exit code 44 means "payment not found" (not our exit 4); not found,
any other failure, a timeout and malformed output (not JSON, not an object, over 1 MB) are all
retried until the deadline, because the payment may still settle or appear. Only a fetch command that
cannot start, or a kill the guard or the OS refuses, ends the run (exit 2). A timed-out or oversized fetch is
killed with its whole process group. Each fetch waits at most min(--fetch-timeout, time left to
the deadline), at least 0.1 s.
Rules: a wrong reference is always a mismatch; amount and currency are checked only on a final
success (currency: three ASCII letters, compared case-insensitively); a final failure skips the
amount check; a missing, blank or unknown status keeps polling. Gateway values in the result line
(the reason and last_status) are cut to 200 characters.
Read-only: it never changes the payment, so a rerun is safe. The caller's action on exit 0 or 1 must
itself be idempotent, keyed on our reference.
Exit codes:
  0    paid
  1    failed
  2    usage error, or a fetch command that cannot start or whose process group may not be signalled
  3    pending-reconcile: still not final at the deadline, or not found; leave it pending, hand it to reconciliation
  4    mismatch: reference, amount or currency differ from ours; nothing is acted on
  5    internal error (a bug, or the result line cannot be written, also when stdout is closed; the line then
       goes to stderr): the payment state is unknown; act on nothing
  143  stopped by SIGTERM: the running fetch command's group is killed first; act on nothing
"""
import argparse
import contextlib
import json
import os
import re
import selectors
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

EXIT_PAID, EXIT_FAILED, EXIT_USAGE, EXIT_PENDING, EXIT_MISMATCH, EXIT_INTERNAL = 0, 1, 2, 3, 4, 5
NOT_FOUND_EXIT = 44  # exit code of the fetch command meaning "no such payment"
FETCH_TIMEOUT_S = 30
MAX_FETCH_BYTES = 1_000_000
MIN_FETCH_TIMEOUT_S = 0.1
REAP_POLL_S = 0.01
MAX_DEADLINE_S = 86400
MAX_SHOWN_CHARS = 200
DEFAULT_BACKOFF = (1, 2, 4, 8, 15, 30)
RETRY, NOT_FOUND, FATAL = "retry", "not_found", "fatal"


class NotFoundError(Exception):
    """The gateway answered that the payment does not exist (a 404-like answer)."""


class MalformedResponse(Exception):
    """The fetch answer is unreadable (not JSON, not an object, too large); retried, it may be a blip."""


class FetchSetupError(Exception):
    """The fetch command cannot be started or the request must not be sent; retrying will not help."""


@dataclass(frozen=True)
class Result:
    outcome: str  # paid | failed | pending-reconcile | mismatch
    last_status: Optional[str]
    attempts: int
    reason: str


def default_classifier(exc):
    if isinstance(exc, NotFoundError):
        return NOT_FOUND
    if isinstance(exc, (FetchSetupError, TypeError, KeyError, AttributeError, NameError)):
        return FATAL  # a bug or a setup fault: retrying until the deadline would hide it
    return RETRY  # timeouts, connection errors, 5xx, malformed output


def _status(value):
    """strip + ASCII-only lowercase: a confusable such as the Kelvin sign never folds to 'k'."""
    if value is None:
        return ""
    return "".join(c.lower() if c.isascii() else c for c in str(value).strip())


def _cut(text):
    return text if len(text) <= MAX_SHOWN_CHARS else text[:MAX_SHOWN_CHARS] + "...(cut)"


def _shown(value):
    """repr of a gateway value for a reason line, cut so a huge reply cannot flood the output."""
    return _cut(repr(value))


def _shown_status(value):
    """The last status for the result line: kept when short, else a cut string (a list becomes its repr)."""
    if value is None or isinstance(value, (bool, int, float)) and len(repr(value)) <= MAX_SHOWN_CHARS:
        return value
    return _cut(value if isinstance(value, str) else repr(value))


def _currency(value):
    """Upper-cased ISO-style code, or None unless exactly three ASCII letters."""
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z]{3}", value):
        return value.upper()
    return None


def _final_set(entries, name):
    if isinstance(entries, (str, bytes)):
        raise TypeError("%s must be a collection of statuses, not a single string" % name)
    result = set()
    for entry in entries:
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError("%s has a blank or non-string entry: %r" % (name, entry))
        result.add(_status(entry))
    if not result:
        raise ValueError("%s must not be empty" % name)
    return result


def _check_expected(reference, amount_minor, currency):
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("reference must be a non-blank string")
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor <= 0:
        raise ValueError("expected amount must be a positive integer in minor units")
    if _currency(currency) is None:
        raise ValueError("expected currency must be three ASCII letters")


def _wrong_reference(reply, reference):
    """Why the reply is not our payment, or None. Always checked, on every status."""
    got = reply.get("reference")
    if got != reference:
        return "reference mismatch: expected %r, got %s" % (reference, _shown(got))
    return None


def _wrong_money(reply, amount_minor, currency):
    """Why a final-success reply differs from what we expect to be paid, or None."""
    got_amount = reply.get("amount_minor")
    if isinstance(got_amount, bool) or not isinstance(got_amount, int) or got_amount != amount_minor:
        return "amount mismatch: expected %r, got %s" % (amount_minor, _shown(got_amount))
    got_cur = _currency(reply.get("currency"))
    if got_cur is None or got_cur != _currency(currency):
        return "currency mismatch: expected %r, got %s" % (currency, _shown(reply.get("currency")))
    return None


def confirm(fetch, reference, expected_amount_minor, expected_currency, final_success, final_failure,
            deadline_s, clock=time.monotonic, sleep=time.sleep, backoff=DEFAULT_BACKOFF,
            classify=default_classifier):
    """Poll fetch(reference) with backoff until a final status, a mismatch, or the deadline.

    The last read happens exactly at the deadline, never after it.
    """
    success = _final_set(final_success, "final_success")
    failure = _final_set(final_failure, "final_failure")
    _check_expected(reference, expected_amount_minor, expected_currency)
    if success & failure:
        raise ValueError("final status sets overlap: %s" % sorted(success & failure))
    if not backoff:
        raise ValueError("backoff must not be empty")

    start = clock()
    attempts = 0
    last_status = None
    last_error = ""
    while True:
        attempts += 1
        try:
            reply = fetch(reference)
        except Exception as exc:  # classified below; fatal ones are re-raised
            kind = classify(exc)
            if kind == FATAL:
                raise
            if kind == NOT_FOUND:  # often just not visible yet right after create
                last_error = "not found by reference %r: %s" % (reference, str(exc)[:MAX_SHOWN_CHARS])
            else:
                last_error = "%s: %s" % (type(exc).__name__, str(exc)[:MAX_SHOWN_CHARS])
        else:
            if not isinstance(reply, dict):
                last_error = "reply is not an object"
            else:
                why = _wrong_reference(reply, reference)
                if why:
                    return Result("mismatch", last_status, attempts, why)
                last_status = reply.get("status")
                status = _status(last_status)
                if status in success:
                    why = _wrong_money(reply, expected_amount_minor, expected_currency)
                    if why:
                        return Result("mismatch", last_status, attempts, why)
                    return Result("paid", last_status, attempts, "gateway reports final success")
                if status in failure:
                    return Result("failed", last_status, attempts, "gateway reports final failure")
                last_error = ""  # intermediate or unknown: keep polling
        remaining = deadline_s - (clock() - start)
        if remaining <= 0:
            break
        sleep(min(backoff[min(attempts - 1, len(backoff) - 1)], remaining))
    detail = last_error or "status %s is not final" % _shown(last_status)
    return Result("pending-reconcile", last_status, attempts, "deadline reached, %s" % detail)


def parse_duration(text):
    match = re.fullmatch(r"([0-9]+)([smh]?)", text.strip())
    if not match:
        raise ValueError("bad duration %r (use 30, 30s, 10m or 2h)" % text)
    seconds = int(match.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600}[match.group(2)]
    if seconds > MAX_DEADLINE_S:
        raise ValueError("duration %r is over the 1 day cap" % text)
    return seconds


def _protected_groups():
    """Our own process group and our parent's: signalling either would kill the caller's session."""
    groups = {os.getpgrp()}
    try:
        groups.add(os.getpgid(os.getppid()))
    except OSError:
        pass
    return groups


def kill_group(pgid, sig):
    """killpg that never reaches beyond the child's group: killpg(1) is kill(-1), every process we may signal.

    Same rules as the quality-gate and multi-session-delivery helpers (tests/test_kill_safety.py checks all).
    """
    if isinstance(pgid, bool) or not isinstance(pgid, int) or pgid <= 1 or pgid in _protected_groups():
        raise ValueError("refusing to signal process group %r" % (pgid,))
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


class _SigtermHold:
    """Set while a fetch command starts or is killed; _stop_on_sigterm then records the signal instead.

    proc is the running fetch command, so a SIGTERM outside the hold kills its group itself and the
    exit-143 promise does not depend on the unwinding reaching _run_bounded's cleanup.
    """
    active = False
    pending = None
    proc = None


@contextlib.contextmanager
def _sigterm_held():
    """Hold SIGTERM for the block, then exit 128 + signum if one arrived (over any error the block raised)."""
    _SigtermHold.active = True
    try:
        yield
    finally:
        _SigtermHold.active = False
        signum, _SigtermHold.pending = _SigtermHold.pending, None
        if signum is not None:
            raise SystemExit(128 + signum)


def _run_bounded(argv, timeout):
    """Run argv; return (exit code, stdout bytes). Raises TimeoutError or MalformedResponse (too big).

    stdout is read in chunks and the process group is killed as soon as it exceeds MAX_FETCH_BYTES or
    the time is up; the pipe is then closed without draining, so a descendant that escaped the group
    and still holds it cannot block the poll.
    """
    end = time.monotonic() + timeout
    chunks, size = [], 0
    proc, clean, stopping = None, False, False
    try:
        with _sigterm_held():  # a SIGTERM during the start fires here, with proc set and the kill armed
            try:
                proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, start_new_session=True)
            except (OSError, ValueError) as exc:  # ValueError: a NUL byte in an argument
                raise FetchSetupError("cannot run fetch command: %s" % exc) from exc
            _SigtermHold.proc = proc
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout, selectors.EVENT_READ)
            while True:
                left = end - time.monotonic()
                if left <= 0:
                    raise TimeoutError("fetch command exceeded %ss" % timeout)
                if not sel.select(left):
                    continue
                data = os.read(proc.stdout.fileno(), 65536)
                if not data:
                    break
                size += len(data)
                if size > MAX_FETCH_BYTES:
                    raise MalformedResponse("fetch output is over %d bytes" % MAX_FETCH_BYTES)
                chunks.append(data)
        wait_end = max(end, time.monotonic() + MIN_FETCH_TIMEOUT_S)
        while True:
            with _sigterm_held():  # waitpid and returncode in one hold: a SIGTERM between them would kill a freed pid
                if proc.poll() is not None:
                    break
            if time.monotonic() >= wait_end:
                raise TimeoutError("fetch command exceeded %ss" % timeout)
            time.sleep(REAP_POLL_S)
        clean = True
        return proc.returncode, b"".join(chunks)
    except SystemExit:
        stopping = True
        raise
    finally:
        if proc is not None:
            try:
                if not clean:
                    with _sigterm_held():  # a second SIGTERM must not cut the kill short
                        _kill_and_reap(proc)
            except FetchSetupError as exc:
                if not stopping:
                    raise
                _warn("error: %s" % exc)  # a refused kill must not replace the SIGTERM exit 143
            finally:
                _SigtermHold.proc = None
                proc.stdout.close()


def _kill_unreaped(proc):
    """SIGKILL the fetch command and anything it started in its group, unless it was already reaped."""
    if proc.returncode is None:  # once reaped, the pid may belong to someone else
        kill_group(proc.pid, signal.SIGKILL)


def _kill_and_reap(proc):
    try:
        _kill_unreaped(proc)
    except (ValueError, OSError) as exc:  # guard or OS (EPERM) refused: a retry adds one more unkilled child
        raise FetchSetupError(str(exc)) from exc
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def command_fetcher(template, fetch_timeout=FETCH_TIMEOUT_S, remaining=None):
    """A fetch(reference) that runs the template as argv, with {ref} inside a word, never via a shell.

    remaining() gives the seconds left to the overall deadline; one call waits at most
    min(fetch_timeout, max(remaining(), MIN_FETCH_TIMEOUT_S)).
    """
    words = shlex.split(template)
    if not any("{ref}" in word for word in words):
        raise ValueError("--fetch-cmd must contain {ref}")
    if "{ref}" in words[0]:
        raise ValueError("--fetch-cmd must start with the program, not {ref}: the reference must not pick it")

    def fetch(reference):
        if reference.startswith("-"):
            raise FetchSetupError("reference must not start with '-': it could be read as an option")
        argv = [word.replace("{ref}", reference) for word in words]
        timeout = min(fetch_timeout, max(remaining() if remaining else fetch_timeout, MIN_FETCH_TIMEOUT_S))
        code, stdout = _run_bounded(argv, timeout)
        if code == NOT_FOUND_EXIT:
            raise NotFoundError("fetch command exit %d" % NOT_FOUND_EXIT)
        if code != 0:
            raise RuntimeError("fetch command exit %d" % code)
        try:
            reply = json.loads(stdout)
        except (ValueError, RecursionError) as exc:
            raise MalformedResponse("fetch output is not JSON") from exc
        if not isinstance(reply, dict):
            raise MalformedResponse("fetch output is not a JSON object")
        return reply

    return fetch


def _amount_minor(text):
    if not re.fullmatch(r"[1-9][0-9]*", text):
        raise argparse.ArgumentTypeError("must be a positive integer without separators: %r" % text)
    return int(text)


def _fetch_timeout(text):
    try:
        seconds = parse_duration(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None
    if seconds < 1:
        raise argparse.ArgumentTypeError("must be at least 1 second")
    return seconds


def build_parser():
    parser = argparse.ArgumentParser(prog="confirm_status.py", description=__doc__.split("\n")[0])
    parser.add_argument("--fetch-cmd", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--amount-minor", required=True, type=_amount_minor)
    parser.add_argument("--currency", required=True)
    parser.add_argument("--success", required=True, action="append")
    parser.add_argument("--failure", required=True, action="append")
    parser.add_argument("--deadline", default="10m")
    parser.add_argument("--fetch-timeout", default=FETCH_TIMEOUT_S, type=_fetch_timeout)
    return parser


def _stop_on_sigterm(signum, frame):
    if _SigtermHold.active:
        _SigtermHold.pending = signum
        return
    proc, _SigtermHold.proc = _SigtermHold.proc, None
    if proc is not None:
        try:
            _kill_unreaped(proc)
        except (ValueError, OSError) as exc:  # guard or OS (EPERM) refused: the exit must still be 143
            _warn("error: %s" % exc)
    raise SystemExit(128 + signum)  # _run_bounded's cleanup then reaps the fetch command


def _warn(message):
    """Print to stderr; a lost stderr must not end the run with Python's exit 1, which reads as "failed"."""
    if sys.stderr is None:  # fd 2 closed at start; print(file=None) would write to stdout instead
        return
    with contextlib.suppress(OSError, ValueError):
        print(message, file=sys.stderr)


def exit_with(code, hard_exit=os._exit):
    """Exit with code. A stdout whose flush fails at interpreter exit would turn any code into 120."""
    try:
        if sys.stdout is not None:
            sys.stdout.flush()
    except (OSError, ValueError):  # the unwritten bytes stay buffered, so skip the exit-time flush
        with contextlib.suppress(OSError, ValueError, AttributeError):
            sys.stderr.flush()
        hard_exit(code)
    sys.exit(code)


def main(argv=None, fetch_factory=command_fetcher, clock=time.monotonic, sleep=time.sleep):
    args = build_parser().parse_args(argv)  # argparse exits 2 on bad usage
    previous = signal.signal(signal.SIGTERM, _stop_on_sigterm)
    try:
        return _run(args, fetch_factory, clock, sleep)
    finally:
        signal.signal(signal.SIGTERM, previous)


def _run(args, fetch_factory, clock, sleep):
    try:
        if args.reference.startswith("-"):
            raise ValueError("reference must not start with '-': it could be read as an option")
        deadline = parse_duration(args.deadline)
        start = clock()
        fetch = fetch_factory(args.fetch_cmd, args.fetch_timeout, lambda: deadline - (clock() - start))
        result = confirm(fetch, args.reference, args.amount_minor, args.currency, args.success,
                         args.failure, deadline, clock=clock, sleep=sleep)
    except (ValueError, FetchSetupError) as exc:
        _warn("error: %s" % exc)
        return EXIT_USAGE
    except Exception as exc:  # an uncaught crash exits 1, which reads as "failed"
        _warn("internal error: %s: %s" % (type(exc).__name__, exc))
        return EXIT_INTERNAL
    line = json.dumps({"outcome": result.outcome, "last_status": _shown_status(result.last_status),
                       "attempts": result.attempts, "reason": result.reason})
    if sys.stdout is None:  # fd 1 closed at start: print() would drop the line without an error
        _warn("internal error: stdout is closed, the result line is: %s" % line)
        return EXIT_INTERNAL
    try:
        print(line, flush=True)
    except (OSError, ValueError) as exc:  # a full disk, a closed pipe or file: exit 1 would read as "failed"
        _warn("internal error: cannot write the result: %s" % exc)  # exit 5 still says "act on nothing"
        return EXIT_INTERNAL
    return {"paid": EXIT_PAID, "failed": EXIT_FAILED, "pending-reconcile": EXIT_PENDING,
            "mismatch": EXIT_MISMATCH}[result.outcome]


if __name__ == "__main__":
    exit_with(main())
