"""Unit tests for the payments-integrity confirm_status reference implementation."""
import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "payments-integrity" / "scripts" / "confirm_status.py"
sys.path.insert(0, str(SCRIPT.parent))

import confirm_status as cs  # noqa: E402

REF = "ord-1001"
OK = frozenset({"paid"})
BAD = frozenset({"failed", "expired"})


def is_zombie(pid):
    try:
        return Path("/proc/%d/stat" % pid).read_text().rsplit(")", 1)[1].split()[0] == "Z"
    except (OSError, IndexError):
        return False


class FakeTime:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def reply(status, amount=5000, currency="SEK", reference=REF):
    return {"status": status, "amount_minor": amount, "currency": currency, "reference": reference}


class Script:
    """A fetch that plays a scripted list; an Exception item is raised."""

    def __init__(self, *items):
        self.items = list(items)
        self.calls = 0

    def __call__(self, reference):
        self.calls += 1
        if self.calls > 60:
            raise AssertionError("fetch called more than 60 times: the loop does not stop")
        item = self.items.pop(0) if len(self.items) > 1 else self.items[0]
        if isinstance(item, Exception):
            raise item
        return item


def run(fetch, deadline=600, ft=None, **kw):
    ft = ft or FakeTime()
    args = dict(reference=REF, expected_amount_minor=5000, expected_currency="SEK",
                final_success=OK, final_failure=BAD, deadline_s=deadline)
    args.update(kw)
    return cs.confirm(fetch, clock=ft.clock, sleep=ft.sleep, **args), ft


