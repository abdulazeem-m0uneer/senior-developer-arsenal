"""Unit tests for the helper scripts. Run: python3 -m unittest discover -s tests -p "test_*.py" """
import contextlib
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa: E402
import mcp_merge  # noqa: E402
import trending_rank  # noqa: E402


def run_quietly(function, *arguments):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return function(*arguments)


class FrontmatterTests(unittest.TestCase):
    def test_parses_quoted_and_plain_values(self):
        meta = build.parse_frontmatter("name: code-review\ndescription: 'Triggers on: \"x\". It''s fine.'", "f")
        self.assertEqual(meta, {"name": "code-review", "description": 'Triggers on: "x". It\'s fine.'})

    def test_rejects_unquoted_value_with_colon_space(self):
        with self.assertRaises(build.SourceError):
            build.parse_frontmatter("description: Triggers on: x", "f")

    def test_rejects_unbalanced_quote_duplicate_key_and_nested_yaml(self):
        for block in ("description: 'it's broken'", "name: a\nname: b", "triggers:\n  - one"):
            with self.subTest(block=block), self.assertRaises(build.SourceError):
                build.parse_frontmatter(block, "f")

    def test_split_requires_frontmatter(self):
        self.assertEqual(build.split_frontmatter("---\na: b\n---\n\nbody\n", "f"), ("a: b", "body\n"))
        for text in ("no frontmatter", "---\na: b\nnever closed"):
            with self.subTest(text=text), self.assertRaises(build.SourceError):
                build.split_frontmatter(text, "f")


class RenderTests(unittest.TestCase):
    AGENT = {"name": "auditor", "description": 'Finds "bugs": fast', "body": "You audit.", "writes": False, "pro": True}

    def test_read_only_agent_is_restricted_on_every_target(self):
        self.assertIn("disallowedTools: Write, Edit, NotebookEdit", build.render_agent("claude", self.AGENT))
        self.assertIn("readonly: true", build.render_agent("cursor", self.AGENT))
        self.assertIn("permission:\n  edit: deny", build.render_agent("opencode", self.AGENT))
        self.assertIn('sandbox_mode = "read-only"', build.render_agent("codex", self.AGENT))
        self.assertNotIn('"edit"', build.render_agent("copilot", self.AGENT))

    def test_writing_agent_is_not_restricted(self):
        agent = dict(self.AGENT, writes=True, pro=False)
        self.assertNotIn("disallowedTools", build.render_agent("claude", agent))
        self.assertIn("readonly: false", build.render_agent("cursor", agent))
        self.assertNotIn("sandbox_mode", build.render_agent("codex", agent))
        self.assertIn("model: inherit", build.render_agent("antigravity", agent))

    def test_description_with_quotes_stays_valid(self):
        self.assertIn('description: "Finds \\"bugs\\": fast"', build.render_agent("claude", self.AGENT))
        self.assertIn('description = "Finds \\"bugs\\": fast"', build.render_agent("codex", self.AGENT))

    def test_unknown_target_is_an_error(self):
        with self.assertRaises(ValueError):
            build.render_agent("nope", self.AGENT)

    def test_rules_map_triggers_per_target(self):
        glob_rule = {"name": "py", "trigger": "glob", "description": "Python", "globs": ["**/*.py", "**/x.toml"], "body": "B\n"}
        always = dict(glob_rule, trigger="always_on", globs=[])
        self.assertIn('paths:\n  - "**/*.py"\n  - "**/x.toml"', build.render_rule("claude", glob_rule))
        self.assertFalse(build.render_rule("claude", always).startswith("---"))
        self.assertIn("globs: **/*.py,**/x.toml\nalwaysApply: false", build.render_rule("cursor", glob_rule))
        self.assertIn("alwaysApply: true", build.render_rule("cursor", always))
        self.assertIn('applyTo: "**"', build.render_rule("copilot", always))

    def test_mcp_entries_match_each_client_shape(self):
        stdio = {"type": "stdio", "command": "codegraph", "args": ["serve", "--mcp"]}
        http = {"type": "http", "url": "http://localhost:8888/mcp/x/"}
        self.assertEqual(json.loads(build.render_mcp("opencode", stdio)),
                         {"type": "local", "command": ["codegraph", "serve", "--mcp"], "enabled": True})
        self.assertEqual(json.loads(build.render_mcp("serverurl", http)), {"serverUrl": http["url"]})
        self.assertEqual(json.loads(build.render_mcp("gemini", http)), {"httpUrl": http["url"]})
        self.assertEqual(build.render_mcp("codex", stdio), 'command = "codegraph"\nargs = ["serve", "--mcp"]\n')


