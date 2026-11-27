#!/usr/bin/env python3
"""A container started without resource limits, for guard_lessons' opt-in `container-limits` rule.

Usage: text = guard_container_limits.problem(command, entry, parse)   # Bash: None, or the refusal text
Never raises: any error passes the command.
Judged: `docker run`, `docker create`, their `container` forms and the same for podman, without both a memory limit
(-m or --memory above 0) and a CPU limit (--cpus above 0, --cpu-quota above 0, or a non-empty --cpuset-cpus): a
scanner or job without limits can take the whole host. The image is the first word after the options; an image whose
name (the part after the last /, before : or @) is in the entry's "allow" list passes. `docker run --help` passes.
With "compose_project": true in the entry also `docker compose up` and `docker-compose up` without -p or
--project-name (or a non-empty COMPOSE_PROJECT_NAME set on the command or earlier on the line, or a name set in the
compose file's top-level `name:` or in .env / --env-file in the current folder): two runs from one
folder share a project name and collide on container names. Other docker commands (ps, stats, logs, exec, compose
down) pass. Wrappers (sudo, env, timeout), sh -c and eval are looked through by the parser.
The last value of a limit counts (`-m 1g --memory 0` is unlimited); a value built from a variable is not seen.
Not seen: limits set in a compose file or a daemon default, an image or option built from a variable,
`docker service create`, `docker compose run`, podman-compose.
Standard library only.
"""
import os
import re

CONTAINER_TOOLS = frozenset(("docker", "podman"))
DOCKER_VALUE = frozenset(("--host", "--context", "--log-level", "--config", "--tlscacert", "--tlscert", "--tlskey",
                          "--root", "--runroot", "--connection", "--url", "--storage-driver"))
DOCKER_SHORT_VALUE = frozenset("Hcl")
COMPOSE_VALUE = frozenset(("--file", "--project-name", "--profile", "--env-file", "--project-directory", "--parallel",
                           "--ansi", "--progress"))
COMPOSE_SHORT_VALUE = frozenset("fp")
RUN_VALUE = frozenset((
    "--name", "--env", "--env-file", "--volume", "--publish", "--network", "--net", "--entrypoint", "--user",
    "--workdir", "--label", "--label-file", "--hostname", "--domainname", "--add-host", "--cap-add", "--cap-drop",
    "--device", "--dns", "--dns-search", "--dns-option", "--link", "--mount", "--memory", "--memory-swap",
    "--memory-reservation", "--cpus", "--cpu-quota", "--cpu-period", "--cpu-shares", "--cpuset-cpus", "--cpuset-mems",
    "--restart", "--platform", "--pull", "--security-opt", "--shm-size", "--tmpfs", "--ulimit", "--log-driver",
    "--log-opt", "--gpus", "--expose", "--group-add", "--ipc", "--pid", "--uts", "--cgroup-parent", "--runtime",
    "--stop-signal", "--stop-timeout", "--sysctl", "--health-cmd", "--health-interval", "--health-retries",
    "--health-start-period", "--health-timeout", "--pids-limit", "--userns", "--volumes-from", "--attach",
    "--cidfile", "--isolation", "--mac-address", "--oom-score-adj", "--annotation", "--detach-keys", "--blkio-weight",
    "--device-read-bps", "--device-write-bps", "--kernel-memory", "--storage-opt", "--cgroupns", "--ip", "--ip6",
    "--network-alias", "--net-alias", "--memory-swappiness", "--cpu-rt-runtime", "--cpu-rt-period",
    "--device-cgroup-rule", "--link-local-ip", "--blkio-weight-device", "--cpu-count", "--cpu-percent",
    "--device-read-iops", "--device-write-iops", "--health-start-interval", "--volume-driver", "--io-maxbandwidth",
    "--io-maxiops", "--secret", "--tz", "--pod", "--pod-id-file", "--uidmap", "--gidmap", "--subuidname",
    "--subgidname", "--unsetenv", "--authfile", "--env-merge", "--image-volume", "--timeout", "--sdnotify",
    "--umask", "--cgroup-conf", "--decryption-key", "--hooks-dir", "--init-path", "--override-arch", "--override-os",
    "--passwd-entry", "--personality", "--preserve-fds", "--requires", "--retry", "--retry-delay", "--seccomp-policy",
    "--cert-dir", "--creds", "--arch", "--os", "--variant", "--cgroups", "--pidfile", "--conmon-pidfile", "--rdt-class",
    "--systemd", "--health-on-failure", "--health-log-destination", "--health-max-log-count", "--health-max-log-size",
    "--health-startup-cmd", "--health-startup-interval", "--health-startup-retries", "--health-startup-success",
    "--health-startup-timeout", "--hostuser", "--chrootdirs", "--group-entry", "--exit-command-delay"))
RUN_SHORT_VALUE = frozenset("aceghlmpuvw")
POSITIVE = re.compile(r"(\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?[A-Za-z]*")
COMPOSE_FILES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
COMPOSE_NAME = re.compile(r"^name:[ \t]*[^\s#]", re.M)
ENV_NAME = re.compile(r"^[ \t]*(?:export[ \t]+)?COMPOSE_PROJECT_NAME=[ \t]*[^\s#]", re.M)
MAX_FILE_BYTES = 1 << 20
REASON = ("{what}. A container without {missing} can take the whole host. Add {fix}, or list the image in the "
          "entry's \"allow\" when it is meant to run unbounded.")