class ConfirmTests(unittest.TestCase):
    def test_paid_on_first_read(self):
        res, ft = run(Script(reply("paid")))
        self.assertEqual((res.outcome, res.attempts, res.last_status), ("paid", 1, "paid"))
        self.assertEqual(ft.sleeps, [])

    def test_pending_pending_then_paid(self):
        f = Script(reply("pending"), reply("initiated"), reply("paid"))
        res, ft = run(f)
        self.assertEqual((res.outcome, res.attempts), ("paid", 3))
        self.assertEqual(ft.sleeps, [1, 2])

    def test_pending_then_failed(self):
        res, _ = run(Script(reply("in_progress"), reply("failed")))
        self.assertEqual((res.outcome, res.attempts, res.last_status), ("failed", 2, "failed"))

    def test_still_pending_follows_backoff_and_ends_exactly_at_deadline(self):
        f = Script(reply("pending"))
        res, ft = run(f, deadline=100)
        self.assertEqual(res.outcome, "pending-reconcile")
        self.assertEqual(res.last_status, "pending")
        # reads at 0,1,3,7,15,30,60,90,100 -> sleeps follow the schedule, last one trimmed to the deadline
        self.assertEqual(ft.sleeps, [1, 2, 4, 8, 15, 30, 30, 10])
        self.assertEqual(res.attempts, 9)
        self.assertEqual(f.calls, 9)
        self.assertEqual(ft.now, 1100.0)

    def test_deadline_zero_reads_once(self):
        res, ft = run(Script(reply("pending")), deadline=0)
        self.assertEqual((res.outcome, res.attempts), ("pending-reconcile", 1))
        self.assertEqual(ft.sleeps, [])

    def test_unknown_status_keeps_polling_and_never_fails(self):
        f = Script(reply("weird"), reply("weird"), reply("paid"))
        res, _ = run(f)
        self.assertEqual((res.outcome, res.attempts), ("paid", 3))
        res, _ = run(Script(reply("weird")), deadline=10)
        self.assertEqual((res.outcome, res.last_status), ("pending-reconcile", "weird"))

    def test_missing_status_is_intermediate(self):
        res, _ = run(Script({**reply("x"), "status": None}), deadline=5)
        self.assertEqual(res.outcome, "pending-reconcile")

    def test_fetch_timeout_retried_then_success(self):
        f = Script(TimeoutError("slow"), ConnectionError("5xx"), reply("paid"))
        res, ft = run(f)
        self.assertEqual((res.outcome, res.attempts), ("paid", 3))
        self.assertEqual(ft.sleeps, [1, 2])

    def test_only_errors_until_deadline_is_pending_reconcile(self):
        res, _ = run(Script(TimeoutError("slow")), deadline=20)
        self.assertEqual(res.outcome, "pending-reconcile")
        self.assertIn("slow", res.reason)
        self.assertIsNone(res.last_status)

    def test_not_found_keeps_polling_until_the_deadline_then_pending_reconcile(self):
        f = Script(cs.NotFoundError("404"))
        res, ft = run(f, deadline=100)
        self.assertEqual(res.outcome, "pending-reconcile")
        self.assertEqual(res.attempts, 9)
        self.assertEqual(ft.sleeps, [1, 2, 4, 8, 15, 30, 30, 10])
        self.assertIn("not found", res.reason)
        self.assertIn("deadline", res.reason)

    def test_not_found_then_visible_then_paid(self):
        f = Script(cs.NotFoundError("404"), cs.NotFoundError("404"), reply("paid"))
        res, _ = run(f)
        self.assertEqual((res.outcome, res.attempts), ("paid", 3))

    def test_non_dict_reply_is_retried(self):
        res, ft = run(Script(["paid"], None, reply("paid")))
        self.assertEqual((res.outcome, res.attempts), ("paid", 3))
        res, _ = run(Script("garbage"), deadline=5)
        self.assertEqual(res.outcome, "pending-reconcile")
        self.assertIn("not an object", res.reason)

    def test_programming_errors_are_fatal_by_default(self):
        for exc in (TypeError("x"), KeyError("k"), AttributeError("a"), NameError("n")):
            with self.assertRaises(type(exc)):
                run(Script(exc))

    def test_malformed_response_and_runtime_errors_are_retried_by_default(self):
        res, _ = run(Script(cs.MalformedResponse("html"), RuntimeError("exit 1"), reply("paid")))
        self.assertEqual((res.outcome, res.attempts), ("paid", 3))

    def test_fetch_setup_error_is_fatal(self):
        with self.assertRaises(cs.FetchSetupError):
            run(Script(cs.FetchSetupError("cannot start")))

    def test_custom_classifier(self):
        class Gone(Exception):
            pass

        res, _ = run(Script(Gone()), deadline=0,
                     classify=lambda exc: "not_found" if isinstance(exc, Gone) else "retry")
        self.assertEqual((res.outcome, res.attempts), ("pending-reconcile", 1))
        self.assertIn("not found", res.reason)

    def test_fatal_classification_reraises(self):
        with self.assertRaises(KeyError):
            run(Script(KeyError("bug")), classify=lambda exc: "fatal")

    def test_amount_mismatch(self):
        res, _ = run(Script(reply("paid", amount=4999)))
        self.assertEqual((res.outcome, res.attempts), ("mismatch", 1))
        self.assertIn("amount", res.reason)

    def test_currency_mismatch(self):
        res, _ = run(Script(reply("paid", currency="USD")))
        self.assertEqual(res.outcome, "mismatch")
        self.assertIn("currency", res.reason)

    def test_reference_mismatch(self):
        res, _ = run(Script(reply("paid", reference="other")))
        self.assertEqual(res.outcome, "mismatch")
        self.assertIn("reference", res.reason)

    def test_wrong_reference_is_mismatch_on_any_status(self):
        for status in ("failed", "pending", "weird"):
            f = Script(reply(status, reference="other"))
            res, ft = run(f)
            self.assertEqual((res.outcome, res.attempts), ("mismatch", 1), status)
            self.assertEqual(ft.sleeps, [])

    def test_missing_or_null_reference_is_mismatch_on_any_status(self):
        for status in ("paid", "failed", "pending"):
            missing = reply(status)
            del missing["reference"]
            for body in (missing, reply(status, reference=None)):
                res, ft = run(Script(body))
                self.assertEqual((res.outcome, res.attempts), ("mismatch", 1), body)
                self.assertEqual(ft.sleeps, [])

    def test_failed_reply_skips_amount_and_currency_check(self):
        res, _ = run(Script(reply("failed", amount=1, currency="USD")))
        self.assertEqual(res.outcome, "failed")

    def test_pending_reply_with_missing_or_placeholder_amount_keeps_polling(self):
        no_amount = reply("pending")
        del no_amount["amount_minor"]
        f = Script(no_amount, reply("initiated", amount=0, currency=None), reply("paid"))
        res, ft = run(f)
        self.assertEqual((res.outcome, res.attempts), ("paid", 3))
        self.assertEqual(ft.sleeps, [1, 2])

    def test_reference_compared_exactly(self):
        res, _ = run(Script(reply("paid", reference=" " + REF)))
        self.assertEqual(res.outcome, "mismatch")

    def test_currency_must_be_ascii_letters_and_not_fold_confusables(self):
        for cur in ("\u017fEK", " SEK", "SEK\n", "SE", "SEK1", None):
            res, _ = run(Script(reply("paid", currency=cur)))
            self.assertEqual(res.outcome, "mismatch", repr(cur))

    def test_status_does_not_fold_confusables(self):
        res, _ = run(Script(reply("\u212aO")), final_success={"ko"}, deadline=0)
        self.assertEqual(res.outcome, "pending-reconcile")

    def test_none_status_never_matches_a_none_entry(self):
        res, _ = run(Script({**reply("x"), "status": None}), final_success={"none"}, deadline=0)
        self.assertEqual(res.outcome, "pending-reconcile")

    def test_blank_reply_status_is_never_final(self):
        res, _ = run(Script(reply("   ")), deadline=0)
        self.assertEqual(res.outcome, "pending-reconcile")

    def test_error_text_does_not_leak_into_a_later_pending_reason(self):
        res, _ = run(Script(TimeoutError("boom"), reply("pending")), deadline=5)
        self.assertNotIn("boom", res.reason)
        self.assertIn("not final", res.reason)

    def test_plain_string_final_set_raises_type_error(self):
        for kw in ("final_success", "final_failure"):
            with self.assertRaises(TypeError):
                run(Script(reply("a")), **{kw: "paid"})

    def test_blank_final_entry_raises(self):
        for blank in ("", "  ", "\t"):
            for kw in ("final_success", "final_failure"):
                with self.assertRaises(ValueError, msg=repr(blank)):
                    run(Script(reply("paid")), **{kw: {blank, "x"}})
        with self.assertRaises(ValueError):
            run(Script(reply("paid")), final_success={5})

    def test_degenerate_expected_values_raise(self):
        bad = [dict(expected_amount_minor=0), dict(expected_amount_minor=-5),
               dict(expected_amount_minor=True), dict(expected_amount_minor="5000"),
               dict(expected_amount_minor=50.0), dict(reference=""), dict(reference="  "),
               dict(reference=None), dict(expected_currency=""), dict(expected_currency="  "),
               dict(expected_currency="SA"), dict(expected_currency="S4R"), dict(expected_currency=None)]
        for kw in bad:
            f = Script(reply("paid", amount=kw.get("expected_amount_minor", 5000),
                             currency=kw.get("expected_currency", "SEK"),
                             reference=kw.get("reference", REF)))
            with self.assertRaises(ValueError, msg=repr(kw)):
                run(f, **kw)
            self.assertEqual(f.calls, 0)

    def test_missing_amount_is_mismatch(self):
        r = reply("paid")
        del r["amount_minor"]
        res, _ = run(Script(r))
        self.assertEqual(res.outcome, "mismatch")

    def test_string_amount_is_mismatch(self):
        res, _ = run(Script(reply("paid", amount="5000")))
        self.assertEqual(res.outcome, "mismatch")

    def test_overlapping_sets_raise(self):
        with self.assertRaises(ValueError):
            run(Script(reply("paid")), final_success={"paid", "Done"}, final_failure={" done "})

    def test_empty_sets_raise(self):
        with self.assertRaises(ValueError):
            run(Script(reply("paid")), final_success=set())
        with self.assertRaises(ValueError):
            run(Script(reply("paid")), final_failure=[])

    def test_case_and_whitespace_normalised(self):
        res, _ = run(Script(reply("  PAID ")), final_success={" Paid"})
        self.assertEqual(res.outcome, "paid")
        res, _ = run(Script(reply("EXPIRED\n")), final_failure={"Expired "})
        self.assertEqual(res.outcome, "failed")
        res, _ = run(Script(reply("paid", currency="sek")), expected_currency="Sek")
        self.assertEqual(res.outcome, "paid")

    def test_backoff_last_value_repeats(self):
        res, ft = run(Script(reply("pending")), deadline=40, backoff=(1, 5))
        self.assertEqual(ft.sleeps, [1, 5, 5, 5, 5, 5, 5, 5, 4])
        self.assertEqual(res.attempts, 10)

    def test_final_status_exactly_at_deadline_is_honoured(self):
        f = Script(reply("pending"), reply("pending"), reply("paid"))
        res, ft = run(f, deadline=3)
        self.assertEqual((res.outcome, res.attempts), ("paid", 3))
        self.assertEqual(ft.sleeps, [1, 2])

    def test_no_read_after_deadline(self):
        f = Script(reply("pending"))
        _, ft = run(f, deadline=3)
        self.assertEqual(f.calls, 3)
        self.assertEqual(ft.now, 1003.0)

    def test_read_one_second_before_deadline_still_happens(self):
        f = Script(reply("pending"))
        res, ft = run(f, deadline=91)
        self.assertEqual(res.attempts, 9)
        self.assertEqual(ft.sleeps[-1], 1)
        self.assertEqual(ft.now, 1091.0)

    def test_bool_amount_is_not_an_integer_match(self):
        res, _ = run(Script(reply("paid", amount=True)), expected_amount_minor=1)
        self.assertEqual(res.outcome, "mismatch")

    def test_huge_gateway_values_are_cut_in_the_reason(self):
        res, _ = run(Script(reply("paid", reference="r" * 5000)))
        self.assertEqual(res.outcome, "mismatch")
        self.assertLess(len(res.reason), 300)
        self.assertIn("...(cut)", res.reason)
        res, _ = run(Script(reply("paid", amount="9" * 5000)))
        self.assertLess(len(res.reason), 300)
        res, _ = run(Script(reply("p" * 5000)), deadline_s=0)
        self.assertEqual(res.outcome, "pending-reconcile")
        self.assertLess(len(res.reason), 300)
        res, _ = run(Script(RuntimeError("e" * 5000)), deadline_s=0)
        self.assertLess(len(res.reason), 300)

    def test_empty_backoff_raises(self):
        with self.assertRaises(ValueError):
            run(Script(reply("paid")), backoff=())


