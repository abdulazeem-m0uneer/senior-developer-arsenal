"""Unit tests for the lessons-learned skill's ledger script."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "lessons-learned" / "scripts"))

import ledger_store  # noqa: E402
import lessons  # noqa: E402
import promotion  # noqa: E402
import relevance  # noqa: E402

SCRIPT = str(Path(lessons.__file__).resolve())


class LedgerCase(unittest.TestCase):
    """A project ledger and a global ledger in a temp dir; the user's real global ledger is never touched."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.file = str(self.dir / "nested" / "lessons.md")
        self.shared = self.dir / "home" / "lessons.md"
        self.env = {**os.environ, "LESSONS_GLOBAL_FILE": str(self.shared)}
        patch = mock.patch.dict(os.environ, {"LESSONS_GLOBAL_FILE": str(self.shared)})
        patch.start()
        self.addCleanup(patch.stop)

    def run_cli(self, *argv, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(sys, "stdin", io.StringIO(stdin)):
            code = lessons.main(["--file", self.file, *argv])
        return code, out.getvalue(), err.getvalue()

    def add(self, mistake, rule="Run the migration dry run first", tags="sql", extra=()):
        return self.run_cli("add", "--tags", tags, "--mistake", mistake, "--cause", "assumed it was safe",
                            "--rule", rule, "--check", "grep dry-run in CI", *extra)

    def add_distinct(self, count, extra=(), tags="sql"):
        for n in range(count):
            self.add(f"unique{n} thing{n} broke{n}", rule=f"distinct{n} guard{n} step{n}", tags=tags, extra=extra)

    def hook_context(self, stdin=""):
        code, out, _ = self.run_cli("active", "--hook", stdin=stdin)
        self.assertEqual(code, 0)
        payload = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(payload["hookEventName"], "SessionStart")
        return payload["additionalContext"]


class LessonsTests(LedgerCase):

    def test_add_creates_file_and_active_lists_it(self):
        code, out, _ = self.add("Dropped a column without a dry run")
        self.assertEqual((code, out.strip()), (0, "added L001"))
        _, active, _ = self.run_cli("active")
        self.assertIn("L001 [sql] hits:1", active)
        self.assertIn("Check: grep dry-run in CI", active)

    def test_similar_lesson_bumps_instead_of_adding(self):
        self.add("Dropped a column without a dry run")
        _, out, _ = self.add("Dropped a column without any dry run again")
        self.assertIn("duplicate of L001: hits bumped to 2", out)
        self.assertEqual(self.run_cli("check")[1].count("L00"), 0)
        self.assertIn("1 lessons", self.run_cli("check")[1])

    def test_third_repeat_suggests_promotion(self):
        self.add("Dropped a column without a dry run")
        self.run_cli("bump", "L001")
        _, out, _ = self.run_cli("bump", "L001")
        self.assertIn("PROMOTE L001", out)

    def test_active_cap_archives_least_hit_oldest(self):
        self.add_distinct(lessons.ACTIVE_CAP + 1)
        active = self.run_cli("active")[1]
        self.assertEqual(len(active.strip().splitlines()), lessons.ACTIVE_CAP)
        self.assertIn("[archive]", self.run_cli("search", "unique0")[1])

    def test_secret_like_content_is_refused(self):
        code, _, err = self.run_cli("add", "--mistake", "Committed api_key=sk-123456", "--cause", "x", "--rule", "y")
        self.assertEqual(code, 2)
        self.assertIn("secret", err)
        self.assertFalse(Path(self.file).exists())

    def test_missing_required_field_is_a_usage_error(self):
        self.assertEqual(self.run_cli("add", "--mistake", "m", "--rule", "r")[0], 2)

    def test_pipe_in_text_cannot_break_the_line_format(self):
        self.run_cli("add", "--mistake", "a | b", "--cause", "c | d", "--rule", "e | f")
        self.assertEqual(self.run_cli("check")[0], 0)

    def test_search_requires_every_word_and_archive_moves_lesson(self):
        self.add("Dropped a column without a dry run")
        self.assertEqual(self.run_cli("search", "column", "nonexistent")[1], "")
        self.run_cli("archive", "L001")
        self.assertEqual(self.run_cli("active")[1], "")
        self.assertIn("[archive] - L001", self.run_cli("search", "column")[1])

    def test_unknown_id_and_stray_lines_are_reported(self):
        self.assertEqual(self.run_cli("bump", "L999")[0], 2)
        self.add("Dropped a column without a dry run")
        Path(self.file).write_text(Path(self.file).read_text() + "hand written note\n")
        self.assertEqual(self.run_cli("check")[0], 1)
        self.assertEqual(self.run_cli("bump", "L001")[0], 2)

    def test_hook_mode_emits_session_start_json_with_self_recording_instruction(self):
        context = self.hook_context()
        self.assertIn("If you catch your own mistake", context)
        self.assertIn("lessons.py add", context)
        self.assertIn("(no lessons yet)", context)
        self.add("Dropped a column without a dry run")
        context = self.hook_context()
        self.assertIn("L001 [sql]", context)
        self.assertNotIn("(no lessons yet)", context)

    def test_shipped_session_hook_points_at_this_script(self):
        config = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        entries = config["hooks"]["SessionStart"]
        self.assertIn("compact", entries[0]["matcher"])
        command = next(h["command"] for h in entries[0]["hooks"] if "lessons.py" in h["command"])
        relative = command.split("${CLAUDE_PLUGIN_ROOT}/")[1].split('"')[0]
        self.assertTrue((ROOT / relative).is_file(), relative)
        self.assertIn("active --hook", command)

    def test_date_is_today(self):
        with mock.patch.object(lessons, "today", return_value="2026-11-04"):
            self.add("Dropped a column without a dry run")
        self.assertIn("| 2026-11-04 |", self.run_cli("active")[1])

    def test_tags_are_normalised_and_capped(self):
        self.add("Dropped a column", tags="SQL, a]b ," + ",".join(f"tag{n}" for n in range(40)))
        tags = self.run_cli("active")[1].split("[", 1)[1].split("]", 1)[0]
        self.assertTrue(tags.startswith("sql,ab,tag0"))
        self.assertLessEqual(len(tags), lessons.TAGS_MAX)
        self.assertEqual(self.run_cli("check")[0], 0)


class ConcurrencyTests(LedgerCase):
    def spawn_add(self, n):
        return subprocess.Popen(
            [sys.executable, SCRIPT, "--file", self.file, "add", "--mistake", f"unique{n} thing{n} broke{n}",
             "--cause", "c", "--rule", f"distinct{n} guard{n} step{n}"],
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True)

    def test_parallel_adds_keep_every_lesson(self):
        count = 20
        self.add("Dropped a column without a dry run")
        results = [(process.communicate(timeout=60), process.returncode)
                   for process in [self.spawn_add(n) for n in range(count)]]
        self.assertEqual([code for _, code in results], [0] * count, results)
        code, out, _ = self.run_cli("check")
        self.assertEqual(code, 0, out)
        self.assertIn(f"{count + 1} lessons, 0 problems", out)
        text = Path(self.file).read_text(encoding="utf-8")
        self.assertEqual(sum(f"unique{n} thing{n} " in text for n in range(count)), count)
        self.assertEqual(text.count("\n- L"), count + 1)

    def test_busy_ledger_fails_loudly_and_writes_nothing(self):
        self.add("Dropped a column without a dry run")
        before = Path(self.file).read_text(encoding="utf-8")
        with ledger_store.locked(self.file), mock.patch.object(ledger_store, "LOCK_WAIT", 0.1):
            code, out, err = self.add("Something entirely different happened", rule="Another unrelated guard")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("locked", err)
        self.assertEqual(Path(self.file).read_text(encoding="utf-8"), before)
        self.assertEqual(self.add("Something entirely different happened", rule="Another unrelated guard")[0], 0)

    def test_lock_is_beside_the_ledger_so_a_different_tmpdir_cannot_bypass_it(self):
        self.add("Dropped a column without a dry run")
        other_tmp = self.dir / "other-tmp"
        other_tmp.mkdir()
        self.assertEqual(ledger_store.lock_path(self.file).parent, Path(self.file).parent)
        self.assertNotEqual(ledger_store.lock_path(self.file), ledger_store.lock_path(self.shared))
        with ledger_store.locked(self.file), mock.patch.object(ledger_store, "LOCK_WAIT", 0.1), \
                mock.patch.object(tempfile, "tempdir", str(other_tmp)):
            with self.assertRaises(ledger_store.LedgerBusy):
                with ledger_store.locked(self.file):
                    pass

    def test_unwritable_ledger_directory_falls_back_to_the_temp_dir(self):
        with mock.patch.object(Path, "mkdir", side_effect=PermissionError("read-only")):
            self.assertEqual(ledger_store.lock_path(self.file).parent, Path(tempfile.gettempdir()))

    def test_failed_write_keeps_the_old_file_and_leaves_no_temp_file(self):
        self.add("Dropped a column without a dry run")
        before = Path(self.file).read_text(encoding="utf-8")
        with mock.patch.object(ledger_store.os, "replace", side_effect=OSError("disk full")):
            code, _, err = self.run_cli("bump", "L001")
        self.assertEqual(code, 2)
        self.assertIn("disk full", err)
        self.assertEqual(Path(self.file).read_text(encoding="utf-8"), before)
        self.assertEqual(sorted(p.name for p in Path(self.file).parent.iterdir()), [".lessons.md.lock", "lessons.md"])

    @unittest.skipIf(os.name == "nt", "POSIX file modes")
    def test_rewrite_keeps_the_file_mode(self):
        self.add("Dropped a column without a dry run")
        os.chmod(self.file, 0o640)
        self.run_cli("bump", "L001")
        self.assertEqual(os.stat(self.file).st_mode & 0o777, 0o640)


class RecurrenceTests(LedgerCase):
    def test_archived_lesson_that_recurs_returns_to_active(self):
        self.add("Dropped a column without a dry run")
        self.run_cli("archive", "L001")
        _, out, _ = self.add("Dropped a column without any dry run again")
        self.assertIn("duplicate of L001: hits bumped to 2 (back in Active)", out)
        self.assertIn("L001 [sql] hits:2", self.run_cli("active")[1])
        self.assertIn("1 lessons, 0 problems", self.run_cli("check")[1])

    def test_bump_of_an_archived_lesson_reactivates_it_within_the_cap(self):
        self.add_distinct(lessons.ACTIVE_CAP + 1)
        archived = self.run_cli("search", "unique0")[1]
        self.assertIn("[archive] - L001", archived)
        _, out, _ = self.run_cli("bump", "L001")
        self.assertIn("L001 hits:2 (back in Active)", out)
        self.assertIn(f"active cap {lessons.ACTIVE_CAP} reached: archived L002", out)
        active = self.run_cli("active")[1]
        self.assertIn("- L001 ", active)
        self.assertEqual(len(active.strip().splitlines()), lessons.ACTIVE_CAP)


class SecretFilterTests(LedgerCase):
    def accepted(self, text):
        code, _, err = self.run_cli("add", "--mistake", text, "--cause", "c", "--rule", f"r {len(text)} {hash(text)}")
        return code == 0, err

    def test_paths_shas_and_long_names_are_not_secrets(self):
        harmless = [
            "edited /srv/app/.agents/skills/x/snapshot.py",
            "reverted e385c72f86fda0c85bf097c62dd0e30286f12345 without reading it",
            "broke commit e385c72 on feat/enforcement-hooks-task-snapshot-benchmark",
            "renamed test_concurrent_adds_keep_every_lesson_written_by_parallel_processes",
            "misused MyVeryLongClassNameForHandlingOAuth2CallbacksAndRefreshV2",
            r"ran C:\\Users\\someone\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
            "reused request id 16fd2706-8baf-433b-82eb-8c7fada847da",
            "the token bucket refilled too slowly and the secret santa job timed out",
            "never log the session token: redact it first", "rotate the secret: do not reuse it",
            "password: never echo it to the terminal", "pass --token=$CI_TOKEN from the environment",
            "use `api_key = os.environ[...]` instead of a literal", "token:refresh endpoint returned 401",
        ]
        for text in harmless:
            self.assertEqual(self.accepted(text), (True, ""), text)

    def test_real_secret_shapes_are_refused(self):
        secrets = [
            "sk-ant-api03-abcdefghijklmnop1234", "ghp_" + "a1B2c3D4e5" * 4, "github_pat_" + "A1b2C3d4E5" * 3,
            "AKIAIOSFODNN7EXAMPLE", "xoxb-123456789012-abcdefGHIJ",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
            "-----BEGIN RSA PRIVATE KEY-----", "password: hunter2", "Authorization bearer=abc123",
            "Zx8Kq2Lm9Pw4Rt7Yv1Bn6Cd3Fg5Hj0Ks",
            "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            "glpat-" + "a1b2" * 5, "https://hooks.slack.com/services/T0123ABCD/B0123ABCD/xyz",
            "postgres://app:s3cretpw@db.internal:5432/prod",
        ]
        for text in secrets:
            ok, err = self.accepted(f"pasted {text} into the log")
            self.assertFalse(ok, text)
            self.assertIn("secret", err)
        self.assertFalse(Path(self.file).exists())

    def test_secret_in_tags_is_refused(self):
        code, _, _ = self.run_cli("add", "--tags", "ghp_" + "a1B2c3D4e5" * 4, "--mistake", "m", "--cause", "c",
                                  "--rule", "r")
        self.assertEqual(code, 2)


class DamagedLedgerTests(LedgerCase):
    def test_non_utf8_ledger_is_read_and_reported_but_not_rewritten(self):
        self.add("Dropped a column without a dry run")
        Path(self.file).write_bytes(Path(self.file).read_bytes().replace(b"Dropped", b"Dr\xffpped"))
        self.assertIn("L001 [sql]", self.hook_context())
        self.assertEqual(self.run_cli("check")[0], 1)  # reported: a write would replace the bad byte
        self.assertEqual(self.run_cli("bump", "L001")[0], 2)

    def test_lesson_above_the_sections_is_reported_and_kept(self):
        self.add("Dropped a column without a dry run")
        text = Path(self.file).read_text(encoding="utf-8")
        orphan = "- L009 [git] hits:1 | 2026-01-01 | Mistake: m | Cause: c | Rule: r | Check: k"
        Path(self.file).write_text(text.replace("\n## Active", orphan + "\n\n## Active"), encoding="utf-8")
        code, out, _ = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("problem: lesson outside any section", out)
        self.assertIn("L009", out)
        self.assertEqual(self.run_cli("bump", "L001")[0], 0)
        self.assertIn(orphan, Path(self.file).read_text(encoding="utf-8"))

    def test_hook_never_fails_the_session(self):
        with mock.patch.object(lessons.Ledger, "_parse", side_effect=RuntimeError("boom")):
            self.add("Dropped a column without a dry run")
        Path(self.file).write_text("## Active\n", encoding="utf-8")
        for error in (RuntimeError("boom"), OSError("gone")):
            with mock.patch.object(lessons.Ledger, "_parse", side_effect=error):
                self.assertEqual(self.run_cli("active", "--hook"), (0, "", ""))
        with mock.patch.object(lessons.Ledger, "_parse", side_effect=OSError("gone")):
            self.assertEqual(self.run_cli("active")[0], 2)

    def test_hook_does_not_wait_on_a_stdin_that_stays_open(self):
        self.add("Dropped a column without a dry run")
        started = time.monotonic()
        process = subprocess.Popen([sys.executable, SCRIPT, "--file", self.file, "active", "--hook"], env=self.env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            out = process.stdout.read()
            self.assertEqual(process.wait(timeout=20), 0)
        finally:
            process.stdin.close()
            process.stdout.close()
            process.stderr.close()
        self.assertIn("L001 [sql]", json.loads(out)["hookSpecificOutput"]["additionalContext"])
        self.assertLess(time.monotonic() - started, 10)


class GlobalLedgerTests(LedgerCase):
    def test_add_global_writes_only_the_global_ledger_with_its_own_ids(self):
        code, out, _ = self.add("Force pushed over a teammate's commits", rule="Use --force-with-lease", tags="git",
                                extra=("--global",))
        self.assertEqual((code, out.strip()), (0, "added G001"))
        self.assertFalse(Path(self.file).exists())
        self.assertIn("- G001 [git] hits:1", self.shared.read_text(encoding="utf-8"))

    def test_active_lists_project_then_labelled_global_without_duplicates(self):
        self.add("Dropped a column without a dry run")
        self.add("Dropped a column without a dry run", extra=("--global",))
        self.add("Force pushed over a teammate's commits", rule="Use --force-with-lease", tags="git",
                 extra=("--global",))
        lines = self.run_cli("active")[1].strip().splitlines()
        self.assertEqual([line[:6] for line in lines], ["- L001", lessons.GLOBAL_LABEL[:6], "- G002"])
        context = self.hook_context()
        self.assertLess(context.index("- L001"), context.index(lessons.GLOBAL_LABEL))
        self.assertLess(context.index(lessons.GLOBAL_LABEL), context.index("- G002"))
        self.assertNotIn("- G001", context)

    def test_global_lessons_load_in_a_project_with_no_ledger(self):
        self.add("Force pushed over a teammate's commits", rule="Use --force-with-lease", extra=("--global",))
        context = self.hook_context()
        self.assertIn("- G001", context)
        self.assertNotIn("(no lessons yet)", context)
        self.assertIn("[global active] - G001", self.run_cli("search", "force")[1])

    def test_global_id_routes_commands_to_the_global_ledger(self):
        self.add("Force pushed over a teammate's commits", rule="Use --force-with-lease", extra=("--global",))
        self.assertIn("G001 hits:2", self.run_cli("bump", "G001")[1])
        self.assertIn("1 lessons, 0 problems", self.run_cli("check", "--global")[1])
        self.assertEqual(self.run_cli("archive", "g001")[1].strip(), "archived G001")
        self.assertEqual(self.run_cli("active")[1], "")

    def test_globalize_moves_a_project_lesson(self):
        self.add("Dropped a column without a dry run")
        self.run_cli("bump", "L001")
        code, out, _ = self.run_cli("globalize", "L001")
        self.assertEqual(code, 0)
        self.assertIn("as G001", out)
        self.assertIn("- G001 [sql] hits:2", self.shared.read_text(encoding="utf-8"))
        project = Path(self.file).read_text(encoding="utf-8")
        self.assertIn("| Promoted: global G001", project.split("## Archive")[1])
        self.assertEqual(self.run_cli("active")[1].strip().splitlines()[0], lessons.GLOBAL_LABEL)
        self.assertEqual(self.run_cli("check")[0], 0)

    def test_globalize_merges_into_a_matching_global_lesson(self):
        self.add("Dropped a column without a dry run", extra=("--global",))
        self.add("Dropped a column without a dry run")
        self.assertIn("duplicate of G001: hits bumped to 2", self.run_cli("globalize", "L001")[1])
        self.assertIn("1 lessons", self.run_cli("check", "--global")[1])

    def test_global_ledger_inside_the_repository_is_refused(self):
        repo = self.dir / "repo"
        (repo / ".git").mkdir(parents=True)
        inside = repo / "sub" / "global-lessons.md"
        project = repo / ".agents" / "lessons.md"
        with mock.patch.dict(os.environ, {"LESSONS_GLOBAL_FILE": str(inside)}):
            for cwd in (repo, self.dir):  # run from inside it, and from outside with the project ledger named
                with mock.patch.object(lessons.Path, "cwd", return_value=cwd):
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        code = lessons.main(["--file", str(project), "add", "--global", "--mistake", "Force pushed",
                                             "--cause", "c", "--rule", "Use --force-with-lease", "--check", "k"])
                    self.assertEqual(code, 2, cwd)
                    self.assertIn("inside this repository", err.getvalue())
        self.assertFalse(inside.exists())

    def test_default_global_ledger_is_under_the_home_agents_dir(self):
        with mock.patch.dict(os.environ), mock.patch.object(lessons.Path, "home", return_value=self.dir):
            del os.environ["LESSONS_GLOBAL_FILE"]
            self.assertEqual(lessons.global_path(), self.dir / ".agents" / "lessons.md")

    def test_global_ledger_that_is_the_project_ledger_is_not_listed_twice(self):
        self.add("Dropped a column without a dry run")
        with mock.patch.dict(os.environ, {"LESSONS_GLOBAL_FILE": self.file}):
            self.assertEqual(len(self.run_cli("active")[1].strip().splitlines()), 1)


class RobustnessTests(LedgerCase):
    def test_latin1_ledger_is_reported_and_never_rewritten(self):
        self.add("Dropped a column without a dry run")
        raw = Path(self.file).read_bytes().replace(b"column", b"caf\xe9")
        Path(self.file).write_bytes(raw)
        code, out, _ = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("not valid UTF-8", out)
        code, _, err = self.add("Something entirely different happened", rule="Another unrelated guard")
        self.assertEqual(code, 2)
        self.assertIn("not valid UTF-8", err)
        self.assertEqual(Path(self.file).read_bytes(), raw)
        self.assertIn("L001", self.run_cli("active")[1])  # reading still works

    def test_empty_lessons_file_variable_uses_the_default_path(self):
        with mock.patch.dict(os.environ, {"LESSONS_FILE": ""}):
            self.assertEqual(lessons.build_parser().parse_args(["check"]).file, ".agents/lessons.md")

    def test_unencodable_argument_is_an_error_not_a_traceback(self):
        code, _, err = self.add("bad \udcff byte arg")
        self.assertEqual(code, 2)
        self.assertIn("error:", err)

    def test_unreadable_global_ledger_keeps_the_project_lessons(self):
        self.add("Dropped a column without a dry run")
        self.shared.parent.mkdir(parents=True)
        self.shared.write_text("x", encoding="utf-8")
        real = lessons.Ledger.__init__

        def init(ledger, path, prefix="L"):
            if prefix == "G":
                raise PermissionError("denied")
            real(ledger, path, prefix)

        with mock.patch.object(lessons.Ledger, "__init__", init):
            self.assertIn("L001", self.hook_context())
            code, out, err = self.run_cli("active")
        self.assertEqual(code, 0)
        self.assertIn("L001", out)
        self.assertIn("global ledger", err)


class PromotionTests(LedgerCase):
    def setUp(self):
        super().setUp()
        self.add("Dropped a column without a dry run")
        self.rules = Path(self.file).parent / "rules" / promotion.RULE_FILE

    def test_promote_writes_a_rule_stub_and_stops_injecting(self):
        code, out, _ = self.run_cli("promote", "L001")
        self.assertEqual(code, 0)
        self.assertIn("promoted L001", out)
        rule = self.rules.read_text(encoding="utf-8")
        self.assertTrue(rule.startswith("---\ntrigger: always_on\ndescription: '"))
        self.assertEqual(rule.split("\n")[3], "---")
        self.assertIn("\n# Promoted Lessons\n\n- Run the migration dry run first Check: grep dry-run in CI. "
                      "(From lesson L001, seen 1 times: Dropped a column without a dry run)\n", rule)
        self.assertEqual(self.run_cli("active")[1], "")
        self.assertNotIn("- L001", self.hook_context())
        self.assertIn(f"| Promoted: {self.rules.as_posix()}", Path(self.file).read_text(encoding="utf-8"))
        self.assertEqual(self.run_cli("check")[0], 0)

    def test_rule_file_collects_lessons_without_repeating_a_line(self):
        self.add("Force pushed over a teammate's commits", rule="Use --force-with-lease", tags="git")
        for lesson_id in ("L001", "L002"):
            self.assertEqual(self.run_cli("promote", lesson_id)[0], 0)
        self.run_cli("bump", "L001")
        self.assertEqual(self.run_cli("promote", "L001")[0], 0)
        rule = self.rules.read_text(encoding="utf-8")
        self.assertEqual((rule.count("From lesson L001"), rule.count("From lesson L002"), rule.count("trigger:")),
                         (1, 1, 1))

    def test_cap_never_evicts_the_lesson_just_added(self):
        self.add_distinct(lessons.ACTIVE_CAP)
        for n in range(lessons.ACTIVE_CAP):  # the new lesson will have the lowest hits and the newest date
            self.run_cli("bump", f"L{n + 1:03d}")
        code, out, _ = self.add("Brand new unrelated mishap xyzzy", rule="plugh quux guard")
        self.assertEqual(code, 0)
        self.assertIn("archived", out)
        self.assertIn("xyzzy", self.run_cli("active")[1])

    def test_a_reused_lesson_id_still_gets_its_own_rule_line(self):
        self.run_cli("promote", "L001")
        Path(self.file).unlink()
        self.add("Deployed past the quota", rule="Check quota before deploy")
        code, out, _ = self.run_cli("promote", "L001")
        self.assertEqual(code, 0)
        self.assertIn("rule stub written to", out)
        self.assertIn("Check quota before deploy", self.rules.read_text(encoding="utf-8"))

    def test_promoting_an_already_written_rule_says_so(self):
        self.run_cli("promote", "L001")
        self.run_cli("bump", "L001")
        self.assertIn("already present in", self.run_cli("promote", "L001")[1])

    def test_rules_dir_option_and_global_lesson_rules_location(self):
        other = self.dir / "elsewhere"
        self.assertEqual(self.run_cli("promote", "L001", "--rules-dir", str(other))[0], 0)
        self.assertTrue((other / promotion.RULE_FILE).is_file())
        self.add("Force pushed over a teammate's commits", rule="Use --force-with-lease", extra=("--global",))
        self.assertEqual(self.run_cli("promote", "G001")[0], 0)
        self.assertTrue((self.shared.parent / "rules" / promotion.RULE_FILE).is_file())

    def test_test_stub_is_printed_and_marks_nothing(self):
        code, out, _ = self.run_cli("promote", "L001", "--as", "test")
        self.assertEqual(code, 0)
        self.assertIn("class LessonL001Test(unittest.TestCase):", out)
        self.assertIn("def test_run_the_migration_dry_run_first(self):", out)
        self.assertIn("grep dry-run in CI", out)
        self.assertIn("promote L001 --guard", out)
        compile(out.split("\nWrite it")[0], "stub", "exec")
        self.assertIn("- L001", self.run_cli("active")[1])
        self.assertFalse(self.rules.exists())

    def test_guard_must_exist_then_marks_the_lesson(self):
        guard = self.dir / "test_migration.py"
        code, _, err = self.run_cli("promote", "L001", "--guard", str(guard))
        self.assertEqual(code, 2)
        self.assertIn("does not exist", err)
        self.assertIn("- L001", self.run_cli("active")[1])
        guard.write_text("", encoding="utf-8")
        self.assertEqual(self.run_cli("promote", "L001", "--guard", str(guard))[0], 0)
        self.assertIn(f"| Promoted: {guard.as_posix()}", self.run_cli("search", "column")[1])
        self.assertFalse(self.rules.exists())

    def test_promoted_lesson_that_recurs_returns_and_names_its_guard(self):
        self.run_cli("promote", "L001")
        _, out, _ = self.add("Dropped a column without any dry run again")
        self.assertIn("(back in Active)", out)
        self.assertIn("GUARD FAILED L001", out)
        self.assertNotIn("PROMOTE L001", out)
        self.assertIn("- L001", self.run_cli("active")[1])
        self.run_cli("bump", "L001")
        self.assertIn("candidate L001 hits:3: recurred after promotion", self.run_cli("check")[1])

    def test_unpromoted_repeat_still_gets_the_hint(self):
        self.run_cli("bump", "L001")
        self.assertIn("PROMOTE L001", self.run_cli("bump", "L001")[1])
        self.assertIn("candidate L001 hits:3: run `promote L001`", self.run_cli("check")[1])

    def test_unknown_id_is_a_usage_error(self):
        for command in ("promote", "globalize", "archive"):
            self.assertEqual(self.run_cli(command, "L999")[0], 2, command)


class RelevanceTests(LedgerCase):
    @staticmethod
    def lesson(lesson_id, tags, hits=1, when="2026-01-01", text="nothing special"):
        return {"id": lesson_id, "tags": tags, "hits": hits, "date": when, "mistake": text, "rule": text, "check": ""}

    def test_rank_keeps_most_recurrent_then_relevant_then_newest(self):
        tokens = relevance.path_tokens([" M db/migrations/0042_orders.sql", "src/api/handler.py"])
        self.assertTrue({"sql", "database", "migrations", "python", "handler"} <= tokens)
        pool = [self.lesson("old", "css", when="2025-01-01"), self.lesson("new", "css", when="2026-06-01"),
                self.lesson("word", "", text="the orders handler lost rows"), self.lesson("tag", "sql,python"),
                self.lesson("often", "css", hits=5), self.lesson("twice", "css", hits=2),
                self.lesson("thrice", "css", hits=3), self.lesson("four", "css", hits=4)]
        order = [lesson["id"] for lesson in relevance.rank(pool, tokens)]
        self.assertEqual(order, ["often", "four", "thrice", "tag", "word", "new", "twice", "old"])

    def test_rank_without_paths_is_recency(self):
        pool = [self.lesson("a", "x", when="2026-01-01"), self.lesson("b", "x", when="2026-03-01"),
                self.lesson("c", "x", when="2026-03-01")]
        self.assertEqual([lesson["id"] for lesson in relevance.rank(pool, set())], ["c", "b", "a"])

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_changed_paths_reads_working_tree_and_recent_commits(self):
        repo = self.dir / "repo"
        (repo / "db").mkdir(parents=True)
        (repo / "db" / "schema.sql").write_text("select 1;\n", encoding="utf-8")
        git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
               "-c", "commit.gpgsign=false"]
        for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "init"]):
            subprocess.run(git + args, check=True, capture_output=True)
        (repo / "worker.py").write_text("x = 1\n", encoding="utf-8")
        paths = " ".join(relevance.changed_paths(str(repo)))
        self.assertIn("db/schema.sql", paths)
        self.assertIn("worker.py", paths)
        self.assertEqual(relevance.changed_paths(str(self.dir / "home")), [])

    def test_changed_paths_is_empty_when_git_is_missing_or_slow(self):
        for error in (FileNotFoundError("git"), subprocess.TimeoutExpired("git", 1)):
            with mock.patch.object(relevance.subprocess, "run", side_effect=error) as run:
                self.assertEqual(relevance.changed_paths("."), [])
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.kwargs["timeout"], relevance.GIT_TIMEOUT)

    def test_hook_uses_the_session_cwd_and_puts_relevant_lessons_first(self):
        self.add("Left a console.log in the bundle", rule="Strip debug output before commit", tags="node")
        self.add("Dropped a column without a dry run", tags="sql")
        with mock.patch.object(relevance, "changed_paths", return_value=["db/001_init.sql"]) as changed:
            context = self.hook_context(stdin=json.dumps({"cwd": str(self.dir)}))
        changed.assert_called_once_with(str(self.dir))
        self.assertLess(context.index("- L002"), context.index("- L001"))
        with mock.patch.object(relevance, "changed_paths", return_value=["web/app.js"]) as changed:
            context = self.hook_context(stdin="not json")
        changed.assert_called_once_with(os.getcwd())
        self.assertLess(context.index("- L001"), context.index("- L002"))

    def test_hook_output_is_capped_and_says_how_to_find_the_rest(self):
        long = "x" * lessons.FIELD_MAX
        for scope in ((), ("--global",)):
            for n in range(lessons.ACTIVE_CAP):
                key = f"{n}{'g' if scope else 'p'}"
                self.run_cli("add", "--tags", f"tag{n}", "--mistake", f"unique{key} {long}", "--cause", long,
                             "--rule", f"distinct{key} {long}", "--check", long, *scope)
        self.run_cli("bump", "L007")
        with mock.patch.object(relevance, "changed_paths", return_value=[]):
            context = self.hook_context()
        self.assertLessEqual(len(context), lessons.HOOK_MAX)
        self.assertLess(lessons.HOOK_MAX, 10000)
        self.assertEqual(lessons.HOOK_MAX, 4000)  # the documented cap
        self.assertEqual(relevance.TAG_WEIGHT, 3)
        self.assertLess(2 * relevance.GIT_TIMEOUT + relevance.STDIN_WAIT, 10)  # inside the hook's 10 s timeout
        shown = context.count("\n- L") + context.count("\n- G")
        self.assertGreaterEqual(shown, 3)
        self.assertTrue(context.endswith(f"(+{2 * lessons.ACTIVE_CAP - shown} more: lessons.py search <words>)"))
        self.assertTrue(context.split("\n")[1].startswith("- L007 "), "the most recurrent lesson is always kept")
        self.assertIn(lessons.GLOBAL_LABEL, context)
        self.assertIn(" ...", context)

    def test_short_ledger_is_shown_whole_with_no_more_line(self):
        self.add_distinct(lessons.ACTIVE_CAP)
        with mock.patch.object(relevance, "changed_paths", return_value=[]):
            context = self.hook_context()
        self.assertEqual(context.count("\n- L"), lessons.ACTIVE_CAP)
        self.assertNotIn("more: lessons.py search", context)


if __name__ == "__main__":
    unittest.main()
