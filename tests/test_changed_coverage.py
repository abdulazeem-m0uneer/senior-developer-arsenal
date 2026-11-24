"""Tests for quality-gate's changed_coverage.py: coverage of the lines a branch changes, from lcov or Cobertura."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "quality-gate" / "scripts" / "changed_coverage.py"
IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@example.com")


def git(cwd, *args):
    return subprocess.run(["git", *IDENTITY, *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def lcov(path, hits):
    """An lcov record for `path` with {line: hits}."""
    lines = [f"SF:{path}", *(f"DA:{line},{count}" for line, count in sorted(hits.items())), "end_of_record"]
    return "TN:\n" + "\n".join(lines) + "\n"


def cobertura(filename, hits, source="."):
    rows = "".join(f'<line number="{line}" hits="{count}"/>' for line, count in sorted(hits.items()))
    return (f'<?xml version="1.0" ?><coverage><sources><source>{source}</source></sources><packages><package name="p">'
            f'<classes><class name="m" filename="{filename}"><methods/><lines>{rows}</lines></class></classes>'
            '</package></packages></coverage>')


class ChangedCoverageCase(unittest.TestCase):
    """Repo with pkg/src/app.py (5 lines) on main; branch `feature` rewrites lines 2-4 and adds lines 6-7."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(os.path.realpath(self.tmp.name)) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        self.write("pkg/src/app.py", "".join(f"line{n}\n" for n in range(1, 6)))
        self.write("README.md", "docs\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "init")
        git(self.repo, "checkout", "-q", "-b", "feature")
        self.write("pkg/src/app.py", "line1\nnew2\nnew3\nnew4\nline5\nnew6\nnew7\n")
        git(self.repo, "commit", "-qam", "change")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def report(self, name, text):
        path = Path(self.tmp.name) / name
        path.write_text(text)
        return path

    def run_check(self, report, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), "--report", str(report), "--base", "main", *args],
                                cwd=self.repo, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr


class LcovTests(ChangedCoverageCase):
    def test_under_threshold_refuses_and_lists_uncovered_lines(self):
        # changed: 2,3,4,6,7; executable among them: 2,3,4,6 (7 not in report); covered: 2 -> 1/4 = 25%
        report = self.report("lcov.info", lcov("pkg/src/app.py", {1: 1, 2: 3, 3: 0, 4: 0, 5: 1, 6: 0}))
        code, out, err = self.run_check(report)
        self.assertEqual(code, 1, out + err)
        self.assertIn("1/4", out)
        self.assertIn("25.0%", out)
        self.assertIn("pkg/src/app.py: 3, 4, 6", out)

    def test_at_threshold_passes(self):
        report = self.report("lcov.info", lcov("pkg/src/app.py", {2: 1, 3: 1, 4: 1, 6: 0}))
        code, out, err = self.run_check(report, "--min", "75")
        self.assertEqual(code, 0, out + err)
        self.assertIn("3/4", out)

    def test_over_threshold_passes_with_json(self):
        report = self.report("lcov.info", lcov("pkg/src/app.py", {2: 1, 3: 1, 4: 1, 6: 1, 7: 2}))
        code, out, _ = self.run_check(report, "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual((data["covered"], data["executable"], data["pass"]), (5, 5, True))
        self.assertEqual(data["files"], [{"path": "pkg/src/app.py", "executable": 5, "covered": 5, "uncovered": []}])

    def test_absolute_report_path_matches(self):
        absolute = self.repo / "pkg" / "src" / "app.py"
        report = self.report("lcov.info", lcov(str(absolute), {2: 0, 3: 0}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 1)
        self.assertIn("0/2", out)

    def test_path_relative_to_sub_package_matches_by_suffix(self):
        report = self.report("lcov.info", lcov("src/app.py", {2: 1, 3: 1}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 0)
        self.assertIn("2/2", out)

    def test_suffix_must_match_whole_path_components(self):
        report = self.report("lcov.info", lcov("rc/app.py", {2: 0}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 0)
        self.assertIn("no changed line is executable", out)

    def test_no_executable_changed_line_passes(self):
        report = self.report("lcov.info", lcov("pkg/src/app.py", {1: 0, 5: 0}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 0)
        self.assertIn("no changed line is executable", out)

    def test_changed_file_absent_from_report_is_named(self):
        self.write("pkg/src/other.py", "a\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "other")
        report = self.report("lcov.info", lcov("pkg/src/app.py", {2: 1}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 0)
        self.assertIn("not in the report: pkg/src/other.py", out)

    def test_uncovered_list_is_bounded_to_twenty_per_file(self):
        self.write("pkg/src/big.py", "".join(f"b{n}\n" for n in range(1, 31)))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "big")
        report = self.report("lcov.info", lcov("pkg/src/big.py", {n: 0 for n in range(1, 31)}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 1)
        self.assertIn("pkg/src/big.py: 1, 2,", out)
        self.assertIn("20, and 10 more", out)
        self.assertNotIn(" 21,", out)

    def test_path_with_a_space_is_measured(self):
        # git ends the "+++ b/my file.py" header with a TAB when the path holds a space
        self.write("my file.py", "a\nb\nc\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "spaced")
        report = self.report("lcov.info", lcov("pkg/src/app.py", {2: 1}) + lcov(str(self.repo / "my file.py"),
                                                                                 {2: 0, 3: 0}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 1, out)
        self.assertIn("1/3", out)
        self.assertIn("my file.py: 2, 3", out)
        self.assertNotIn("not in the report", out)

    def test_percent_shown_never_rounds_up_to_the_minimum(self):
        report = self.report("lcov.info", lcov("pkg/src/app.py", {2: 1, 3: 1, 4: 0}))  # 2/3 = 66.66..%
        code, out, _ = self.run_check(report, "--min", "66.7")
        self.assertEqual(code, 1, out)
        self.assertIn("2/3 (66.6%), minimum 66.7%", out)
        code, out, _ = self.run_check(report, "--min", "66.7", "--json")
        self.assertEqual((json.loads(out)["percent"], json.loads(out)["pass"]), (66.66, False))

    def test_report_path_matching_several_changed_files_is_skipped(self):
        self.write("other/src/app.py", "o\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "twin")
        report = self.report("lcov.info", lcov("src/app.py", {1: 0, 2: 0}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 0, out)
        self.assertIn("report paths matching several files (skipped): src/app.py", out)
        self.assertIn("no changed line is executable", out)

    def test_lines_after_end_of_record_belong_to_no_file(self):
        report = self.report("lcov.info", lcov("pkg/src/app.py", {2: 1}) + "DA:3,0\n")
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 0, out)
        self.assertIn("1/1", out)

    def test_hits_of_one_line_are_summed_across_records(self):
        # lcov repeats a file per test run; a line hit in any record is covered
        report = self.report("lcov.info", "SF:pkg/src/app.py\nDA:2,1\nDA:2,0\nend_of_record\n"
                             + lcov("pkg/src/app.py", {3: 2}) + lcov("pkg/src/app.py", {3: 0}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 0, out)
        self.assertIn("2/2", out)

    def test_hits_are_summed_across_report_paths_of_one_file(self):
        report = self.report("lcov.info", lcov("pkg/src/app.py", {2: 1}) + lcov(str(self.repo / "pkg/src/app.py"),
                                                                                 {2: 0}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 0, out)
        self.assertIn("1/1", out)

    def test_negative_hits_count_as_zero(self):
        report = self.report("lcov.info", lcov("pkg/src/app.py", {2: -1}) + lcov("pkg/src/app.py", {2: 1}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 0, out)
        self.assertIn("1/1", out)

    def test_backslash_report_path_matches(self):
        report = self.report("lcov.info", lcov("pkg\\src\\app.py", {2: 0}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 1, out)
        self.assertIn("0/1", out)

    def test_exact_record_beats_a_longer_record_ending_with_the_same_path(self):
        # a root-relative report also covering an example copy: only the record naming the file itself counts
        covered, missed = {n: 1 for n in (2, 3, 4, 6, 7)}, {n: 0 for n in (2, 3, 4, 6, 7)}
        for own, other, code_wanted, shown in ((covered, missed, 0, "5/5"), (missed, covered, 1, "0/5")):
            with self.subTest(own=own[2]):
                report = self.report("lcov.info", lcov("pkg/src/app.py", own) + lcov("examples/demo/pkg/src/app.py",
                                                                                     other))
                code, out, _ = self.run_check(report)
                self.assertEqual(code, code_wanted, out)
                self.assertIn(shown, out)

    def test_dot_dot_report_path_matches_after_leading_parents_are_dropped(self):
        report = self.report("lcov.info", lcov("../src/app.py", {2: 0}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 1, out)
        self.assertIn("0/1", out)

    def test_added_line_starting_with_two_plus_signs_is_content(self):
        # with -U0 the added line "++ x" shows as "+++ x", which looks like a file header
        self.write("pkg/src/app.py", "++ x\nnew2\nnew3\nnew4\nline5\nnew6\nnew7\n")
        git(self.repo, "commit", "-qam", "plus line")
        report = self.report("lcov.info", lcov("pkg/src/app.py", {1: 1, 6: 0}))
        code, out, _ = self.run_check(report, "--json")
        self.assertEqual(code, 1, out)
        self.assertEqual((json.loads(out)["covered"], json.loads(out)["executable"]), (1, 2))

    def test_lines_the_base_changed_after_the_fork_are_not_measured(self):
        git(self.repo, "checkout", "-q", "main")
        self.write("README.md", "")
        git(self.repo, "commit", "-qam", "main drops a line")
        git(self.repo, "checkout", "-q", "feature")
        report = self.report("lcov.info", lcov("pkg/src/app.py", {n: 1 for n in (2, 3, 4, 6, 7)})
                             + lcov("README.md", {1: 0}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 0, out)
        self.assertIn("5/5", out)

    def test_non_ascii_path_is_measured(self):
        self.write("café.py", "a\nb\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "accent")
        report = self.report("lcov.info", lcov("pkg/src/app.py", {2: 1}) + lcov(str(self.repo / "café.py"),
                                                                                 {1: 0, 2: 0}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 1, out)
        self.assertIn("café.py: 1, 2", out)
        self.assertNotIn("not in the report", out)

    def test_deleted_lines_are_not_changed_lines(self):
        self.write("pkg/src/app.py", "line1\nnew2\nnew3\nnew4\nline5\n")
        git(self.repo, "commit", "-qam", "drop 6-7")
        report = self.report("lcov.info", lcov("pkg/src/app.py", {2: 1, 3: 1, 4: 1, 6: 0, 7: 0}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 0)
        self.assertIn("3/3", out)


class MonorepoTests(ChangedCoverageCase):
    """web/src/app.py, a twin of pkg/src/app.py, is on main and unchanged by the branch."""

    def setUp(self):
        super().setUp()
        git(self.repo, "checkout", "-q", "main")
        self.write("web/src/app.py", "w\n" * 7)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "web")
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "merge", "-q", "--no-edit", "main")

    def report_in(self, folder, text):
        path = self.repo / folder / "coverage" / "lcov.info"
        path.parent.mkdir(parents=True)
        path.write_text(text)
        return path

    def test_twin_package_record_from_outside_the_repo_is_ambiguous_not_credited(self):
        report = self.report("lcov.info", lcov("src/app.py", {n: 5 for n in (2, 3, 4, 6, 7)}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 0, out)
        self.assertIn("report paths matching several files (skipped): src/app.py", out)
        self.assertIn("not in the report: pkg/src/app.py", out)
        self.assertNotIn("5/5", out)

    def test_other_package_record_is_not_summed_into_the_changed_file(self):
        report = self.report("lcov.info", lcov(str(self.repo / "pkg/src/app.py"), {2: 0})
                             + lcov("src/app.py", {2: 5}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 1, out)
        self.assertIn("0/1", out)

    def test_report_inside_a_package_resolves_against_its_own_folder(self):
        hits = {n: 5 for n in (2, 3, 4, 6, 7)}
        code, out, _ = self.run_check(self.report_in("web", lcov("src/app.py", hits)))
        self.assertEqual(code, 0, out)
        self.assertIn("not in the report: pkg/src/app.py", out)
        self.assertNotIn("skipped", out)
        code, out, _ = self.run_check(self.report_in("pkg", lcov("src/app.py", {n: 0 for n in hits})))
        self.assertEqual(code, 1, out)
        self.assertIn("0/5", out)

    def test_report_path_climbing_to_a_sibling_package_is_resolved(self):
        code, out, _ = self.run_check(self.report_in("web", lcov("../pkg/src/app.py", {2: 0, 3: 1})))
        self.assertEqual(code, 1, out)
        self.assertIn("1/2", out)


class CoberturaTests(ChangedCoverageCase):
    def test_under_threshold_refuses(self):
        report = self.report("coverage.xml", cobertura("src/app.py", {2: 1, 3: 0, 4: 0, 6: 0, 7: 0}, "/x/pkg"))
        code, out, _ = self.run_check(report, "--min", "50")
        self.assertEqual(code, 1)
        self.assertIn("1/5", out)
        self.assertIn("pkg/src/app.py: 3, 4, 6, 7", out)

    def test_over_threshold_passes(self):
        report = self.report("coverage.xml", cobertura("pkg/src/app.py", {2: 1, 3: 1, 4: 1, 6: 1, 7: 0}))
        code, out, _ = self.run_check(report, "--min", "80")
        self.assertEqual(code, 0)
        self.assertIn("4/5", out)

    def test_absolute_filename_matches(self):
        report = self.report("coverage.xml", cobertura(str(self.repo / "pkg/src/app.py"), {2: 0}))
        code, out, _ = self.run_check(report)
        self.assertEqual(code, 1)
        self.assertIn("0/1", out)

    def test_filename_relative_to_the_source_folder_names_that_file(self):
        # coverage.py writes <source>/abs/repo/pkg/src</source> and filenames relative to it; other/app.py would
        # otherwise win the suffix match by fewer extra components
        git(self.repo, "checkout", "-q", "main")
        self.write("other/app.py", "o\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "other")
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "rebase", "-q", "main")
        for source in (str(self.repo / "pkg" / "src"), "repo/pkg/src", "/elsewhere/pkg/src"):
            with self.subTest(source=source):  # absolute, relative to the report's folder, not on this machine
                xml = cobertura("app.py", {2: 1, 3: 0, 4: 0, 6: 0, 7: 0}, source)
                report = self.report("coverage.xml", xml.replace("<sources>", "<sources><source>/missing</source>"))
                code, out, err = self.run_check(report, "--min", "50")
                if source.startswith("/elsewhere"):
                    self.assertEqual(code, 0, out + err)  # no file there: the suffix match decides, as before
                    self.assertIn("not in the report: pkg/src/app.py", out)
                else:
                    self.assertEqual(code, 1, out + err)
                    self.assertIn("pkg/src/app.py: 3, 4, 6, 7", out)

    def test_report_starting_with_a_byte_order_mark_is_read(self):
        # .NET tools such as coverlet write UTF-8 with a BOM
        path = Path(self.tmp.name) / "coverage.xml"
        path.write_bytes(b"\xef\xbb\xbf" + cobertura("pkg/src/app.py", {2: 1, 3: 0}).encode())
        code, out, err = self.run_check(path, "--min", "50")
        self.assertEqual(code, 0, out + err)
        self.assertIn("1/2", out)

    def test_hits_of_a_class_split_in_two_are_summed(self):
        split = cobertura("pkg/src/app.py", {2: 1}).replace(
            "</classes>", '<class name="n" filename="pkg/src/app.py"><lines><line number="2" hits="0"/></lines></class>'
            "</classes>")
        code, out, _ = self.run_check(self.report("coverage.xml", split))
        self.assertEqual(code, 0, out)
        self.assertIn("1/1", out)


class ErrorTests(ChangedCoverageCase):
    def test_missing_report_is_exit_2(self):
        code, _, err = self.run_check(Path(self.tmp.name) / "nope.info")
        self.assertEqual(code, 2)
        self.assertIn("nope.info", err)

    def test_unreadable_cobertura_is_exit_2(self):
        code, _, err = self.run_check(self.report("coverage.xml", "<coverage><broken"))
        self.assertEqual(code, 2)
        self.assertIn("coverage.xml", err)

    def test_report_with_no_records_is_exit_2(self):
        code, _, err = self.run_check(self.report("lcov.info", "not lcov at all\n"))
        self.assertEqual(code, 2)
        self.assertIn("no coverage records", err)

    def test_unknown_base_is_exit_2(self):
        report = self.report("lcov.info", lcov("pkg/src/app.py", {2: 1}))
        result = subprocess.run([sys.executable, str(SCRIPT), "--report", str(report), "--base", "no-such-ref"],
                                cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("git", result.stderr)

    def test_min_out_of_range_is_exit_2(self):
        report = self.report("lcov.info", lcov("pkg/src/app.py", {2: 1}))
        code, _, _ = self.run_check(report, "--min", "101")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