class DeadlineParseTests(unittest.TestCase):
    def test_units(self):
        self.assertEqual(cs.parse_duration("10m"), 600)
        self.assertEqual(cs.parse_duration("45s"), 45)
        self.assertEqual(cs.parse_duration("2h"), 7200)
        self.assertEqual(cs.parse_duration("90"), 90)
        self.assertEqual(cs.parse_duration("24h"), 86400)

    def test_bad(self):
        for bad in ("", "m", "-5s", "1d", "abc", "1.5m", "\u0665m", "25h", "86401"):
            with self.assertRaises(ValueError, msg=bad):
                cs.parse_duration(bad)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def fetcher(self, body, code=0):
        path = self.dir / "fetch.py"
        path.write_text(
            "import sys\n"
            "sys.stdout.write(%r)\n"
            "sys.exit(%d)\n" % (body, code), encoding="utf-8")
        return "%s %s {ref}" % (sys.executable, path)

    def stderr_of(self, proc):
        return proc.stderr

    def cli(self, fetch_cmd, *extra, reference=REF):
        argv = [sys.executable, str(SCRIPT), "--fetch-cmd", fetch_cmd, "--reference=" + reference,
                "--amount-minor", "5000", "--currency", "SEK", "--success", "paid",
                "--failure", "failed", "--deadline", "1s", *extra]
        return subprocess.run(argv, capture_output=True, text=True, cwd=self.dir, timeout=60)

    def assert_dead(self, pid, message):
        for _ in range(40):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            if is_zombie(pid):  # dead, waiting for a reaper (in a PID namespace the runner is init)
                return
            time.sleep(0.1)
        os.kill(pid, 9)
        self.fail(message)

    def assert_no_traceback(self, proc):
        self.assertNotIn("Traceback", proc.stderr + proc.stdout)

    def test_paid_exit_0(self):
        proc = self.cli(self.fetcher(json.dumps(reply("PAID"))))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["outcome"], "paid")

    def test_failed_exit_1(self):
        proc = self.cli(self.fetcher(json.dumps(reply("failed"))))
        self.assertEqual(proc.returncode, 1, proc.stderr)

    def test_pending_exit_3(self):
        proc = self.cli(self.fetcher(json.dumps(reply("pending"))))
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["outcome"], "pending-reconcile")

    def test_mismatch_exit_4(self):
        proc = self.cli(self.fetcher(json.dumps(reply("paid", amount=1))))
        self.assertEqual(proc.returncode, 4, proc.stderr)

    def test_paid_reply_without_reference_exit_4(self):
        body = reply("paid")
        del body["reference"]
        proc = self.cli(self.fetcher(json.dumps(body)))
        self.assertEqual(proc.returncode, 4, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["outcome"], "mismatch")

    def test_garbage_output_is_retried_and_ends_exit_3(self):
        proc = self.cli(self.fetcher("<html>502</html>"))
        self.assertEqual(proc.returncode, 3)
        self.assert_no_traceback(proc)

    def run_main(self, body, *extra, code=0, deadline="0s"):
        """Run main() in-process on a fake clock; every fetch gets a generous 5 s floor."""
        ft = FakeTime()
        out = io.StringIO()
        argv = ["--fetch-cmd", self.fetcher(body, code), "--reference", REF, "--amount-minor", "5000",
                "--currency", "SEK", "--success", "paid", "--failure", "failed",
                "--deadline", deadline, *extra]
        with unittest.mock.patch.object(cs, "MIN_FETCH_TIMEOUT_S", 5), contextlib.redirect_stdout(out):
            rc = cs.main(argv, clock=ft.clock, sleep=ft.sleep)
        return rc, json.loads(out.getvalue()), ft

    def test_garbage_then_valid_paid_is_not_aborted(self):
        script = self.dir / "flaky.py"
        state = self.dir / "state"
        script.write_text(
            "import json, pathlib, sys\n"
            "st = pathlib.Path(%r)\n"
            "if not st.exists():\n"
            "    st.write_text('x'); print('<html>502</html>'); sys.exit(0)\n"
            "print(json.dumps({'status': 'paid', 'amount_minor': 5000, 'currency': 'SEK', 'reference': sys.argv[1]}))\n"
            % str(state), encoding="utf-8")
        ft = FakeTime()
        out = io.StringIO()
        argv = ["--fetch-cmd", "%s %s {ref}" % (sys.executable, script), "--reference", REF,
                "--amount-minor", "5000", "--currency", "SEK", "--success", "paid", "--failure", "failed",
                "--deadline", "1m"]
        with contextlib.redirect_stdout(out):
            rc = cs.main(argv, clock=ft.clock, sleep=ft.sleep)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["attempts"], 2)

    def test_deadline_reason_names_the_last_malformed_output(self):
        rc, out, _ = self.run_main("<html>502</html>")
        self.assertEqual(rc, 3)
        self.assertIn("MalformedResponse", out["reason"])

    def test_deadline_reason_says_not_found(self):
        rc, out, _ = self.run_main("", code=44)
        self.assertEqual(rc, 3)
        self.assertIn("not found", out["reason"])

    def test_deeply_nested_json_is_malformed_not_a_crash(self):
        rc, out, _ = self.run_main("[" * 100000)
        self.assertEqual(rc, 3)
        self.assertIn("MalformedResponse", out["reason"])

    def test_json_non_object_exit_3_after_the_deadline(self):
        proc = self.cli(self.fetcher("[1, 2]"))
        self.assertEqual(proc.returncode, 3)

    def test_fetch_command_not_found_exit_3(self):
        proc = self.cli(self.fetcher("", code=44))
        self.assertEqual(proc.returncode, 3)

    def test_fetch_command_exit_4_is_an_ordinary_failure_not_not_found(self):
        rc, out, _ = self.run_main("", code=4)
        self.assertEqual(rc, 3)
        self.assertNotIn("not found", out["reason"])

    def test_fetch_command_failing_is_retried_until_deadline_exit_3(self):
        proc = self.cli(self.fetcher("", code=1))
        self.assertEqual(proc.returncode, 3)
        self.assert_no_traceback(proc)

    def test_missing_executable_exit_2(self):
        proc = self.cli("/nonexistent/fetcher {ref}")
        self.assertEqual(proc.returncode, 2)
        self.assert_no_traceback(proc)

    def test_usage_errors_exit_2(self):
        for argv in ([], ["--reference", "x"]):
            proc = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2, argv)
            self.assert_no_traceback(proc)

    def test_template_without_ref_placeholder_exit_2(self):
        proc = self.cli("%s -c pass" % sys.executable)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("{ref}", proc.stderr)
        with self.assertRaisesRegex(ValueError, r"\{ref\}"):
            cs.command_fetcher("echo hi")

    def test_bad_amounts_exit_2(self):
        ok = self.fetcher(json.dumps(reply("paid")))
        for amount in ("1_000", "0", "-5", "05", "\u0665\u0660", "5000.0", "", "x"):
            proc = self.cli(ok, "--amount-minor", amount)
            self.assertEqual(proc.returncode, 2, amount)
            self.assert_no_traceback(proc)

    def test_blank_success_or_failure_entry_exit_2(self):
        ok = self.fetcher(json.dumps({"status": None, "amount_minor": 5000, "currency": "SEK", "reference": REF}))
        for flag in ("--success", "--failure"):
            proc = self.cli(ok, flag, "")
            self.assertEqual(proc.returncode, 2, flag)
            self.assert_no_traceback(proc)

    def test_bad_currency_and_blank_reference_exit_2(self):
        ok = self.fetcher(json.dumps(reply("paid")))
        self.assertEqual(self.cli(ok, "--currency", "SA").returncode, 2)
        self.assertEqual(self.cli(ok, reference="").returncode, 2)
        self.assertEqual(self.cli(ok, reference="  ").returncode, 2)

    def test_reference_starting_with_dash_exit_2_and_fetch_not_run(self):
        marker = self.dir / "ran"
        script = self.dir / "mark.py"
        script.write_text("import pathlib; pathlib.Path(%r).write_text('x')\n" % str(marker), encoding="utf-8")
        proc = self.cli("%s %s {ref}" % (sys.executable, script), reference="--version")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("-", proc.stderr)
        self.assertFalse(marker.exists())

    def test_command_fetcher_refuses_a_dash_reference_itself(self):
        fetch = cs.command_fetcher("%s -c pass {ref}" % sys.executable)
        # Popen must raise, never return a fake process: a mock's pid reads as 1 and killpg(1) is kill(-1).
        with unittest.mock.patch.object(cs.subprocess, "Popen", side_effect=AssertionError("Popen ran")) as popen:
            with self.assertRaisesRegex(cs.FetchSetupError, "'-'"):
                fetch("--version")
        popen.assert_not_called()

    def test_oversized_fetch_output_is_retried_exit_3(self):
        big = json.dumps({**reply("pending"), "pad": "x" * (cs.MAX_FETCH_BYTES + 10)})
        rc, out, _ = self.run_main(big)
        self.assertEqual(rc, 3)
        self.assertIn("over", out["reason"])

    def test_bad_fetch_timeout_exit_2(self):
        ok = self.fetcher(json.dumps(reply("paid")))
        for value in ("0", "abc", "-1"):
            self.assertEqual(self.cli(ok, "--fetch-timeout", value).returncode, 2, value)

    def test_fetch_timeout_is_retried_ends_pending_and_kills_the_process_group(self):
        pidfile = self.dir / "grandchild.pid"
        script = self.dir / "slow.py"
        script.write_text(
            "import subprocess, sys, time\n"
            "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "open(%r, 'a').write(str(g.pid) + '\\n')\n"
            "time.sleep(60)\n" % str(pidfile), encoding="utf-8")
        started = time.monotonic()
        proc = self.cli("%s %s {ref}" % (sys.executable, script), "--fetch-timeout", "1")
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertIn("TimeoutError", out["reason"])
        for pid in map(int, pidfile.read_text().split()):
            self.assert_dead(pid, "grandchild survived the timeout")

    def test_overlapping_sets_exit_2(self):
        proc = self.cli(self.fetcher(json.dumps(reply("paid"))), "--failure", "PAID")
        self.assertEqual(proc.returncode, 2)
        self.assert_no_traceback(proc)

    def test_bad_deadline_exit_2(self):
        proc = self.cli(self.fetcher(json.dumps(reply("paid"))), "--deadline", "soon")
        self.assertEqual(proc.returncode, 2)

    def test_reference_is_one_argument_no_shell(self):
        evil = "x; touch pwned"
        # the fetcher echoes its argv[1] back as the reference: only one word means a match
        script = self.dir / "echo_ref.py"
        script.write_text(
            "import json, sys\n"
            "assert len(sys.argv) == 2, sys.argv\n"
            "print(json.dumps({'status': 'paid', 'amount_minor': 5000, 'currency': 'SEK',"
            " 'reference': sys.argv[1]}))\n", encoding="utf-8")
        proc = self.cli("%s %s {ref}" % (sys.executable, script), reference=evil)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((self.dir / "pwned").exists())

    def test_command_fetcher_never_waits_past_the_remaining_deadline(self):
        script = self.dir / "sleep.py"
        script.write_text("import time; time.sleep(60)\n", encoding="utf-8")
        fetch = cs.command_fetcher("%s %s {ref}" % (sys.executable, script), fetch_timeout=30,
                                   remaining=lambda: 2)
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            fetch(REF)
        self.assertLess(time.monotonic() - started, 10)

    def test_command_fetcher_timeout_is_min_of_both_with_a_tenth_of_a_second_floor(self):
        seen = []

        def fake_run(argv, timeout):
            seen.append(timeout)
            return 0, b"{}"

        with unittest.mock.patch.object(cs, "_run_bounded", fake_run):
            for fetch_timeout, left in ((30, 0), (30, -3), (30, 2.5), (2, 100), (30, 0.05)):
                cs.command_fetcher("x {ref}", fetch_timeout=fetch_timeout, remaining=lambda: left)(REF)
        self.assertEqual(seen, [0.1, 0.1, 2.5, 2, 0.1])

    def test_template_starting_with_ref_is_refused(self):
        for template in ("{ref}", "{ref} --flag", "pre{ref} x"):
            with self.assertRaisesRegex(ValueError, "start with the program"):
                cs.command_fetcher(template)
        proc = self.cli("{ref}")
        self.assertEqual(proc.returncode, 2)

    def test_escaped_descendant_holding_the_pipe_cannot_block_the_poll(self):
        pidfile = self.dir / "escaped.pid"
        script = self.dir / "escape.py"
        script.write_text(
            "import subprocess, sys\n"
            "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)\n"
            "open(%r, 'w').write(str(g.pid))\n" % str(pidfile), encoding="utf-8")
        fetch = cs.command_fetcher("%s %s {ref}" % (sys.executable, script), fetch_timeout=1)
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            fetch(REF)
        elapsed = time.monotonic() - started
        pid = int(pidfile.read_text())
        self.addCleanup(lambda: os.kill(pid, 9) if os.path.exists("/proc/%d" % pid) else None)
        self.assertLess(elapsed, 5)

    def test_oversized_output_kills_the_group_at_once(self):
        pidfile = self.dir / "flood.pid"
        script = self.dir / "flood.py"
        script.write_text(
            "import os, sys, time\n"
            "open(%r, 'w').write(str(os.getpid()))\n"
            "while True:\n"
            "    sys.stdout.write('x' * 65536); sys.stdout.flush()\n" % str(pidfile), encoding="utf-8")
        fetch = cs.command_fetcher("%s %s {ref}" % (sys.executable, script), fetch_timeout=30)
        started = time.monotonic()
        with self.assertRaisesRegex(cs.MalformedResponse, "over"):
            fetch(REF)
        self.assertLess(time.monotonic() - started, 10)
        self.assert_dead(int(pidfile.read_text()), "flooding fetch command survived")

    def test_command_fetcher_stdin_is_devnull_and_runs_in_own_session(self):
        seen = {}
        real = cs.subprocess.Popen

        def spy(*a, **kw):
            seen.update(kw)
            return real(*a, **kw)

        fetch = cs.command_fetcher("%s -c pass {ref}" % sys.executable)
        with unittest.mock.patch.object(cs.subprocess, "Popen", spy):
            with self.assertRaises(cs.MalformedResponse):
                fetch(REF)
        self.assertIs(seen["stdin"], cs.subprocess.DEVNULL)
        self.assertIs(seen["stderr"], cs.subprocess.DEVNULL)
        self.assertIs(seen["start_new_session"], True)

    def main_args(self):
        return ["--fetch-cmd", "unused {ref}", "--reference", REF, "--amount-minor", "5000", "--currency", "SEK",
                "--success", "paid", "--failure", "failed", "--deadline", "10m"]

    def test_a_crash_exits_5_never_1_which_reads_as_failed(self):
        def broken(ref):
            raise TypeError("bug in the fetch")

        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()) as out:
            code = cs.main(self.main_args(), fetch_factory=lambda cmd, fetch_timeout, remaining: broken)
        self.assertEqual(code, cs.EXIT_INTERNAL)
        self.assertEqual(code, 5)
        self.assertIn("internal error: TypeError", err.getvalue())
        self.assertEqual(out.getvalue(), "")

    def test_main_restores_the_previous_sigterm_handler(self):
        def marker(signum, frame):
            pass

        before = signal.signal(signal.SIGTERM, marker)
        self.addCleanup(signal.signal, signal.SIGTERM, before)
        with contextlib.redirect_stdout(io.StringIO()):
            cs.main(self.main_args(), fetch_factory=lambda cmd, fetch_timeout, remaining: (lambda ref: reply("paid")))
        self.assertIs(signal.getsignal(signal.SIGTERM), marker)

    def test_sigterm_kills_the_fetch_group_and_exits_143(self):
        pidfile = self.dir / "term.pid"
        script = self.dir / "hang.py"
        script.write_text(
            "import os, subprocess, sys, time\n"
            "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "tmp = %r + '.tmp'\n"
            "open(tmp, 'w').write(str(g.pid))\n"
            "os.replace(tmp, %r)\n"
            "time.sleep(60)\n" % (str(pidfile), str(pidfile)), encoding="utf-8")
        argv = [sys.executable, str(SCRIPT), "--fetch-cmd", "%s %s {ref}" % (sys.executable, script),
                "--reference", REF, "--amount-minor", "5000", "--currency", "SEK", "--success", "paid",
                "--failure", "failed", "--deadline", "1m"]
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=self.dir)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        for _ in range(200):
            if pidfile.exists() or proc.poll() is not None:
                break
            time.sleep(0.05)
        self.assertTrue(pidfile.exists(), "fetch command never started")
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=20)
        self.assertEqual(proc.returncode, 143, err)
        self.assertEqual(out, "")
        self.assert_dead(int(pidfile.read_text()), "fetch grandchild survived SIGTERM")

    def test_a_nul_byte_in_the_reference_is_a_setup_error_not_retried(self):
        fetch = cs.command_fetcher("%s -c pass {ref}" % sys.executable)
        with self.assertRaisesRegex(cs.FetchSetupError, "cannot run"):
            fetch("ord\x00x")

    def main_once(self, status, out):
        """Run main for one read (deadline 0) of a reply with this status, stdout to out; return the exit."""
        argv = self.main_args()
        argv[-1] = "0"
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(out):
            return cs.main(argv, fetch_factory=lambda cmd, fetch_timeout, remaining: (lambda ref: reply(status)))

    def test_a_failed_result_write_exits_5_never_1_which_reads_as_failed(self):
        class Unwritable(io.StringIO):
            def __init__(self, error):
                super().__init__()
                self.error = error

            def write(self, text):
                raise self.error

        for error in (OSError(28, "No space left on device"), BrokenPipeError(32, "Broken pipe"),
                      ValueError("I/O operation on closed file.")):
            for status in ("pending", "failed", "paid"):
                with self.subTest(error=type(error).__name__, status=status):
                    self.assertEqual(self.main_once(status, Unwritable(error)), cs.EXIT_INTERNAL)

    def test_the_result_line_cuts_a_huge_last_status(self):
        for status in ("x" * 5000, ["x" * 5000]):
            with self.subTest(status=type(status).__name__):
                out = io.StringIO()
                self.assertEqual(self.main_once(status, out), cs.EXIT_PENDING)
                line = out.getvalue()
                self.assertLess(len(line), 1000)
                shown = json.loads(line)["last_status"]
                self.assertIsInstance(shown, str)
                self.assertTrue(shown.endswith("...(cut)"))
                self.assertEqual(len(shown), cs.MAX_SHOWN_CHARS + len("...(cut)"))

    def test_the_result_line_keeps_a_short_last_status_as_is(self):
        for status in ("weird", "x" * cs.MAX_SHOWN_CHARS, 7, None):
            with self.subTest(status=status):
                out = io.StringIO()
                self.assertEqual(self.main_once(status, out), cs.EXIT_PENDING)
                self.assertEqual(json.loads(out.getvalue())["last_status"], status)

    @unittest.skipUnless(os.path.exists("/dev/full"), "needs /dev/full")
    def test_a_full_stdout_exits_5_not_1_or_120(self):
        argv = [sys.executable, str(SCRIPT), "--fetch-cmd", self.fetcher(json.dumps(reply("pending"))),
                "--reference", REF, "--amount-minor", "5000", "--currency", "SEK", "--success", "paid",
                "--failure", "failed", "--deadline", "0"]
        with open("/dev/full", "w") as full:
            proc = subprocess.run(argv, stdout=full, stderr=subprocess.PIPE, text=True, cwd=self.dir, timeout=60)
        self.assertEqual(proc.returncode, cs.EXIT_INTERNAL, proc.stderr)
        self.assertIn("cannot write the result", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_main_polls_with_injected_time(self):
        ft = FakeTime()
        seq = [reply("pending"), reply("paid")]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cs.main(["--fetch-cmd", "unused {ref}", "--reference", REF, "--amount-minor", "5000",
                            "--currency", "SEK", "--success", "paid", "--failure", "failed",
                            "--deadline", "10m"],
                           fetch_factory=lambda cmd, fetch_timeout, remaining: (lambda ref: seq.pop(0)),
                           clock=ft.clock, sleep=ft.sleep)
        self.assertEqual(code, 0)
        self.assertEqual(ft.sleeps, [1])


if __name__ == "__main__":
    unittest.main()
