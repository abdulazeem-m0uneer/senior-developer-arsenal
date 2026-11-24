"""CHANGELOG.md follows Keep a Changelog and covers the VERSION file's version."""
import datetime
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Override to judge another copy, e.g. to see a test fail against a broken one.
CHANGELOG = Path(os.environ.get("ARSENAL_CHANGELOG", ROOT / "CHANGELOG.md"))
VERSION = ROOT / "VERSION"

SECTION = re.compile(r"^## \[(\d+)\.(\d+)\.(\d+)\] - (\d{4})-(\d{2})-(\d{2})$")
UNRELEASED = "## [Unreleased]"
REPO = "https://github.com/abdulazeem-m0uneer/senior-developer-arsenal"
LINK = re.compile(r"^\[([^\]]+)\]: (\S+)$", re.M)
# A release links its pull request; 1.0.0 predates pull requests and links the tree of its last commit.
RELEASE_URL = re.compile(rf"^{re.escape(REPO)}/(?:pull/(\d+)|tree/[0-9a-f]{{40}})$")
UNRELEASED_URL = re.compile(rf"^{re.escape(REPO)}/compare/v\d+\.\d+\.\d+\.\.\.HEAD$")
CITED_PR = re.compile(r"#(\d+)\b")
SUBSECTIONS = {"### Added", "### Changed", "### Deprecated", "### Removed", "### Fixed", "### Security"}


def sections(text):
    """Return [(heading, version tuple or None, body lines)] for each "## " heading.

    The version is None for the Unreleased heading and for a malformed one."""
    found = []
    for line in text.splitlines():
        if line.startswith("## "):
            match = SECTION.match(line)
            version = tuple(int(part) for part in match.groups()[:3]) if match else None
            found.append((line, version, []))
        elif found:
            found[-1][2].append(line)
    return found


class ChangelogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CHANGELOG.read_text(encoding="utf-8")
        cls.sections = sections(cls.text)
        cls.links = LINK.findall(cls.text)

    def test_has_sections(self):
        self.assertTrue(self.sections, "no '## ' section found")

    def test_current_version_has_a_section(self):
        version = VERSION.read_text(encoding="utf-8").strip()
        pattern = re.compile(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$")
        self.assertTrue(any(pattern.match(heading) for heading, _, _ in self.sections),
                        f"no '## [{version}] - YYYY-MM-DD' section")

    def test_headings_are_well_formed(self):
        bad = [heading for heading, version, _ in self.sections if version is None and heading != UNRELEASED]
        self.assertEqual(bad, [], f"headings must read '## [X.Y.Z] - YYYY-MM-DD' or '{UNRELEASED}'")
        for heading, version, _ in self.sections:
            if version is None:
                continue
            year, month, day = (int(part) for part in SECTION.match(heading).groups()[3:])
            try:
                datetime.date(year, month, day)
            except ValueError as error:
                self.fail(f"{heading}: {error}")

    def test_unreleased_is_first_and_appears_once(self):
        positions = [i for i, (heading, _, _) in enumerate(self.sections) if heading == UNRELEASED]
        self.assertIn(positions, ([], [0]), f"'{UNRELEASED}' must appear at most once, as the first section")

    def test_no_version_appears_twice(self):
        versions = [version for _, version, _ in self.sections if version]
        duplicates = sorted({v for v in versions if versions.count(v) > 1})
        self.assertEqual(duplicates, [])

    def test_versions_strictly_decrease(self):
        versions = [version for _, version, _ in self.sections if version]
        for newer, older in zip(versions, versions[1:]):
            self.assertGreater(newer, older, f"{newer} must come before {older} and differ from it")

    def test_every_section_has_a_bullet_under_a_known_subsection(self):
        for heading, _, body in self.sections:
            subsection, bullets = None, 0
            for line in body:
                if line.startswith("### "):
                    self.assertIn(line, SUBSECTIONS, f"{heading}: unknown subsection {line!r}")
                    subsection = line
                elif line.startswith("- "):
                    self.assertIsNotNone(subsection, f"{heading}: bullet before any subsection")
                    bullets += 1
            if heading != UNRELEASED:
                self.assertGreater(bullets, 0, f"{heading}: no bullet")

    def test_every_section_has_exactly_one_link_and_every_link_a_section(self):
        names = [name for name, _ in self.links]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        self.assertEqual(duplicates, [], "link reference defined twice")
        released = [".".join(map(str, version)) for _, version, _ in self.sections if version]
        headed = released + (["Unreleased"] if any(h == UNRELEASED for h, _, _ in self.sections) else [])
        self.assertEqual(sorted(set(released) - set(names)), [], "section without a link reference")
        self.assertEqual(sorted(set(names) - set(headed)), [], "link reference without a section")

    def test_links_point_to_the_project(self):
        for name, url in self.links:
            pattern = UNRELEASED_URL if name == "Unreleased" else RELEASE_URL
            self.assertRegex(url, pattern, f"[{name}]")

    def test_linked_pull_requests_match_the_sections(self):
        urls = dict(self.links)
        previous = None
        for heading, version, body in reversed(self.sections):
            if version is None:
                continue
            match = RELEASE_URL.match(urls.get(".".join(map(str, version)), ""))
            if not match or not match.group(1):
                continue
            linked = int(match.group(1))
            cited = [int(n) for n in CITED_PR.findall("\n".join(body))]
            self.assertTrue(all(n <= linked for n in cited),
                            f"{heading}: links #{linked} but cites a later pull request {max(cited)}")
            if previous is not None:
                self.assertGreater(linked, previous, f"{heading}: links #{linked}, not after the older release's #{previous}")
            previous = linked


if __name__ == "__main__":
    unittest.main()
