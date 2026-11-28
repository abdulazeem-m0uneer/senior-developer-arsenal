"""Tests for the opt-in replace-dollar lesson guard (hooks/guard_replace_dollar.py, wired in guard_lessons)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))

import guard_lessons  # noqa: E402
import guard_replace_dollar  # noqa: E402

ENTRY = {"rule": "replace-dollar", "lesson": "G009", "min_version": "1.40.0"}
BACKTICK, QUOTE = "$`", "$'"

# the command that started the lesson, sanitised: JS held by a variable replacement and a `$` before a backtick
TRIGGER_COMMAND = r'''cd tools/x && node -e '
const fs=require("fs");const f="report-head.mjs";let s=fs.readFileSync(f,"utf8");const rep=(a,b)=>{if(!s.includes(a)){console.error("MISSING",a.slice(0,60));process.exit(1)}s=s.replace(a,b)};
rep("new RegExp(`^attachment; filename=\"export-${day}\\\\.csv\"$`)","new RegExp(`^attachment; filename=\"export-(${days.join(\x27|\x27)})\\\\.csv\"$`)");
fs.writeFileSync(f,s);
'
'''


class ReplaceDollarCase(unittest.TestCase):
    """A project whose registry names replace-dollar, and a 1.40.0 hook."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.project = self.dir / "project"
        (self.project / ".agents").mkdir(parents=True)
        env = {"LESSONS_GUARDS_GLOBAL_FILE": str(self.dir / "home" / "lesson-guards.json"),
               "LESSONS_GUARD_HITS_FILE": str(self.dir / "home" / "hits.jsonl")}
        for patch in (mock.patch.dict(os.environ, env), mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 40, 0))):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.registry(ENTRY)

    def registry(self, *guards):
        (self.project / ".agents" / "lesson-guards.json").write_text(json.dumps({"guards": list(guards)}),
                                                                     encoding="utf-8")

    def judge(self, command):
        return guard_lessons.judge(command, str(self.project))

    def assertRefused(self, command, token=None):
        hit = self.judge(command)
        self.assertIsNotNone(hit, command)
        self.assertEqual((hit.lesson, hit.rule), ("G009", "replace-dollar"))
        if token:
            self.assertIn(f"`{token}`", hit.reason)
        return hit

    def assertPasses(self, command):
        self.assertIsNone(self.judge(command), command)


