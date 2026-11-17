"""One bounded `gh` call for the ship scripts: missing, unauthenticated or silent gh is GhUnavailable."""
import json
import subprocess


class GhUnavailable(Exception):
    """gh is not installed, not authenticated, or did not answer in time: nothing is known."""


class GhFailed(Exception):
    """gh answered with an error (no such pull request, bad query, unreadable output)."""


def call(args, cwd=None, timeout=30):
    """(exit code, stdout, stderr) of `gh <args>`; raises GhUnavailable when gh is missing, silent or logged out."""
    try:
        out = subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise GhUnavailable("gh is not installed: install it and run `gh auth login`") from error
    except subprocess.TimeoutExpired as error:
        raise GhUnavailable(f"gh {' '.join(args[:2])} did not answer within {timeout}s") from error
    except OSError as error:
        raise GhUnavailable(f"gh: {error}") from error
    lowered = out.stderr.lower()
    if out.returncode and ("gh auth login" in lowered or "not logged" in lowered or "authentication" in lowered):
        raise GhUnavailable("gh is not authenticated: run `gh auth login`")
    return out.returncode, out.stdout, out.stderr.strip()


def run(args, cwd=None, timeout=30, ok=(0,)):
    """stdout of `gh <args>` when its exit code is in `ok`; raises GhUnavailable or GhFailed otherwise."""
    code, stdout, stderr = call(args, cwd, timeout)
    if code in ok:
        return stdout
    raise GhFailed(stderr or f"gh {' '.join(args[:2])} exited {code}")


def run_json(args, cwd=None, timeout=30, ok=(0,)):
    """Parsed JSON output of `gh <args>`; GhFailed when it is not JSON."""
    text = run(args, cwd, timeout, ok)
    try:
        return json.loads(text)
    except ValueError as error:
        raise GhFailed(f"gh {' '.join(args[:2])} returned unreadable output") from error
