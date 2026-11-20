"""reading.py check-report claim rules: NO-SOURCE, BUS-CLAIM, UNCLOSED-FENCE."""
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_reading import ReadingTestCase  # noqa: E402


class ClaimTests(ReadingTestCase):
    def check(self, text, *args):
        return self.run_cmd("check-report", self.put(text, name="report.md"), *args)

    def assertFlagged(self, text, *expected, args=()):
        code, out, _ = self.check(text, *args)
        self.assertEqual(code, 1, out)
        for line in expected:
            self.assertIn(line, out)

    def assertClean(self, text, *args):
        code, out, _ = self.check(text, *args)
        self.assertEqual((code, out), (0, "ok: no unmarked or stale readings"))

    def test_each_inflected_default_claim_form_is_flagged_without_a_marker(self):
        forms = ("merges merged merging deploys deployed deploying releases released releasing ships shipped shipping "
                 "verifies verified verifying passes passed passing fixes fixed fixing closes closed closing").split()
        for word in forms:
            with self.subTest(word=word):
                self.assertFlagged(f"Auth change {word}\n", f"NO-SOURCE line 1 ({word}):")

    def test_base_forms_are_plans_not_claims(self):
        for text in ("We will merge it", "Plan to deploy", "Will fix tomorrow", "ship", "verify later",
                     "pass", "close it"):
            with self.subTest(text=text):
                self.assertClean(text + "\n")

    def test_re_and_un_prefixes_still_claim(self):
        for word in ("unmerged", "rereleased", "redeployed", "unverified", "reclosed"):
            with self.subTest(word=word):
                self.assertFlagged(f"Auth change {word}\n", f"NO-SOURCE line 1 ({word}):")

    def test_a_hyphen_right_after_the_word_is_not_a_claim(self):
        self.assertClean("A fixed-width font and closed-loop control\n")
        self.assertFlagged("Fixed - done\n", "NO-SOURCE line 1 (Fixed):")
        self.assertFlagged("Merged-in later, merged\n", "NO-SOURCE line 1 (merged):")

    def test_claim_words_override_keeps_exact_word_semantics(self):
        self.assertFlagged("Please merge\n", "NO-SOURCE line 1 (merge):", args=("--claim-words", "merge"))
        self.assertClean("It merged\n", "--claim-words", "merge")

    def test_done_live_and_green_are_not_default_claim_words(self):
        self.assertClean("All done\nThe site is live\n")
        self.assertClean("Build green (as of 14:10)\n")

    def test_claim_word_is_whole_word_and_any_case(self):
        self.assertFlagged("Auth change MERGED\n", "NO-SOURCE line 1 (MERGED):")
        for text in ("The prefixed list", "Mergedown plan", "Closedown notes", "Passedby"):
            with self.subTest(text=text):
                self.assertClean(text + "\n")

    def test_source_and_live_markers_are_the_only_sources(self):
        for marker in ("(source: gh pr view 741)", "(source: https://example.test/pr/741)",
                       "(source: gh pr view 741 -> MERGED a1b2c3d)", "(live: gh pr view 741 --json state)"):
            with self.subTest(marker=marker):
                self.assertClean(f"Auth change merged {marker}\n")

    def test_marker_prefix_is_case_insensitive_for_source(self):
        self.assertClean("Auth change merged (Source: gh pr view 741)\n")

    def test_bare_sha_url_run_id_or_date_is_not_a_source(self):
        for bare in ("a1b2c3d", "https://example.test/pr/741", "run 1234567890", "on 20261120", "on 2026-11-20", "#741"):
            with self.subTest(bare=bare):
                self.assertFlagged(f"Auth change merged {bare}\n", "NO-SOURCE line 1 (merged):")

    def test_empty_or_malformed_markers_are_not_markers(self):
        for fake in ("(source: )", "(source:)", "(live)", "(live: )", "(sourced: gh pr view 741)", "source: gh pr view 741"):
            with self.subTest(fake=fake):
                self.assertFlagged(f"Auth change merged {fake}\n", "NO-SOURCE line 1")

    def test_a_source_must_be_a_link_or_a_command(self):
        for text in ("-", "x", "n/a", "tbd", "todo", "?", "none", "see above", "gh", "x y", "-- --", "N/A", "TBD", "See Above", "none none"):
            with self.subTest(text=text):
                code, out, _ = self.check(f"Auth change merged (source: {text})\n")
                self.assertEqual(code, 1)
                self.assertIn("NO-SOURCE line 1 (merged): source is not a command or link", out)

    def test_a_live_marker_must_be_a_command_too(self):
        self.assertFlagged("Auth change merged (live: x)\n", "NO-SOURCE line 1 (merged): source is not a command or link")
        self.assertClean("Auth change merged (live: git log -1)\n")

    def test_commands_and_links_are_valid_sources(self):
        for text in ("gh pr view 741", "git log -1", "curl -s https://example.test/x", "https://example.test/x",
                     "http://example.test/x", "./check.sh --all", "a.b/c d", "gh pr view 741 x"):
            with self.subTest(text=text):
                self.assertClean(f"Auth change merged (source: {text})\n")

    def test_balanced_parentheses_inside_a_marker_parse(self):
        self.assertClean("Auth change merged (source: gh pr view (741) -> MERGED)\n")
        self.assertClean("Auth change merged (live: gh pr list --search (merged is:pr))\n")
        self.assertFlagged("Auth change merged (source: gh pr view (741) -> bus said)\n", "BUS-CLAIM line 1 (merged):")

    def test_a_negated_claim_is_still_a_claim(self):
        self.assertFlagged("PR #741 not merged\n", "NO-SOURCE line 1 (merged):")
        self.assertClean("PR #741 not merged (source: gh pr view 741)\n")

    def test_one_marker_covers_every_claim_before_it_back_to_the_previous_marker(self):
        self.assertClean("Merged and verified (source: gh pr view 741)\n")
        self.assertClean("Merged (source: gh pr view 741) and closed (live: gh issue view 5)\n")

    def test_claim_after_the_last_marker_is_uncovered(self):
        self.assertFlagged("Merged (source: gh pr view 741) closed\n", "NO-SOURCE line 1 (closed):")

    def test_clause_punctuation_ends_a_markers_cover(self):
        for sep in ("; ", ", ", ". ", "! ", "? "):
            with self.subTest(sep=sep):
                self.assertFlagged(f"Merged{sep}verified (source: gh pr view 741)\n", "NO-SOURCE line 1 (Merged):")

    def test_later_unrelated_source_does_not_cover_an_earlier_sentence(self):
        self.assertFlagged("backend said #741 merged. Branch has 3 commits (source: git log -3 -> abc)\n",
                           "NO-SOURCE line 1 (merged):")
        self.assertFlagged("Merged, then waited (source: gh pr view 741)\n", "NO-SOURCE line 1 (Merged):")

    def test_punctuation_inside_a_token_or_after_the_marker_does_not_split(self):
        self.assertClean("Merged v1.2 build (source: gh pr view 741)\n")
        self.assertFlagged("Merged.(source: gh pr view 741)\n", "NO-SOURCE line 1 (Merged):")
        self.assertClean("Merged (source: gh pr view 741), verified (live: gh run list).\n")

    def test_a_marker_of_another_claim_does_not_cover_an_earlier_one_past_a_marker(self):
        self.assertFlagged("Merged (as of 14:10) verified (source: gh pr view 741)\n", "NO-SOURCE line 1 (Merged):")

    def test_as_of_marker_is_not_a_source(self):
        self.assertFlagged("Auth change merged (as of 14:10)\n", "NO-SOURCE line 1 (merged):")

    def test_one_url_does_not_clear_two_claims(self):
        self.assertFlagged("Merged and closed https://example.test/pr/741\n", "NO-SOURCE line 1 (Merged):")

    def test_source_text_citing_the_bus_or_a_session_is_a_bus_claim(self):
        for cite in ("bus", "backend inbox", "backend said merged a1b2c3d", "lane reported", "told by qa", "per backend",
                     "according to backend", "backend says ok", "BUS line 4",
                     "ask the backend lane", "qa session output", "agent output", "channel log", "message from qa",
                     "gh pr view 741, per qa"):
            with self.subTest(cite=cite):
                self.assertFlagged(f"Auth change merged (source: {cite})\n", "BUS-CLAIM line 1 (merged):")

    def test_each_bus_cue_alone_is_a_bus_claim(self):
        for cue in ("ask", "session", "lane", "agent", "channel", "message", "inbox", "bus", "said", "says", "reported",
                    "told", "per qa", "according to qa"):
            with self.subTest(cue=cue):
                self.assertFlagged(f"Auth change merged (source: gh pr view 741 {cue})\n", "BUS-CLAIM line 1 (merged):")

    def test_a_cue_inside_a_longer_word_is_not_a_cue(self):
        self.assertClean("Auth change merged (source: gh pr view 741 task helper tell)\n")

    def test_source_text_that_only_resembles_a_cue_is_a_read(self):
        self.assertClean("Auth change merged (source: busybox ls; perl run; gh pr view 741 -> MERGED)\n")
        self.assertClean("Auth change merged (source: gh api repos/x/y/pulls/741 --jq .perk)\n")

    def test_live_marker_text_is_checked_for_bus_cues_too(self):
        self.assertFlagged("Auth change merged (live: cat bus/inbox/backend.txt)\n", "BUS-CLAIM line 1 (merged):")

    def test_forwarded_lines_in_any_form_are_no_source(self):
        for line in ("backend: #741 merged", "> backend: merged", "from backend: fixed a1b2c3d",
                     "according to qa, verified", "Per the bus: closed", "lane x reported passed"):
            with self.subTest(line=line):
                self.assertFlagged(line + "\n", "NO-SOURCE line 1")

    def test_own_work_verbs_are_not_claims(self):
        self.assertClean("I confirmed the plan and told the team\n")

    def test_fenced_blocks_are_skipped_across_lines(self):
        self.assertFlagged("```bash\nmerged\nverified\n```\nclosed\n", "NO-SOURCE line 5 (closed):")
        code, out, _ = self.check("```\nmerged\n```\nclosed\n")
        self.assertNotIn("line 2", out)
        self.assertNotIn("line 1", out)

    def test_the_fence_lines_themselves_are_skipped(self):
        self.assertClean("```merged\nx\n```closed\n")

    def test_an_unclosed_fence_is_a_finding_and_the_lines_after_it_are_checked(self):
        code, out, _ = self.check("```\nmerged\nverified\n")
        self.assertEqual(code, 1)
        self.assertIn("UNCLOSED-FENCE line 1", out)
        self.assertIn("NO-SOURCE line 2 (merged):", out)

    def test_unclosed_fence_is_not_reported_when_claims_are_off(self):
        self.assertClean("```\nmerged\n", "--no-claims")

    def test_a_self_closed_inline_triple_backtick_is_not_a_fence(self):
        code, out, _ = self.check("```x```\nclosed\n")
        self.assertEqual(code, 1)
        self.assertIn("NO-SOURCE line 2 (closed):", out)
        self.assertNotIn("UNCLOSED-FENCE", out)

    def test_triple_backticks_that_do_not_start_the_line_are_not_a_fence(self):
        code, out, _ = self.check("a ```\nmerged\n")
        self.assertEqual(code, 1)
        self.assertIn("NO-SOURCE line 2 (merged):", out)
        self.assertNotIn("UNCLOSED-FENCE", out)

    def test_a_fence_with_an_info_string_opens_and_closes(self):
        self.assertClean("```bash\nmerged\n```\n")

    def test_table_rows_are_still_checked_and_separators_are_harmless(self):
        self.assertFlagged("| PR | state |\n|----|:-----:|\n| 741 | merged |\n", "NO-SOURCE line 3 (merged):")

    def test_code_span_is_not_a_claim(self):
        self.assertClean("Run `gh pr merged` later\n")
        self.assertFlagged("Run `gh pr view` and merged\n", "NO-SOURCE line 1 (merged):")

    def test_claim_word_inside_a_valid_source_or_live_marker_is_not_a_claim(self):
        self.assertFlagged("State ok (as of 14:10, merged)\n", "NO-SOURCE line 1 (merged):")
        self.assertClean("State ok (source: gh pr list --state merged)\n")
        self.assertClean("State ok (live: gh pr list --state merged)\n")

    def test_claims_and_cues_inside_a_source_marker_are_judged_not_skipped(self):
        self.assertFlagged("Status (source: backend said #741 merged)\n", "BUS-CLAIM line 1 (merged):")
        self.assertFlagged("Status (live: backend said #741 merged)\n", "BUS-CLAIM line 1 (merged):")

    def test_a_claim_in_the_free_text_of_an_as_of_marker_is_a_claim(self):
        self.assertFlagged("(as of 14:05, backend: #741 merged)\n", "NO-SOURCE line 1 (merged):")
        self.assertFlagged("Quota fine (file modified 14:05, release verified)\n", "NO-SOURCE line 1 (verified):")

    def test_every_marker_is_validated_wherever_it_sits_even_without_a_claim(self):
        self.assertFlagged("Branch ok (source: x)\n", "NO-SOURCE line 1 (marker): source is not a command or link")
        self.assertFlagged("Branch ok (live: trust me)\n", "BUS-CLAIM line 1 (marker):")
        self.assertClean("Branch ok (source: gh pr view 741)\n")

    def test_an_invalid_marker_after_a_clean_claim_still_flags_the_line(self):
        self.assertFlagged("Merged (source: gh pr view 741); also ok (source: -)\n", "NO-SOURCE line 1 (marker):")

    def test_a_claim_touching_a_marker_is_judged_by_it(self):
        self.assertClean("Fixed(source: gh pr view 741)\n")
        self.assertFlagged("Fine (source: gh pr view 741)merged\n", "NO-SOURCE line 1 (merged):")

    def test_an_empty_marker_is_no_marker_at_all(self):
        self.assertClean("Branch ok (source: )\nBranch ok (live:   )\n")

    def test_a_marker_example_inside_a_code_span_is_not_validated(self):
        self.assertClean("Write `(source: x)` after the claim\n")

    def test_marker_cues_for_self_attestation_apply_to_source_and_live(self):
        for cue in ("confirmed", "confirms", "trust", "verified by", "checked by", "me", "we", "they"):
            for kind in ("source", "live"):
                with self.subTest(cue=cue, kind=kind):
                    self.assertFlagged(f"Auth change merged ({kind}: gh pr view 741 {cue})\n", "BUS-CLAIM line 1 (merged):")
        self.assertFlagged("Auth change merged (source: backend confirmed it)\n", "BUS-CLAIM line 1 (merged):")
        self.assertFlagged("Auth change merged (live: trust me)\n", "BUS-CLAIM line 1 (merged):")

    def test_self_attestation_cues_are_whole_words(self):
        self.assertClean("Auth change merged (source: gh pr view 741 mean weekly theme)\n")

    def test_unicode_clause_ends_break_a_markers_cover_without_a_space(self):
        for sep in ("\u3002", "\uff1b", "\uff0c", "\uff01", "\uff1f"):
            with self.subTest(sep=sep):
                self.assertFlagged(f"Merged{sep}verified (source: gh pr view 741)\n", "NO-SOURCE line 1 (Merged):")

    def test_format_characters_cannot_hide_a_claim_word(self):
        for word in ("Mer\u200bged", "Mer\u200dged", "\ufeffMerged", "Mer\u00adged", "Mer\u2060ged"):
            with self.subTest(word=word):
                self.assertFlagged(f"Auth change {word}\n", "NO-SOURCE line 1 (Merged):")
        self.assertClean("Mer\u200bged (source: gh pr view 741)\n")

    def test_nfkc_forms_of_a_claim_word_are_claims(self):
        self.assertFlagged("Auth change \uff4d\uff45\uff52\uff47\uff45\uff44\n", "NO-SOURCE line 1 (merged):")
        self.assertFlagged("Auth change \ufb01xed\n", "NO-SOURCE line 1 (fixed):")
        self.assertClean("Auth change merged \uff08source\uff1a gh pr view 741\uff09\n")

    def test_homoglyphs_beyond_nfkc_are_out_of_scope(self):
        self.assertClean("Auth change m\u0435rged\n")  # Cyrillic e: a known limit, see the docstring

    def test_no_claims_turns_the_claim_rules_off_only(self):
        self.assertClean("#741 merged\nPer backend, fixed a1b2c3d\n", "--no-claims")
        self.assertFlagged("Quota 98% merged\n", "NO-MARKER line 1", args=("--no-claims",))

    def test_claim_words_override_replaces_the_default_list(self):
        self.assertFlagged("Build rolled out\n", "NO-SOURCE line 1 (rolled out):", args=("--claim-words", "rolled out"))
        self.assertClean("#741 merged\n", "--claim-words", "shipped")
        self.assertFlagged("Shipped it\n", "NO-SOURCE line 1 (Shipped):", args=("--claim-words", "shipped"))

    def test_empty_claim_words_is_a_usage_error(self):
        self.assertEqual(self.check("x\n", "--claim-words", " , ")[0], 2)

    def test_stale_marker_and_claim_report_both(self):
        self.assertFlagged("#741 merged (as of 2026-11-20 12:00 +03:00)\n", "STALE line 1", "NO-SOURCE line 1 (merged):")

    def test_reading_and_claim_on_one_line_report_both(self):
        self.assertFlagged("Quota 98% merged\n", "NO-MARKER line 1 (Quota)", "NO-SOURCE line 1 (merged)")
        self.assertClean("Quota 98% (as of 14:10); merged (source: gh pr view 741)\n")

    def test_findings_carry_their_own_line_number(self):
        self.assertFlagged("ok line\n\nsecond #5 merged\n", "NO-SOURCE line 3 (merged):")

    def test_long_lines_stay_too_long_and_are_not_claim_checked(self):
        code, out, _ = self.check("merged " + "x" * 4000 + "\n")
        self.assertEqual(code, 1)
        self.assertIn("TOO-LONG line 1", out)
        self.assertNotIn("NO-SOURCE", out)
        self.assertEqual(self.check("merged (source: gh pr view 7) " + "x" * 3900 + "\n")[0], 0)

    def test_hostile_repetition_is_linear(self):
        started = time.monotonic()
        self.check(("merged " * 300 + "(source: " * 100 + "\n") * 50)
        self.assertLess(time.monotonic() - started, 5)


if __name__ == "__main__":
    unittest.main()
