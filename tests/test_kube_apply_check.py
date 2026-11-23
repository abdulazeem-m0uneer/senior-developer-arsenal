"""kube_apply_check.py: dry-run diff gate and plan-bound apply. A fake `kubectl` on PATH answers; no cluster is touched."""
import hashlib
import io
import json
import os
import stat
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared-infra-changes" / "scripts"))

import kube_apply_check  # noqa: E402

STUB = '''#!/usr/bin/env python3
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
args = " ".join(sys.argv[1:])
stdin = sys.stdin.read() if "-f -" in args else ""
with open(os.path.join(here, "calls.log"), "a", encoding="utf-8") as log:
    log.write(args + "\\n")
with open(os.path.join(here, "stdin.jsonl"), "a", encoding="utf-8") as log:
    log.write(json.dumps({"args": args, "stdin": stdin}) + "\\n")
rules = json.load(open(os.path.join(here, "rules.json"), encoding="utf-8"))
counts_path = os.path.join(here, "counts.json")
counts = json.load(open(counts_path)) if os.path.exists(counts_path) else {}
for index, rule in enumerate(rules):
    if all(part in args for part in rule["match"]) and not any(part in args for part in rule.get("unless", [])):
        seen = counts.get(str(index), 0)
        counts[str(index)] = seen + 1
        json.dump(counts, open(counts_path, "w"))
        time.sleep(rule.get("sleep", 0))
        if "write_file" in rule:
            open(rule["write_file"][0], "w", encoding="utf-8").write(rule["write_file"][1])
        stdout = rule["sequence"][min(seen, len(rule["sequence"]) - 1)] if "sequence" in rule else rule.get("stdout", "")
        sys.stdout.write(stdout)
        sys.stderr.write(rule.get("stderr", ""))
        sys.exit(rule.get("rc", 0))
sys.stderr.write("fake kubectl: no rule for: " + args)
sys.exit(97)
'''

T0 = "2030-01-01T10:00:00+00:00"
CTX, NS = "ctx-a", "shared"
OWNER = "owner=us"


def obj(kind, name, namespace=NS, api="apps/v1", labels=None, rv=None):
    meta = {"name": name}
    if namespace:
        meta["namespace"] = namespace
    if labels:
        meta["labels"] = labels
    if rv:
        meta["resourceVersion"] = rv
    return {"apiVersion": api, "kind": kind, "metadata": meta}


def dry_run(*items):
    return json.dumps({"apiVersion": "v1", "kind": "List", "items": list(items)})


class FakeKubectl:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        script = self.dir / "kubectl"
        script.write_text(STUB, encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.rules([])

    def rules(self, rules):
        """Replace the rules and the per-rule counters; the call log is kept."""
        (self.dir / "rules.json").write_text(json.dumps(rules), encoding="utf-8")
        (self.dir / "counts.json").write_text("{}", encoding="utf-8")

    def calls(self):
        log = self.dir / "calls.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def forget_calls(self):
        (self.dir / "calls.log").unlink(missing_ok=True)
        (self.dir / "stdin.jsonl").unlink(missing_ok=True)

    def stdin_of(self, part):
        """The stdin of every call whose arguments contain `part` and that is not a dry run, as bytes."""
        log = self.dir / "stdin.jsonl"
        rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        return [r["stdin"].encode() for r in rows if part in r["args"]]


class KubeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.kubectl = FakeKubectl(self.root / "bin")
        self.manifest = self.root / "m.yaml"
        self.manifest.write_text("kind: Deployment\nname: web\n", encoding="utf-8")
        self.plan = self.root / "plan.json"
        env = {"PATH": f"{self.kubectl.dir}{os.pathsep}{os.environ.get('PATH', '')}", "KUBE_CHECK_NOW": T0, "KUBE_CHECK_TEST": "1"}
        patcher = unittest.mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cmd(self, *args, stdin=None):
        out, err = [], []
        with unittest.mock.patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin or b""))):
            code = kube_apply_check.main(list(args), out=out.append, err=err.append)
        return code, "\n".join(out), "\n".join(err)

    def check(self, *extra, manifest=None, context=CTX):
        args = ["check", "-f", str(manifest or self.manifest), "--namespace", NS, *extra]
        return self.run_cmd(*(args + ["--context", context] if context else args))

    def serve(self, items, live=None, **extra):
        """Dry run returns `items`; `live` maps 'Kind.group name' (or 'Kind name') to the live object (absent: not found)."""
        rules = [{"match": ["--dry-run=server"], "stdout": dry_run(*items), **extra}]
        for item in items:
            group = item["apiVersion"].partition("/")[0] if "/" in item["apiVersion"] else ""
            res = f"{item['kind']}.{group}" if group else item["kind"]
            found = (live or {}).get(item["metadata"]["name"])
            found = found if found and found["kind"] == item["kind"] else None
            rules.append({"match": [f"get {res} {item['metadata']['name']} "], "stdout": json.dumps(found) if found else ""})
        self.kubectl.rules(rules)

    def plan_data(self):
        return json.loads(self.plan.read_text(encoding="utf-8"))

    def apply_calls(self):
        return [c for c in self.kubectl.calls() if " apply " in c and "--dry-run" not in c]


