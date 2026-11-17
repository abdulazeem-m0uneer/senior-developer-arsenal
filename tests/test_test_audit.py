"""Unit tests for the test-strategy skill's test-suite audit."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "test-strategy" / "scripts" / "test_audit.py"
sys.path.insert(0, str(SCRIPT.parent))

import test_audit  # noqa: E402

PY = '''import pytest

def test_good():
    total = add(1, 2) + add(3, 4)
    assert total == 10, total

def test_empty():
    result = add(1, 2)

@pytest.mark.skip(reason="later")
def test_skipped():
    assert add(1, 1) == 2

def test_helper():
    verify_total(add(1, 2))

def test_raises():
    with pytest.raises(ValueError):
        add("a", None)

def test_copy():
    total = add(1, 2) + add(3, 4)
    assert total == 10, total

def test_grep():
    text = open("src/app.py").read()
    assert "def add" in text
'''
JS = '''describe("math", () => {
  it("adds", () => {
    const total = add(1, 2) + add(3, 4);
    expect(total).toBe(10);
  });
  it("has no assertion", () => {
    const total = add(1, 2);
  });
  it.skip("is skipped", () => {
    expect(add(1, 1)).toBe(2);
  });
  it.only("is focused", () => {
    expect(add(2, 2)).toBe(4);
  });
  test("copies adds", () => {
    const total = add(1, 2) + add(3, 4);
    expect(total).toBe(10);
  });
  it("greps", () => {
    const text = fs.readFileSync("src/app.ts", "utf8");
    expect(text).toContain("export function add");
  });
  it("uses a custom matcher helper", () => {
    expectValid(add(1, 2));
  });
  it("is concise", () => expect(add(1, 1)).toBe(2));
});
'''
CS = '''public class MathTests {
    [Fact]
    public void Adds() {
        var total = Calc.Add(1, 2) + Calc.Add(3, 4);
        Assert.Equal(10, total);
    }
    [Fact]
    public void NoAssertion() {
        var total = Calc.Add(1, 2);
    }
    [Fact(Skip = "flaky")]
    public void Skipped() {
        Assert.Equal(2, Calc.Add(1, 1));
    }
    [Fact]
    public void Copy() {
        var total = Calc.Add(1, 2) + Calc.Add(3, 4);
        Assert.Equal(10, total);
    }
    [Fact]
    public void Greps() {
        var text = File.ReadAllText("src/Calc.cs");
        Assert.Contains("public static int Add", text);
    }
    [Fact]
    public void FluentAssertion() {
        Calc.Add(1, 1).Should().Be(2);
    }
}
'''
JAVA = '''class CalcTest {
    @Test
    void adds() {
        int total = Calc.add(1, 2) + Calc.add(3, 4);
        assertEquals(10, total);
    }
    @Test
    void noAssertion() {
        int total = Calc.add(1, 2);
    }
    @Disabled("later")
    @Test
    void skipped() {
        assertEquals(2, Calc.add(1, 1));
    }
    @Test
    void copy() {
        int total = Calc.add(1, 2) + Calc.add(3, 4);
        assertEquals(10, total);
    }
    @Test
    void greps() throws Exception {
        String text = Files.readString(Path.of("src/main/java/Calc.java"));
        assertTrue(text.contains("int add"));
    }
    @Test
    void hamcrest() {
        assertThat(Calc.add(1, 1), is(2));
    }
}
'''
KOTLIN = '''class CalcTest {
    @Test
    fun `adds two numbers`() {
        val total = add(1, 2) + add(3, 4)
        assertEquals(10, total)
    }
    @Test
    fun noAssertion() {
        val total = add(1, 2)
    }
    @Test
    @Ignore
    fun skipped() {
        assertEquals(2, add(1, 1))
    }
}
'''
GO = '''package calc

func TestAdds(t *testing.T) {
	if Add(1, 2)+Add(3, 4) != 10 {
		t.Fatalf("bad total")
	}
}

func TestNoAssertion(t *testing.T) {
	_ = Add(1, 2)
}

func TestSkipped(t *testing.T) {
	t.Skip("later")
	if Add(1, 1) != 2 {
		t.Error("bad")
	}
}

func TestCopy(t *testing.T) {
	if Add(1, 2)+Add(3, 4) != 10 {
		t.Fatalf("bad total")
	}
}

func TestGreps(t *testing.T) {
	data, _ := os.ReadFile("calc.go")
	if !strings.Contains(string(data), "func Add") {
		t.Error("missing")
	}
}

func TestTestify(t *testing.T) {
	require.Equal(t, 2, Add(1, 1))
}
'''
RUST = '''pub fn add(a: i32, b: i32) -> i32 { a + b }

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn adds() {
        let total = add(1, 2) + add(3, 4);
        assert_eq!(total, 10);
    }

    #[test]
    fn no_assertion() {
        let _ = add(1, 2);
    }

    #[test]
    #[ignore]
    fn skipped() {
        assert_eq!(add(1, 1), 2);
    }

    #[test]
    fn copy() {
        let total = add(1, 2) + add(3, 4);
        assert_eq!(total, 10);
    }

    #[test]
    fn greps() {
        let text = include_str!("lib.rs");
        assert!(text.contains("fn add"));
    }

    #[test]
    #[should_panic]
    fn panics<'a>() {
        divide(1, 0);
    }
}
'''
PHP = '''<?php
class CalcTest extends TestCase {
    public function testAdds(): void {
        $total = add(1, 2) + add(3, 4);
        $this->assertSame(10, $total);
    }
    public function testNoAssertion(): void {
        $total = add(1, 2);
    }
    public function testSkipped(): void {
        $this->markTestSkipped('later');
    }
    public function testCopy(): void {
        $total = add(1, 2) + add(3, 4);
        $this->assertSame(10, $total);
    }
    public function testGreps(): void {
        $text = file_get_contents('src/Calc.php');
        $this->assertStringContainsString('function add', $text);
    }
    private function helper(): int {
        return 1;
    }
}
'''
RUBY = '''describe Calc do
  it "adds" do
    total = Calc.add(1, 2) + Calc.add(3, 4)
    expect(total).to eq(10)
  end
  it "has no assertion" do
    total = Calc.add(1, 2)
  end
  xit "is skipped" do
    expect(Calc.add(1, 1)).to eq(2)
  end
  fit "is focused" do
    expect(Calc.add(2, 2)).to eq(4)
  end
  it "copies" do
    total = Calc.add(1, 2) + Calc.add(3, 4)
    expect(total).to eq(10)
  end
  it "greps" do
    text = File.read("lib/calc.rb")
    expect(text).to include("def self.add")
  end
end
'''
CASES = {
    "test_app.py": (PY, {("no-assertion", "test_empty"), ("skipped", "test_skipped"), ("duplicate", "test_copy"),
                         ("source-grep", "test_grep")}),
    "app.test.ts": (JS, {("no-assertion", "has no assertion"), ("skipped", "is skipped"), ("focused", "is focused"),
                         ("duplicate", "copies adds"), ("source-grep", "greps")}),
    "MathTests.cs": (CS, {("no-assertion", "NoAssertion"), ("skipped", "Skipped"), ("duplicate", "Copy"),
                          ("source-grep", "Greps")}),
    "CalcTest.java": (JAVA, {("no-assertion", "noAssertion"), ("skipped", "skipped"), ("duplicate", "copy"),
                             ("source-grep", "greps")}),
    "CalcTest.kt": (KOTLIN, {("no-assertion", "noAssertion"), ("skipped", "skipped")}),
    "calc_test.go": (GO, {("no-assertion", "TestNoAssertion"), ("skipped", "TestSkipped"), ("duplicate", "TestCopy"),
                          ("source-grep", "TestGreps")}),
    "lib.rs": (RUST, {("no-assertion", "no_assertion"), ("skipped", "skipped"), ("duplicate", "copy"),
                      ("source-grep", "greps")}),
    "CalcTest.php": (PHP, {("no-assertion", "testNoAssertion"), ("skipped", "testSkipped"), ("duplicate", "testCopy"),
                           ("source-grep", "testGreps")}),
    "calc_spec.rb": (RUBY, {("no-assertion", "has no assertion"), ("skipped", "is skipped"),
                            ("focused", "is focused"), ("duplicate", "copies"), ("source-grep", "greps")}),
}


class AuditCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def kinds(self, *names):
        return {(f.kind, f.name.split(" (same as")[0]) for f in test_audit.audit([str(self.dir / n) for n in names])}


class LanguageTest(AuditCase):
    def test_each_kind_in_each_language_family(self):
        for name, (text, expected) in CASES.items():
            with self.subTest(file=name):
                self.write(name, text)
                self.assertEqual(self.kinds(name), expected)

    def test_helper_and_library_assertions_count_as_assertions(self):
        for name, (text, _) in CASES.items():
            self.write(name, text)
        reported = {finding_name for _, finding_name in self.kinds(*CASES)}
        for helper_test in ("test_helper", "test_raises", "uses a custom matcher helper", "is concise",
                            "FluentAssertion", "hamcrest", "TestTestify", "panics", "adds two numbers"):
            self.assertNotIn(helper_test, reported)

    def test_a_helper_named_otherwise_is_the_accepted_false_negative(self):
        self.write("test_x.py", "def test_uses_odd_helper():\n    confirm_total(add(1, 2))\n")
        self.assertEqual(self.kinds("test_x.py"), {("no-assertion", "test_uses_odd_helper")})

    def test_duplicate_reports_the_later_copy_with_the_first_line(self):
        self.write("test_app.py", PY)
        dup = [f for f in test_audit.audit([str(self.dir / "test_app.py")]) if f.kind == "duplicate"]
        self.assertEqual([(f.line, f.name) for f in dup], [(21, "test_copy (same as line 3)")])

    def test_short_bodies_are_never_duplicates(self):
        self.write("test_x.py", "def test_a():\n    assert ok()\n\ndef test_b():\n    assert ok()\n")
        self.assertEqual(self.kinds("test_x.py"), set())
        self.assertEqual(len(test_audit.audit([str(self.dir / "test_x.py")], min_dup=5)), 1)

    def test_python_unconditional_skips_are_reported_and_conditional_ones_are_not(self):
        self.write("test_x.py", "import unittest\nclass T(unittest.TestCase):\n    @unittest.skip('x')\n"
                                "    def test_a(self):\n        self.assertTrue(1)\n    def test_b(self):\n"
                                "        self.skipTest('later')\n    @unittest.skipIf(os.name == 'nt', 'posix')\n"
                                "    def test_c(self):\n        self.assertTrue(1)\n    def test_d(self):\n"
                                "        if os.name == 'nt':\n            self.skipTest('posix')\n"
                                "        self.assertTrue(1)\n")
        self.assertEqual(self.kinds("test_x.py"), {("skipped", "test_a"), ("skipped", "test_b")})

    def test_raising_checks_count_as_assertions(self):
        self.write("test_x.py", "def test_a():\n    subprocess.run(['x'], check=True)\n\ndef test_b():\n"
                                "    if bad():\n        raise AssertionError('bad')\n")
        self.assertEqual(self.kinds("test_x.py"), set())

    def test_reading_generated_code_after_running_the_generator_is_not_source_grep(self):
        self.write("test_x.py", "def test_gen():\n    build(out)\n    text = open('out/app.py').read()\n"
                                "    assert 'def main' in text\n")
        self.assertEqual(self.kinds("test_x.py"), set())

    def test_a_code_path_mentioned_but_not_read_is_not_source_grep(self):
        self.write("test_x.py", "def test_wiring():\n    config = open('hooks.json').read()\n"
                                "    assert 'guard.py' in config\n")
        self.write("y.test.js", "it('wires', () => {\n  const c = fs.readFileSync('hooks.json');\n"
                                "  expect(c).toContain('guard.py');\n});\n")
        self.assertEqual(self.kinds("test_x.py", "y.test.js"), set())

    def test_reading_a_fixture_is_not_source_grep(self):
        self.write("test_x.py", "def test_parse():\n    text = open('fixtures/input.json').read()\n"
                                "    assert 'name' in parse(text)\n")
        self.write("x.test.js", "it('parses', () => {\n  const t = fs.readFileSync('fixtures/a.json');\n"
                                "  expect(parse(t)).toContain('name');\n});\n")
        self.assertEqual(self.kinds("test_x.py", "x.test.js"), set())

    def test_describe_level_focus_and_skip(self):
        self.write("a.spec.js", "describe.only('x', () => {\n  it('a', () => { expect(1).toBe(1); });\n});\n"
                                "xdescribe('y', () => {\n  it('b', () => { expect(2).toBe(2); });\n});\n")
        self.assertEqual(self.kinds("a.spec.js"), {("focused", "describe block"), ("skipped", "describe block")})

    def test_comments_do_not_count_as_assertions(self):
        self.write("a.test.ts", "it('a', () => {\n  // expect(x).toBe(1)\n  run();\n});\n")
        self.assertEqual(self.kinds("a.test.ts"), {("no-assertion", "a")})


class RobustnessTest(AuditCase):
    def test_broken_inputs_never_crash(self):
        self.write("test_bad.py", "def test_x(:\n")
        self.write("bad.test.js", "it('never closes', () => {\n  expect(1")
        self.write("lib.rs", "#[test]\nfn open() {\n")
        self.write("Bin.Tests.cs", "\0\0binary")
        self.assertEqual(test_audit.audit([str(self.dir)]), [])

    def test_non_test_files_and_rust_without_tests_are_ignored(self):
        self.write("app.py", "def test_like():\n    pass\n")
        self.write("src/lib.rs", "fn main() {}\n")
        self.write("node_modules/x/a.test.js", "it('a', () => { run(); });\n")
        self.assertEqual(test_audit.audit([str(self.dir)]), [])

    def test_git_ignored_files_are_skipped_inside_a_repository(self):
        subprocess.run(["git", "init", "-q"], cwd=self.dir, check=True)
        self.write(".gitignore", "generated/\n")
        self.write("generated/test_gen.py", "def test_x():\n    pass\n")
        self.write("test_real.py", "def test_y():\n    pass\n")
        self.assertEqual({f.path.replace(os.sep, "/").rsplit("/", 1)[-1] for f in test_audit.audit([str(self.dir)])},
                         {"test_real.py"})


class CliTest(AuditCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = test_audit.main(list(args))
        return code, out.getvalue()

    def test_exit_codes_and_output(self):
        self.write("test_ok.py", "def test_a():\n    assert True\n")
        self.assertEqual(self.run_cli(str(self.dir)), (0, ""))
        self.write("test_bad.py", "def test_b():\n    run()\n")
        code, out = self.run_cli(str(self.dir))
        self.assertEqual(code, 1)
        self.assertTrue(out.strip().endswith("test_bad.py:1 no-assertion test_b"))
        code, out = self.run_cli("--json", str(self.dir))
        self.assertEqual((code, json.loads(out)[0]["kind"]), (1, "no-assertion"))
        self.assertEqual(self.run_cli(str(self.dir / "missing"))[0], 2)
        self.assertEqual(self.run_cli("--bogus")[0], 2)
        self.assertEqual(self.run_cli("--min-dup-chars", "0", str(self.dir))[0], 2)

    def test_runs_as_a_script(self):
        self.write("test_ok.py", "def test_a():\n    assert True\n")
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.dir)], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