class RepositoryTests(unittest.TestCase):
    def test_sources_are_valid_and_generated_output_is_current(self):
        sources = build.load_sources()
        self.assertEqual(build.stale_paths(build.generate(sources)), [])

    def test_manifest_has_no_empty_fields_and_only_known_kinds(self):
        rows = build.manifest_rows(build.load_sources())
        kinds = {row[2] for row in rows}
        self.assertLessEqual(kinds, {"dir", "file", "block", "mcp", "mcp-if-exists", "mcp-note", "note"})
        self.assertTrue(all(field for row in rows for field in row))
        self.assertTrue(all((ROOT / row[4]).exists() for row in rows if row[4] != "-"))


class McpMergeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.entry = self.root / "entry.json"
        self.entry.write_text('{"url": "http://localhost/{{BANK_ID}}/"}')
        self.config = self.root / "nested" / "mcp.json"

    def merge(self, *extra):
        return run_quietly(mcp_merge.main, ["--file", str(self.config), "--key", "mcpServers", "--name", "hindsight",
                                           "--entry", str(self.entry), "--set", "BANK_ID=demo", *extra])

    def test_creates_missing_file_and_substitutes_placeholder(self):
        self.assertEqual(self.merge(), 0)
        self.assertEqual(json.loads(self.config.read_text()),
                         {"mcpServers": {"hindsight": {"url": "http://localhost/demo/"}}})

    def test_preserves_existing_content_and_writes_backup(self):
        self.config.parent.mkdir()
        self.config.write_text('{"other": [1], "mcpServers": {"mine": {"command": "x"}}}')
        self.assertEqual(self.merge(), 0)
        data = json.loads(self.config.read_text())
        self.assertEqual((data["other"], data["mcpServers"]["mine"]), ([1], {"command": "x"}))
        self.assertEqual(len(list(self.config.parent.glob("mcp.json.bak-*"))), 1)

    def test_second_run_is_unchanged_and_writes_no_backup(self):
        self.merge()
        self.assertEqual(self.merge(), 0)
        self.assertEqual(list(self.config.parent.glob("mcp.json.bak-*")), [])

    def test_empty_file_is_treated_as_new(self):
        self.config.parent.mkdir()
        self.config.write_text("")
        self.assertEqual(self.merge(), 0)
        self.assertIn("hindsight", json.loads(self.config.read_text())["mcpServers"])

    def test_refuses_invalid_json_and_wrong_shapes_without_touching_the_file(self):
        self.config.parent.mkdir()
        for content in ("{ not json", "[1, 2]", '{"mcpServers": []}'):
            with self.subTest(content=content):
                self.config.write_text(content)
                self.assertEqual(self.merge(), 2)
                self.assertEqual(self.config.read_text(), content)

    def test_existing_permissions_and_a_utf8_bom_are_handled(self):
        self.config.parent.mkdir()
        self.config.write_bytes(b"\xef\xbb\xbf" + b'{"mcpServers": {}}')
        self.config.chmod(0o600)
        self.assertEqual(self.merge(), 0)
        self.assertIn("hindsight", json.loads(self.config.read_text())["mcpServers"])
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)

    def test_dry_run_writes_nothing(self):
        self.assertEqual(self.merge("--dry-run"), 0)
        self.assertFalse(self.config.exists())


