#!/usr/bin/env python3
"""A typed SHA where git or GitHub match a commit exactly, for guard_lessons' built-in `typed-sha` rule.

Usage: refused = guard_typed_sha.refused(commands, transcript_path, agent_id=None)  # True or False
       text = guard_typed_sha.plain_quotes(command)  # the command to split into the simple commands judged
commands: (name, operands, args, variables) of each simple command of one Bash call: the program, its leading
operands (guard_lessons.leading_operands: for git from the subcommand on), its words after quote removal, and the
NAME=value words set earlier on the line (guard_lessons.commands). Judged: the value of gh pr merge
--match-head-commit (`V` or `=V`) and the expected value of git push --force-with-lease=<ref>:<V>
(`--force-with-lease <ref>:<V>` is not a form git accepts, so it is not judged), after $NAME and ${NAME} are read
from the line's own assignments (`H=<sha>; ... "$H"`) and an ANSI-C quote holding only hex ($'<sha>') is read as a
plain quote. Only a literal hex value is a typed SHA: one from $(...) or a backtick, or a variable not set on the
line, passes, so a SHA passed from git in the same command (`"$(git rev-parse HEAD)"`) always does.
Refused: (a) a literal --match-head-commit value of fewer than 40 hex characters (GitHub's GraphQL needs the
full object id and refuses it); (b) any value of 7 to 40 hex characters (any case)
that no transcript entry the assistant did not write printed: the seen check, window and budget of
guard_unseen_hash (unseen_tokens, the default window), one read and one budget for the whole call.
(a) needs no transcript; without one, or on any error or timeout of (b), only (a) applies.
"""
import re

import guard_destructive as shell
import guard_unseen_hash

HEX = re.compile(r"[0-9a-fA-F]+")
ANSI_C_HEX = re.compile(r"\$'([0-9a-fA-F]+)'")  # $'<hex>' holds no escape: the same word as '<hex>'
FULL_LENGTH = 40
MERGE_PIN = "--match-head-commit"
LEASE = "--force-with-lease="


def plain_quotes(command):
    """The command with each hex-only ANSI-C quote written as a plain quote, so quote removal keeps its value."""
    return ANSI_C_HEX.sub(r"'\1'", command)


def values(name, operands, args, variables=()):
    """(merge pins, lease values) this command gives, with the line's own variables read."""
    pins, leases = [], []
    if name == "gh" and operands[:2] == ["pr", "merge"]:
        for index, arg in enumerate(args):
            if arg == MERGE_PIN and index + 1 < len(args):
                pins.append(args[index + 1])
            elif arg.startswith(MERGE_PIN + "="):
                pins.append(arg[len(MERGE_PIN) + 1:])
    elif name == "git" and operands[:1] == ["push"]:
        leases = [arg[len(LEASE):].partition(":")[2] for arg in args if arg.startswith(LEASE)]
    return [shell.expand(v, variables) for v in pins], [shell.expand(v, variables) for v in leases]


def refused(commands, transcript_path, agent_id=None):
    """True when the call gives a short merge pin, or a typed SHA no tool output of this session printed."""
    pins, leases = [], []
    for command in commands:
        found = values(*command)
        pins += found[0]
        leases += found[1]
    if any(HEX.fullmatch(pin) and len(pin) < FULL_LENGTH for pin in pins):
        return True
    wanted = list(dict.fromkeys(v.lower() for v in pins + leases
                                if HEX.fullmatch(v) and guard_unseen_hash.PREFIX <= len(v) <= FULL_LENGTH))
    return bool(wanted) and bool(guard_unseen_hash.unseen_tokens(wanted, transcript_path, agent_id=agent_id,
                                                                 partial=False))
