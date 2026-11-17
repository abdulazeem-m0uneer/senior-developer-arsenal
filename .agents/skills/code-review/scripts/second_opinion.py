#!/usr/bin/env python3
"""Ask another installed coding CLI (Codex, Gemini) for a read-only second review of a diff or a plan.

Usage:
  second_opinion.py --diff <ref> [--cli codex|gemini|auto] [--timeout S] [--max-bytes N] [--dry-run]
  second_opinion.py --plan <file> [same options]
--diff reviews the working tree against <ref> (`git diff <ref>`); --plan reviews a plan or design document.
Before anything is sent: diff blocks of files that look like secrets (.env, *.pem, *.key, id_rsa, names with a
key, secret or credential segment) are dropped and named on stderr, every remaining line that looks like a
credential (lessons-learned's ledger_store.find_secret) is replaced by a redaction marker, and material over
--max-bytes (default 200,000) is refused, never truncated. --dry-run prints the prompt and sends nothing.
CLIs, run non-interactively in read-only mode with the prompt on stdin:
  codex   codex exec --sandbox read-only --skip-git-repo-check --color never -
  gemini  gemini -p <instruction>   (never --yolo: the CLI cannot run edit or shell tools unattended)
Exit codes: 0 review printed, 2 usage, git error, nothing to review, refused file or secret check unavailable,
3 no supported CLI installed (nothing sent), 4 material over --max-bytes (nothing sent), 5 the CLI failed or timed out.
Standard library only.
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 200_000
MAX_LINE = 2000  # longer lines are minified or generated: replaced, never scanned or sent
TIMEOUT = 300
CLIS = ("codex", "gemini")
SECRET_NAME = re.compile(  # a file name, not a path: `key` must be its own segment (keys.yaml, not keyboard.ts)
    r"\.env(?:\..*)?|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?|.*\.(?:pem|key|p12|pfx|jks|keystore|gpg|asc)"
    r"|(?:.*[._-])?(?:api[._-]?)?(?:keys?|secrets?|credentials?)(?:[._-].*)?", re.I)
INSTRUCTION = {
    "diff": ("You are a second, independent code reviewer. Read-only: do not run commands, edit files or call "
             "tools. Review the git diff below for correctness bugs, security holes, data loss, race conditions and "
             "missing tests. Report each finding as `severity | file:line | what fails, with a concrete input | fix`, "
             "most severe first. Report only what you can point to in the diff; say `no findings` when there are none."),
    "plan": ("You are a second, independent reviewer of an engineering plan. Read-only: do not run commands, edit "
             "files or call tools. Review the plan below for wrong assumptions, missing steps, risky ordering, "
             "unhandled failure modes and untested claims. Report each finding as `severity | section | problem | "
             "fix`, most severe first; say `no findings` when there are none."),
}


class Refused(Exception):
    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code


def secret_check():
    """lessons-learned's find_secret, shipped beside this skill; None when the install lacks it."""
    scripts = Path(__file__).resolve().parents[2] / "lessons-learned" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        from ledger_store import find_secret
    except ImportError:
        return None
    return find_secret


def looks_secret(path):
    return bool(SECRET_NAME.fullmatch(path.replace("\\", "/").rstrip("/").rpartition("/")[2]))