COMPOSE_REASON = ("`{tool} up` without --project-name: two runs from one folder share a project name and collide on "
                  "container names. Add -p/--project-name <unique name> (or set COMPOSE_PROJECT_NAME).")


def scan(args, long_value, short_value):
    """(options, rest): options as (name, value) pairs up to the first operand or `--`; rest from there on."""
    options, index = [], 0
    while index < len(args):
        word = args[index]
        if word == "--":
            index += 1
            break
        if word.startswith("--"):
            name, equals, value = word.partition("=")
            if not equals and name in long_value:
                index += 1
                value = args[index] if index < len(args) else ""
            options.append((name, value))
        elif word.startswith("-") and len(word) > 1:
            for position in range(1, len(word)):
                letter = word[position]
                if letter in short_value:
                    value = word[position + 1:]
                    value = value.removeprefix("=") if len(value) > 1 else value  # -m=512m is -m 512m
                    if not value:
                        index += 1
                        value = args[index] if index < len(args) else ""
                    options.append(("-" + letter, value))
                    break
                options.append(("-" + letter, ""))
        else:
            break
        index += 1
    return options, args[index:]


def positive(value):
    if "$" in value or "`" in value:
        return True  # built from a variable: not seen, so not refused
    match = POSITIVE.fullmatch(value)
    return bool(match) and float(match.group(1)) > 0


def has_limit(options, names, check=positive):
    """The last value given among `names` passes `check` (Docker honours the last one)."""
    values = [value for name, value in options if name in names]
    return bool(values) and check(values[-1])


def image_name(image):
    """nginx for registry.example/x/nginx:1.2 and for nginx@sha256:..."""
    return re.split(r"[:@]", image.rpartition("/")[2])[0]


def run_problem(args, entry):
    options, rest = scan(args, RUN_VALUE, RUN_SHORT_VALUE)
    if any(name == "--help" for name, _ in options) or not rest or image_name(rest[0]) in entry.get("allow", ()):
        return None
    missing = []
    if not has_limit(options, ("-m", "--memory")):
        missing.append("--memory")
    if not any(has_limit(options, (name,), check) for name, check in
               (("--cpus", positive), ("--cpu-quota", positive), ("--cpuset-cpus", bool))):
        missing.append("--cpus")
    if not missing:
        return None
    return REASON.format(what=f"`run {image_name(rest[0])}` has no {' and no '.join(missing)} limit",
                         missing="a memory or CPU limit", fix=" and ".join(f"{name} <value>" for name in missing))


def file_matches(path, pattern):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return bool(pattern.search(handle.read(MAX_FILE_BYTES)))
    except OSError:
        return False


def name_from_files(options):
    """The project name is set in a compose file (top-level `name:`) or an env file (COMPOSE_PROJECT_NAME=)."""
    base = next((value for name, value in options if name == "--project-directory" and value), "")
    files = [value for name, value in options if name in ("-f", "--file") and value]
    envs = [value for name, value in options if name == "--env-file" and value]
    files = files or [name for name in COMPOSE_FILES if os.path.exists(os.path.join(base, name))][:1]
    envs = envs or [".env"]
    return (any(file_matches(os.path.join(base, path), COMPOSE_NAME) for path in files)
            or any(file_matches(os.path.join(base, path), ENV_NAME) for path in envs))


def compose_problem(tool, args, assignments):
    options, rest = scan(args, COMPOSE_VALUE, COMPOSE_SHORT_VALUE)
    if not rest or rest[0] != "up" or any(word in ("--help", "-h") for word in rest[1:]):
        return None
    if has_limit(options, ("-p", "--project-name"), bool):
        return None
    if any(item.partition("=")[0] == "COMPOSE_PROJECT_NAME" and item.partition("=")[2] for item in assignments):
        return None
    if name_from_files(options):
        return None
    return COMPOSE_REASON.format(tool=tool)


def command_problem(cmd, entry):
    if cmd.name == "docker-compose":
        return compose_problem("docker-compose", cmd.args, cmd.assignments) if entry.get("compose_project") else None
    if cmd.name not in CONTAINER_TOOLS:
        return None
    _, rest = scan(cmd.args, DOCKER_VALUE, DOCKER_SHORT_VALUE)
    if rest[:1] == ["container"]:
        rest = rest[1:]
    if rest[:1] in (["run"], ["create"]):
        return run_problem(rest[1:], entry)
    if rest[:1] == ["compose"] and cmd.name == "docker" and entry.get("compose_project"):
        return compose_problem("docker compose", rest[1:], cmd.assignments)
    return None


def problem(command, entry, parse=None):
    """The refusal text for a container run without limits (or a compose up without a project name), or None."""
    try:
        if not isinstance(command, str) or not isinstance(entry, dict) or not re.search(r"docker|podman", command):
            return None
        if parse is None:
            import guard_lessons  # imported here: guard_lessons imports this module
            parse = guard_lessons.commands
        for cmd in parse(command):
            text = command_problem(cmd, entry)
            if text:
                return text
        return None
    except Exception:  # a guard never refuses for its own fault
        return None
