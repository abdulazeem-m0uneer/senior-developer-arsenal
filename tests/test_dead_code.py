"""Unit tests for the dead-code detector shared by the Stop gate and the dead-code skill."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "dead-code" / "scripts" / "dead_code.py"
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(ROOT / "hooks"))
import dead_code  # noqa: E402
import guard  # noqa: E402


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                   capture_output=True)


def is_source(path):
    return guard.kind(path) == "source"


class Repo(unittest.TestCase):
    """A git repository; `commit` records the files written so far, `found` scans the working tree against it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(os.path.realpath(self.tmp.name))
        git(self.dir, "init", "-q")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode())

    def commit(self, files=None):
        for name, text in (files or {}).items():
            self.write(name, text)
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-qm", "c", "--allow-empty")
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.dir, capture_output=True, text=True).stdout.strip()

    def found(self, sha, **kwargs):
        return dead_code.findings(str(self.dir), sha, is_source=kwargs.pop("is_source", is_source), **kwargs)

    def kinds(self, sha, **kwargs):
        return [(f.path, f.line, f.kind, f.name, f.note) for f in self.found(sha, **kwargs)]


# (language, file, committed text, edited text, expected (line, name) or None)
COMMENTED = [
    ("py", "a.py", "x = 1\n", "x = 1\n# return compute(x)\n", (2, "return compute(x)")),
    ("py", "a.py", "x = 1\n", "x = 1\n# keep the retry count low (see the runbook)\n", None),
    ("ts", "a.ts", "let x = 1;\n", "let x = 1;\n// const total = sum(items);\n", (2, "const total = sum(items);")),
    ("ts", "a.ts", "let x = 1;\n", "let x = 1;\n// explains why the retry loop exists\n", None),
    ("cs", "A.cs", "class A {}\n", "class A {}\n// var total = Sum(items);\n", (2, "var total = Sum(items);")),
    ("cs", "A.cs", "class A {}\n", "class A {}\n// Returns the total for the invoice\n", None),
    ("go", "a.go", "package a\n", "package a\n// if err != nil {\n", (2, "if err != nil {")),
    ("go", "a.go", "package a\n", "package a\n// Run starts the worker pool\n", None),
    ("rs", "a.rs", "fn x() {}\n", "fn x() {}\n// let v = compute();\n", (2, "let v = compute();")),
    ("rs", "a.rs", "fn x() {}\n", "fn x() {}\n// the cache is warmed lazily\n", None),
]
DEBUG = [
    ("py", "a.py", "x = 1\n", "x = 1\nbreakpoint()\n", (2, "breakpoint()")),
    ("py", "a.py", "x = 1\n", "x = 1\nprint(x)\n", None),
    ("ts", "a.ts", "let x = 1;\n", "let x = 1;\ndebugger;\n", (2, "debugger")),
    ("ts", "a.ts", "let x = 1;\n", "let x = 1;\nconsole.log(x);\n", None),
    ("cs", "A.cs", "class A {}\n", "class A {}\nDebugger.Break();\n", (2, "Debugger.Break()")),
    ("cs", "A.cs", "class A {}\n", "class A {}\nConsole.WriteLine(x);\n", None),
    ("go", "a.go", "package a\n", "package a\nruntime.Breakpoint()\n", (2, "runtime.Breakpoint()")),
    ("go", "a.go", "package a\n", "package a\nfmt.Println(x)\n", None),
    ("rs", "a.rs", "fn x() {}\n", "fn x() {}\ndbg!(x);\n", (2, "dbg!")),
    ("rs", "a.rs", "fn x() {}\n", "fn x() {}\nprintln!(\"{}\", x);\n", None),
]
UNREFERENCED = [
    ("py", "a.py", "x = 1\n", "x = 1\ndef helper_unused():\n    return 2\n", (2, "helper_unused")),
    ("py", "a.py", "x = 1\n", "x = 1\ndef helper_used():\n    return 2\nhelper_used()\n", None),
    ("ts", "a.ts", "let x = 1;\n", "let x = 1;\nfunction formatUnused() {}\n", (2, "formatUnused")),
    ("ts", "a.ts", "let x = 1;\n", "let x = 1;\nfunction formatUsed() {}\nformatUsed();\n", None),
    ("cs", "A.cs", "class A {}\n", "class A {}\nprivate int ComputeUnused() { return 1; }\n", (2, "ComputeUnused")),
    ("cs", "A.cs", "class A {}\n", "class A {}\nprivate int ComputeUsed() { return 1; }\nint y = ComputeUsed();\n", None),
    ("go", "a.go", "package a\n", "package a\nfunc helperUnused() {}\n", (2, "helperUnused")),
    ("go", "a.go", "package a\n", "package a\nfunc helperUsed() {}\nfunc Run() { helperUsed() }\n", None),
    ("rs", "a.rs", "fn x() {}\n", "fn x() {}\nfn helper_unused() {}\n", (2, "helper_unused")),
    ("rs", "a.rs", "fn x() {}\n", "fn x() {}\nfn helper_used() {}\nfn run() { helper_used() }\n", None),
]
ORPHANED = [
    ("py", "a.py", "import json\nprint(json.dumps(1))\n", "import json\n", (1, "json", "import")),
    ("py", "a.py", "import json\nprint(json.dumps(1))\nprint(json.loads('1'))\n", "import json\nprint(json.loads('1'))\n",
     None),
    ("ts", "a.ts", 'import { format } from "./fmt";\nformat(1);\n', 'import { format } from "./fmt";\n',
     (1, "format", "import")),
    ("ts", "a.ts", 'import { format } from "./fmt";\nformat(1);\nformat(2);\n', 'import { format } from "./fmt";\nformat(2);\n',
     None),
    ("cs", "A.cs", "class A {\nprivate static int Twice(int x) => x * 2;\nint y = Twice(3);\n}\n",
     "class A {\nprivate static int Twice(int x) => x * 2;\n}\n", (2, "Twice", "definition")),
    ("cs", "A.cs", "class A {\nprivate static int Twice(int x) => x * 2;\nint y = Twice(3);\nint z = Twice(4);\n}\n",
     "class A {\nprivate static int Twice(int x) => x * 2;\nint z = Twice(4);\n}\n", None),
    ("go", "a.go", 'package a\nimport "strings"\nvar s = strings.ToUpper("x")\n', 'package a\nimport "strings"\n',
     (2, "strings", "import")),
    ("go", "a.go", 'package a\nimport "strings"\nvar s = strings.ToUpper("x")\nvar t = strings.ToLower("x")\n',
     'package a\nimport "strings"\nvar t = strings.ToLower("x")\n', None),
    ("rs", "a.rs", "use std::fmt;\nfn x() { fmt::format(args); }\n", "use std::fmt;\nfn x() {}\n", (1, "fmt", "import")),
    ("rs", "a.rs", "use std::fmt;\nfn x() { fmt::format(a); }\nfn y() { fmt::format(b); }\n",
     "use std::fmt;\nfn x() {}\nfn y() { fmt::format(b); }\n", None),
]


