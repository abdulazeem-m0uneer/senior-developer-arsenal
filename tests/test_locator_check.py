"""Tests for test-every-change's locator_check.py (loose Playwright text locators)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "test-every-change" / "scripts" / "locator_check.py"


class LocatorCheckCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def spec(self, body, name="a.spec.ts"):
        path = self.dir / name
        path.write_text(body)
        return path

    def run_check(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                              cwd=cwd or self.dir)

    def assert_reported(self, body, call_text):
        path = self.spec(body)
        res = self.run_check(path)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn(f"{path}:1: {call_text} needs {{ exact: true }} or a test id", res.stdout)

    def assert_clean(self, body):
        res = self.run_check(self.spec(body))
        self.assertEqual((res.returncode, res.stdout), (0, ""), res.stderr)


class ReportedTests(LocatorCheckCase):
    def test_get_by_label(self):
        self.assert_reported("await page.getByLabel('Email').fill('x');\n", "getByLabel('Email')")

    def test_get_by_text(self):
        self.assert_reported("await page.getByText(\"Save\").click();\n", 'getByText("Save")')

    def test_get_by_placeholder(self):
        self.assert_reported("await page.getByPlaceholder('Search').fill('x');\n", "getByPlaceholder('Search')")

    def test_get_by_title(self):
        self.assert_reported("await page.getByTitle('Close').click();\n", "getByTitle('Close')")

    def test_get_by_alt_text(self):
        self.assert_reported("await page.getByAltText('Logo').click();\n", "getByAltText('Logo')")

    def test_role_with_name(self):
        self.assert_reported("await page.getByRole('button', { name: 'Save' }).click();\n",
                             "getByRole('button', { name: 'Save' })")

    def test_the_word_exact_inside_the_name_string_is_still_loose(self):
        self.assert_reported("page.getByRole('button', { name: 'Pay exact amount' });\n",
                             "getByRole('button', { name: 'Pay exact amount' })")
        self.assert_reported("page.getByText('x', { name: \"exact: true\" });\n",
                             "getByText('x', { name: \"exact: true\" })")

    def test_an_exact_key_after_a_name_is_strict(self):
        self.assert_clean("page.getByRole('button', { name: 'x', exact: true });\n")
        self.assert_clean("page.getByRole('button', { name: 'Pay exact amount', exact: true });\n")

    def test_exact_false_is_loose(self):
        self.assert_reported("await page.getByLabel('Email', { exact: false }).fill('x');\n",
                             "getByLabel('Email', { exact: false })")

    def test_role_name_with_exact_false_is_loose(self):
        self.assert_reported("page.getByRole('row', { name: 'Ann', exact: false });\n",
                             "getByRole('row', { name: 'Ann', exact: false })")

    def test_options_object_on_next_line(self):
        path = self.spec("await page.getByRole('button', {\n  name: 'Save',\n}).click();\n")
        res = self.run_check(path)
        self.assertEqual(res.returncode, 1)
        self.assertIn(f"{path}:1: getByRole('button', {{ name: 'Save', }}) needs {{ exact: true }} or a test id",
                      res.stdout)

    def test_call_split_across_lines_reports_first_line(self):
        path = self.spec("\n\nawait page.getByLabel(\n  'Email'\n).fill('x');\n")
        res = self.run_check(path)
        self.assertEqual(res.returncode, 1)
        self.assertTrue(res.stdout.startswith(f"{path}:3: "), res.stdout)

    def test_every_loose_call_on_one_line_is_reported(self):
        res = self.run_check(self.spec("page.getByLabel('A'); page.getByText('B');\n"))
        self.assertEqual(res.stdout.count(" needs "), 2)

    def test_string_holding_paren_and_comma(self):
        self.assert_reported("page.getByText('Save (all), now');\n", "getByText('Save (all), now')")

    def test_chained_locator_is_still_found(self):
        self.assert_reported("page.getByTestId('row').getByText('Ann');\n", "getByText('Ann')")

    def test_template_literal_without_interpolation_is_loose(self):
        self.assert_reported("page.getByText(`Row`);\n", "getByText(`Row`)")
        self.assert_reported("page.getByRole('row', { name: `Ann Lee` });\n", "getByRole('row', { name: `Ann Lee` })")


class AcceptedTests(LocatorCheckCase):
    def test_template_literal_with_interpolation_is_a_variable(self):
        for body in ("page.getByText(`Row ${n}`);", "page.getByRole('row', { name: `${word} ${date}` });",
                     "page.getByRole('row', { name: `a ${f({ b: 1 })} c` });"):
            with self.subTest(body=body):
                self.assert_clean(body + "\n")

    def test_non_literal_arguments_may_be_intentional_regexps(self):
        for body in ("page.getByText(label);", "page.getByText(new RegExp('x'));", "page.getByText(re);",
                     "page.getByRole('button', { name: label });", "page.getByRole('button', { name: new RegExp('x') });",
                     "page.getByRole('button', { name });", "page.getByRole('button', opts);"):
            with self.subTest(body=body):
                self.assert_clean(body + "\n")

    def test_exact_given_by_a_variable_may_be_true(self):
        self.assert_clean("page.getByText('x', { exact });\n")
        self.assert_clean("page.getByRole('row', { name: 'x', exact: flag });\n")

    def test_testing_library_file_is_skipped_in_a_walked_folder(self):
        (self.dir / "u.test.tsx").write_text(
            "import { screen } from '@testing-library/react';\nscreen.getByText('x');\n")
        res = self.run_check(self.dir)
        self.assertEqual((res.returncode, res.stdout), (0, ""), res.stderr)

    def test_testing_library_file_named_explicitly_is_checked(self):
        path = self.dir / "u.test.tsx"
        path.write_text("import { screen } from '@testing-library/react';\nscreen.getByText('x');\n")
        self.assertEqual(self.run_check(path).returncode, 1)

    def test_exact_true_text_locators(self):
        for kind in ("Label", "Text", "Placeholder", "Title", "AltText"):
            with self.subTest(kind=kind):
                self.assert_clean(f"page.getBy{kind}('x', {{ exact: true }});\n")

    def test_role_name_exact_true(self):
        self.assert_clean("page.getByRole('button', { name: 'Save', exact: true });\n")

    def test_role_name_exact_true_on_next_line(self):
        self.assert_clean("page.getByRole('button', {\n  name: 'Save',\n  exact: true,\n});\n")

    def test_regexp_argument_is_intentional(self):
        self.assert_clean("page.getByLabel(/email/i); page.getByText(/a\\)b'/);\n")

    def test_regexp_with_quote_does_not_hide_comment_after_it(self):
        self.assert_clean("page.getByLabel(/it's/);\n// page.getByText('C')\n")

    def test_role_with_regexp_name(self):
        self.assert_clean("page.getByRole('button', { name: /save/i });\n")

    def test_role_without_name(self):
        self.assert_clean("page.getByRole('button');\n")

    def test_test_id_and_css_locators(self):
        self.assert_clean("page.getByTestId('x'); page.locator('#id'); page.locator('[href=\"/a\"]');\n")

    def test_commented_call_is_ignored(self):
        self.assert_clean("// page.getByLabel('Email')\n/* page.getByText('x') */\n")

    def test_unterminated_call_does_not_crash(self):
        res = self.run_check(self.spec("page.getByLabel('Email'\n"))
        self.assertIn(res.returncode, (0, 1))
        self.assertNotIn("Traceback", res.stderr)


class PathTests(LocatorCheckCase):
    def test_directory_is_walked_and_node_modules_skipped(self):
        (self.dir / "sub").mkdir()
        (self.dir / "node_modules").mkdir()
        (self.dir / "sub" / "b.e2e.ts").write_text("page.getByText('x');\n")
        (self.dir / "node_modules" / "c.spec.ts").write_text("page.getByText('y');\n")
        (self.dir / "notes.md").write_text("page.getByText('z');\n")
        res = self.run_check(self.dir)
        self.assertEqual(res.returncode, 1)
        self.assertEqual(res.stdout.count(" needs "), 1)
        self.assertIn("b.e2e.ts:1", res.stdout)

    def test_default_paths_are_e2e_directories(self):
        (self.dir / "tests" / "e2e").mkdir(parents=True)
        (self.dir / "tests" / "e2e" / "a.spec.ts").write_text("page.getByLabel('x');\n")
        (self.dir / "src").mkdir()
        (self.dir / "src" / "b.spec.ts").write_text("page.getByLabel('x');\n")
        res = self.run_check(cwd=self.dir)
        self.assertEqual(res.returncode, 1)
        self.assertIn("a.spec.ts:1", res.stdout)
        self.assertNotIn("b.spec.ts", res.stdout)

    def test_default_with_no_e2e_directory_is_clean(self):
        res = self.run_check(cwd=self.dir)
        self.assertEqual(res.returncode, 0)
        self.assertIn("nothing to check", res.stderr)

    def test_missing_path_is_bad_input(self):
        res = self.run_check(self.dir / "nope.ts")
        self.assertEqual(res.returncode, 2)
        self.assertIn("nope.ts", res.stderr)

    def test_non_utf8_file_is_bad_input(self):
        path = self.dir / "bin.spec.ts"
        path.write_bytes(b"\xff\xfe\x00getByText('x')")
        res = self.run_check(path)
        self.assertEqual(res.returncode, 2)


if __name__ == "__main__":
    unittest.main()
