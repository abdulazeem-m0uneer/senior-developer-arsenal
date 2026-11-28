"""unseen-time on the writers a registry entry names in "programs": how each passes its text (lesson L324)."""
import os
import sys
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from test_guard_unseen_time import RuleCase  # noqa: E402

SEEN, UNSEEN = "16:36", "17:36"  # RuleCase's transcript shows 16:36 only


class ProgramTextTests(RuleCase):
    def setUp(self):
        super().setUp()
        self.registry({**self.ENTRY, "programs": ["api.mjs", "report.sh"]})

    def judge(self, command):
        from guard_lessons import judge
        return judge(command, str(self.project), transcript=self.path)

    def body_file(self, text, name="body.txt"):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_argv_text_of_a_script_run_by_an_interpreter(self):
        self.assertEqual(self.judge(f"node .agents/pm/api.mjs POST /task/abc/comment '{{\"comment_text\":\"merged {UNSEEN}\"}}'").rule,
                         "unseen-time")
        self.assertIsNone(self.judge(f"node .agents/pm/api.mjs POST /task/abc/comment '{{\"comment_text\":\"merged {SEEN}\"}}'"))

    def test_interpreter_options_before_the_script_are_skipped(self):
        self.assertEqual(self.judge(f"node --no-warnings api.mjs POST /task/a/comment 'at {UNSEEN}'").rule, "unseen-time")
        self.assertEqual(self.judge(f"python3 -u report.sh 'at {UNSEEN}'").rule, "unseen-time")

    def test_an_interpreter_running_code_or_another_script_is_not_judged(self):
        self.assertIsNone(self.judge(f"node -e 'console.log(\"{UNSEEN}\")'"))
        self.assertIsNone(self.judge(f"node other.mjs 'at {UNSEEN}'"))

    def test_body_flag_text(self):
        self.assertEqual(self.judge(f"./report.sh --body 'done at {UNSEEN}'").rule, "unseen-time")
        self.assertIsNone(self.judge(f"./report.sh --body 'done at {SEEN}'"))

    def test_heredoc_body_on_stdin(self):
        self.assertEqual(self.judge(f"./report.sh --body-file - <<'EOF'\ndone at {UNSEEN}\nEOF").rule, "unseen-time")
        self.assertIsNone(self.judge(f"./report.sh --body-file - <<'EOF'\ndone at {SEEN}\nEOF"))

    def test_heredoc_written_to_a_file_the_program_then_reads(self):
        command = f"cat > /nonexistent-dir/b.txt <<'EOF'\ndone at {UNSEEN}\nEOF\n./report.sh --body-file /nonexistent-dir/b.txt"
        self.assertEqual(self.judge(command).rule, "unseen-time")

    def test_body_file_content_is_judged(self):
        path = self.body_file(f"done at {UNSEEN}")
        self.assertEqual(self.judge(f"node api.mjs POST /task/a/comment --body-file {path}").rule, "unseen-time")
        self.assertEqual(self.judge(f"./report.sh --body-file={path}").rule, "unseen-time")
        self.assertIsNone(self.judge(f"./report.sh --body-file {self.body_file(f'done at {SEEN}', 'ok.txt')}"))

    def test_body_file_after_a_home_or_variable_path_is_read(self):
        self.body_file(f"done at {UNSEEN}", "home.txt")
        command = f"B={self.dir}; ./report.sh --body-file $B/home.txt"
        self.assertEqual(self.judge(command).rule, "unseen-time")

    def test_an_unreadable_body_file_is_skipped(self):
        self.assertIsNone(self.judge("./report.sh --body-file /nonexistent-dir/none.txt"))
        self.assertIsNone(self.judge(f"./report.sh --body-file {self.dir}"))  # a directory
        self.assertIsNone(self.judge("./report.sh --body-file /dev/stdin"))

    def test_a_huge_body_file_is_skipped(self):
        path = self.body_file(f"{UNSEEN} " + "x" * 300_000)
        self.assertIsNone(self.judge(f"./report.sh --body-file {path}"))

    def test_an_unlisted_program_is_never_judged(self):
        path = self.body_file(f"done at {UNSEEN}")
        self.assertIsNone(self.judge(f"./other.sh --body 'at {UNSEEN}' --body-file {path}"))
        self.assertIsNone(self.judge(f"node other.mjs --body-file {path}"))

    def test_an_allow_entry_passes(self):
        self.registry({**self.ENTRY, "programs": ["report.sh"], "allow": [UNSEEN]})
        path = self.body_file(f"done at {UNSEEN}")
        self.assertIsNone(self.judge(f"./report.sh --body-file {path}"))
        self.assertIsNone(self.judge(f"./report.sh 'at {UNSEEN}'"))

    def test_a_body_file_the_same_call_writes_is_judged_by_the_new_content(self):
        path = self.body_file(f"old at {UNSEEN}", "c.json")
        write = f"cat > {path} <<'EOF'\nmerged at %s\nEOF\nnode api.mjs POST /task/a/comment --body-file {path}"
        self.assertIsNone(self.judge(write % SEEN))
        self.assertEqual(self.judge(write % UNSEEN).rule, "unseen-time")

    def test_a_code_here_document_beside_a_body_file_is_not_a_message(self):
        command = f"python3 - <<'EOF'\nprint('{UNSEEN}')\nEOF\nnode api.mjs POST /task/a/comment --body-file /nonexistent-dir/x.json"
        self.assertIsNone(self.judge(command))

    def test_a_relative_body_file_follows_a_cd_of_the_call(self):
        self.body_file(f"done at {UNSEEN}", "rel.txt")
        self.assertEqual(self.judge(f"cd {self.dir} && ./report.sh --body-file rel.txt").rule, "unseen-time")
        self.assertIsNone(self.judge("cd /nonexistent-dir && ./report.sh --body-file rel.txt"))

    def test_interpreter_options_that_take_a_value(self):
        for runner in ("node --loader ts-node/esm api.mjs", "python3 -W ignore report.sh", "python3 -X utf8 report.sh",
                       "deno run -A api.mjs", "bun run api.mjs", "node -r ts-node/register api.mjs"):
            with self.subTest(runner=runner):
                self.assertEqual(self.judge(f"{runner} POST /x 'at {UNSEEN}'").rule, "unseen-time")
        self.assertIsNone(self.judge(f"node other.mjs api.mjs 'at {UNSEEN}'"))
        self.assertIsNone(self.judge(f"node --eval 'x' api.mjs 'at {UNSEEN}'"))

    def test_a_read_request_is_not_a_message(self):
        self.assertIsNone(self.judge(f"node api.mjs GET '/task/abc?x={UNSEEN}'"))
        self.assertEqual(self.judge(f"node api.mjs PUT '/task/abc' 'at {UNSEEN}'").rule, "unseen-time")

    def test_a_body_file_the_call_writes_with_echo_or_printf_is_judged_by_that_text(self):
        for writer in ("echo '{\"c\":\"merged %s\"}' > b.json", "printf 'merged %s' > b.json", "echo 'merged %s' >> b.json",
                       "echo 'merged %s' | tee b.json", "echo 'merged %s' | tee -a b.json"):
            send = "node api.mjs POST /t/a/comment --body-file b.json"
            with self.subTest(writer=writer):
                self.assertEqual(self.judge(f"cd {self.dir} && {writer % UNSEEN} && {send}").rule, "unseen-time")
                self.assertIsNone(self.judge(f"cd {self.dir} && {writer % SEEN} && {send}"))

    def test_an_appended_body_file_also_sends_its_old_content(self):
        self.body_file(f"old at {UNSEEN}", "b.json")
        send = "node api.mjs POST /t/a/comment --body-file b.json"
        self.assertEqual(self.judge(f"cd {self.dir} && echo 'new at {SEEN}' >> b.json && {send}").rule, "unseen-time")
        self.assertIsNone(self.judge(f"cd {self.dir} && echo 'new at {SEEN}' > b.json && {send}"))

    def test_the_same_file_spelled_two_ways_is_one_file(self):
        home = self.dir / "home"
        home.mkdir(exist_ok=True)
        (home / "x.json").write_text(f"old at {UNSEEN}", encoding="utf-8")
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            write = "cat > \"$HOME/x.json\" <<'EOF'\n{\"c\":\"new %s\"}\nEOF\nnode api.mjs POST /t/a/comment --body-file ~/x.json"
            self.assertIsNone(self.judge(write % SEEN))
            self.assertEqual(self.judge(write % UNSEEN).rule, "unseen-time")
            rel = f"cd {home} && echo 'new %s' > ./x.json && node api.mjs POST /t/a/comment --body-file x.json"
            self.assertIsNone(self.judge(rel % SEEN))
            self.assertEqual(self.judge(rel % UNSEEN).rule, "unseen-time")

    def test_a_relative_body_file_starts_from_the_session_directory(self):
        sub = self.project / "sub"
        sub.mkdir()
        (sub / "a.json").write_text(f"done at {UNSEEN}", encoding="utf-8")
        from guard_lessons import judge
        send = "node api.mjs POST /t/a/comment --body-file a.json"
        self.assertEqual(judge(send, str(sub), transcript=self.path).rule, "unseen-time")
        self.assertIsNone(judge(send, str(self.project), transcript=self.path))
        self.assertIsNone(judge(f"cd .. && {send}", str(sub), transcript=self.path))
        self.assertEqual(judge(f"cd sub && {send}", str(self.project), transcript=self.path).rule, "unseen-time")

    SEND = "node api.mjs POST /t/a/comment --body-file b.json"

    def test_an_ampersand_redirect_is_a_write(self):
        self.body_file(f"old at {UNSEEN}", "b.json")
        for redirect in ("&>b.json", "&> b.json", "&>>b.json", "&>> b.json"):
            appends = ">>" in redirect
            with self.subTest(redirect=redirect):
                self.assertEqual(self.judge(f"cd {self.dir} && echo 'new at {UNSEEN}' {redirect} && {self.SEND}").rule, "unseen-time")
                seen = self.judge(f"cd {self.dir} && echo 'new at {SEEN}' {redirect} && {self.SEND}")
                self.assertEqual(seen.rule if seen else None, "unseen-time" if appends else None)  # an append keeps the old text

    def test_a_cd_inside_a_subshell_does_not_move_the_rest_of_the_call(self):
        (self.project / "b.json").write_text(f"done at {UNSEEN}", encoding="utf-8")
        self.assertEqual(self.judge(f"(cd /tmp && ls); {self.SEND}").rule, "unseen-time")
        self.assertEqual(self.judge(f"x=$(cd /tmp && pwd); {self.SEND}").rule, "unseen-time")
        self.assertEqual(self.judge(f"(cd {self.project} && {self.SEND})").rule, "unseen-time")

    def test_an_absolute_cd_after_an_unknown_one_finds_the_directory_again(self):
        self.body_file(f"done at {UNSEEN}", "b.json")
        self.assertEqual(self.judge(f"cd; cd {self.dir} && {self.SEND}").rule, "unseen-time")
        self.assertIsNone(self.judge(f"cd; cd /nonexistent-dir && {self.SEND}"))

    def test_an_option_without_a_value_does_not_hide_the_script_name(self):
        self.assertIsNone(self.judge(f"node --no-warnings other.mjs api.mjs 'at {UNSEEN}'"))
        self.assertIsNone(self.judge(f"python3 -u other.py report.sh 'at {UNSEEN}'"))
        self.assertEqual(self.judge(f"node --no-warnings api.mjs 'at {UNSEEN}'").rule, "unseen-time")

    def test_echo_or_printf_piped_to_the_body_file_stdin_is_judged(self):
        for writer in ("echo 'x %s'", "printf 'x %s'"):
            with self.subTest(writer=writer):
                self.assertEqual(self.judge(f"{writer % UNSEEN} | node api.mjs POST /t/a/comment --body-file -").rule, "unseen-time")
                self.assertIsNone(self.judge(f"{writer % SEEN} | node api.mjs POST /t/a/comment --body-file -"))
        self.assertIsNone(self.judge(f"echo 'x {UNSEEN}' | node other.mjs --body-file -"))
        self.assertIsNone(self.judge(f"echo 'x {UNSEEN}' | ./report.sh --body-file /nonexistent-dir/n.txt"))

    def test_a_code_here_document_beside_an_echoed_body_file_is_not_a_message(self):
        command = f"echo 'x {SEEN}' > f; python3 - <<'EOF'\nprint('{UNSEEN}')\nEOF\nnode api.mjs POST /t/a/comment --body-file f"
        self.assertIsNone(self.judge(command))


if __name__ == "__main__":
    unittest.main()
