#!/usr/bin/env python3
"""Refuse a kubectl apply into a shared namespace unless a server-side dry run shows no existing object would change.

usage: kube_apply_check.py check -f MANIFEST|- --namespace NS --context CTX [--owner-label key=value]
                                [--allow-update] [--plan OUT.json] [--kubectl-timeout 60] [--overall-timeout 600]
       kube_apply_check.py apply --plan PLAN.json -f MANIFEST|- [--max-age 30m] [--yes] [--kubectl-timeout 120] [--overall-timeout 600]

check: reads MANIFEST once (`-` is stdin, e.g. kustomize or helm output) and sends exactly those bytes on stdin to
`kubectl --context CTX -n NS apply --dry-run=server -o json -f -`. The server's answer (objects after defaulting and
admission; one List, or several concatenated documents) is the object list. This is not a field diff: each object
is looked up with `kubectl get`, and every object that already exists is refused unless --allow-update is given
and the live object carries our --owner-label. Also refused: another namespace, a cluster-scoped kind (or an
object returned without a namespace), a duplicate group/kind/namespace/name, and an empty list. Each object is
reported as NEW, UPDATE-OURS or REFUSED-EXISTING (with the live owner label value or "none"). With --plan, a plan
(context, namespace, manifest sha256, UTC time, per object group, kind, namespace, name, action and live
resourceVersion) is written, only when nothing was refused.
apply: reads the manifest once (sha256 must match the plan), refuses a plan older than --max-age (s, m or h) or
with no objects, re-runs the server-side dry run on those same bytes and refuses unless its objects equal the
plan's, re-reads every live object (resourceVersion unchanged, a NEW object still absent, an owned object still
owned), then prints the command it would run; with --yes it runs `kubectl --context CTX -n NS apply -f -` with the
verified bytes on stdin (client-side, no prune) and checks that every planned object exists afterwards.

--kubectl-timeout bounds each kubectl call; --overall-timeout (seconds, default 600) bounds all kubectl calls of the
run. Exceeded before the write, it is exit 4. The write starts only while a full --kubectl-timeout is still left
(else exit 4, nothing written), so on apply an --overall-timeout not above --kubectl-timeout is exit 2; a lookup after the write that runs out of time is exit 3. kubectl output over 32 MB
is an error (exit 2), and its stderr is cut to 2 KB in messages. kubectl runs in its own process group. On a
timeout or too much output that group is killed, so a child of kubectl (an exec credential plugin) that holds its
pipes cannot stretch the call. A child still holding them 2 s after kubectl exits is killed too. POSIX only; the
group kill is gate_lock.killpg from the quality-gate skill, and without it no kubectl call is made (exit 2).

Limits: resourceVersion changes whenever a controller or status update touches an object, so apply may refuse a
stale plan: run check again. The short window between the last re-check and the apply cannot be closed with
client-side apply.

The context is always explicit; the current context is never used. A context, namespace, kind, apiVersion or name
that is empty or starts with '-' is an error (exit 2), from the command line, the dry run or the plan. --prune, --force, --overwrite,
--force-conflicts, --server-side and --all are never passed. KUBE_CHECK_NOW (ISO 8601) is for tests only: it
fixes the clock and is honoured only when KUBE_CHECK_TEST=1 is also set (otherwise a warning is printed). kubectl is found on PATH. Standard library only.
Exit: 0 ok, 1 refused (nothing was written), 2 usage, IO, kubectl or JSON error before the write, 4 kubectl timeout
before the write, 3 the write may have happened: the real apply, a lookup or the output failed or timed out, or an
object is missing afterwards; inspect the namespace before retrying. Exit 3 is used only after the write started,
and every error after that point is exit 3.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import math
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "quality-gate" / "scripts"))
try:
    from gate_lock import killpg  # refuses pgid <= 1, non-int, our own and our parent's group
except ImportError:  # the quality-gate skill ships beside this one; without it no kubectl call is made
    killpg = None

CLUSTER_SCOPED_KINDS = frozenset({
    "Namespace", "ClusterRole", "ClusterRoleBinding", "CustomResourceDefinition", "PersistentVolume",
    "StorageClass", "PriorityClass", "Node", "APIService", "IngressClass", "RuntimeClass", "CSIDriver",
})
WEBHOOK_KIND = re.compile(r"Webhook.*Configuration")
NEVER_PASSED = frozenset({"--prune", "--force", "--overwrite", "--force-conflicts", "--server-side", "--all"})
AGE = re.compile(r"([0-9]+(?:\.[0-9]+)?)([smh])")
STDERR_LIMIT = 2048
OUTPUT_LIMIT = 32 * 1024 * 1024
READ_SIZE = 65536
EXIT_GRACE = 2  # seconds to wait for the end of output once kubectl has exited
UNITS = {"s": 1, "m": 60, "h": 3600}
NEW, UPDATE_OURS, REFUSED = "NEW", "UPDATE-OURS", "REFUSED-EXISTING"


class Refused(Exception):
    """Exit 1."""


class Failure(Exception):
    """Exit 2: usage, IO, kubectl or JSON error."""


class TimedOut(Exception):
    """Exit 4: kubectl did not answer in time."""


class PartlyApplied(Exception):
    """Exit 3: the write started, so the namespace may be partly changed."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Failure(f"usage: {message}")