class CheckTests(KubeTestCase):
    def test_all_new_is_ok_and_runs_the_exact_dry_run(self):
        self.serve([obj("Deployment", "web"), obj("Service", "web", api="v1")])
        code, out, err = self.check()
        self.assertEqual((code, err), (0, ""))
        self.assertIn("NEW", out)
        self.assertEqual(self.kubectl.calls()[0], f"--context {CTX} -n {NS} apply --dry-run=server -o json -f -")
        self.assertEqual(self.kubectl.stdin_of("--dry-run=server"), [self.manifest.read_bytes()])
        self.assertIn(f"--context {CTX} -n {NS} get Deployment.apps web -o json --ignore-not-found", self.kubectl.calls())
        self.assertIn(f"--context {CTX} -n {NS} get Service web -o json --ignore-not-found", self.kubectl.calls())

    def test_single_object_output_not_a_list_is_read(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": json.dumps(obj("Deployment", "web"))},
                            {"match": ["get Deployment.apps web"], "stdout": ""}])
        self.assertEqual(self.check()[0], 0)

    def test_existing_foreign_object_is_refused_with_its_owner(self):
        self.serve([obj("Deployment", "web")], live={"web": obj("Deployment", "web", labels={"owner": "team-b"}, rv="7")})
        code, out, err = self.check("--owner-label", OWNER, "--allow-update", "--plan", str(self.plan))
        self.assertEqual(code, 1)
        self.assertIn("REFUSED-EXISTING", out)
        self.assertIn("owner=team-b", out)
        self.assertIn("refused", err)
        self.assertFalse(self.plan.exists())

    def test_existing_unlabelled_object_shows_owner_none(self):
        self.serve([obj("Deployment", "web")], live={"web": obj("Deployment", "web", rv="7")})
        code, out, _ = self.check("--owner-label", OWNER)
        self.assertEqual(code, 1)
        self.assertIn("owner=none", out)

    def test_existing_object_without_owner_label_option_is_refused(self):
        self.serve([obj("Deployment", "web")], live={"web": obj("Deployment", "web", labels={"owner": "us"}, rv="7")})
        self.assertEqual(self.check()[0], 1)

    def test_existing_ours_is_refused_without_allow_update(self):
        self.serve([obj("Deployment", "web")], live={"web": obj("Deployment", "web", labels={"owner": "us"}, rv="7")})
        code, out, _ = self.check("--owner-label", OWNER)
        self.assertEqual(code, 1)
        self.assertIn("REFUSED-EXISTING", out)

    def test_existing_ours_is_allowed_with_allow_update_and_planned_with_its_resource_version(self):
        self.serve([obj("Deployment", "web"), obj("Service", "web", api="v1")],
                   live={"web": obj("Deployment", "web", labels={"owner": "us"}, rv="7")})
        code, out, _ = self.check("--owner-label", OWNER, "--allow-update", "--plan", str(self.plan))
        self.assertEqual(code, 0)
        self.assertIn("UPDATE-OURS", out)
        rows = {row["kind"]: row for row in self.plan_data()["objects"]}
        self.assertEqual((rows["Deployment"]["action"], rows["Deployment"]["resourceVersion"]), ("UPDATE-OURS", "7"))
        self.assertEqual((rows["Service"]["action"], rows["Service"]["resourceVersion"]), ("NEW", None))

    def test_one_foreign_among_ours_refuses_the_whole_check(self):
        self.serve([obj("Deployment", "web"), obj("ConfigMap", "cfg", api="v1")],
                   live={"web": obj("Deployment", "web", labels={"owner": "us"}), "cfg": obj("ConfigMap", "cfg", api="v1")})
        self.assertEqual(self.check("--owner-label", OWNER, "--allow-update")[0], 1)

    def test_allow_update_without_owner_label_is_a_usage_error(self):
        self.serve([obj("Deployment", "web")])
        code, _, err = self.check("--allow-update")
        self.assertEqual(code, 2)
        self.assertIn("--owner-label", err)

    def test_malformed_owner_label_is_a_usage_error(self):
        self.serve([obj("Deployment", "web")])
        for bad in ("owner", "=us", "owner="):
            with self.subTest(bad=bad):
                self.assertEqual(self.check("--owner-label", bad)[0], 2)

    def test_object_in_another_namespace_is_refused(self):
        self.serve([obj("Deployment", "web", namespace="other")])
        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("other", err)

    def test_cluster_scoped_kinds_are_refused(self):
        kinds = [*kube_apply_check.CLUSTER_SCOPED_KINDS, "ValidatingWebhookConfiguration", "MutatingWebhookConfiguration"]
        for kind in kinds:
            with self.subTest(kind=kind):
                self.serve([obj(kind, "x", namespace=NS)])
                code, _, err = self.check()
                self.assertEqual(code, 1)
                self.assertIn("cluster-scoped", err)

    def test_the_cluster_scoped_list_covers_the_required_kinds(self):
        required = {"Namespace", "ClusterRole", "ClusterRoleBinding", "CustomResourceDefinition", "PersistentVolume", "StorageClass", "PriorityClass",
                    "Node", "APIService", "IngressClass", "RuntimeClass", "CSIDriver"}
        self.assertLessEqual(required, kube_apply_check.CLUSTER_SCOPED_KINDS)

    def test_object_returned_without_a_namespace_is_refused(self):
        self.serve([obj("Widget", "w", namespace=None, api="example.com/v1")])
        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("cluster-scoped", err)

    def test_duplicate_kind_namespace_name_is_refused(self):
        self.serve([obj("Deployment", "web"), obj("Deployment", "web"), obj("Service", "web", api="v1")])
        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("duplicate", err)

    def test_same_name_with_different_kinds_is_not_a_duplicate(self):
        self.serve([obj("Deployment", "web"), obj("Service", "web", api="v1")])
        self.assertEqual(self.check()[0], 0)

    def test_failing_dry_run_is_exit_2_with_kubectl_stderr_and_no_lookup(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "rc": 1, "stderr": "Error from server (Forbidden): nope"}])
        code, _, err = self.check()
        self.assertEqual(code, 2)
        self.assertIn("Error from server (Forbidden): nope", err)
        self.assertEqual(len(self.kubectl.calls()), 1)

    def test_kubectl_timeout_is_exit_4(self):
        self.serve([obj("Deployment", "web")], sleep=5)
        self.assertEqual(self.check("--kubectl-timeout", "0.3")[0], 4)

    def test_timeout_on_a_lookup_is_exit_4(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": dry_run(obj("Deployment", "web"))},
                            {"match": ["get Deployment"], "sleep": 5}])
        self.assertEqual(self.check("--kubectl-timeout", "0.3")[0], 4)

    def test_missing_or_empty_context_is_exit_2_and_calls_nothing(self):
        self.serve([obj("Deployment", "web")])
        for context in (None, ""):
            with self.subTest(context=context):
                code, _, err = self.check(context=context)
                self.assertEqual(code, 2)
                self.assertIn("--context", err)
        self.assertEqual(self.kubectl.calls(), [])

    def test_missing_manifest_file_is_exit_2(self):
        self.assertEqual(self.check(manifest=self.root / "nope.yaml")[0], 2)

    def test_empty_manifest_is_exit_2(self):
        self.manifest.write_text("  \n", encoding="utf-8")
        self.serve([obj("Deployment", "web")])
        code, _, err = self.check()
        self.assertEqual(code, 2)
        self.assertIn("is empty", err)
        self.assertEqual(self.kubectl.calls(), [])

    def test_kubectl_missing_from_path_is_exit_2(self):
        with unittest.mock.patch.dict(os.environ, {"PATH": str(self.root / "empty")}):
            code, _, err = self.check()
        self.assertEqual(code, 2)
        self.assertIn("kubectl not found", err)

    def test_stdin_manifest_is_hashed_and_piped_to_the_dry_run(self):
        self.serve([obj("Deployment", "web")])
        body = b"kind: Deployment\nmetadata: {name: web}\n"
        code, _, _ = self.run_cmd("check", "-f", "-", "--namespace", NS, "--context", CTX, "--plan", str(self.plan), stdin=body)
        self.assertEqual(code, 0)
        self.assertTrue(self.kubectl.calls()[0].endswith("-f -"))
        self.assertEqual(self.kubectl.stdin_of("--dry-run=server"), [body])
        self.assertEqual(self.plan_data()["manifest_sha256"], hashlib.sha256(body).hexdigest())

    def test_plan_is_written_with_context_namespace_hash_and_clock(self):
        self.serve([obj("Deployment", "web")])
        code, out, _ = self.check("--plan", str(self.plan))
        data = self.plan_data()
        self.assertEqual(code, 0)
        self.assertEqual((data["context"], data["namespace"], data["created_at"]), (CTX, NS, T0))
        self.assertEqual(data["manifest_sha256"], hashlib.sha256(self.manifest.read_bytes()).hexdigest())
        self.assertEqual(data["objects"], [{"kind": "Deployment", "group": "apps", "name": "web", "namespace": NS, "action": "NEW", "resourceVersion": None}])
        self.assertIn(str(self.plan), out)

    def test_no_plan_file_without_the_option(self):
        self.serve([obj("Deployment", "web")])
        self.check()
        self.assertEqual(list(self.root.glob("*.json")), [])

    def test_unwritable_plan_path_is_exit_2(self):
        self.serve([obj("Deployment", "web")])
        code, _, err = self.check("--plan", str(self.root / "no-dir" / "p.json"))
        self.assertEqual(code, 2)
        self.assertIn("cannot write plan", err)

    def test_concatenated_documents_and_mixed_lists_are_read(self):
        web, svc, cfg = obj("Deployment", "web"), obj("Service", "web", api="v1"), obj("ConfigMap", "cfg", api="v1")
        outputs = {"bare documents": "\n".join(json.dumps(o) for o in (web, svc, cfg)),
                   "list then bare": dry_run(web, svc) + "\n" + json.dumps(cfg),
                   "bare then list": json.dumps(web) + dry_run(svc, cfg)}
        for name, text in outputs.items():
            with self.subTest(name=name):
                self.kubectl.forget_calls()
                self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": text}, {"match": ["get "], "stdout": ""}])
                code, out, _ = self.check("--plan", str(self.plan))
                self.assertEqual(code, 0)
                self.assertEqual([r["name"] for r in self.plan_data()["objects"]], ["web", "web", "cfg"])
                self.assertEqual(len(self.kubectl.calls()), 4)

    def test_trailing_garbage_after_a_document_is_exit_2(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": dry_run(obj("Deployment", "web")) + "\nWARNING: x"}])
        self.assertEqual(self.check()[0], 2)

    def test_empty_object_list_is_refused(self):
        for text in (dry_run(), "", "  \n"):
            with self.subTest(text=text):
                self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": text}])
                code, _, err = self.check("--plan", str(self.plan))
                self.assertIn(code, (1, 2))
                self.assertFalse(self.plan.exists())
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": dry_run()}])
        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("no objects", err)

    def test_same_kind_namespace_name_in_different_groups_is_not_a_duplicate(self):
        self.serve([obj("Widget", "w", api="example.com/v1"), obj("Widget", "w", api="other.io/v1")])
        self.assertEqual(self.check()[0], 0)

    def test_bad_kubectl_timeout_values_are_exit_2(self):
        self.serve([obj("Deployment", "web")])
        for bad in ("nan", "inf", "-inf", "0", "-1", "abc"):
            with self.subTest(bad=bad):
                code, _, err = self.check(f"--kubectl-timeout={bad}")
                self.assertEqual(code, 2)
                self.assertRegex(err, "positive, finite|not a number")
        self.assertEqual(self.kubectl.calls(), [])

    def test_an_unexpected_exception_is_exit_2_not_a_traceback(self):
        with unittest.mock.patch.object(kube_apply_check, "do_check", side_effect=RuntimeError("kaboom")):
            code, _, err = self.check()
        self.assertEqual(code, 2)
        self.assertIn("kaboom", err)

    def test_object_with_its_own_items_field_is_looked_up_not_read_as_a_list(self):
        foo = {**obj("Foo", "f", api="example.com/v1"), "items": ["a", "b"]}
        live = obj("Foo", "f", api="example.com/v1", labels={"owner": "team-b"}, rv="3")
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": json.dumps(foo)},  # one object: kubectl prints it bare
                            {"match": ["get Foo.example.com f "], "stdout": json.dumps(live)}])
        code, out, _ = self.check("--owner-label", OWNER)
        self.assertEqual(code, 1)
        self.assertIn("REFUSED-EXISTING", out)
        self.assertIn(f"--context {CTX} -n {NS} get Foo.example.com f -o json --ignore-not-found", self.kubectl.calls())

    def test_a_namespace_that_is_not_a_string_is_exit_2_with_a_clear_message(self):
        for namespace in (["shared"], {"a": 1}, 5):
            with self.subTest(namespace=namespace):
                item = {**obj("Deployment", "web"), "metadata": {"name": "web", "namespace": namespace}}
                self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": dry_run(item)}])
                code, _, err = self.check()
                self.assertEqual(code, 2)
                self.assertIn("Deployment/web has a metadata.namespace that is not a string", err)

    def test_a_list_nested_in_a_list_is_exit_2(self):
        inner = {"apiVersion": "v1", "kind": "List", "items": [obj("Deployment", "web")]}
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": json.dumps({"apiVersion": "v1", "kind": "List", "items": [inner]})}])
        code, _, err = self.check()
        self.assertEqual(code, 2)
        self.assertIn("List inside a List", err)

    def test_a_list_whose_items_is_not_a_list_is_rejected_as_such(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": '{"kind": "List", "items": 4}'}])
        code, _, err = self.check()
        self.assertEqual(code, 2)
        self.assertIn("neither a List nor an object", err)

    def test_only_kind_list_is_unwrapped_other_list_kinds_without_metadata_are_exit_2(self):
        text = json.dumps({"apiVersion": "apps/v1", "kind": "DeploymentList", "items": [obj("Deployment", "web")]})
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": text}, {"match": ["get "], "stdout": ""}])
        self.assertEqual(self.check()[0], 2)

    def test_custom_kinds_ending_in_list_are_objects_that_get_looked_up_and_refused(self):
        live = obj("WishList", "w", api="example.com/v1", labels={"owner": "team-b"}, rv="3")
        for name, items in (("empty items", []), ("object-shaped items", [obj("Deployment", "x")])):
            with self.subTest(name=name):
                self.kubectl.forget_calls()
                wish = {**obj("WishList", "w", api="example.com/v1"), "items": items}
                self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": json.dumps(wish)},
                                    {"match": ["get WishList.example.com w "], "stdout": json.dumps(live)}])
                code, out, _ = self.check("--owner-label", OWNER)
                self.assertEqual(code, 1)
                self.assertIn("REFUSED-EXISTING", out)
                self.assertTrue(any("get WishList.example.com w " in c for c in self.kubectl.calls()))

    def test_check_uses_the_given_context_and_namespace_in_every_call(self):
        self.serve([obj("Deployment", "web", namespace="team-x"), obj("Service", "web", namespace="team-x", api="v1")])
        code, _, _ = self.run_cmd("check", "-f", str(self.manifest), "--namespace", "team-x", "--context", "ctx-b", "--plan", str(self.plan))
        self.assertEqual(code, 0)
        self.assertEqual(len(self.kubectl.calls()), 3)
        self.assertTrue(all(c.startswith("--context ctx-b -n team-x ") for c in self.kubectl.calls()), self.kubectl.calls())
        self.assertEqual((self.plan_data()["context"], self.plan_data()["namespace"]), ("ctx-b", "team-x"))

    def test_recursion_depth_bombs_give_the_invalid_json_message(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": "[" * 200000}])
        code, _, err = self.check()
        self.assertEqual((code, "invalid JSON" in err), (2, True))
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": dry_run(obj("Deployment", "web"))},
                            {"match": ["get "], "stdout": "[" * 200000}])
        code, _, err = self.check()
        self.assertEqual((code, "invalid JSON" in err), (2, True))

    def test_kubectl_stderr_is_truncated_to_2kb(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "rc": 1, "stderr": "E" * 6000}])
        code, _, err = self.check()
        self.assertEqual(code, 2)
        self.assertLess(len(err), 2600)
        self.assertIn("truncated", err)

    def test_overall_timeout_across_calls_is_exit_4(self):
        items = [obj("ConfigMap", f"c{i}", api="v1") for i in range(6)]
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": dry_run(*items)}, {"match": ["get "], "stdout": "", "sleep": 0.5}])
        code, _, err = self.check("--kubectl-timeout", "5", "--overall-timeout", "1")
        self.assertEqual(code, 4)
        self.assertLess(len(self.kubectl.calls()), 6)

    def test_an_exhausted_budget_raises_the_overall_deadline_error(self):
        budget = kube_apply_check.Budget(5, overall=0.01)
        time.sleep(0.05)
        with self.assertRaisesRegex(kube_apply_check.TimedOut, "overall deadline of 0.01s"):
            budget.next()
        self.assertEqual(kube_apply_check.Budget(5).next(), 5)
        self.assertLessEqual(kube_apply_check.Budget(5, overall=1).next(), 1)

    def test_bad_overall_timeout_is_exit_2(self):
        for bad in ("nan", "inf", "0", "-1", "abc"):
            with self.subTest(bad=bad):
                self.assertEqual(self.check(f"--overall-timeout={bad}")[0], 2)

    def test_names_that_look_like_flags_are_exit_2(self):
        for name in ("-o", "--all", "-"):
            with self.subTest(name=name):
                self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": dry_run(obj("Deployment", name))}])
                code, _, err = self.check()
                self.assertEqual(code, 2)
                self.assertIn("starts with '-'", err)
        self.assertEqual(len(self.kubectl.calls()), 3)

    def test_a_cluster_scoped_crd_kind_missing_from_the_list_is_refused_because_it_has_no_namespace(self):
        self.assertNotIn("ClusterWidget", kube_apply_check.CLUSTER_SCOPED_KINDS)
        self.serve([obj("ClusterWidget", "w", namespace=None, api="example.com/v1")])
        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("ClusterWidget/w: cluster-scoped", err)

    def test_the_test_clock_is_honoured_only_with_the_test_flag(self):
        self.serve([obj("Deployment", "web")])
        with unittest.mock.patch.dict(os.environ):
            os.environ.pop("KUBE_CHECK_TEST")
            code, _, err = self.check("--plan", str(self.plan))
        self.assertEqual(code, 0)
        self.assertIn("KUBE_CHECK_NOW ignored", err)
        self.assertNotEqual(self.plan_data()["created_at"], T0)

    def test_garbage_dry_run_json_is_exit_2(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": "{not json"}])
        code, _, err = self.check()
        self.assertEqual(code, 2)
        self.assertIn("invalid JSON", err)

    def test_dry_run_json_of_the_wrong_shape_is_exit_2(self):
        for body in ("[]", "3", '{"kind": "List", "items": 4}', '{"items": [{"kind": "Deployment"}]}', '{"items": [{"metadata": {"name": "x"}}]}'):
            with self.subTest(body=body):
                self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": body}])
                self.assertEqual(self.check()[0], 2)

    def test_garbage_live_object_json_is_exit_2(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": dry_run(obj("Deployment", "web"))},
                            {"match": ["get Deployment"], "stdout": "<html>"}])
        self.assertEqual(self.check()[0], 2)

    def test_live_object_without_metadata_is_exit_2(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": dry_run(obj("Deployment", "web"))},
                            {"match": ["get Deployment"], "stdout": "{}"}])
        self.assertEqual(self.check()[0], 2)

    def test_no_forbidden_flag_is_ever_passed(self):
        self.serve([obj("Deployment", "web")], live={"web": obj("Deployment", "web", labels={"owner": "us"}, rv="1")})
        self.check("--owner-label", OWNER, "--allow-update", "--plan", str(self.plan))
        for call in self.kubectl.calls():
            for flag in ("--prune", "--force", "--overwrite", "--server-side", "--all", "--force-conflicts"):
                self.assertNotIn(flag, call)
        self.assertEqual(self.apply_calls(), [])

    def test_the_guard_refuses_a_forbidden_flag(self):
        flags = [*sorted(kube_apply_check.NEVER_PASSED), "--force=true", "--prune=true"]
        for args in (["apply", flag] for flag in flags):
            with self.subTest(args=args), self.assertRaisesRegex(kube_apply_check.Failure, "forbidden flag"):
                kube_apply_check.kubectl(args, 1)
        self.assertEqual(self.kubectl.calls(), [])

    def test_context_or_namespace_that_look_like_flags_or_are_empty_are_exit_2_and_call_nothing(self):
        self.serve([obj("Deployment", "web")])
        for args in (["--namespace=-o", "--context", CTX], ["--namespace=", "--context", CTX], ["--namespace", NS, "--context=-o"]):
            with self.subTest(args=args):
                code, _, err = self.run_cmd("check", "-f", str(self.manifest), *args)
                self.assertEqual(code, 2)
                self.assertRegex(err, "starts with '-'|is empty")
        self.assertEqual(self.kubectl.calls(), [])

    def test_empty_owner_label_is_a_usage_error_not_ignored(self):
        self.serve([obj("Deployment", "web")])
        code, _, err = self.check("--owner-label=", "--plan", str(self.plan))
        self.assertEqual(code, 2)
        self.assertIn("key=value", err)
        self.assertFalse(self.plan.exists())

    def test_kinds_and_api_versions_that_look_like_flags_or_are_missing_are_exit_2(self):
        bad = [obj("-o", "web"), obj("Deployment", "web", api="-o"), {"kind": "Deployment", "metadata": {"name": "web", "namespace": NS}},
               obj("Deployment", "")]
        for item in bad:
            with self.subTest(item=item):
                self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": dry_run(item)}, {"match": ["get "], "stdout": ""}])
                self.assertEqual(self.check()[0], 2)
        self.assertFalse(any(" get " in c for c in self.kubectl.calls()))

    def test_the_kubeconfig_current_context_is_never_read_or_used(self):
        self.kubectl.rules([{"match": ["config"], "stdout": "ctx-b\n"},
                            {"match": ["--dry-run=server"], "stdout": dry_run(obj("Deployment", "web"))}, {"match": ["get "], "stdout": ""}])
        self.assertEqual(self.check()[0], 0)
        self.assertTrue(all(c.startswith(f"--context {CTX} -n {NS} ") for c in self.kubectl.calls()), self.kubectl.calls())
        self.assertFalse(any("ctx-b" in c or "config" in c for c in self.kubectl.calls()))

    def test_stdout_over_the_output_limit_is_exit_2(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": dry_run(*[obj("ConfigMap", f"c{i}", api="v1") for i in range(50)])}])
        with unittest.mock.patch.object(kube_apply_check, "OUTPUT_LIMIT", 1000):
            code, _, err = self.check()
        self.assertEqual(code, 2)
        self.assertIn("output is over 1000 bytes", err)
        self.assertFalse(any(" get " in c for c in self.kubectl.calls()))

    def test_stderr_under_the_limit_is_kept_whole(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "rc": 1, "stderr": "E" * 2048}])
        code, _, err = self.check()
        self.assertEqual(code, 2)
        self.assertIn("E" * 2048, err)
        self.assertNotIn("truncated", err)

    def test_usage_errors_are_exit_2_without_a_traceback(self):
        for args in ([], ["check"], ["check", "-f", "x"], ["apply"], ["bogus"], ["apply", "--plan", "p", "-f", "x", "--nope"]):
            with self.subTest(args=args):
                self.assertEqual(self.run_cmd(*args)[0], 2)