class KindTest(Repo):
    def check(self, kind, cases):
        for language, name, before, after, expected in cases:
            with self.subTest(kind=kind, language=language, expected=expected):
                sha = self.commit({name: before})
                self.write(name, after)
                got = [f for f in self.found(sha) if f.kind == kind]
                if expected is None:
                    self.assertEqual(got, [])
                else:
                    self.assertEqual([(f.path, f.line, f.name, f.note)[:len(expected) + 1] for f in got],
                                     [(name, *expected)])
                self.commit({name: before})  # reset for the next case

    def test_commented_out(self):
        self.check("commented-out", COMMENTED)

    def test_debug_leftover(self):
        self.check("debug-leftover", DEBUG)

    def test_unreferenced(self):
        self.check("unreferenced", UNREFERENCED)

    def test_orphaned(self):
        self.check("orphaned", ORPHANED)


class ShapeTest(Repo):
    def setUp(self):
        super().setUp()
        self.sha = self.commit({"a.py": "x = 1\n", "a.ts": "let x = 1;\n"})

    def test_a_run_of_commented_code_is_one_finding_at_its_first_code_line(self):
        self.write("a.py", "x = 1\n# old version:\n# for item in items:\n#     total += item.price\n")
        self.assertEqual(self.kinds(self.sha), [("a.py", 3, "commented-out", "for item in items:", "")])

    def test_two_closing_lines_are_code_and_one_prose_line_ending_in_a_paren_is_not(self):
        self.write("a.py", "x = 1\n# see the runbook (section two)\n")
        self.assertEqual(self.kinds(self.sha), [])
        self.write("a.py", "x = 1\n# setup(app)\n# teardown(app)\n")
        self.assertEqual([k[1:3] for k in self.kinds(self.sha)], [(2, "commented-out")])

    def test_pragmas_urls_doc_tags_and_shebangs_are_not_code(self):
        self.write("a.py", "#!/usr/bin/env python3\nx = 1  \n# noqa: F401\n# type: ignore[attr];\n# pylint: disable=x;\n")
        self.write("a.ts", "let x = 1;\n// eslint-disable-next-line no-console;\n// see https://example.com/a;\n"
                           "/** @param {string} name */\n// #region helpers {\n")
        self.assertEqual(self.kinds(self.sha), [])

    def test_a_block_comment_holding_code_is_found(self):
        self.write("a.ts", "let x = 1;\n/*\nconst old = compute();\n*/\n")
        self.assertEqual([k[1:3] for k in self.kinds(self.sha)], [(3, "commented-out")])

    def test_documentation_comments_and_their_examples_are_not_dead_code(self):
        self.commit({"a.rs": "fn x() {}\n"})
        sha = self.commit()
        self.write("a.rs", "fn x() {}\n/// let v = compute();\n//! use crate::thing;\n")
        self.write("a.ts", "let x = 1;\n/**\n * @example\n * const total = sum(items);\n */\n")
        self.assertEqual(self.kinds(sha), [])

    def test_a_minified_line_is_not_scanned(self):
        self.write("a.ts", "let x = 1;\n" + "debugger;" + " " * dead_code.MAX_LINE + "\n")
        self.assertEqual(self.kinds(self.sha), [])

    def test_a_debug_call_inside_a_string_is_data(self):
        self.write("a.py", 'x = 1\nhint = "call breakpoint() here"\n')
        self.assertEqual(self.kinds(self.sha), [])

    def test_php_dd_counts_only_in_php(self):
        self.commit({"a.php": "<?php\n", "b.ts": "let y = 1;\n"})
        sha = self.commit()
        self.write("a.php", "<?php\ndd($order);\n")
        self.write("b.ts", "let y = 1;\nadd(1);\n")
        self.assertEqual([k[:3] for k in self.kinds(sha)], [("a.php", 2, "debug-leftover")])

    def test_a_name_that_also_appears_in_a_string_is_not_unreferenced(self):
        self.write("a.py", 'x = 1\ndef registered_handler():\n    pass\nHANDLERS = ["registered_handler"]\n')
        self.assertEqual(self.kinds(self.sha), [])

    def test_skipped_names_and_decorated_definitions(self):
        self.write("a.py", "x = 1\ndef main():\n    pass\ndef test_thing():\n    pass\ndef abc():\n    pass\n"
                           "def __init__(self):\n    pass\n@app.route('/x')\ndef route_handler():\n    pass\n")
        self.assertEqual(self.kinds(self.sha), [])

    def test_at_most_forty_findings_per_kind(self):
        self.write("a.py", "x = 1\n" + "breakpoint()\n" * 50)
        self.assertEqual(len(self.found(self.sha)), dead_code.MAX_PER_KIND)

    def test_describe_and_key(self):
        orphan = dead_code.Finding("b.ts", 40, "orphaned", "foo", "import")
        self.assertEqual(dead_code.describe(orphan), "b.ts:40 orphaned import foo")
        self.assertEqual(dead_code.describe(dead_code.Finding("a.py", 12, "commented-out", "x = 1")),
                         "a.py:12 commented-out")
        self.assertEqual(dead_code.key(orphan), "b.ts:orphaned:foo")