class TrendingTests(unittest.TestCase):
    README = "intro\n" + trending_rank.render_block(["| Today | Not trending |"], "2026-01-01") + "\noutro\n"

    @staticmethod
    def page(*repositories):
        return "".join(f'<h2 class="h3 lh-condensed">\n <a data-x="1" href="/{name}" class="Link">' for name in repositories)

    def test_rank_is_one_based_and_case_insensitive(self):
        self.assertEqual(trending_rank.describe_rank("Me/Repo", ["a/b", "me/repo"]), "**#2**")
        self.assertEqual(trending_rank.describe_rank("me/repo", ["a/b"]), "Not trending")

    def test_page_markup_is_parsed_in_order(self):
        self.assertEqual(trending_rank.REPO_LINK_RE.findall(self.page("a/b", "c/d")), ["a/b", "c/d"])

    def test_rows_cover_all_periods(self):
        fake = lambda period: ["me/repo"] if period == "weekly" else ["a/b"]  # noqa: E731
        with mock.patch.object(trending_rank, "fetch_trending", fake):
            rows = trending_rank.render_rows("me/repo")
        self.assertEqual(rows, ["| Today | Not trending |", "| This week | **#1** |", "| This month | Not trending |"])

    def test_fetch_parses_the_page_and_rejects_an_empty_one(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = self.page("A/B", "c/d").encode()
        with mock.patch("urllib.request.urlopen", return_value=response):
            self.assertEqual(trending_rank.fetch_trending("daily"), ["a/b", "c/d"])
        response.__enter__.return_value.read.return_value = b"<html>markup changed</html>"
        with mock.patch("urllib.request.urlopen", return_value=response), self.assertRaises(trending_rank.TrendingError):
            trending_rank.fetch_trending("daily")

    def test_network_failure_becomes_a_trending_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")), \
                self.assertRaises(trending_rank.TrendingError):
            trending_rank.fetch_trending("daily")

    def test_unchanged_ranks_leave_the_readme_alone(self):
        self.assertIsNone(trending_rank.update_readme(self.README, ["| Today | Not trending |"], "2026-02-02"))

    def test_changed_rank_rewrites_only_the_block(self):
        updated = trending_rank.update_readme(self.README, ["| Today | **#3** |"], "2026-02-02")
        self.assertTrue(updated.startswith("intro\n") and updated.endswith("\noutro\n"))
        self.assertIn("| Today | **#3** |", updated)
        self.assertIn("2026-02-02", updated)
        self.assertEqual(updated.count(trending_rank.BEGIN), 1)

    def test_missing_or_malformed_block_is_an_error(self):
        for text in ("no block", trending_rank.END + trending_rank.BEGIN, self.README + self.README):
            with self.subTest(text=text[:20]), self.assertRaises(trending_rank.TrendingError):
                trending_rank.update_readme(text, [], "2026-02-02")

    def test_main_exits_non_zero_without_writing_when_the_fetch_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text(self.README)
            with mock.patch.object(trending_rank, "fetch_trending", side_effect=trending_rank.TrendingError("offline")):
                code = run_quietly(trending_rank.main, ["--readme", str(readme), "--repo", "me/repo"])
            self.assertEqual(code, 1)
            self.assertEqual(readme.read_text(), self.README)

    def test_main_updates_the_readme_when_the_rank_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text(self.README)
            with mock.patch.object(trending_rank, "fetch_trending", return_value=["me/repo"]):
                code = run_quietly(trending_rank.main, ["--readme", str(readme), "--repo", "me/repo"])
            self.assertEqual(code, 0)
            self.assertIn("| This month | **#1** |", readme.read_text())


if __name__ == "__main__":
    unittest.main()