class ApplyTests(KubeTestCase):
    def setUp(self):
        super().setUp()
        self.items = [obj("Deployment", "web"), obj("Service", "web", api="v1")]
        self.ours = obj("Deployment", "web", labels={"owner": "us"}, rv="7")
        self.serve(self.items, live={"web": None})
        self.dry = {"match": ["--dry-run=server"], "stdout": dry_run(*self.items)}
        self.make_plan()

    def make_plan(self, ours=False):
        live = {"web": self.ours} if ours else {}
        self.serve(self.items, live=live)
        self.assertEqual(self.check("--owner-label", OWNER, "--allow-update", "--plan", str(self.plan))[0], 0)
        self.kubectl.forget_calls()

    def serve_live(self, deployment=None, service=None):
        """Live state seen by apply: get lookups only (apply itself falls through to a rule for the real apply)."""
        self.kubectl.rules([
            self.dry,
            {"match": ["get Deployment.apps web"], "stdout": json.dumps(deployment) if deployment else ""},
            {"match": ["get Service web"], "stdout": json.dumps(service) if service else ""},
            {"match": [" apply -f"], "stdout": "deployment.apps/web configured\n"},
        ])

    def apply(self, *extra, **kw):
        return self.run_cmd("apply", "--plan", str(self.plan), "-f", str(self.manifest), *extra, **kw)

    def set_now(self, value):
        os.environ["KUBE_CHECK_NOW"] = value

    def test_dry_run_without_yes_prints_the_command_and_runs_no_apply(self):
        self.serve_live()
        code, out, _ = self.apply()
        self.assertEqual(code, 0)
        self.assertIn(f"kubectl --context {CTX} -n {NS} apply -f -", out)
        self.assertIn(str(self.manifest), out)
        self.assertEqual(self.apply_calls(), [])
        self.assertTrue(all(" get " in c or "--dry-run=server" in c for c in self.kubectl.calls()))

    def test_yes_runs_exactly_apply_f_and_rechecks_existence(self):
        self.kubectl.rules([
            self.dry,
            {"match": ["get Deployment.apps web"], "sequence": ["", json.dumps(self.ours)]},
            {"match": ["get Service web"], "sequence": ["", json.dumps(obj("Service", "web", api="v1"))]},
            {"match": [" apply -f"], "stdout": "ok\n"},
        ])
        code, out, _ = self.apply("--yes")
        self.assertEqual(code, 0)
        self.assertEqual(self.apply_calls(), [f"--context {CTX} -n {NS} apply -f -"])
        for call in self.kubectl.calls():
            for flag in ("--prune", "--force", "--overwrite", "--server-side", "--all"):
                self.assertNotIn(flag, call)
        self.assertEqual(sum(" get " in c for c in self.kubectl.calls()), 4)
        self.assertEqual(self.kubectl.stdin_of(" apply -f -"), [self.manifest.read_bytes()])
        self.assertEqual(self.kubectl.stdin_of("--dry-run=server"), [self.manifest.read_bytes()])
        self.assertIn("applied: 2", out)

    def test_yes_fails_when_a_planned_object_is_missing_afterwards(self):
        self.serve_live()
        code, _, err = self.apply("--yes")
        self.assertEqual(code, 3)
        self.assertIn("missing after apply", err)
        self.assertIn(f"inspect namespace {NS}", err)

    def test_failing_kubectl_apply_is_exit_3_with_its_stderr(self):
        self.kubectl.rules([self.dry, {"match": ["get "], "stdout": ""}, {"match": [" apply -f"], "rc": 1, "stderr": "boom"}])
        code, _, err = self.apply("--yes")
        self.assertEqual((code, "boom" in err), (3, True))
        self.assertIn(f"apply may be partly applied: inspect namespace {NS} before retrying", err)

    def test_kubectl_apply_timeout_is_exit_3(self):
        self.kubectl.rules([self.dry, {"match": ["get "], "stdout": ""}, {"match": [" apply -f"], "sleep": 5}])
        code, _, err = self.apply("--yes", "--kubectl-timeout", "0.3")
        self.assertEqual(code, 3)
        self.assertIn("partly applied", err)

    def test_failures_before_the_write_keep_their_ordinary_codes(self):
        cases = [("dry run fails", [{"match": ["--dry-run=server"], "rc": 1, "stderr": "no"}], 2),
                 ("get fails", [self.dry, {"match": ["get "], "rc": 1, "stderr": "no"}], 2),
                 ("get times out", [self.dry, {"match": ["get "], "sleep": 5}], 4)]
        for name, rules, want in cases:
            with self.subTest(name=name):
                self.kubectl.rules(rules)
                code, _, err = self.apply("--yes", "--kubectl-timeout", "0.3")
                self.assertEqual(code, want)
                self.assertNotIn("partly applied", err)
                self.assertEqual(self.apply_calls(), [])

    def test_a_failing_lookup_after_the_write_is_exit_3(self):
        self.kubectl.rules([self.dry,
                            {"match": ["get Deployment.apps web"], "sequence": ["", json.dumps(self.ours)]},
                            {"match": ["get Service web"], "sequence": ["", "garbage{"]},
                            {"match": [" apply -f"], "stdout": "ok"}])
        code, _, err = self.apply("--yes")
        self.assertEqual(code, 3)
        self.assertIn("partly applied", err)

    def test_manifest_hash_change_is_refused_and_nothing_runs(self):
        self.serve_live()
        self.manifest.write_text("kind: Deployment\nname: web2\n", encoding="utf-8")
        code, _, err = self.apply("--yes")
        self.assertEqual(code, 1)
        self.assertIn("manifest changed", err)
        self.assertEqual(self.kubectl.calls(), [])

    def test_stale_plan_is_refused_and_exactly_the_limit_is_not(self):
        self.serve_live()
        cases = [("2030-01-01T10:30:00+00:00", 0), ("2030-01-01T10:30:01+00:00", 1), ("2030-01-01T09:59:59+00:00", 1)]
        for now, want in cases:
            with self.subTest(now=now):
                self.set_now(now)
                self.assertEqual(self.apply()[0], want)

    def test_max_age_option_is_honoured(self):
        self.serve_live()
        self.set_now("2030-01-01T10:01:30+00:00")
        self.assertEqual(self.apply("--max-age", "90s")[0], 0)
        self.assertEqual(self.apply("--max-age", "1m")[0], 1)
        self.set_now("2030-01-01T11:30:00+00:00")
        self.assertEqual(self.apply("--max-age", "2h")[0], 0)

    def test_bad_max_age_is_exit_2(self):
        for bad in ("30", "0m", "-5m", "abc", "5d", "30m\n", "\u0663\u0660m"):
            with self.subTest(bad=bad):
                self.assertEqual(self.apply("--max-age", bad)[0], 2)

    def test_changed_resource_version_is_refused(self):
        self.make_plan(ours=True)
        self.serve_live(deployment=obj("Deployment", "web", labels={"owner": "us"}, rv="8"))
        code, _, err = self.apply("--yes")
        self.assertEqual(code, 1)
        self.assertIn("resourceVersion", err)
        self.assertEqual(self.apply_calls(), [])

    def test_same_resource_version_with_our_label_passes_the_recheck(self):
        self.make_plan(ours=True)
        self.serve_live(deployment=self.ours)
        self.assertEqual(self.apply()[0], 0)

    def test_owned_object_that_lost_our_label_is_refused(self):
        self.make_plan(ours=True)
        self.serve_live(deployment=obj("Deployment", "web", labels={"owner": "them"}, rv="7"))
        self.assertEqual(self.apply()[0], 1)

    def test_owned_object_that_vanished_is_refused(self):
        self.make_plan(ours=True)
        self.serve_live()
        self.assertEqual(self.apply()[0], 1)

    def test_new_object_that_appeared_meanwhile_is_refused(self):
        self.serve_live(service=obj("Service", "web", api="v1", rv="3"))
        code, _, err = self.apply("--yes")
        self.assertEqual(code, 1)
        self.assertIn("now exists", err)
        self.assertEqual(self.apply_calls(), [])

    def test_stdin_manifest_is_applied_with_the_same_bytes(self):
        body = b"kind: Deployment\nmetadata: {name: web}\n"
        self.serve(self.items)
        self.run_cmd("check", "-f", "-", "--namespace", NS, "--context", CTX, "--plan", str(self.plan), stdin=body)
        self.kubectl.forget_calls()
        self.kubectl.rules([
            self.dry,
            {"match": ["get Deployment.apps web"], "sequence": ["", json.dumps(self.ours)]},
            {"match": ["get Service web"], "sequence": ["", json.dumps(obj("Service", "web", api="v1"))]},
            {"match": [" apply -f -"], "stdout": "ok\n"},
        ])
        code, _, _ = self.run_cmd("apply", "--plan", str(self.plan), "-f", "-", "--yes", stdin=body)
        self.assertEqual(code, 0)
        self.assertEqual(self.kubectl.stdin_of(" apply -f -"), [body])
        self.assertEqual(self.kubectl.stdin_of("--dry-run=server"), [body])
        self.assertEqual(len(self.apply_calls()), 1)

    def test_file_swapped_after_the_hash_cannot_change_what_is_applied(self):
        original = self.manifest.read_bytes()
        self.kubectl.rules([
            self.dry,
            {"match": ["get Deployment.apps web"], "stdout": "", "write_file": [str(self.manifest), "kind: Secret\nname: evil\n"]},
            {"match": ["get Service web"], "sequence": ["", json.dumps(obj("Service", "web", api="v1"))]},
            {"match": [" apply -f -"], "stdout": "ok\n"},
        ])
        self.apply("--yes")
        self.assertEqual(self.kubectl.stdin_of(" apply -f -"), [original])
        self.assertEqual(self.kubectl.stdin_of("--dry-run=server"), [original])

    def test_forged_plan_with_no_objects_is_refused_without_applying(self):
        forged = {**self.plan_data(), "objects": []}
        self.plan.write_text(json.dumps(forged), encoding="utf-8")
        self.serve_live()
        code, _, err = self.apply("--yes")
        self.assertEqual(code, 1)
        self.assertIn("no objects", err)
        self.assertEqual(self.apply_calls(), [])

    def test_plan_that_differs_from_the_dry_run_objects_is_refused(self):
        good = self.plan_data()
        variants = {
            "fewer": good["objects"][:1],
            "renamed": [{**good["objects"][0], "name": "other"}, good["objects"][1]],
            "namespace": [{**good["objects"][0], "namespace": "elsewhere"}, good["objects"][1]],
            "group": [{**good["objects"][0], "group": "extensions"}, good["objects"][1]],
            "kind": [{**good["objects"][0], "kind": "StatefulSet"}, good["objects"][1]],
        }
        self.serve_live()
        for name, objects in variants.items():
            with self.subTest(name=name):
                self.plan.write_text(json.dumps({**good, "objects": objects}), encoding="utf-8")
                code, _, err = self.apply("--yes")
                self.assertEqual(code, 1)
                self.assertIn("differ from the plan", err)
        self.assertEqual(self.apply_calls(), [])

    def test_manifest_that_now_renders_an_extra_object_is_refused(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": dry_run(*self.items, obj("ConfigMap", "extra", api="v1"))}])
        code, _, err = self.apply("--yes")
        self.assertEqual((code, "differ from the plan" in err), (1, True))
        self.assertEqual(self.apply_calls(), [])

    def test_dry_run_that_now_finds_a_foreign_namespace_is_refused(self):
        self.kubectl.rules([{"match": ["--dry-run=server"], "stdout": dry_run(obj("Deployment", "web", namespace="other"), self.items[1])}])
        self.assertEqual(self.apply("--yes")[0], 1)
        self.assertEqual(self.apply_calls(), [])

    def test_bad_kubectl_timeout_values_are_exit_2_on_apply(self):
        self.serve_live()
        for bad in ("nan", "inf", "-inf", "0", "-1", "abc"):
            with self.subTest(bad=bad):
                code, _, err = self.apply(f"--kubectl-timeout={bad}")
                self.assertEqual(code, 2)
                self.assertRegex(err, "positive, finite|not a number")

    def test_overflowing_max_age_is_exit_2(self):
        for bad in ("9999999999999999h", "9" * 400 + "s"):
            with self.subTest(bad=bad[:20]):
                code, _, err = self.apply("--max-age", bad)
                self.assertEqual(code, 2)
                self.assertIn("too large", err)

    def test_plan_dated_in_the_future_is_refused(self):
        self.serve_live()
        self.set_now("2029-12-31T10:00:00+00:00")
        code, _, err = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("created in the future (clock skew?)", err)
        self.assertNotIn("-1 day", err)

    def test_apply_uses_the_plan_context_and_namespace_not_fixed_values(self):
        items = [obj("Deployment", "web", namespace="team-x")]
        self.serve(items)
        self.assertEqual(self.run_cmd("check", "-f", str(self.manifest), "--namespace", "team-x", "--context", "ctx-b", "--plan", str(self.plan))[0], 0)
        self.kubectl.forget_calls()
        self.kubectl.rules([
            {"match": ["--dry-run=server"], "stdout": dry_run(*items)},
            {"match": ["get Deployment.apps web"], "sequence": ["", json.dumps(obj("Deployment", "web", namespace="team-x"))]},
            {"match": [" apply -f -"], "stdout": "ok\n"},
        ])
        self.assertEqual(self.apply("--yes")[0], 0)
        self.assertEqual(len(self.kubectl.calls()), 4)
        self.assertTrue(all(c.startswith("--context ctx-b -n team-x ") for c in self.kubectl.calls()), self.kubectl.calls())

    def test_plan_names_kinds_groups_starting_with_a_dash_and_bad_owner_labels_are_exit_2(self):
        self.serve_live()
        good = self.plan_data()
        for field in ("name", "kind", "group"):
            with self.subTest(field=field):
                bad = [{**good["objects"][0], field: "-o"}, good["objects"][1]]
                self.plan.write_text(json.dumps({**good, "objects": bad}), encoding="utf-8")
                code, _, err = self.apply()
                self.assertEqual(code, 2)
                self.assertIn("damaged", err)
        for label in (5, ["a=b"], "novalue", "=x"):
            with self.subTest(label=label):
                self.plan.write_text(json.dumps({**good, "owner_label": label}), encoding="utf-8")
                code, _, err = self.apply()
                self.assertEqual(code, 2)
                self.assertIn("damaged", err)

    def test_missing_or_damaged_plans_are_exit_2(self):
        self.serve_live()
        good = self.plan_data()
        bad_plans = ["{not json", "[]", "{}", json.dumps({**good, "created_at": "yesterday"}),
                     json.dumps({**good, "created_at": "2030-01-01T10:00:00"}),
                     json.dumps({**good, "objects": [{"kind": "Deployment"}]}),
                     json.dumps({**good, "objects": [{**good["objects"][0], "action": "DELETE"}]}),
                     json.dumps({k: v for k, v in good.items() if k != "context"})]
        for text in bad_plans:
            with self.subTest(text=text[:40]):
                self.plan.write_text(text, encoding="utf-8")
                code, _, err = self.apply()
                self.assertEqual(code, 2)
                self.assertRegex(err, "damaged|time zone")
        self.plan.unlink()
        self.assertEqual(self.apply()[0], 2)

    def test_plan_context_namespace_and_object_fields_are_guarded(self):
        self.serve_live()
        good = self.plan_data()
        objects = good["objects"]
        cases = {"context dash": {"context": "-o"}, "namespace dash": {"namespace": "--all"}, "context empty": {"context": ""},
                 "objects not a list": {"objects": {"a": 1}}, "objects a string": {"objects": "Deployment"},
                 "resourceVersion missing": {"objects": [{k: v for k, v in objects[0].items() if k != "resourceVersion"}, objects[1]]},
                 "resourceVersion a number": {"objects": [{**objects[0], "resourceVersion": 7}, objects[1]]},
                 "object kind empty": {"objects": [{**objects[0], "kind": ""}, objects[1]]},
                 "object name empty": {"objects": [{**objects[0], "name": ""}, objects[1]]},
                 "object namespace dash": {"objects": [{**objects[0], "namespace": "-o"}, objects[1]]},
                 "object namespace empty": {"objects": [{**objects[0], "namespace": ""}, objects[1]]}}
        for name, change in cases.items():
            with self.subTest(name=name):
                self.plan.write_text(json.dumps({**good, **change}), encoding="utf-8")
                code, _, err = self.apply()
                self.assertEqual(code, 2)
                self.assertIn("damaged", err)
        self.assertEqual(self.kubectl.calls(), [])

    def test_deeply_nested_plan_gives_the_damaged_message_not_a_recursion_error(self):
        self.plan.write_text("[" * 200000, encoding="utf-8")
        code, _, err = self.apply()
        self.assertEqual(code, 2)
        self.assertIn("is damaged or not a plan", err)
        self.assertNotIn("RecursionError", err)

    def test_plan_for_ctx_a_ignores_a_current_context_of_ctx_b(self):
        self.kubectl.rules([{"match": ["config"], "stdout": "ctx-b\n"}, self.dry, {"match": ["get "], "stdout": ""}])
        self.assertEqual(self.apply()[0], 0)
        self.assertTrue(all(c.startswith(f"--context {CTX} -n {NS} ") for c in self.kubectl.calls()), self.kubectl.calls())
        self.assertFalse(any("ctx-b" in c or "config" in c for c in self.kubectl.calls()))

    def test_apply_takes_no_context_or_namespace_override(self):
        for extra in (["--context", "ctx-b"], ["--namespace", "team-x"], ["-n", "team-x"]):
            with self.subTest(extra=extra):
                code, _, err = self.apply(*extra)
                self.assertEqual(code, 2)
                self.assertIn("usage", err)
        self.assertEqual(self.kubectl.calls(), [])

    def test_plan_edited_to_another_namespace_is_refused_by_the_dry_run(self):
        good = self.plan_data()
        moved = {**good, "namespace": "team-x", "objects": [{**o, "namespace": "team-x"} for o in good["objects"]]}
        self.plan.write_text(json.dumps(moved), encoding="utf-8")
        self.serve_live()
        code, _, err = self.apply("--yes")
        self.assertEqual(code, 1)
        self.assertIn("namespace shared is not team-x", err)
        self.assertEqual(self.apply_calls(), [])

    def test_overall_timeout_bounds_the_rechecks_before_the_write(self):
        self.kubectl.rules([self.dry, {"match": ["get "], "stdout": "", "sleep": 0.6}, {"match": [" apply -f"], "stdout": "ok"}])
        code, _, err = self.apply("--yes", "--kubectl-timeout", "1", "--overall-timeout", "1.2")
        self.assertEqual(code, 4)
        self.assertIn("timed out", err)
        self.assertNotIn("partly applied", err)
        self.assertEqual(self.apply_calls(), [])

    def test_write_needs_a_full_kubectl_timeout_left_of_the_overall_timeout(self):
        self.kubectl.rules([self.dry, {"match": ["get "], "stdout": "", "sleep": 0.3}, {"match": [" apply -f"], "stdout": "ok"}])
        code, _, err = self.apply("--yes", "--kubectl-timeout", "1.5", "--overall-timeout", "2")
        self.assertEqual(code, 4)
        self.assertIn("left for the write", err)
        self.assertNotIn("partly applied", err)
        self.assertEqual(self.apply_calls(), [])

    def test_overall_timeout_not_above_kubectl_timeout_is_exit_2_on_apply(self):
        self.serve_live()
        for overall in ("60", "120"):
            with self.subTest(overall=overall):
                code, _, err = self.apply("--yes", "--kubectl-timeout", "120", "--overall-timeout", overall)
                self.assertEqual(code, 2)
                self.assertIn("--overall-timeout must be greater than --kubectl-timeout", err)
        self.assertEqual(self.kubectl.calls(), [])
        self.assertEqual(self.apply("--kubectl-timeout", "5", "--overall-timeout", "5.5")[0], 0)

    def run_with_broken_stdout(self, breaks_on, *extra):
        def out(line):
            if breaks_on in line:
                raise BrokenPipeError(32, "Broken pipe")
        err = []
        code = kube_apply_check.main(["apply", "--plan", str(self.plan), "-f", str(self.manifest), *extra], out=out, err=err.append)
        return code, "\n".join(err)

    def test_an_unexpected_error_after_the_write_is_exit_3_not_2(self):
        for breaks_on in ("deployment.apps/web configured", "applied: 2"):
            with self.subTest(breaks_on=breaks_on):
                self.kubectl.forget_calls()
                self.kubectl.rules([
                    self.dry,
                    {"match": ["get Deployment.apps web"], "sequence": ["", json.dumps(self.ours)]},
                    {"match": ["get Service web"], "sequence": ["", json.dumps(obj("Service", "web", api="v1"))]},
                    {"match": [" apply -f"], "stdout": "deployment.apps/web configured\n"},
                ])
                code, err = self.run_with_broken_stdout(breaks_on, "--yes")
                self.assertEqual(code, 3)
                self.assertIn(f"partly applied: inspect namespace {NS}", err)
                self.assertIn("BrokenPipeError", err)
                self.assertEqual(self.apply_calls(), [f"--context {CTX} -n {NS} apply -f -"])

    def test_a_broken_stdout_before_the_write_is_exit_2_and_writes_nothing(self):
        self.serve_live()
        code, err = self.run_with_broken_stdout("dry run, nothing applied")
        self.assertEqual(code, 2)
        self.assertNotIn("partly applied", err)
        self.assertEqual(self.apply_calls(), [])

    def test_apply_uses_the_plan_context_and_namespace_only(self):
        self.serve_live()
        self.apply()
        self.assertTrue(all(c.startswith(f"--context {CTX} -n {NS} ") for c in self.kubectl.calls()))

    def test_garbage_live_json_during_apply_is_exit_2(self):
        self.kubectl.rules([self.dry, {"match": ["get "], "stdout": "nope"}])
        self.assertEqual(self.apply()[0], 2)


if __name__ == "__main__":
    unittest.main()