class ScopeTest(Repo):
    def test_empty_diff(self):
        sha = self.commit({"a.py": "breakpoint()\n"})
        self.assertEqual(self.found(sha), [])

    def test_untracked_new_file_is_read_whole(self):
        sha = self.commit({"a.py": "x = 1\n"})
        self.write("new.py", "y = 2\nbreakpoint()\n")
        self.assertEqual(self.kinds(sha), [("new.py", 2, "debug-leftover", "breakpoint()", "")])

    def test_no_head_commit_reads_every_file_as_new(self):
        self.write("a.py", "breakpoint()\n")
        git(self.dir, "add", "a.py")
        self.write("b.py", "import pdb\n")
        self.assertEqual([k[:3] for k in self.kinds("")], [("a.py", 1, "debug-leftover"), ("b.py", 1, "debug-leftover")])

    def test_a_pure_rename_adds_nothing(self):
        sha = self.commit({"a.py": "# return compute(x)\nbreakpoint()\n"})
        git(self.dir, "mv", "a.py", "b.py")
        self.assertEqual(self.found(sha), [])

    def test_a_binary_file_is_skipped(self):
        sha = self.commit({"a.py": "x = 1\n"})
        self.write("blob.py", b"breakpoint()\n\0\0binary")
        self.assertEqual(self.found(sha), [])

    def test_vendor_generated_and_test_files_are_skipped(self):
        sha = self.commit({"a.py": "x = 1\n"})
        for name in ("vendor/lib.py", "node_modules/x/index.js", "app.min.js", "tests/test_app.py", "app.test.ts",
                     "README.md"):
            self.write(name, "breakpoint()\ndebugger;\n")
        self.assertEqual(self.found(sha), [])

    def test_ignored_paths_are_skipped(self):
        sha = self.commit({"a.py": "x = 1\n"})
        self.write("a.py", "x = 1\nbreakpoint()\n")
        self.assertEqual(self.found(sha, ignore={"a.py"}), [])

    def test_gitignored_files_are_skipped(self):
        sha = self.commit({".gitignore": "build.py\n"})
        self.write("build.py", "breakpoint()\n")
        self.assertEqual(self.found(sha), [])