def positive_finite(text):
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text}") from None
    if not (math.isfinite(value) and value > 0):
        raise argparse.ArgumentTypeError(f"must be a positive, finite number of seconds: {text}")
    return value


def build_parser():
    parser = Parser(prog="kube_apply_check.py")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("-f", "--filename", required=True)
    check.add_argument("--namespace", "-n", required=True)
    check.add_argument("--context")
    check.add_argument("--owner-label")
    check.add_argument("--allow-update", action="store_true")
    check.add_argument("--plan")
    check.add_argument("--kubectl-timeout", type=positive_finite, default=60)
    check.add_argument("--overall-timeout", type=positive_finite, default=600)
    apply = commands.add_parser("apply")
    apply.add_argument("--plan", required=True)
    apply.add_argument("-f", "--filename", required=True)
    apply.add_argument("--max-age", default="30m")
    apply.add_argument("--yes", action="store_true")
    apply.add_argument("--kubectl-timeout", type=positive_finite, default=120)
    apply.add_argument("--overall-timeout", type=positive_finite, default=600)
    return parser


def now(err):
    raw = os.environ.get("KUBE_CHECK_NOW")
    if raw and os.environ.get("KUBE_CHECK_TEST") != "1":
        err("warning: KUBE_CHECK_NOW ignored: it is for tests and needs KUBE_CHECK_TEST=1")
        raw = None
    if not raw:
        return dt.datetime.now(dt.timezone.utc)
    try:
        moment = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise Failure(f"KUBE_CHECK_NOW is not an ISO 8601 time: {raw}") from None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


class Budget:
    """Per-call timeout, capped by what is left of an optional overall deadline."""

    def __init__(self, per_call, overall=None):
        self.per_call = per_call
        self.deadline = None if overall is None else time.monotonic() + overall
        self.overall = overall

    def next(self):
        if self.deadline is None:
            return self.per_call
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise TimedOut(f"overall deadline of {self.overall:g}s exceeded")
        return min(self.per_call, left)