class RefusedTests(ReplaceDollarCase):
    def test_trigger_command_is_refused_with_the_token_and_the_fixes(self):
        hit = self.assertRefused(TRIGGER_COMMAND, BACKTICK)
        for fix in ("(m) =>", "split", "Edit"):
            self.assertIn(fix, hit.reason)

    def test_literal_second_argument_with_each_bad_token(self):
        for token in (BACKTICK, QUOTE, "$$"):
            with self.subTest(token=token):
                written = token.replace("'", "\\x27")  # a quote cannot sit inside the shell's single quotes
                self.assertRefused(f"""node -e 'let s="a"; s=s.replace("a","x{written}y"); console.log(s)'""", token)

    def test_replace_all_and_template_literal_and_regex_first_argument(self):
        self.assertRefused("node -e 's.replaceAll(\"a\", \"$$\")'", "$$")
        self.assertRefused("node -e 's.replace(/a/g, `pid $$ here`)'", "$$")

    def test_bash_pid_in_a_template_replacement(self):
        self.assertRefused('''node -e 's=s.replace(`pids=()`,`mine() { [[ "$q" == "$$" ]]; }`)' ''', "$$")

    def test_shell_regex_end_anchor_inside_a_single_quoted_node_script(self):
        self.assertRefused("""node -e 's=s.replace(a,"echo \\"$(grep -vE \\x27^\\\\s*$\\x27 f)\\"")' """, QUOTE)
        self.assertRefused("""node -e 's=s.replace(a,"echo $(grep -vE '"'"'^[[:space:]]*$'"'"' f)")' """, QUOTE)

    def test_variable_replacement_with_a_bad_literal_in_the_script(self):
        self.assertRefused("""node -e 'const add="x ${out##*$\\x27\\n\\x27}"; s=s.replace("# what", add+"\\n")' """, QUOTE)
        self.assertRefused("""node -e 'edit(a,b); s=s.replace(a,b); const t="$$"' """, "$$")

    def test_eval_print_and_double_quoted_forms(self):
        self.assertRefused("node --eval='s.replace(a, \"$$\")'", "$$")
        self.assertRefused("node -p 's.replace(a, \"$$\")'", "$$")
        self.assertRefused('node -e "s.replace(a, \'\\$\\`\')"', BACKTICK)
        self.assertRefused('''sh -c "node -e 's.replace(a, \\"\\$\\$\\")'"''', "$$")

    def test_heredoc_fed_to_node(self):
        for opener in ("node <<'EOF'", "node - <<'EOF'", 'node <<"EOF"', "node <<\\EOF", "node -r ./pre.cjs <<'EOF'", "cd x && node --input-type=module <<'EOF'"):
            with self.subTest(opener=opener):
                self.assertRefused(f"{opener}\nlet s='a';\ns = s.replace('a', '$$');\nEOF\n", "$$")

    def test_an_unquoted_heredoc_keeps_an_escaped_dollar(self):
        self.assertRefused("node <<EOF\ns = s.replace('a', '\\$\\$');\nEOF\n", "$$")

    def test_here_string_fed_to_node(self):
        self.assertRefused("""node <<< 's.replace(a, "$$")'""", "$$")
        self.assertRefused("""node - <<< 's.replace(a, "$$")'""", "$$")

    def test_a_token_split_across_a_concatenation(self):
        for script in ("""s.replace(a, "x$" + "\\x27")""", """s.replace(a, "$" + "$")""", "s.replace(a, \"$\" + `$`)"):
            with self.subTest(script=script):
                self.assertRefused(f"node -e '{script}'")

    def test_a_slash_after_an_increment_is_a_division(self):
        self.assertRefused("""node -e 'let n=i++ / 2; s=s.replace(a,"$$")'""", "$$")
        self.assertRefused("""node -e 'let n=i-- / 2; s=s.replace(a,"$$")'""", "$$")

    def test_script_file_the_same_command_writes_and_runs(self):
        body = "cat > fix.mjs <<'EOF'\nlet s='a'; s = s.replace('a', \"$'\");\nEOF\n"
        self.assertRefused(body + "node fix.mjs\n", QUOTE)
        self.assertRefused("cd w && " + body.replace("fix.mjs", "./fix.cjs") + "&& node ./fix.cjs", QUOTE)

    def test_a_regex_literal_does_not_hide_the_literals_after_it(self):
        self.assertRefused("""node -e 'x.replace(/"$/,"x"); y.replace(a,b); const t="$$"' """, "$$")
        self.assertRefused("""node -e 'x.replace(/'"'"'$/,"x"); y.replace(a,b); const t="$$"' """, "$$")

    def test_a_template_with_an_interpolation_is_an_expression(self):
        self.assertRefused("node -e 's.replace(a, `${x} $$`)'", "$$")

    def test_a_refused_command_after_a_passing_one(self):
        self.assertRefused("node -e 'a.replace(b,(m)=>m)' && node -e 'a.replace(b,\"$$\")'", "$$")


class PassTests(ReplaceDollarCase):
    def test_function_replacement_split_join_and_idioms_pass(self):
        for script in ("s.replace(/x/g, (m) => '$$')", "s.replace(/x/g, function (m) { return '$`'; })",
                       "s.replace(/x/g, m => `$'`)", "s.split(a).join('$$')",
                       "s.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')", "s.replace(/(a)(b)/, '$2$1$&$<n>')",
                       "s.replace(a, b); console.log('ok')"):
            with self.subTest(script=script):
                self.assertPasses(f"node -e '{script}'")

    def test_the_shell_expands_the_pid_before_node_starts(self):
        self.assertPasses("""node -e "s=s.replace(a,'$$')" """)
        self.assertPasses("""node -e 's=s.replace(a,"x")' "$$" """)
        self.assertPasses("node <<EOF\ns = s.replace('a', '$$');\nEOF\n")
        self.assertPasses("node <<EOF\ns = s.replace('a', '\\\\$$');\nEOF\n")

    def test_concatenated_literals_without_a_token_pass(self):
        self.assertPasses("""node -e 's.replace(a, "x" + "y"); s.replace(a, "$" + x)'""")

    def test_here_string_to_a_script_file_and_a_preload_are_data(self):
        self.assertPasses("""node run.mjs <<< 's.replace(a, "$$")'""")
        self.assertPasses("node -r ./pre.cjs run.mjs <<'EOF'\ns.replace('a', '$$')\nEOF\n")

    def test_replaces_with_no_token_pass_even_when_the_second_argument_is_a_variable(self):
        self.assertPasses("""node -e 'let s="AS"; s=s.replace(a,b); s=s.replace(/\\n*$/,"\\n")' """)

    def test_plain_literal_with_a_token_but_only_literal_replacements(self):
        self.assertPasses("""node -e 'let s="AS $$ x"; s+="more $$"; s=s.replace(/\\n*$/,"\\n"); console.log(s)' """)

    def test_no_replace_call_passes(self):
        self.assertPasses("""node -e 'console.log("$$", "$`")'""")
        self.assertPasses("""node -e 'const r = replace("$$"); x.replace; s.replacer("a","$$")' """)

    def test_a_token_in_a_comment_passes(self):
        self.assertPasses("node -e '// s.replace(a, \"$$\")\n/* s.replace(a,\"$`\") */ s.replace(a, b)'")

    def test_not_node(self):
        self.assertPasses("""python3 -c 's=s.replace("a","$$")'""")
        self.assertPasses("""echo 's.replace(a, "$$")'""")
        self.assertPasses("""grep -vE '^\\s*$' f | sed 's/a/b/'""")
        self.assertPasses("python3 - <<'EOF'\ns = s.replace('a', '$$')\nEOF\n")
        self.assertPasses("cat > notes.txt <<'EOF'\ns.replace('a', '$$')\nEOF\nnode notes.mjs\n")

    def test_script_written_but_not_run_by_this_command_passes(self):
        self.assertPasses("cat > fix.mjs <<'EOF'\ns.replace('a', '$$');\nEOF\nnode other.mjs\n")
        self.assertPasses("cat > fix.mjs <<'EOF'\ns.replace('a', '$$');\nEOF\n")

    def test_heredoc_to_node_that_runs_a_script_file_is_data(self):
        self.assertPasses("node run.mjs <<'EOF'\ns.replace('a', '$$')\nEOF\n")

    def test_unparsable_commands_pass(self):
        self.assertPasses("node -e 's.replace(a, \"$$)")
        self.assertPasses("node -e 's.replace(a, `$$'")
        self.assertPasses("node -e 's.replace(' ")

    def test_oversized_command_passes(self):
        self.assertPasses("node -e 's.replace(a, \"$$\")' # " + "x" * 100_000)

    def test_off_until_a_registry_entry_names_it(self):
        self.registry()
        self.assertPasses("node -e 's.replace(a, \"$$\")'")
        self.registry({**ENTRY, "min_version": "1.41.0"})
        self.assertPasses("node -e 's.replace(a, \"$$\")'")

    def test_problem_never_raises(self):
        for bad in (None, 5, "", b"x"):
            self.assertIsNone(guard_replace_dollar.problem(bad, ENTRY))
        with mock.patch.object(guard_replace_dollar, "js_sources", side_effect=RuntimeError):
            self.assertIsNone(guard_replace_dollar.problem("node -e 's.replace(a,\"$$\")'", ENTRY))