class LimitTest(Repo):
    def setUp(self):
        super().setUp()
        self.sha = self.commit({"a.py": "x = 1\n"})
        self.write("a.py", "x = 1\nbreakpoint()\n")

    def test_over_size_diffs_are_skipped_silently(self):
        root = str(self.dir)
        self.assertEqual(len(dead_code.scan(root, self.sha, is_source=is_source)), 1)
        self.assertEqual(len(dead_code.scan(root, self.sha, is_source=is_source, max_added=1)), 1)  # at the limit
        self.assertEqual(dead_code.scan(root, self.sha, is_source=is_source, max_added=0), [])  # over it
        self.write("b.py", "y = 1\n")
        self.assertEqual(len(dead_code.scan(root, self.sha, is_source=is_source, max_files=2)), 1)
        self.assertEqual(dead_code.scan(root, self.sha, is_source=is_source, max_files=1), [])

    def test_too_many_files_are_skipped_before_any_is_read(self):
        for index in range(3):
            self.write(f"n{index}.py", "breakpoint()\n")
        with mock.patch.object(dead_code, "read_text", side_effect=AssertionError("read")) as read:
            self.assertEqual(dead_code.scan(str(self.dir), self.sha, is_source=is_source, max_files=2), [])
        read.assert_not_called()

    def test_a_spent_time_budget_fails_open(self):
        self.assertEqual(self.found(self.sha, budget=0), [])
        with self.assertRaises(dead_code.GitError):
            dead_code.scan(str(self.dir), self.sha, budget=0)

    def test_git_failures_fail_open(self):
        self.assertEqual(self.found("0" * 40), [])  # unknown commit
        with tempfile.TemporaryDirectory() as plain:
            self.assertEqual(dead_code.findings(plain, ""), [])  # not a repository
        with mock.patch.dict(os.environ, {"PATH": ""}):
            self.assertEqual(self.found(self.sha), [])  # git missing