def stop_group(proc):
    """SIGKILL kubectl's own session group, which also ends the children (exec plugins) that hold its pipes."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        killpg(proc.pid, signal.SIGKILL)


def run_capped(argv, timeout, stdin):
    """(returncode, stdout, stderr, stdout_overflowed): stdout capped at OUTPUT_LIMIT, stderr at STDERR_LIMIT.

    One thread feeds stdin and reads both pipes without blocking, so the call ends by `timeout` even when a
    child of kubectl keeps a pipe open after kubectl is gone."""
    if killpg is None:
        raise Failure("quality-gate/scripts/gate_lock.py is missing: kubectl calls cannot be bounded safely")
    deadline = time.monotonic() + timeout
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            bufsize=0, start_new_session=True)
    kept = {proc.stdout: bytearray(), proc.stderr: bytearray()}
    limits = {proc.stdout: OUTPUT_LIMIT, proc.stderr: STDERR_LIMIT}
    pending, overflowed, exited_at = memoryview(stdin), False, None
    selector = selectors.DefaultSelector()
    try:
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_WRITE if stream is proc.stdin else selectors.EVENT_READ)
        while selector.get_map() and not overflowed:
            moment = time.monotonic()
            if moment >= deadline:
                stop_group(proc)
                raise subprocess.TimeoutExpired(argv, timeout)
            if exited_at is None and proc.poll() is not None:
                exited_at = moment
            if exited_at is not None and moment - exited_at >= EXIT_GRACE:
                stop_group(proc)  # kubectl is gone but a child of it still holds a pipe
                break
            for key, _ in selector.select(min(deadline - moment, 0.1)):
                stream = key.fileobj
                if stream is proc.stdin:
                    try:
                        pending = pending[os.write(key.fd, pending):]
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:  # kubectl stopped reading stdin; its exit code tells why
                        pending = pending[:0]
                    if not pending:
                        selector.unregister(stream)
                        stream.close()
                    continue
                try:
                    chunk = os.read(key.fd, READ_SIZE)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    continue
                buffer, room = kept[stream], limits[stream] - len(kept[stream])
                buffer += chunk[:max(room, 0)]
                if len(chunk) > room >= 0:
                    if stream is proc.stdout:
                        overflowed = True
                        stop_group(proc)
                    else:
                        buffer += b"... (truncated)"
        try:
            proc.wait(timeout=max(deadline - time.monotonic(), 0.01))
        except subprocess.TimeoutExpired:  # kubectl closed its pipes but still runs
            stop_group(proc)
            raise
    finally:
        selector.close()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            stream.close()
        if proc.poll() is None:
            stop_group(proc)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=5)
    return proc.returncode, bytes(kept[proc.stdout]), bytes(kept[proc.stderr]), overflowed


def kubectl(args, timeout, stdin=b""):
    if NEVER_PASSED & {arg.split("=")[0] for arg in args}:
        raise Failure(f"internal error: refusing to pass a forbidden flag: {' '.join(args)}")
    try:
        code, out, err, overflowed = run_capped(["kubectl", *args], timeout, stdin)
    except FileNotFoundError:
        raise Failure("kubectl not found on PATH") from None
    except subprocess.TimeoutExpired:
        raise TimedOut(f"kubectl timed out after {timeout:g}s: {' '.join(args)}") from None
    except OSError as error:
        raise Failure(f"kubectl could not run: {error}") from None
    if overflowed:
        raise Failure(f"kubectl output is over {OUTPUT_LIMIT} bytes: {' '.join(args)}")
    if code:
        raise Failure(f"kubectl failed (rc={code}): {' '.join(args)}\n{err.decode('utf-8', 'replace').strip()}")
    return out.decode("utf-8", "replace")


def parse_json(text, what):
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        raise Failure(f"{what}: kubectl returned invalid JSON") from None


def read_manifest(filename):
    try:
        data = sys.stdin.buffer.read() if filename == "-" else Path(filename).read_bytes()
    except OSError as error:
        raise Failure(f"cannot read manifest {filename}: {error}") from None
    if not data.strip():
        raise Failure(f"manifest {filename} is empty")
    return data


def split_label(text):
    key, sep, value = (text or "").partition("=")
    if not sep or not key or not value:
        raise Failure("--owner-label must be key=value")
    return key, value


def json_documents(text):
    decoder, pos, documents = json.JSONDecoder(), 0, []
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            return documents
        try:
            document, pos = decoder.raw_decode(text, pos)
        except (ValueError, RecursionError):
            raise Failure("dry run: kubectl returned invalid JSON") from None
        documents.append(document)


def reject_flag_like(value, what):
    if not value:
        raise Failure(f"{what} is empty")
    if value.startswith("-"):
        raise Failure(f"{what} {value} starts with '-' and would be read as a kubectl flag")


def dry_run_objects(text):
    items = []
    for document in json_documents(text):
        if not isinstance(document, dict):
            raise Failure("dry run: output holds something that is not an object")
        if document.get("kind") == "List" and isinstance(document.get("items"), list):
            if any(isinstance(i, dict) and i.get("kind") == "List" for i in document["items"]):
                raise Failure("dry run: a List inside a List")
            items.extend(document["items"])
        elif "metadata" in document:
            items.append(document)
        else:
            raise Failure("dry run: output is neither a List nor an object")
    objects = []
    for item in items:
        meta = item.get("metadata") if isinstance(item, dict) else None
        if not isinstance(meta, dict) or not all(isinstance(v, str) for v in (item.get("kind"), item.get("apiVersion"), meta.get("name"))):
            raise Failure("dry run: an object has no kind, apiVersion or metadata.name")
        if not isinstance(meta.get("namespace"), (str, type(None))):
            raise Failure(f"dry run: {item['kind']}/{meta['name']} has a metadata.namespace that is not a string")
        reject_flag_like(item["kind"], "dry run: object kind")
        reject_flag_like(item["apiVersion"], "dry run: object apiVersion")
        reject_flag_like(meta["name"], "dry run: object name")
        api_version = item["apiVersion"]
        group = api_version.partition("/")[0] if "/" in api_version else ""
        objects.append({"kind": item["kind"], "group": group, "name": meta["name"], "namespace": meta.get("namespace")})
    return objects


def identity(obj):
    return (obj["group"], obj["kind"], obj["namespace"], obj["name"])


def server_objects(base, namespace, data, budget):
    """The server-side dry run of exactly `data`, as a checked, non-empty object list."""
    text = kubectl([*base, "apply", "--dry-run=server", "-o", "json", "-f", "-"], budget.next(), data)
    objects = dry_run_objects(text)
    if not objects:
        raise Refused("the dry run returned no objects; nothing to apply")
    problems = scope_problems(objects, namespace)
    if problems:
        raise Refused("\n".join(problems))
    return objects


def scope_problems(objects, namespace):
    problems, seen = [], set()
    for obj in objects:
        label = f"{obj['kind']}/{obj['name']}"
        if obj["kind"] in CLUSTER_SCOPED_KINDS or WEBHOOK_KIND.search(obj["kind"]) or not obj["namespace"]:
            problems.append(f"{label}: cluster-scoped, not allowed in a namespaced apply")
        elif obj["namespace"] != namespace:
            problems.append(f"{label}: namespace {obj['namespace']} is not {namespace}")
        key = identity(obj)
        if key in seen:
            problems.append(f"{label}: duplicate in the manifest")
        seen.add(key)
    return problems


def resource(obj):
    return f"{obj['kind']}.{obj['group']}" if obj["group"] else obj["kind"]


def get_live(obj, base, budget):
    text = kubectl([*base, "get", resource(obj), obj["name"], "-o", "json", "--ignore-not-found"], budget.next())
    if not text.strip():
        return None
    doc = parse_json(text, f"get {obj['kind']}/{obj['name']}")
    if not isinstance(doc, dict) or not isinstance(doc.get("metadata"), dict):
        raise Failure(f"get {obj['kind']}/{obj['name']}: unexpected output")
    return doc


def labels_of(live):
    labels = live["metadata"].get("labels")
    return labels if isinstance(labels, dict) else {}


def classify(live, owner, allow_update):
    value = None if live is None or not owner else labels_of(live).get(owner[0])
    if live is None:
        return NEW, value
    return (UPDATE_OURS if allow_update and value == owner[1] else REFUSED), value


def do_check(options, out, err):
    if not options.context:
        raise Failure("--context is required: the current context is never used implicitly")
    reject_flag_like(options.context, "--context")
    reject_flag_like(options.namespace, "--namespace")
    owner = split_label(options.owner_label) if options.owner_label is not None else None
    if options.allow_update and not owner:
        raise Failure("--allow-update needs --owner-label key=value")
    budget = Budget(options.kubectl_timeout, options.overall_timeout)
    data = read_manifest(options.filename)
    base = ["--context", options.context, "-n", options.namespace]
    objects = server_objects(base, options.namespace, data, budget)
    rows = []
    for obj in objects:
        live = get_live(obj, base, budget)
        action, value = classify(live, owner, options.allow_update)
        rows.append({**obj, "action": action, "owner": value, "resourceVersion": live and live["metadata"].get("resourceVersion")})
    for row in rows:
        out(f"{row['action']:<16} {row['kind']}/{row['name']}" + (f"  owner={row['owner'] or 'none'}" if row["action"] != NEW else ""))
    refused = [row for row in rows if row["action"] == REFUSED]
    if refused:
        raise Refused(f"{len(refused)} existing object(s) not ours would be changed; nothing written")
    if options.plan:
        plan = {
            "context": options.context, "namespace": options.namespace, "owner_label": options.owner_label,
            "manifest_sha256": hashlib.sha256(data).hexdigest(), "created_at": now(err).isoformat(),
            "objects": [{k: row[k] for k in ("group", "kind", "namespace", "name", "action", "resourceVersion")} for row in rows],
        }
        try:
            Path(options.plan).write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        except OSError as error:
            raise Failure(f"cannot write plan {options.plan}: {error}") from None
        out(f"plan written: {options.plan}")
    return 0


def load_plan(path):
    try:
        plan = json.loads(Path(path).read_text(encoding="utf-8"))
        created = dt.datetime.fromisoformat(plan["created_at"])
        for key in ("context", "namespace", "manifest_sha256"):
            if not isinstance(plan[key], str) or not plan[key] or plan[key].startswith("-"):
                raise ValueError(key)
        for obj in plan["objects"]:
            if not all(isinstance(obj[k], str) for k in ("kind", "group", "name", "namespace")) or obj["action"] not in (NEW, UPDATE_OURS):
                raise ValueError("object")
            if not isinstance(obj["resourceVersion"], (str, type(None))):
                raise ValueError("resourceVersion")
            for field in ("kind", "name", "namespace"):
                reject_flag_like(obj[field], f"plan object {field}")
            if obj["group"]:
                reject_flag_like(obj["group"], "plan object group")
        label = plan.get("owner_label")
        if label is not None:
            split_label(label if isinstance(label, str) else "")
    except OSError as error:
        raise Failure(f"cannot read plan {path}: {error}") from None
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError, Failure):
        raise Failure(f"plan {path} is damaged or not a plan from check") from None
    if created.tzinfo is None:
        raise Failure(f"plan {path} has a created_at without a time zone")
    return plan, created


def parse_age(text):
    match = AGE.fullmatch(text)
    if not match or float(match.group(1)) <= 0:
        raise Failure(f"--max-age must look like 30m, 90s or 2h, got {text}")
    try:
        return dt.timedelta(seconds=float(match.group(1)) * UNITS[match.group(2)])
    except OverflowError:
        raise Failure(f"--max-age is too large: {text}") from None


def verify_live(plan, base, budget):
    owner = split_label(plan["owner_label"]) if plan.get("owner_label") else None
    for obj in plan["objects"]:
        live, label = get_live(obj, base, budget), f"{obj['kind']}/{obj['name']}"
        if obj["action"] == NEW:
            if live is not None:
                raise Refused(f"{label}: planned as NEW but now exists; run check again")
        elif live is None:
            raise Refused(f"{label}: planned as an update but is gone; run check again")
        elif live["metadata"].get("resourceVersion") != obj["resourceVersion"]:
            raise Refused(f"{label}: resourceVersion changed since the plan; run check again")
        elif not owner or labels_of(live).get(owner[0]) != owner[1]:
            raise Refused(f"{label}: no longer carries our owner label; run check again")


def do_apply(options, out, err):
    if options.overall_timeout <= options.kubectl_timeout:
        raise Failure("--overall-timeout must be greater than --kubectl-timeout, or the write could never start")
    plan, created = load_plan(options.plan)
    if not plan["objects"]:
        raise Refused(f"plan {options.plan} has no objects")
    max_age, budget = parse_age(options.max_age), Budget(options.kubectl_timeout, options.overall_timeout)
    data = read_manifest(options.filename)
    if hashlib.sha256(data).hexdigest() != plan["manifest_sha256"]:
        raise Refused("manifest changed since the plan was made; run check again")
    age = now(err) - created
    if age < dt.timedelta(0):
        raise Refused(f"plan was created in the future (clock skew?): {options.plan}; run check again")
    if age > max_age:
        raise Refused(f"plan is {age} old (limit {options.max_age}); run check again")
    base = ["--context", plan["context"], "-n", plan["namespace"]]
    planned = sorted(identity(o) for o in plan["objects"])
    if sorted(identity(o) for o in server_objects(base, plan["namespace"], data, budget)) != planned:
        raise Refused("the manifest's dry-run objects differ from the plan; run check again")
    verify_live(plan, base, budget)
    command = [*base, "apply", "-f", "-"]
    if not options.yes:
        out(f"dry run, nothing applied: kubectl {' '.join(command)}  (stdin: the verified bytes of {options.filename})")
        return 0
    if budget.next() < options.kubectl_timeout:
        raise TimedOut(f"less than --kubectl-timeout ({options.kubectl_timeout:g}s) of --overall-timeout is left for the write")
    advice = f"apply may be partly applied: inspect namespace {plan['namespace']} before retrying"
    try:
        out(kubectl(command, budget.next(), data).rstrip())
        missing = [f"{o['kind']}/{o['name']}" for o in plan["objects"] if get_live(o, base, budget) is None]
        if not missing:
            out(f"applied: {len(plan['objects'])} object(s) exist")
    except Exception as error:  # the write has started: whatever fails now, the namespace may be changed
        detail = error if isinstance(error, (Failure, TimedOut)) else f"{type(error).__name__}: {error}"
        raise PartlyApplied(f"{advice}\n{detail}") from None
    if missing:
        raise PartlyApplied(f"{advice}\nmissing after apply: " + ", ".join(missing))
    return 0


def main(argv=None, out=print, err=None):
    err = err or (lambda line: print(line, file=sys.stderr))
    try:
        options = build_parser().parse_args(argv)
        return (do_check if options.command == "check" else do_apply)(options, out, err)
    except SystemExit as exit_request:
        return exit_request.code or 0
    except PartlyApplied as partial:
        err(f"error: {partial}")
        return 3
    except Refused as refusal:
        err(f"refused: {refusal}")
        return 1
    except TimedOut as timeout:
        err(f"error: {timeout}")
        return 4
    except Failure as failure:
        err(f"error: {failure}")
        return 2
    except Exception as unexpected:  # no traceback ever leaves with exit 1
        err(f"error: {type(unexpected).__name__}: {unexpected}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
