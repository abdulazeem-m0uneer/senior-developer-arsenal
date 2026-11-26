"""lite/ is current and holds only what the plugin directory accepts from an unverified organization."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_lite  # noqa: E402

LITE = ROOT / "lite"
ALLOWED_FILES = {".claude-plugin/plugin.json", ".claude-plugin/icon.png", "LICENSE"}
ALLOWED_MANIFEST = {"name", "version", "description", "author", "license", "homepage", "repository",
                    "keywords", "icon"}


class BuildLiteTest(unittest.TestCase):
    def setUp(self):
        self.expected = build_lite.generate()

    def test_committed_lite_is_current(self):
        self.assertEqual(build_lite.stale(self.expected), [], "run python3 scripts/build_lite.py")

    def test_only_markdown_license_manifest_and_icon(self):
        for rel, content in self.expected.items():
            if rel not in ALLOWED_FILES:
                self.assertTrue(rel.endswith(".md"), rel)
            if isinstance(content, str):
                self.assertFalse(content.startswith("#!"), rel)

    def test_no_hooks_scripts_or_mcp(self):
        for rel in self.expected:
            parts = rel.split("/")
            self.assertNotIn("hooks", parts[:1], rel)
            self.assertNotIn("scripts", parts, rel)
            self.assertNotIn("templates", parts, rel)
            self.assertNotIn(Path(rel).name, {"hooks.json", ".mcp.json"}, rel)

    def test_manifest_has_only_accepted_fields(self):
        manifest = json.loads(self.expected[".claude-plugin/plugin.json"])
        self.assertEqual(set(manifest) - ALLOWED_MANIFEST, set())
        self.assertEqual(manifest["icon"], "./.claude-plugin/icon.png")

    def test_subagents_keep_only_accepted_frontmatter(self):
        agents = {rel: text for rel, text in self.expected.items() if rel.startswith("agents/")}
        self.assertTrue(agents)
        for rel, text in agents.items():
            head = text.split("---\n")[1]
            keys = {line.split(":", 1)[0] for line in head.splitlines()}
            self.assertLessEqual(keys, set(build_lite.AGENT_KEYS), rel)
            self.assertIn("name", keys, rel)

    def test_no_download_and_run_text(self):
        pattern = re.compile(r"\|\s*(ba|z)?sh\b|\biex \(|\buvx |\bnpx (?!--no-install)|@latest\b")
        for rel, content in self.expected.items():
            if rel.endswith(".md"):
                self.assertIsNone(pattern.search(content), rel)

    def test_every_literal_rewrite_still_matches_a_source(self):
        sources = "".join(p.read_text(encoding="utf-8") for p in build_lite.SKILLS.rglob("*.md"))
        for old, _ in build_lite.LITERALS:
            self.assertIn(old, sources, "a rewrite no longer matches; update LITERALS")

    def test_no_machine_credentials_or_install_then_run(self):
        pattern = re.compile(r"GITHUB_TOKEN|PROVIDER_API_KEY|tool install --global \S+ &&|docker run -it|npm ci && npm run dev")
        for rel, content in self.expected.items():
            if rel.endswith(".md"):
                self.assertIsNone(pattern.search(content), rel)

    def test_subagents_drop_only_the_refused_key(self):
        text = self.expected["agents/code-explorer.md"]
        self.assertNotIn("omitClaudeMd", text)
        self.assertIn("effort: low", text)
        self.assertIn("disallowedTools:", text)

    def test_script_bound_skills_are_left_out_and_others_get_the_note(self):
        names = {rel.split("/")[1] for rel in self.expected if rel.startswith("skills/")}
        self.assertFalse(names & build_lite.EXCLUDED_SKILLS)
        self.assertIn("investigate", names)
        self.assertIn(build_lite.SCRIPT_NOTE, self.expected["skills/test-every-change/SKILL.md"])
        self.assertNotIn(build_lite.SCRIPT_NOTE, self.expected["skills/investigate/SKILL.md"])


if __name__ == "__main__":
    unittest.main()