class ReviewRegressionTest(Repo):
    """One case per defect an independent review reproduced."""

    def setUp(self):
        super().setUp()
        self.sha = self.commit({"seed.txt": "x"})

    def assert_clean(self, files, kinds=dead_code.KINDS):
        for name, text in files.items():
            self.write(name, text)
        self.assertEqual([k for k in self.kinds(self.sha) if k[2] in kinds], [])

    def test_hostile_quotes_and_huge_removals_stay_inside_the_budget(self):
        for index in range(5):
            self.write(f"q{index}.py", ("'\\" * 499 + "\n") * 950)
        started = time.monotonic()
        self.assertEqual(self.found(self.sha), [])
        self.assertLess(time.monotonic() - started, 6)
        self.write("big.py", "".join(f"v{i} = fn{i}(a)\n" for i in range(dead_code.MAX_REMOVED + 1)))
        sha = self.commit()
        self.write("big.py", "x = 1\n")
        started = time.monotonic()
        self.assertEqual(self.found(sha), [])  # over MAX_REMOVED: skipped, not scanned for seconds
        self.assertLess(time.monotonic() - started, 6)

    def test_the_scan_budget_covers_the_regex_phase(self):
        self.write("a.py", "x = 1\n" * 3000)
        with mock.patch.object(dead_code.Clock, "check", side_effect=dead_code.GitError("time budget spent")):
            self.assertEqual(self.found(self.sha), [])

    def test_diff_prefix_settings_do_not_hide_findings(self):
        sha = self.commit({"a.py": "x = 1\n", "b/x.py": "y = 1\n", 't"q.py': "z = 1\n"})
        self.write("a.py", "x = 1\nbreakpoint()\n")
        self.write("b/x.py", "y = 1\nbreakpoint()\n")
        self.write('t"q.py', "z = 1\nbreakpoint()\n")
        for setting in ("diff.mnemonicPrefix", "diff.noprefix"):
            with self.subTest(setting=setting):
                git(self.dir, "config", setting, "true")
                self.assertEqual(sorted(k[0] for k in self.kinds(sha)), ["a.py", "b/x.py", 't"q.py'])
                git(self.dir, "config", "--unset", setting)

    def test_licence_headers_and_prose_are_not_commented_out_code(self):
        self.assert_clean({
            "a.java": '// Licensed under the Apache License, Version 2.0 (the "License");\n'
                      "// you may not use this file except in compliance with the License.\n",
            "b.py": "# Retries on failure (see RETRY)\n# and backs off (exponential)\n# for example:\n"
                    "# return value: the id\n# TODO(alice): fix\n",
            "c.ts": "// public API:\n// import the data from the CSV\n"})

    def test_single_commented_out_lines_without_a_terminator_are_found(self):
        cases = {"a.py": "# result = compute(x)\n", "b.go": "// fmt.Println(x)\n", "c.go": "// result := compute(x)\n",
                 "d.py": "# foo(x)\n", "e.kt": "// val total = sum(items)\n"}
        for name, text in cases.items():
            self.write(name, text)
        self.assertEqual(sorted((k[0], k[2]) for k in self.kinds(self.sha)),
                         sorted((name, "commented-out") for name in cases))

    def test_fields_entry_points_and_public_api_are_not_unreferenced(self):
        self.assert_clean({
            "User.cs": "public class User {\n    public string Email { get; set; }\n"
                       "    static void Main(string[] args) {}\n}\nclass Program {}\n",
            "User.java": "public class UserService {\n    private String email;\n}\n",
            "Cache.kt": "class Cache {\n    private val cache = mutableMapOf<String, String>()\n}\n",
            "users_controller.rb": "class UsersController\n  def index\n  end\n  def show(id)\n  end\nend\n",
            "Index.php": "<?php\nclass Index {\n    public function index() {}\n}\n",
            "page.tsx": "export default function Home() { return null; }\nexport const handler = async () => {};\n",
            "srv.go": "package a\nfunc (s *Srv) ServeHTTP(w Writer, r *Request) {}\nfunc Exported() {}\n",
            "lib.rs": "pub fn public_api() {}\nimpl Thing {\n    fn method_on_self(&self) {}\n}\n",
            "hooks.py": "class Cmd:\n    def setUp(self):\n        pass\n    def forward(self, x):\n        return x\n"},
            kinds=("unreferenced",))

    def test_pytest_and_unittest_hooks_are_called_by_their_framework(self):
        self.assert_clean({"svc.py": "def pytest_configure(config):\n    pass\ndef setup_module(module):\n    pass\n"
                                     "def setUpModule():\n    pass\n"}, kinds=("unreferenced",))

    def test_attributes_and_multi_line_decorators_mark_a_definition_as_registered(self):
        self.assert_clean({
            "a.rs": "#[test]\nfn parses_input() {}\n#[tokio::main]\nasync fn entry_point() {}\n",
            "b.py": "@app.route(\n    \"/x\",\n    methods=[\"GET\"])\ndef index_view():\n    pass\n",
            "C.cs": "class C {\n    [HttpGet]\n    private int GetValue() { return 1; }\n}\n"},
            kinds=("unreferenced",))

    def test_a_doctest_breakpoint_is_documentation(self):
        self.assert_clean({"a.py": 'def f():\n    """\n    >>> breakpoint()\n    """\n'}, kinds=("debug-leftover",))

    def test_the_cap_applies_after_filtering(self):
        used = "".join(f"def used{i}xx():\n    pass\nused{i}xx()\n" for i in range(45))
        self.write("a.py", used + "def lonely_unused():\n    pass\n")
        self.assertEqual([k[3] for k in self.kinds(self.sha) if k[2] == "unreferenced"], ["lonely_unused"])

    def test_imports_whose_module_path_repeats_the_name_are_found(self):
        sha = self.commit({"a.ts": "import axios from 'axios';\naxios.get(url);\n",
                           "b.js": "const fs = require('fs');\nfs.readFileSync(p);\n"})
        self.write("a.ts", "import axios from 'axios';\n")
        self.write("b.js", "const fs = require('fs');\n")
        self.assertEqual(sorted(k[:5] for k in self.kinds(sha)),
                         [("a.ts", 1, "orphaned", "axios", "import"), ("b.js", 1, "orphaned", "fs", "import")])

    def test_multi_line_imports_are_import_lines(self):
        sha = self.commit({"a.py": "from m import (\n    alpha,\n    beta,\n)\nalpha()\nbeta()\n",
                           "b.ts": "import {\n  gamma,\n  delta\n} from './m';\ngamma();\ndelta();\n",
                           "c.go": 'package a\nimport (\n    "strings"\n)\nvar s = strings.ToUpper("x")\n'})
        self.write("a.py", "from m import (\n    alpha,\n    beta,\n)\nalpha()\n")
        self.write("b.ts", "import {\n  gamma,\n  delta\n} from './m';\ngamma();\n")
        self.write("c.go", 'package a\nimport (\n    "strings"\n)\n')
        self.assertEqual(sorted(k[:4] for k in self.kinds(sha)),
                         [("a.py", 3, "orphaned", "beta"), ("b.ts", 3, "orphaned", "delta"),
                          ("c.go", 3, "orphaned", "strings")])

    def test_a_removed_line_that_looks_like_a_file_header_is_content(self):
        diff = ("diff --git a/x.lua b/x.lua\n--- a/x.lua\n+++ b/x.lua\n@@ -1,2 +1,0 @@\n"
                "--- old note\n-call_it()\n")
        self.assertEqual(dead_code.parse_diff(diff), {"x.lua": {"added": [], "removed": ["-- old note", "call_it()"]}})

    def test_a_form_feed_does_not_shift_line_numbers(self):
        self.write("a.py", "x = 1\f  # page break\nbreakpoint()\n")
        self.assertEqual([k[:2] for k in self.kinds(self.sha)], [("a.py", 2)])


