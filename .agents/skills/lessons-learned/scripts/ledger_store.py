"""Storage safety for the lessons ledger: one writer at a time, whole-file replacement, no secrets.

Imported by lessons.py; not a command. Standard library only.
  locked(path)       exclusive cross-process lock for one ledger (bounded wait, then LedgerBusy)
  write_atomic(...)  write beside the target and rename over it, so a reader never sees half a file
  find_secret(text)  the reason a text looks like a credential, or None
"""
import contextlib
import hashlib
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

LOCK_WAIT = 10.0
LOCK_POLL = 0.02
CHUNK_MIN = 3.0   # mean length of the word-like pieces of a run; names stay above it, random text falls below
RUN_MIN = 32
SHA_MAX = 40

ASSIGNED_RE = re.compile(r"(?:api[_-]?key|secret|passw(?:or)?d|token|bearer)\s*[:=]\s*(\S+)", re.I)
REFERENCE_MARKERS = ("environ", "getenv", "process.env", "${")
WORD_VALUE_MAX = 12   # an all-letter value shorter than this after `token:` is prose ("token: refresh"), not a secret
SHAPE_RE = re.compile(
    r"\bsk-[A-Za-z0-9_-]{16,}|\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"
    r"|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b|\bxox[abeprs]-[A-Za-z0-9-]{10,}"
    r"|\bglpat-[A-Za-z0-9_-]{20,}|hooks\.slack\.com/services/[A-Za-z0-9/]{20,}"
    r"|\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]{6,}@"
    r"|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|-----BEGIN [A-Z0-9 ]+-----")
RUN_RE = re.compile(r"[A-Za-z0-9+/=_\\-]{%d,}" % RUN_MIN)
HEX_RE = re.compile(r"[0-9a-fA-F]+")
CHUNK_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+|\d+")


class LedgerBusy(OSError):
    """Another process held the ledger lock for the whole wait."""


def lock_path(ledger_path):
    """A sibling `.<name>.lock`, so every process that sees the ledger agrees on the lock, whatever its TMPDIR.

    Fallback for a directory that cannot be written: the temp dir, keyed by the ledger's path.
    """
    ledger = Path(ledger_path).resolve()
    sibling = ledger.with_name(f".{ledger.name}.lock")
    try:
        sibling.parent.mkdir(parents=True, exist_ok=True)
        with open(sibling, "a+b"):
            pass
        return sibling
    except OSError:
        digest = hashlib.sha1(str(ledger).encode("utf-8")).hexdigest()[:16]
        return Path(tempfile.gettempdir()) / f"arsenal-lessons-{digest}.lock"


def _try_lock(handle):
    try:
        if fcntl:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


@contextlib.contextmanager
def locked(ledger_path):
    """Hold the ledger's lock for a read-modify-write. The OS drops it when the holder exits, so it cannot go stale."""
    with open(lock_path(ledger_path), "a+b") as handle:
        deadline = time.monotonic() + LOCK_WAIT
        while not _try_lock(handle):
            if time.monotonic() >= deadline:
                raise LedgerBusy(f"{ledger_path} is locked by another lessons.py; nothing was written, retry")
            time.sleep(LOCK_POLL)
        yield


def write_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp.write_text(text, encoding="utf-8", newline="\n")
        if path.exists():
            shutil.copymode(path, temp)
        os.replace(temp, path)
    finally:
        with contextlib.suppress(OSError):
            temp.unlink()


def _random_run(run):
    """A long unbroken run that is not a path, not a git SHA or UUID, and too choppy to be a name.

    Measured on generated strings: mixed-case random text (base62, base64url) is caught over 99% of the time;
    single-case random text (base32, base36) often is not, unless a key name or a known prefix gives it away.
    """
    if "/" in run or "\\" in run:
        return False
    hex_digits = run.replace("-", "")
    if HEX_RE.fullmatch(hex_digits):
        return len(hex_digits) > SHA_MAX
    chunks = CHUNK_RE.findall(run)
    return sum(map(len, chunks)) < CHUNK_MIN * len(chunks)


def _assigned_secret(text):
    """A key, password or token name followed by a value that looks like one, not a reference or a word."""
    for match in ASSIGNED_RE.finditer(text):
        value = match.group(1).strip("\"'`,.;)")
        if value.startswith(("$", "<", "%", "{")) or any(mark in value for mark in REFERENCE_MARKERS):
            continue
        if value.isalpha() and len(value) < WORD_VALUE_MAX:
            continue
        return True
    return False


def find_secret(text):
    if _assigned_secret(text):
        return "a key, password or token assignment"
    if SHAPE_RE.search(text):
        return "a known credential format (API key, access token, JWT, PEM block, webhook URL or URL with a password)"
    if any(_random_run(run) for run in RUN_RE.findall(text)):
        return "a long random string"
    return None