def git_diff(ref):
    if not ref or ref.startswith("-"):
        raise Refused(f"{ref!r} is not a git ref (a leading '-' would be read as an option)")
    try:
        out = subprocess.run(["git", "-c", "core.quotePath=false", "diff", "--no-color", "--no-ext-diff",
                              "--src-prefix=a/", "--dst-prefix=b/", "--end-of-options", ref, "--"],
                             capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        raise Refused(f"git diff failed: {error}") from error
    if out.returncode != 0:
        raise Refused(f"git diff {ref} failed: {out.stderr.decode('utf-8', 'replace').strip()}")
    return out.stdout.decode("utf-8", "replace")


def drop_secret_files(diff):
    """The diff without the blocks of secret-looking files, and the paths dropped."""
    kept, dropped, keep = [], [], True
    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            path = line.rsplit(" b/", 1)[-1].rstrip('"')
            keep = not looks_secret(path)
            if not keep:
                dropped.append(path)
        if keep:
            kept.append(line)
    return "\n".join(kept), dropped


def redact(text, find_secret):
    """Each line that looks like a credential replaced by a marker that keeps its diff prefix. A line over
    MAX_LINE characters (minified or generated) is replaced unread: the secret check costs too much on it."""
    lines = []
    for line in text.split("\n"):
        reason = f"a line over {MAX_LINE} characters" if len(line) > MAX_LINE else find_secret(line)
        prefix = line[:1] if line[:1] in "+- " and not line.startswith(("+++", "---")) else ""
        lines.append(f"{prefix}[redacted: {reason}]" if reason else line)
    return "\n".join(lines)


def material(args, find_secret):
    """(kind, redacted text) to review; raises Refused."""
    if args.plan:
        if looks_secret(args.plan):
            raise Refused(f"{args.plan} looks like a secrets file; refusing to send it")
        try:
            text = Path(args.plan).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise Refused(f"cannot read {args.plan}: {error}") from error
        kind = "plan"
    else:
        text, dropped = drop_secret_files(git_diff(args.diff))
        for path in dropped:
            print(f"second_opinion: left out {path} (looks like a secrets file)", file=sys.stderr)
        kind = "diff"
    if not text.strip():
        raise Refused("nothing to review")
    for stage in ("raw", "redacted"):  # refused before redaction too: an oversized input must cost nothing
        size = len(text.encode("utf-8"))
        if size > args.max_bytes:
            raise Refused(f"{size} bytes to review is over --max-bytes {args.max_bytes}; narrow the ref or the plan "
                          "(nothing was sent)", code=4)
        if stage == "raw":
            text = redact(text, find_secret)
    return kind, text


def choose_cli(wanted):
    names = CLIS if wanted == "auto" else (wanted,)
    for name in names:
        if shutil.which(name):
            return name
    raise Refused(f"no supported CLI installed ({', '.join(names)}); nothing was sent", code=3)


def command(cli, kind):
    if cli == "codex":
        return ["codex", "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--color", "never", "-"]
    return ["gemini", "-p", INSTRUCTION[kind]]


def prompt(cli, kind, text):
    body = f"```\n{text}\n```\n"
    return f"{INSTRUCTION[kind]}\n\n{body}" if cli == "codex" else body


def ask(cli, kind, text, timeout):
    try:
        out = subprocess.run(command(cli, kind), input=prompt(cli, kind, text), capture_output=True, text=True,
                             timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise Refused(f"{cli} did not answer within {timeout} s", code=5) from error
    except OSError as error:
        raise Refused(f"{cli} could not start: {error}", code=5) from error
    if out.returncode != 0:
        raise Refused(f"{cli} exited {out.returncode}: {out.stderr.strip()[-500:]}", code=5)
    return out.stdout


def parse(argv):
    parser = argparse.ArgumentParser(description="Read-only second review by another coding CLI.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--diff", metavar="REF")
    source.add_argument("--plan", metavar="FILE")
    parser.add_argument("--cli", choices=("auto", *CLIS), default="auto")
    parser.add_argument("--timeout", type=int, default=TIMEOUT)
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.max_bytes <= 0:
        parser.error("--timeout and --max-bytes must be positive")
    return args


def main(argv=None):
    args = parse(argv)
    find_secret = secret_check()
    try:
        if find_secret is None:
            raise Refused("the secret check (lessons-learned/scripts/ledger_store.py) is missing; nothing was sent")
        kind, text = material(args, find_secret)
        if args.dry_run:
            print(prompt("codex", kind, text))
            return 0
        cli = choose_cli(args.cli)
        print(ask(cli, kind, text, args.timeout))
    except Refused as error:
        print(f"second_opinion: {error}", file=sys.stderr)
        return error.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
