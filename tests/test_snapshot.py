import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "handoff" / "scripts" / "snapshot.py"


sys.path.insert(0, str(SCRIPT.parent))
import snapshot_task  # noqa: E402


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                   capture_output=True)


class SnapshotCase(unittest.TestCase):
    """A git repository with one untracked file; snapshot files live in a separate directory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self.tmp.name)
        git(self.dir, "init", "-q")
        (Path(self.dir) / "work.txt").write_text("x")
        self.outside = tempfile.TemporaryDirectory()
        self.snap = Path(self.outside.name) / "snap.md"
        self.prompts = Path(self.outside.name) / "snap.prompts.json"

    def tearDown(self):
        self.tmp.cleanup()
        self.outside.cleanup()

    def run_hook(self, cmd, payload=None, cwd=None, env=None):
        stdin = payload if isinstance(payload, str) else json.dumps(payload or {})
        base = {**os.environ, "HANDOFF_SNAPSHOT": str(self.snap), "TMPDIR": self.outside.name}
        return subprocess.run([sys.executable, str(SCRIPT), cmd], cwd=cwd or self.dir, input=stdin,
                              capture_output=True, text=True, env={**base, **(env or {})})

    def shown(self, **kwargs):
        out = self.run_hook("show", {"source": "compact"}, **kwargs).stdout
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""


class SnapshotTest(SnapshotCase):
    def test_write_records_uncommitted_work(self):
        result = self.run_hook("write")
        self.assertEqual(result.returncode, 0)
        self.assertIn("?? work.txt", self.snap.read_text())

    def test_show_after_compact_emits_hook_json(self):
        self.run_hook("write")
        out = self.run_hook("show", {"source": "compact"})
        context = json.loads(out.stdout)["hookSpecificOutput"]
        self.assertEqual(context["hookEventName"], "SessionStart")
        self.assertIn("work.txt", context["additionalContext"])

    def test_show_is_silent_on_other_sources(self):
        self.run_hook("write")
        for source in ("startup", "resume", "clear"):
            self.assertEqual(self.run_hook("show", {"source": source}).stdout, "")

    def test_never_fails_outside_a_repo_or_on_bad_input(self):
        with tempfile.TemporaryDirectory() as plain:
            self.assertEqual(self.run_hook("write", cwd=plain).returncode, 0)
            self.assertFalse(self.snap.exists())
            for cmd in ("show", "write", "prompt", "unknown"):
                result = self.run_hook(cmd, "not json", cwd=plain)
                self.assertEqual((result.returncode, result.stdout), (0, ""), cmd)

    def test_outside_a_repo_the_task_state_is_still_saved(self):
        with tempfile.TemporaryDirectory() as plain:
            self.run_hook("prompt", {"prompt": "rename the widget"}, cwd=plain)
            self.run_hook("write", cwd=plain)
            text = self.shown(cwd=plain)
        self.assertIn("rename the widget", text)
        self.assertIn("Not a git repository.", text)
        self.assertNotIn("Branch:", text)

    def test_default_path_is_outside_the_project_and_keyed_by_session(self):
        env = {k: v for k, v in os.environ.items() if k != "HANDOFF_SNAPSHOT"}
        env["TMPDIR"] = self.outside.name
        payload = json.dumps({"session_id": "abc/../123", "prompt": "do it"})
        for cmd in ("prompt", "write"):
            subprocess.run([sys.executable, str(SCRIPT), cmd], cwd=self.dir, input=payload,
                           capture_output=True, text=True, env=env, check=True)
        created = [Path(self.outside.name) / name
                   for name in ("arsenal-snapshot-abc123.md", "arsenal-snapshot-abc123.prompts.json")]
        for path in created:
            self.assertTrue(path.is_file(), path)
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600, path)
        self.assertEqual(sorted(os.listdir(self.outside.name)), sorted(p.name for p in created))  # no temp left
        tracked = subprocess.run(["git", "status", "--short"], cwd=self.dir, capture_output=True, text=True)
        self.assertEqual(tracked.stdout.strip(), "?? work.txt")

    def test_scripts_leave_no_bytecode_beside_them(self):
        copy = Path(self.outside.name) / "scripts"
        copy.mkdir()
        for name in ("snapshot.py", "snapshot_task.py"):
            shutil.copy(SCRIPT.parent / name, copy / name)
        env = {**os.environ, "HANDOFF_SNAPSHOT": str(self.snap), "PYTHONDONTWRITEBYTECODE": ""}
        subprocess.run([sys.executable, str(copy / "snapshot.py"), "write"], cwd=self.dir, input="{}",
                       capture_output=True, text=True, env=env, check=True)
        self.assertTrue(self.snap.is_file())
        self.assertEqual(sorted(os.listdir(copy)), ["snapshot.py", "snapshot_task.py"])

    def test_a_missing_helper_module_never_fails_the_session(self):
        copy = Path(self.outside.name) / "alone"
        copy.mkdir()
        shutil.copy(SCRIPT, copy / "snapshot.py")
        result = subprocess.run([sys.executable, str(copy / "snapshot.py"), "prompt"], cwd=self.dir,
                                input='{"prompt": "x"}', capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_precompact_timeout_covers_the_git_budget(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        self.assertGreaterEqual(hooks["PreCompact"][0]["hooks"][0]["timeout"], 15)

    def test_hooks_json_wires_all_three_events(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        self.assertIn("snapshot.py\\\" write", json.dumps(hooks["PreCompact"]))
        self.assertIn("snapshot.py\\\" show", json.dumps(hooks["SessionStart"]))
        submit = hooks["UserPromptSubmit"]
        self.assertEqual(len(submit), 1)
        self.assertNotIn("matcher", submit[0])  # every prompt
        command = submit[0]["hooks"][0]["command"]
        self.assertEqual(command.count("${CLAUDE_PLUGIN_ROOT}/.agents/skills/handoff/scripts/snapshot.py\" prompt"), 2)
        self.assertIn("|| python ", command)
        self.assertLessEqual(submit[0]["hooks"][0]["timeout"], 10)


class PromptRecorderTest(SnapshotCase):
    def record(self, *prompts):
        for text in prompts:
            result = self.run_hook("prompt", {"session_id": "s1", "prompt": text})
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def state(self):
        return json.loads(self.prompts.read_text())

    def test_keeps_the_first_prompt_and_the_last_few(self):
        self.record(*[f"prompt {n}" for n in range(1, 8)])
        self.assertEqual(self.state(), {"first": "prompt 1", "last": ["prompt 5", "prompt 6", "prompt 7"], "count": 7})

    def test_a_single_prompt_is_not_repeated_as_latest(self):
        self.record("only one")
        self.assertEqual(self.state(), {"first": "only one", "last": [], "count": 1})

    def test_caps_each_prompt_and_the_file(self):
        self.record(*["x" * 50000] * 6)
        state = self.state()
        self.assertEqual(len(state["first"]), snapshot_task.FIRST_CHARS)
        self.assertEqual([len(item) for item in state["last"]], [snapshot_task.LAST_CHARS] * snapshot_task.KEEP_LAST)
        self.assertIn("chars)", state["first"])
        self.assertLess(self.prompts.stat().st_size, 2000)

    def test_skips_empty_blank_and_non_text_prompts(self):
        for payload in ({"prompt": ""}, {"prompt": "  \n\t"}, {"prompt": None}, {"prompt": ["a"]}, {}, [1, 2]):
            self.assertEqual(self.run_hook("prompt", payload).returncode, 0)
        self.assertFalse(self.prompts.exists())

    def test_empty_or_garbage_stdin_writes_nothing(self):
        for raw in ("", "not json", "\x00\xff{", "{\"prompt\":"):
            result = self.run_hook("prompt", raw or " ")
            self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertFalse(self.prompts.exists())

    def test_a_damaged_record_is_replaced(self):
        for damaged in ("{broken", "[]", json.dumps({"first": 3, "last": "x", "count": "n"})):
            self.prompts.write_text(damaged)
            self.record("fresh start")
            self.assertEqual(self.state(), {"first": "fresh start", "last": [], "count": 1})

    def test_without_a_session_id_nothing_is_recorded(self):
        env = {k: v for k, v in os.environ.items() if k != "HANDOFF_SNAPSHOT"}
        env["TMPDIR"] = self.outside.name
        subprocess.run([sys.executable, str(SCRIPT), "prompt"], cwd=self.dir, input='{"prompt": "hello"}',
                       capture_output=True, text=True, env=env, check=True)
        self.assertEqual(os.listdir(self.outside.name), [])

    def test_a_prompt_that_cannot_be_encoded_does_not_cost_the_snapshot(self):
        result = self.run_hook("prompt", '{"session_id": "s1", "prompt": "fix \\ud83d bug"}')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.snap.write_text("OLD")
        self.run_hook("write")
        text = self.shown()
        self.assertIn("Original request (first of 1 user prompts):\nfix ? bug", text)
        self.assertIn("Uncommitted (git status --short):\n?? work.txt", text)

    def test_a_failed_write_leaves_no_temp_file_behind(self):
        target = Path(self.outside.name) / "taken"
        target.mkdir()
        (target / "child").write_text("x")  # a non-empty directory cannot be replaced by a file
        with self.assertRaises(OSError):
            snapshot_task.atomic_write(target, "text")
        self.assertEqual(os.listdir(self.outside.name), ["taken"])

    def test_unwritable_location_never_fails_the_turn(self):
        blocker = Path(self.outside.name) / "file"
        blocker.write_text("")
        result = self.run_hook("prompt", {"prompt": "hi"}, env={"HANDOFF_SNAPSHOT": str(blocker / "snap.md")})
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_snapshot_quotes_the_request_and_the_latest_instructions(self):
        self.record("build the importer", "use csv not json", "also add a dry run flag")
        self.run_hook("write")
        text = self.shown()
        self.assertIn("Original request (first of 3 user prompts):\nbuild the importer", text)
        self.assertIn("Latest user instructions (most recent last):\n- use csv not json\n- also add a dry run flag", text)
        self.assertLess(text.index("Original request"), text.index("Branch:"))


def line(role, *blocks, **extra):
    return json.dumps({"type": role, "message": {"role": role, "content": list(blocks)}, **extra})


def use(name, args, use_id="u"):
    return {"type": "tool_use", "id": use_id, "name": name, "input": args}


def result(use_id, content):
    return {"type": "tool_result", "tool_use_id": use_id, "content": content}


TASK_TRANSCRIPT = [
    line("user", {"type": "text", "text": "TaskCreate is mentioned here but this is not a tool call"}),
    line("assistant", use("TaskCreate", {"subject": "write parser", "description": "d"}, "c1")),
    line("user", result("c1", "Task #1 created successfully: write parser")),
    "{ this line is not json but mentions TaskUpdate",
    line("assistant", use("TaskCreate", {"subject": "add tests", "description": "d"}, "c2"),
         use("TaskCreate", {"subject": "update docs", "description": "d"}, "c3")),
    line("user", result("c2", [{"type": "text", "text": "Task #2 created successfully: add tests"}]),
         result("c3", None), toolUseResult={"task": {"id": 3, "subject": "update docs"}}),
    line("assistant", use("TaskCreate", {"subject": "subagent work"}, "c9"), isSidechain=True),
    line("assistant", use("TaskUpdate", {"taskId": "1", "status": "completed"})),
    line("assistant", use("TaskUpdate", {"taskId": "2", "status": "in_progress", "subject": "add unit tests"})),
    line("assistant", use("TaskUpdate", {"taskId": "77", "status": "in_progress"})),
    line("assistant", use("TaskCreate", {"subject": "dropped idea"}, "c4")),
    line("user", result("c4", "Task #4 created successfully: dropped idea")),
    line("assistant", use("TaskUpdate", {"taskId": "4", "status": "deleted"})),
    json.dumps({"type": "assistant", "message": "TaskCreate as a string"}),
    json.dumps({"type": "assistant", "message": {"content": [7, None, {"type": "tool_use", "name": "TaskCreate"},
                                                             {"type": "tool_result", "tool_use_id": ["x"]},
                                                             use("TaskUpdate", "not a dict")]}}),
    json.dumps(["TaskCreate", 1]),
]


class TodoExtractionTest(SnapshotCase):
    def transcript(self, lines):
        path = Path(self.outside.name) / "transcript.jsonl"
        path.write_text("\n".join(lines) + "\n")
        return str(path)

    def test_task_tools_are_replayed_and_garbage_is_skipped(self):
        todos = snapshot_task.open_todos(self.transcript(TASK_TRANSCRIPT))
        self.assertEqual(todos, ["[in_progress] add unit tests", "[pending] update docs",
                                 "(1 completed or other, not listed)", snapshot_task.INCOMPLETE])  # task 77

    def test_a_complete_list_carries_no_warning(self):
        known = [entry for entry in TASK_TRANSCRIPT if '"77"' not in entry]
        self.assertNotIn(snapshot_task.INCOMPLETE, snapshot_task.open_todos(self.transcript(known)))

    def test_task_id_is_read_from_the_structured_result_when_the_text_changes(self):
        lines = [line("assistant", use("TaskCreate", {"subject": "alpha"}, "c1")),
                 line("user", result("c1", "Created."), toolUseResult={"task": {"id": "1", "subject": "alpha"}}),
                 line("assistant", use("TaskUpdate", {"taskId": "1", "status": "in_progress"}))]
        self.assertEqual(snapshot_task.open_todos(self.transcript(lines)), ["[in_progress] alpha"])

    def test_tasks_created_megabytes_before_their_updates_are_still_found(self):
        filler = [json.dumps({"type": "api-request-shape", "blob": "y" * 70_000})] * 30  # 2.1 MB, no task marker
        lines = [line("assistant", use("TaskCreate", {"subject": "alpha step"}, "c1")),
                 line("user", result("c1", "Task #1 created successfully: alpha step")),
                 line("assistant", use("TaskCreate", {"subject": "beta step"}, "c2")),
                 line("user", result("c2", "Task #2 created successfully: beta step")),
                 *filler,
                 line("assistant", use("TaskUpdate", {"taskId": "1", "status": "completed"})),
                 line("assistant", use("TaskUpdate", {"taskId": "2", "status": "in_progress"}))]
        self.assertEqual(snapshot_task.open_todos(self.transcript(lines)),
                         ["[in_progress] beta step", "(1 completed or other, not listed)"])

    def test_the_latest_todowrite_list_wins(self):
        old = use("TodoWrite", {"todos": [{"content": "stale item", "status": "pending", "activeForm": "x"}]})
        new = use("TodoWrite", {"todos": [{"content": "ship it", "status": "in_progress"},
                                          {"content": "done thing", "status": "completed"},
                                          {"content": 5, "status": "pending"}, "junk"]})
        todos = snapshot_task.open_todos(self.transcript([line("assistant", old), line("assistant", new)]))
        self.assertEqual(todos, ["[in_progress] ship it", "(1 completed or other, not listed)"])

    def test_missing_unreadable_or_empty_transcripts_give_nothing(self):
        for path in (None, "", 7, str(Path(self.outside.name) / "absent.jsonl"), self.outside.name,
                     self.transcript(["", "\x00\x01 binary TaskCreate", "[]"])):
            self.assertEqual(snapshot_task.open_todos(path), [], path)

    def test_a_transcript_beyond_the_scan_limit_is_read_from_its_end_and_marked_partial(self):
        early = [line("assistant", use("TaskCreate", {"subject": f"early {n}"}, f"e{n}")) for n in (1, 2)]
        padding = [line("assistant", {"type": "text", "text": "y" * 1000})] * 60
        late = [line("assistant", use("TaskCreate", {"subject": "late"}, "c1")),
                line("user", result("c1", "Task #9 created successfully: late"))]
        update = line("assistant", use("TaskUpdate", {"taskId": "9", "status": "in_progress"}))
        whole = line("assistant", use("TodoWrite", {"todos": [{"content": "all of it", "status": "pending"}]}))
        original = snapshot_task.SCAN_BYTES
        try:
            snapshot_task.SCAN_BYTES = 5000
            self.assertEqual(snapshot_task.open_todos(self.transcript([*early, *padding, *late, update])),
                             ["[in_progress] late", snapshot_task.INCOMPLETE])
            self.assertEqual(snapshot_task.open_todos(self.transcript([*early, *padding])), [])
            # a TodoWrite call carries the whole list, so nothing older can be missing
            self.assertEqual(snapshot_task.open_todos(self.transcript([*early, *padding, whole])),
                             ["[pending] all of it"])
            snapshot_task.SCAN_BYTES = len(update) + 3  # the cut lands inside the previous line, which no longer parses
            self.assertEqual(snapshot_task.open_todos(self.transcript([*early, *padding, *late, update])),
                             [snapshot_task.INCOMPLETE])
        finally:
            snapshot_task.SCAN_BYTES = original

    def test_snapshot_lists_open_todos_and_omits_the_section_when_none(self):
        self.run_hook("write", {"transcript_path": self.transcript(TASK_TRANSCRIPT)})
        self.assertIn("Open todos (from the task list):\n[in_progress] add unit tests\n[pending] update docs",
                      self.shown())
        for missing in ({"transcript_path": "/no/such/file.jsonl"}, {"transcript_path": 5}, {}):
            self.run_hook("write", missing)
            self.assertNotIn("Open todos", self.shown())

    def test_ledgers_on_disk_are_listed_as_pointers_only(self):
        ledger = Path(self.dir) / ".plan-workspace" / "import" / "progress.md"
        plan = Path(self.dir) / "docs" / "plans" / "import.md"
        flat = Path(self.dir) / ".plan-workspace" / "progress.md"
        name = Path(self.dir).name
        handoff = Path(self.outside.name) / f"handoff-{name}-20261113-1000.md"
        others = [Path(self.outside.name) / other for other in (
            "handoff-another-repo-20261113-1000.md", f"handoff-{name}-gateway-20261113-0900.md",
            f"handoff-{name}-notes.md")]
        for path in (ledger, plan, flat, handoff, *others):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("SECRET CONTENT")
        self.run_hook("write")
        text = self.shown()
        self.assertRegex(text, r"\.plan-workspace/import/progress\.md \(modified \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\)")
        self.assertIn("docs/plans/import.md (modified ", text)
        self.assertIn("\n.plan-workspace/progress.md (modified ", text)
        self.assertIn(f"{handoff} (modified ", text)
        for other in others:  # another repository's handoff, even one whose name starts with this one's
            self.assertNotIn(other.name, text)
        self.assertNotIn("SECRET CONTENT", text)

    def test_an_over_long_pointer_keeps_the_end_of_its_path_and_marks_the_cut(self):
        deep = Path(self.outside.name) / ("d" * 120) / ("e" * 120) / ("f" * 60)
        deep.mkdir(parents=True)
        handoff = deep / f"handoff-{Path(self.dir).name}-20261113-1000.md"
        handoff.write_text("x")
        self.run_hook("write", env={"TMPDIR": str(deep)})
        pointer = re.search(r"^\.\.\..*$", self.shown(), re.MULTILINE).group(0)
        self.assertRegex(pointer, re.escape(f"/{handoff.name} (modified ") + r"\S+\)$")
        self.assertEqual(len(pointer), snapshot_task.POINTER_CHARS)

    def test_no_ledgers_means_no_section(self):
        self.run_hook("write")
        self.assertNotIn("Ledgers on disk", self.shown())


class GitStateTest(SnapshotCase):
    def commit_files(self, count):
        names = [f"file_{n:03}.txt" for n in range(count)]
        for name in names:
            (Path(self.dir) / name).write_text("one\n")
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-q", "-m", "feat: base")
        return names

    def test_unstaged_change_keeps_its_leading_space(self):
        self.commit_files(1)
        (Path(self.dir) / "file_000.txt").write_text("two\n")
        self.run_hook("write")
        self.assertIn("Uncommitted (git status --short):\n M file_000.txt\n", self.snap.read_text())

    def test_long_status_says_how_many_entries_were_dropped(self):
        for n in range(80):
            (Path(self.dir) / f"untracked_file_number_{n:03}.txt").write_text("x")
        self.run_hook("write")
        status = self.snap.read_text().split("Uncommitted (git status --short):\n")[1].split("\n\n")[0].splitlines()
        self.assertRegex(status[-1], r"^\(\+\d+ more\)$")
        self.assertEqual(len(status) - 1 + int(status[-1][2:-6]), 81)  # 80 new files and work.txt

    def test_diff_stat_keeps_its_summary_line(self):
        for name in self.commit_files(40):
            (Path(self.dir) / name).write_text("two\n")
        self.run_hook("write")
        stat = self.snap.read_text().split("Diff stat vs HEAD:\n")[1].splitlines()
        self.assertRegex(stat[-2], r"^\(\+\d+ more\)$")
        self.assertIn("40 files changed", stat[-1])

    def test_failed_git_reads_are_unavailable_not_none(self):
        self.run_hook("write")  # no commit yet: log and diff against HEAD fail, status works
        text = self.snap.read_text()
        self.assertIn("Recent commits:\n(unavailable: git failed or timed out)", text)
        self.assertIn("?? work.txt", text)
        self.commit_files(1)
        self.run_hook("write")
        self.assertIn("Uncommitted (git status --short):\n(none)", self.snap.read_text())
        self.assertNotIn("(unavailable", self.snap.read_text())

    def test_without_git_everything_is_unavailable_and_still_shown(self):
        self.run_hook("prompt", {"prompt": "keep me"})
        no_git = {"PATH": self.outside.name}
        self.assertEqual(self.run_hook("write", env=no_git).returncode, 0)
        text = self.snap.read_text()
        self.assertEqual(text.count("(unavailable: git failed or timed out)"), 5)  # repo and four sections
        self.assertNotIn("(none)", text)
        self.assertIn("keep me", self.shown(env=no_git))
        self.assertIn("keep me", self.shown())

    def test_snapshot_is_stamped_and_its_age_is_labelled(self):
        self.run_hook("write")
        text = self.snap.read_text()
        self.assertRegex(text, r"\nTaken: \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\nRepo: " + re.escape(self.dir) + r"\n")
        self.assertRegex(self.shown(), r"\nTaken: \S+ \(\d min before this restart\)\nRepo: ")
        self.snap.write_text(re.sub(r"Taken: \S+", "Taken: 2020-01-01T00:00:00Z", text))
        self.assertRegex(self.shown(), r"Taken: 2020-01-01T00:00:00Z \(\d+ h before this restart\)")
        self.snap.write_text(re.sub(r"Taken: \S+", "Taken: garbage", text))
        self.assertIn("Taken: garbage\n", self.shown())

    def test_snapshot_from_another_repo_is_not_shown(self):
        self.run_hook("write")
        with tempfile.TemporaryDirectory() as other:
            git(other, "init", "-q")
            self.assertEqual(self.shown(cwd=other), "")
            self.assertEqual(self.run_hook("show", {"source": "compact"}, cwd=other).returncode, 0)
            out = self.run_hook("show", {"source": "compact", "cwd": self.dir}, cwd=other).stdout
            self.assertIn("work.txt", out)  # the hook's cwd field wins over the process directory
        sub = Path(self.dir) / "nested"
        sub.mkdir()
        self.assertIn("work.txt", self.shown(cwd=str(sub)))

    def test_skipped_write_removes_the_previous_snapshot(self):
        self.run_hook("write")
        self.assertTrue(self.snap.is_file())
        with tempfile.TemporaryDirectory() as plain:
            self.run_hook("write", cwd=plain)
        self.assertFalse(self.snap.exists())
        self.assertEqual(self.shown(), "")

    def test_long_prompts_cannot_starve_the_git_sections(self):
        for name in self.commit_files(60):
            (Path(self.dir) / name).write_text("two\n")
        ledger = Path(self.dir) / "docs" / "plans"
        ledger.mkdir(parents=True)
        for n in range(9):
            (ledger / f"{'plan' * 20}-{n}.md").write_text("p")
        todos = [{"content": f"todo {n} " + "t" * 300, "status": "pending"} for n in range(40)]
        transcript = Path(self.outside.name) / "t.jsonl"
        transcript.write_text(line("assistant", use("TodoWrite", {"todos": todos})) + "\n")
        for _ in range(5):
            self.run_hook("prompt", {"prompt": "p" * 30000})
        self.run_hook("write", {"transcript_path": str(transcript)})
        text = self.snap.read_text()
        self.assertLessEqual(len(text), 4000)
        for title in ("Original request", "Latest user instructions", "Open todos", "Ledgers on disk", "Branch:",
                      "Uncommitted (git status --short):\n M file_000.txt", "Recent commits:\n", "Diff stat vs HEAD:"):
            self.assertIn(title, text)
        self.assertIn("60 files changed", text.splitlines()[-1])
        self.assertLessEqual(len(self.shown()), 4100)


class SessionCoreTest(unittest.TestCase):
    def test_core_hook_emits_static_capped_context(self):
        script = ROOT / "hooks" / "session_core.py"
        first = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
        second = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
        self.assertEqual(first.returncode, 0)
        self.assertEqual(first.stdout, second.stdout)  # static text keeps the prompt cache warm
        context = json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(context), 1500)
        self.assertIn("test-every-change", context)

    def test_core_names_only_real_skills(self):
        text = (ROOT / "hooks" / "core.md").read_text()
        for skill in ("investigate", "test-every-change", "refactor-legacy", "code-review",
                      "requirements-grilling", "definition-of-done"):
            self.assertIn(skill, text)
            self.assertTrue((ROOT / ".agents" / "skills" / skill / "SKILL.md").is_file(), skill)

    def test_core_hook_is_wired_first_on_session_start(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        self.assertIn("session_core.py", hooks["SessionStart"][0]["hooks"][0]["command"])


class EvalCoverageTest(unittest.TestCase):
    def test_every_skill_has_a_trigger_eval_case(self):
        skills = sorted(p.name for p in (ROOT / ".agents" / "skills").iterdir() if p.is_dir())
        missing = [s for s in skills if not (ROOT / "evals" / f"trigger-{s}" / "prompt.md").is_file()]
        self.assertEqual(missing, [], "add evals/trigger-<skill>/ for each new skill")

    def test_every_trigger_case_names_an_existing_skill(self):
        for case in sorted((ROOT / "evals").glob("trigger-*")):
            skill = case.name[len("trigger-"):]
            self.assertTrue((ROOT / ".agents" / "skills" / skill).is_dir(), case.name)
            self.assertIn(skill, (case / "graders" / "skill-fired.md").read_text())


if __name__ == "__main__":
    unittest.main()