class CliTest(Repo):
    def run_cli(self, *args, cwd=None):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.dir, capture_output=True, text=True)
        return result.returncode, result.stdout

    def test_exit_codes(self):
        sha = self.commit({"a.py": "x = 1\n"})
        self.assertEqual(self.run_cli("--diff", sha), (0, ""))
        self.write("a.py", "x = 1\nbreakpoint()\n")
        self.assertEqual(self.run_cli("--diff", "HEAD"), (1, "a.py:2 debug-leftover breakpoint()\n"))
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(self.run_cli("--bogus")[0], 2)
        self.assertEqual(self.run_cli("--diff", "no-such-ref")[0], 2)
        self.assertEqual(self.run_cli("--diff")[0], 2)  # no origin/HEAD to take a merge-base with
        with tempfile.TemporaryDirectory() as plain:
            self.assertEqual(self.run_cli("--diff", "HEAD", cwd=plain)[0], 2)

    def test_runs_from_a_subdirectory_and_reports_repo_relative_paths(self):
        sha = self.commit({"src/a.py": "x = 1\n"})
        self.write("src/a.py", "x = 1\nbreakpoint()\n")
        self.assertEqual(self.run_cli("--diff", sha, cwd=self.dir / "src"), (1, "src/a.py:2 debug-leftover breakpoint()\n"))


if __name__ == "__main__":
    unittest.main()