class ScannerTests(unittest.TestCase):
    def test_token_scan_reads_left_to_right(self):
        scan = guard_replace_dollar.bad_token
        self.assertEqual([scan(v) for v in ("a$$b", "$$`", "$$$", "$&$$", "$1$`", "$", "$'", "$$$'", "\\$$")],
                         ["$$", "$$", "$$", "$$", BACKTICK, None, QUOTE, "$$", "$$"])
        self.assertIsNone(scan("$&$1$9$<n>$"))

    def test_escapes_are_decoded_before_scanning(self):
        decoded = guard_replace_dollar.js_problem
        self.assertIn("$$", decoded(r"s.replace(a, '\$\$')"))
        self.assertIn("$`", decoded(r"s.replace(a, '\x24\u0060')"))
        self.assertIn("$'", decoded(r"s.replace(a, '\u{24}\x27')"))
        self.assertIsNone(decoded(r"s.replace(a, '\\$&')"))

    def test_nested_template_interpolations_are_scanned(self):
        self.assertIsNotNone(guard_replace_dollar.js_problem("s.replace(a, `${ `${x}$$` }`)"))
        self.assertIsNone(guard_replace_dollar.js_problem("s.replace(a, `${ f(`${x}`) }`)"))


class ShellCommentTests(ReplaceDollarCase):
    BAD = 'node -e \'s.replace(a, "x$\\x27")\''

    def test_apostrophe_in_a_comment_does_not_hide_the_script(self):
        self.assertRefused(self.BAD, QUOTE)
        self.assertRefused("# don't forget\n" + self.BAD, QUOTE)
        self.assertRefused("ls # it's here\n" + self.BAD, QUOTE)

    def test_hash_inside_a_quoted_string_is_not_a_comment(self):
        self.assertPasses("node -e 's.replace(a, \"#x\")'")
        self.assertRefused("node -e 's.replace(a, \"#x$$\")'", "$$")

    def test_hash_inside_a_multiline_quoted_script_is_not_a_comment(self):
        self.assertRefused("node -e '\n# not a comment\ns.replace(a, \"$$\")\n'", "$$")

    def test_url_fragment_is_not_a_comment(self):
        self.assertRefused('echo http://x/#a; node -e \'s.replace(a, "$$")\'', "$$")

    def test_variable_replacement_with_bad_literal_is_refused_for_any_object(self):
        # known false refusal: router.replace is not String.prototype.replace, the guard cannot tell
        self.assertRefused("node -e 'const a=\"$$\"; router.replace(path, target)'", "$$")


if __name__ == "__main__":
    unittest.main()
