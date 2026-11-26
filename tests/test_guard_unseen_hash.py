"""unseen-hash: a commit hash in outbound text must have been printed by a tool in this session (lesson G014)."""
import itertools
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "hooks" / "guard.py"

sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPT.parent))
import guard_lessons  # noqa: E402
import guard_unseen_hash as unseen_hash  # noqa: E402

FULL = "3f9a1c27b8e04d5a9c6b1e2f7a8d9c0b1e2f3a4b"  # a 40-character commit id
SHORT = FULL[:7]
OTHER = "a1b2c3d4e5"


def tool_use(tool_id, name, tool_input):
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}]}}


def tool_result(tool_id, content, is_error=False):
    return {"type": "user", "message": {"role": "user", "content": [
        {"tool_use_id": tool_id, "type": "tool_result", "content": content, "is_error": is_error}]}}


def assistant_text(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def user_text(text, **fields):
    return {"type": "user", "message": {"role": "user", "content": text}, **fields}


def prompt(text, **fields):
    """A prompt the person typed, as Claude Code marks it."""
    return user_text(text, origin={"kind": "human"}, **fields)


class TranscriptCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.transcript = self.dir / "session.jsonl"

    def write(self, *entries, raw=""):
        self.transcript.write_text(raw + "".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
        return str(self.transcript)

    def unseen(self, text, *entries, **kwargs):
        return unseen_hash.unseen([text], self.write(*entries), **kwargs)


class WhatIsAHashTests(unittest.TestCase):
    def test_a_hash_needs_a_digit_and_a_letter(self):
        self.assertEqual(unseen_hash.hashes([f"merged {SHORT} and {FULL}"]), [SHORT, FULL])
        self.assertEqual(unseen_hash.hashes(["deadbeef cafebabe 20261123 1234567"]), [])  # words, dates, numbers

    def test_only_lowercase_tokens_are_hashes_and_repeats_are_dropped(self):
        # git and gh print hashes in lowercase; an uppercase hex id such as a disk label in a path is not one
        self.assertEqual(unseen_hash.hashes([SHORT.upper(), SHORT, "x " + SHORT]), [SHORT])
        self.assertEqual(unseen_hash.hashes(["/media/0A1B2C3D4E5F6789/repo", "A1B2C3D", "a1B2c3d4e"]), [])

    def test_too_short_too_long_and_glued_tokens_are_not_hashes(self):
        sha256 = "ab12" * 16
        self.assertEqual(unseen_hash.hashes(["a1b2c3", sha256, FULL + "0", f"v{SHORT}", f"{SHORT}x", "0x7fff5fbff",
                                             f"id_{SHORT}"]), [])

    def test_uuid_segments_are_not_hashes(self):
        self.assertEqual(unseen_hash.hashes(["run 123e4567-e89b-12d3-a456-426614174000 done"]), [])
        self.assertEqual(unseen_hash.hashes([f"{SHORT}-fix"]), [SHORT])  # a dash alone does not make a UUID

    def test_a_hash_in_a_url_is_checked(self):
        self.assertEqual(unseen_hash.hashes([f"https://example.com/o/r/commit/{FULL}"]), [FULL])

    def test_a_hash_followed_by_a_line_anchor_is_checked(self):
        self.assertEqual(unseen_hash.hashes([f"see {SHORT}#L10"]), [SHORT])  # only a `#` before it exempts it

    def test_a_css_color_is_not_a_hash(self):
        self.assertEqual(unseen_hash.hashes(["color #1a2b3c4d and #1A2B3C4"]), [])

    def test_known_words_and_binary_literals_are_not_hashes(self):
        self.assertEqual(unseen_hash.hashes(["use ED25519 keys, mask 0b10101, 0B1100110"]), [])
        self.assertEqual(unseen_hash.hashes(["0b10102 0b1a1b1c1"]), ["0b10102", "0b1a1b1c1"])  # not binary

    def test_the_allow_list_drops_its_words_in_any_case(self):
        self.assertEqual(unseen_hash.hashes([f"ff00ff00 1e10000 {SHORT}"], allow=["FF00FF00"]), ["1e10000", SHORT])
        self.assertEqual(unseen_hash.hashes(["ff00ff00"], allow=None), ["ff00ff00"])

    def test_at_most_the_first_16_distinct_hashes(self):
        # each distinct 7-character prefix costs one search of the window (about 10 ms for 16 MB): 16 fit 0.2 s
        many = [f"{n:07d}a" for n in range(20)]
        self.assertEqual(unseen_hash.hashes([" ".join(many)]), many[:16])

    def test_the_refusal_names_three_then_counts(self):
        self.assertEqual(unseen_hash.named(["a1", "b2"]), "a1, b2")
        self.assertEqual(unseen_hash.named(["a1", "b2", "c3", "d4", "e5"]), "a1, b2, c3 and 2 more")


class SeenTests(TranscriptCase):
    def test_a_hash_a_tool_printed_passes(self):
        log = tool_result("toolu_1", f"commit {FULL}\nAuthor: x")
        self.assertEqual(self.unseen(f"Merged {FULL}", tool_use("toolu_1", "Bash", {"command": "git log -1"}), log),
                         [])

    def test_a_hash_only_the_assistant_wrote_is_refused(self):
        self.assertEqual(self.unseen(f"Merged {SHORT}", assistant_text(f"I merged {SHORT}")), [SHORT])

    def test_a_hash_only_in_a_tool_input_is_refused(self):
        entries = (tool_use("toolu_1", "Bash", {"command": f"echo-nothing {SHORT}"}), tool_result("toolu_1", "ok"))
        self.assertEqual(self.unseen(f"Merged {SHORT}", *entries), [SHORT])

    def test_a_short_form_of_a_printed_full_hash_passes(self):
        self.assertEqual(self.unseen(f"Merged {SHORT}", tool_result("toolu_1", FULL)), [])
        self.assertEqual(self.unseen(f"Merged {SHORT}", tool_result("toolu_1", FULL.upper())), [])  # printed: any case

    def test_a_full_hash_when_only_its_short_form_was_printed_is_refused(self):
        self.assertEqual(self.unseen(f"Merged {FULL}", tool_result("toolu_1", f"{SHORT} fix: x")), [FULL])

    def test_a_hash_inside_a_longer_printed_word_counts_from_its_hex_start(self):
        self.assertEqual(self.unseen(f"see {SHORT}", tool_result("toolu_1", f"v1.2-3-g{SHORT}")), [])
        self.assertEqual(self.unseen(f"see {SHORT}", tool_result("toolu_1", f"0{SHORT}")), [SHORT])  # not a prefix

    def test_only_the_unseen_hashes_are_returned(self):
        self.assertEqual(self.unseen(f"{SHORT} and {OTHER}", tool_result("toolu_1", FULL)), [OTHER])

    def test_every_unseen_hash_is_returned_in_order(self):
        self.assertEqual(self.unseen(f"{OTHER} {SHORT} b2c3d4e5f6", tool_result("toolu_1", FULL)),
                         [OTHER, "b2c3d4e5f6"])

    def test_a_dashless_uuid_counts_when_its_dashed_form_was_printed(self):
        dashed = "1a2b3c4d-5e6f-47a8-b9c0-d1e2f3a4b5c6"
        printed = tool_result("toolu_1", f"id: {dashed.upper()}")
        bare = dashed.replace("-", "")
        self.assertEqual(self.unseen(f"page {bare} and {bare[:12]}", printed), [])
        self.assertEqual(self.unseen(f"page {bare}", tool_result("toolu_1", "id: 1a2b3c4d")), [bare])
        self.assertEqual(self.unseen(f"page {bare}", assistant_text(dashed)), [bare])

    def test_a_result_in_text_blocks_counts(self):
        self.assertEqual(self.unseen(SHORT, tool_result("toolu_1", [{"type": "text", "text": FULL}])), [])

    def test_every_tool_result_counts(self):
        for name in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Agent", "Task", "mcp__x__get"):
            entries = (tool_use("toolu_9", name, {"x": "y"}), tool_result("toolu_9", f"line 1 {FULL}"))
            self.assertEqual(self.unseen(SHORT, *entries), [], name)

    def test_a_result_whose_tool_use_is_outside_the_window_counts(self):
        self.assertEqual(self.unseen(SHORT, tool_result("toolu_gone", FULL)), [])

    def test_this_rules_own_refusal_does_not_count(self):
        refusal = f"arsenal lesson guard G014 (unseen-hash): Commit hash {SHORT} appears in no tool output"
        self.assertEqual(self.unseen(SHORT, tool_result("toolu_1", refusal, is_error=True)), [SHORT])

    def test_the_users_shell_output_counts(self):
        self.assertEqual(self.unseen(SHORT, user_text(f"<bash-stdout>{FULL}</bash-stdout><bash-stderr></bash-stderr>")),
                         [])
        fake = {"type": "assistant", "message": {"content": f"<bash-stdout>{FULL}</bash-stdout>"}}
        self.assertEqual(self.unseen(SHORT, fake), [SHORT])  # the assistant cannot fake shell output

    def test_a_hash_the_person_typed_counts(self):
        self.assertEqual(self.unseen(f"Revert {SHORT}", prompt(f"please revert {SHORT}")), [])
        typed = prompt([{"type": "text", "text": f"comment on {FULL}"}, {"type": "image", "source": {}}])
        self.assertEqual(self.unseen(SHORT, typed), [])

    def test_any_user_text_the_assistant_did_not_write_counts(self):
        for entry in (user_text(f"please mention {FULL}"),  # no origin
                      user_text(f"<task-notification>{FULL}</task-notification>",
                                origin={"kind": "task-notification"}),
                      user_text(f"Another session says {FULL}", origin={"kind": "peer"}),
                      user_text(f"Your task: report on {FULL}", isSidechain=True),  # a subagent's brief
                      user_text([{"type": "text", "text": f"peer message: {FULL}"}]),
                      prompt(f"skill text {FULL}", isMeta=True)):
            self.assertEqual(self.unseen(SHORT, entry), [], entry)

    def test_a_subagents_brief_counts_in_its_own_transcript(self):
        session = self.write()
        agent = self.dir / "session" / "subagents" / "agent-a1.jsonl"
        agent.parent.mkdir(parents=True)
        agent.write_text(json.dumps(user_text(f"Check commit {FULL} and report", isSidechain=True)) + "\n",
                         encoding="utf-8")
        self.assertEqual(unseen_hash.unseen([SHORT], session, agent_id="a1"), [])

    def test_what_the_assistant_wrote_never_counts(self):
        thinking = {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": f"it was {FULL}"}]}}
        request = {"type": "api-request-blob", "content": f"tool_use git show {FULL}", "messages": [FULL]}
        for entry in (assistant_text(FULL), thinking, tool_use("toolu_1", "Bash", {"command": f"git show {FULL}"}),
                      request, prompt(f"summary {FULL}", isCompactSummary=True)):  # the model wrote the summary
            self.assertEqual(self.unseen(SHORT, entry), [SHORT], entry)

    def test_a_git_or_gh_error_that_echoes_a_hash_does_not_count(self):
        for error in (f"fatal: ambiguous argument '{SHORT}': unknown revision or path not in the working tree.",
                      f"fatal: bad object {SHORT}", f"fatal: Not a valid object name {SHORT}",
                      f"error: pathspec '{SHORT}' did not match any file(s) known to git",
                      f"fatal: bad revision '{SHORT}'", f"GraphQL: No commit found for SHA: {SHORT}",
                      f"fatal: could not parse object '{SHORT}'"):
            self.assertEqual(self.unseen(SHORT, tool_result("toolu_1", f"Exit code 128\n{error}", is_error=True)),
                             [SHORT], error)
        mixed = f"fatal: bad object {OTHER}\ncommit {FULL}"  # another line of the same result still counts
        self.assertEqual(self.unseen(f"{SHORT} {OTHER}", tool_result("toolu_1", mixed, is_error=True)), [OTHER])
        for error in (f"gh: No commit found for SHA: {SHORT} (HTTP 422)",
                      f'{{"message":"No commit found for SHA: {SHORT}","status":"422"}}',
                      f"error: malformed object name {SHORT}"):
            self.assertEqual(self.unseen(SHORT, tool_result("toolu_1", error, is_error=True)), [SHORT], error)

    def test_a_hash_git_echoes_before_rejecting_it_does_not_count(self):
        echoed = f"{SHORT}\nfatal: ambiguous argument '{SHORT}': unknown revision or path not in the working tree."
        self.assertEqual(self.unseen(SHORT, tool_result("toolu_1", echoed, is_error=True)), [SHORT])

    def test_a_rejection_phrase_in_a_commit_subject_does_not_hide_the_hash(self):
        oneline = f"{SHORT} fix: could not resolve module path\n{OTHER} docs: not a commit message"
        self.assertEqual(self.unseen(f"{SHORT} {OTHER}", tool_result("toolu_1", oneline)), [])
        blob = json.dumps([{"oid": FULL, "messageHeadline": "handle unknown revision in parser"}])
        self.assertEqual(self.unseen(SHORT, tool_result("toolu_1", blob)), [])

    def test_a_subject_with_this_rules_scope_still_counts(self):
        log = f"{OTHER} feat(unseen-hash): add rule\n{FULL} fix: other"
        self.assertEqual(self.unseen(f"{SHORT} {OTHER}", tool_result("toolu_1", log)), [])
        refusal = f"x\narsenal lesson guard unseen-hash (unseen-hash): Commit hash {SHORT} appears in no tool output"
        self.assertEqual(self.unseen(f"{SHORT} {OTHER}", tool_result("toolu_1", f"{OTHER}\n{refusal}")), [SHORT])

    def test_queued_messages_count(self):
        def queued(prompt_value, kind="human", **fields):
            return {"type": "attachment", "attachment": {"type": "queued_command", "prompt": prompt_value,
                                                         "origin": {"kind": kind}}, **fields}
        enqueued = {"type": "queue-operation", "operation": "enqueue", "content": f"peer: merged {FULL}"}
        for entry in (queued(f"revert {SHORT}"), queued([{"type": "text", "text": f"see {FULL}"}]),
                      queued(f"revert {SHORT}", kind="peer"), queued(f"done {SHORT}", kind="task-notification"),
                      queued(f"brief {SHORT}", isSidechain=True), enqueued,
                      {"type": "attachment", "attachment": {"type": "file", "content": SHORT}}):
            self.assertEqual(self.unseen(SHORT, entry), [], entry)
        for entry in (queued(None), queued([None, {"type": "text"}]), {"type": "attachment", "attachment": "x"},
                      {"type": "queue-operation", "operation": "dequeue"}):
            self.assertEqual(self.unseen(SHORT, entry), [SHORT], entry)

    def test_each_prefix_is_searched_once_and_each_line_parsed_once(self):
        tokens = [SHORT + "1a", SHORT + "2b", SHORT + "3c"]  # three hashes that share their first 7 characters
        path = self.write(assistant_text(" ".join(tokens)), tool_result("toolu_1", " ".join(tokens)))
        finds = []

        class Counted(bytes):
            def rfind(self, sub, *args):
                if sub != b"\n":
                    finds.append(sub)
                return bytes.rfind(self, sub, *args)

        with mock.patch.object(unseen_hash, "read_tail", lambda name, size: Counted(Path(name).read_bytes().lower())), \
                mock.patch.object(unseen_hash.json, "loads", wraps=json.loads) as loads:
            self.assertEqual(unseen_hash.unseen([" ".join(tokens + [OTHER])], path), [OTHER])
        # one absence search per prefix (OTHER is printed nowhere, so it is judged with no parse), then SHORT from
        # the newest line: the result that shows all three, so the older assistant line is never parsed
        self.assertEqual(finds, [SHORT.encode(), OTHER[:7].encode(), SHORT.encode()])
        self.assertEqual(loads.call_count, 1)

    def test_a_line_parsed_for_one_prefix_is_not_parsed_again_for_another(self):
        near = OTHER[:7] + "ff"  # shares OTHER's prefix but is not OTHER, so OTHER's search reaches this line too
        path = self.write(tool_result("toolu_1", OTHER), tool_result("toolu_2", f"{FULL} {near}"))
        with mock.patch.object(unseen_hash.json, "loads", wraps=json.loads) as loads:
            self.assertEqual(unseen_hash.unseen([f"{SHORT} {OTHER}"], path), [])
        self.assertEqual(loads.call_count, 2)  # the newest line once (for SHORT), then the older one for OTHER

    def test_a_token_resumes_where_an_earlier_one_with_its_prefix_stopped(self):
        first, second = SHORT + "1a", SHORT + "2b"
        path = self.write(tool_result("toolu_1", first), assistant_text(second), tool_result("toolu_2", second))
        self.assertEqual(unseen_hash.unseen([f"{first} {second}"], path), [])
        path = self.write(tool_result("toolu_1", first), assistant_text(second))
        self.assertEqual(unseen_hash.unseen([f"{first} {second}"], path), [second])
        path = self.write(assistant_text(second), tool_result("toolu_1", first), assistant_text(first))
        self.assertEqual(unseen_hash.unseen([f"{first} {second}"], path), [second])  # older lines are still read

    def test_broken_lines_are_skipped(self):
        path = self.write(tool_result("toolu_1", FULL), raw=f'{{"type": "user", "cut {SHORT}\n[1, 2]\n')
        self.assertEqual(unseen_hash.unseen([SHORT], path), [])
        path = self.write(raw=f'{{"type": "user", "cut {SHORT}\n"{SHORT}"\n')
        self.assertEqual(unseen_hash.unseen([SHORT], path), [SHORT])

    def test_odd_shapes_never_raise(self):
        odd = [{"type": "user", "message": "text"}, {"type": "user", "message": {"content": [1, "x", None]}},
               {"type": "user", "message": {"content": [{"type": "tool_result", "content": 5}]}},
               {"type": "user", "message": {"content": [{"type": "tool_result", "content": {"a": SHORT}}]}}]
        self.assertEqual(self.unseen(SHORT, *odd), [SHORT])

    def test_the_window_reads_only_the_newest_part(self):
        old = tool_result("toolu_1", FULL)
        filler = assistant_text("x" * (1024 * 1024 + 10))
        path = self.write(old, filler)
        self.assertEqual(unseen_hash.unseen([SHORT], path, window_mb=1), [SHORT])
        self.assertEqual(unseen_hash.unseen([SHORT], path, window_mb=2), [])
        self.assertEqual(unseen_hash.unseen([SHORT], path), [])  # 16 MB by default

    def test_an_invalid_window_falls_back_to_the_default(self):
        self.assertEqual(unseen_hash.window_bytes(True), 16 * 1024 * 1024)
        self.assertEqual(unseen_hash.window_bytes(0), 16 * 1024 * 1024)
        self.assertEqual(unseen_hash.window_bytes("2"), 16 * 1024 * 1024)
        self.assertEqual(unseen_hash.window_bytes(0.5), 512 * 1024)
        self.assertEqual(unseen_hash.window_bytes(2), 2 * 1024 * 1024)
        # above the cap: 16 searches of a larger window and its read do not fit the 0.2 s budget
        self.assertEqual(unseen_hash.window_bytes(32), 16 * 1024 * 1024)
        self.assertEqual(unseen_hash.window_bytes(64), 16 * 1024 * 1024)


class FailOpenTests(TranscriptCase):
    def test_no_hash_reads_nothing(self):
        with mock.patch.object(unseen_hash, "read_tail", side_effect=AssertionError("read")):
            self.assertEqual(unseen_hash.unseen(["no hashes here"], "/nonexistent"), [])

    def test_a_missing_or_absent_transcript_passes(self):
        for path in (None, "", 5, str(self.dir / "missing.jsonl")):
            self.assertEqual(unseen_hash.unseen([SHORT], path), [], path)

    def test_a_transcript_that_is_not_a_regular_file_passes(self):
        self.assertEqual(unseen_hash.unseen([SHORT], str(self.dir)), [])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFOs on this platform")
    def test_a_fifo_transcript_passes_without_blocking(self):
        fifo = self.dir / "pipe.jsonl"
        os.mkfifo(fifo)
        result = []
        worker = threading.Thread(target=lambda: result.append(unseen_hash.unseen([SHORT], str(fifo))), daemon=True)
        worker.start()
        worker.join(5)  # open() on a FIFO with no writer blocks for ever
        self.assertEqual(result, [[]])

    def test_an_unreadable_transcript_passes(self):
        path = self.write(assistant_text(SHORT))
        with mock.patch("builtins.open", side_effect=PermissionError("denied")):
            self.assertEqual(unseen_hash.unseen([SHORT], path), [])

    def test_a_slow_check_passes(self):
        path = self.write(tool_result("toolu_1", "nothing"), assistant_text(SHORT))
        ticks = iter(range(0, 100, 1))
        self.assertEqual(unseen_hash.unseen([SHORT], path, clock=lambda: next(ticks), budget=0.5), [])
        ticks = iter(range(0, 100, 1))
        self.assertEqual(unseen_hash.unseen([SHORT], path, clock=lambda: next(ticks), budget=50), [SHORT])

    def test_the_default_budget_is_a_fifth_of_a_second(self):
        path = self.write(tool_result("toolu_1", "nothing"))
        # the deadline read, then one absence search: in time at 0.19 s, late at 0.21 s
        for step, expected in ((0.19, [SHORT]), (0.21, [])):
            ticks = itertools.count(0, step)
            self.assertEqual(unseen_hash.unseen([SHORT], path, clock=lambda: next(ticks)), expected, step)

    def test_hashes_judged_before_the_budget_ran_out_are_still_refused(self):
        path = self.write(tool_result("toolu_1", f"nothing {FULL[:9]}"), tool_result("toolu_2", "9e8d7c6"))
        # the deadline read, then two absence searches in time; the third search and everything after are late
        clock = mock.Mock(side_effect=itertools.chain([0, 0, 0], itertools.repeat(10)))
        self.assertEqual(unseen_hash.unseen([f"{OTHER} 0f1e2d3c {FULL}"], path, clock=clock, budget=1),
                         [OTHER, "0f1e2d3c"])
        # three absence searches (only OTHER is absent), then FULL: its line parsed, nothing older; 9e8d7c6b is late
        clock = mock.Mock(side_effect=itertools.chain([0] * 7, itertools.repeat(10)))
        self.assertEqual(unseen_hash.unseen([f"{FULL} {OTHER} 9e8d7c6b"], path, clock=clock, budget=1),
                         [FULL, OTHER])
        clock = mock.Mock(return_value=0)  # with time to spare the third is judged too
        self.assertEqual(unseen_hash.unseen([f"{FULL} {OTHER} 9e8d7c6b"], path, clock=clock, budget=1),
                         [FULL, OTHER, "9e8d7c6b"])

    def test_a_hash_after_real_ones_is_judged_before_the_real_ones_spend_the_budget(self):
        real = [f"{index}a{index}b{index}c{index}d" for index in range(1, 8)]
        fake = "0f1e2d3c"  # printed nowhere
        talk = [assistant_text(" ".join(real)) for _ in range(20)]  # older lines that only quote them
        path = self.write(*talk, *(tool_result(f"toolu_{index}", token) for index, token in enumerate(real)))
        ticks = itertools.count()  # every clock read costs one unit: 50 reads in all
        self.assertEqual(unseen_hash.unseen([" ".join(real + [fake])], path, clock=lambda: next(ticks), budget=50),
                         [fake])
        ticks = itertools.count()
        self.assertEqual(unseen_hash.unseen([" ".join(real)], path, clock=lambda: next(ticks), budget=50), [])

    def test_an_unexpected_error_passes(self):
        path = self.write(assistant_text(SHORT))
        with mock.patch.object(unseen_hash.Transcript, "seen", side_effect=RuntimeError("bug")):
            self.assertEqual(unseen_hash.unseen([SHORT], path), [])

    def test_an_empty_transcript_refuses(self):
        self.assertEqual(unseen_hash.unseen([SHORT], self.write()), [SHORT])


class SubagentTests(TranscriptCase):
    """Inside a subagent the hook names the session transcript; the agent's own results are in a file beside it."""

    def agent_file(self, agent_id, *parts):
        path = self.dir.joinpath("session", "subagents", *parts, f"agent-{agent_id}.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tool_result("toolu_1", FULL)) + "\n", encoding="utf-8")
        return path

    def test_the_subagents_own_results_are_read(self):
        session = self.write(tool_result("toolu_1", OTHER))
        self.agent_file("a1f2")
        self.assertEqual(unseen_hash.unseen([SHORT], session, agent_id="a1f2"), [])
        self.assertEqual(unseen_hash.unseen([OTHER], session, agent_id="a1f2"), [OTHER])  # not the parent's results
        for main_session in (None, ""):
            self.assertEqual(unseen_hash.unseen([SHORT], session, agent_id=main_session), [SHORT])

    def test_a_workflow_agent_is_found_one_folder_deeper(self):
        session = self.write()
        self.agent_file("b2", "workflows", "wf_1")
        self.assertEqual(unseen_hash.unseen([SHORT], session, agent_id="b2"), [])
        self.assertEqual(unseen_hash.unseen([OTHER], session, agent_id="b2"), [OTHER])

    def test_a_hook_that_names_the_agents_own_file_is_read_as_is(self):
        agent = str(self.agent_file("c3"))
        self.assertEqual(unseen_hash.unseen([SHORT], agent, agent_id="c3"), [])
        self.assertEqual(unseen_hash.unseen([OTHER], agent, agent_id="c3"), [OTHER])

    def test_an_agent_without_a_transcript_passes(self):
        session = self.write()
        self.agent_file("b2", "workflows", "wf_1")
        for agent_id in ("missing", "../session", "a/b", 7):
            self.assertEqual(unseen_hash.unseen([OTHER], session, agent_id=agent_id), [], agent_id)

    def test_the_search_is_bounded(self):
        session = self.write()
        self.agent_file("deep", "workflows", "wf_1", "nested")  # deeper than Claude Code writes
        self.assertEqual(unseen_hash.unseen([OTHER], session, agent_id="deep"), [])
        self.agent_file("late", "workflows", "wf_2")
        with mock.patch.object(unseen_hash, "MAX_AGENT_DIRS", 0):  # no run folder is searched
            self.assertEqual(unseen_hash.unseen([OTHER], session, agent_id="late"), [])
        self.assertEqual(unseen_hash.unseen([OTHER], session, agent_id="late"), [OTHER])


class RuleCase(TranscriptCase):
    """A project with its own registry, no global one, and a transcript where only OTHER was printed."""

    def setUp(self):
        super().setUp()
        self.project = self.dir / "project"
        self.project.mkdir()
        env = {"LESSONS_GUARDS_GLOBAL_FILE": str(self.dir / "home" / "lesson-guards.json"),
               "LESSONS_GUARD_HITS_FILE": str(self.dir / "home" / "hits.jsonl")}
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.path = self.write(assistant_text(f"merged {SHORT}"), tool_result("toolu_1", OTHER))

    def registry(self, *guards):
        path = self.project / ".agents" / "lesson-guards.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"guards": list(guards)}), encoding="utf-8")


class RuleTests(RuleCase):
    """The rule inside guard_lessons: off by default, its registry keys, Bash and MCP text."""

    def judge(self, command, transcript=None):
        return guard_lessons.judge(command, str(self.project), transcript=transcript or self.path)

    def test_off_until_a_registry_entry_names_it(self):
        self.assertIsNone(self.judge(f'gh pr comment 5 -b "merged {SHORT}"'))

    def test_a_message_with_an_unseen_hash_is_refused_with_what_to_do(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        hit = self.judge(f'gh pr comment 5 -b "merged {SHORT}, {OTHER}"')
        self.assertEqual((hit.lesson, hit.rule), ("G014", "unseen-hash"))
        self.assertIn(SHORT, hit.reason)
        self.assertNotIn(OTHER, hit.reason)
        self.assertIn("git log -1 --format=%H", hit.reason)
        self.assertIn("gh pr view N --json mergeCommit", hit.reason)
        self.assertIn("never from memory", hit.reason)

    def test_commit_messages_and_heredocs_are_judged(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        self.assertEqual(self.judge(f'git commit -m "Revert {SHORT}"').rule, "unseen-hash")
        self.assertEqual(self.judge(f"git commit -F - <<'EOF'\nRevert {SHORT}\nEOF").rule, "unseen-hash")

    def test_only_the_message_of_a_git_commit_or_tag_is_judged(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        for command in (f"git tag --contains {SHORT}", f"git commit --fixup={SHORT}", f"git commit --squash {SHORT}",
                        f"git commit -C {SHORT}", f"git commit --reuse-message={SHORT}", f"git commit -c {SHORT}",
                        f"git tag -a v1.0 {SHORT} -m release", f"git log --grep tag {SHORT}",
                        f"git -C repo tag v1 {SHORT}"):
            self.assertIsNone(self.judge(command), command)
        for command in (f'git commit -am "Revert {SHORT}"', f'git commit -m"Revert {SHORT}"',
                        f'git commit --message="Revert {SHORT}"', f'git commit --message "Revert {SHORT}"',
                        f'git tag -a v1 {OTHER} -m "tag {SHORT}"', f'git -C repo commit -m "x {SHORT}"',
                        f'git -c user.name=x commit -m "x {SHORT}"', f'git commit -sam"x {SHORT}"'):
            self.assertEqual(getattr(self.judge(command), "rule", None), "unseen-hash", command)

    def test_gh_operands_github_checks_are_not_judged(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        for command in (f"gh pr merge 5 --match-head-commit {SHORT}", f"gh pr merge 5 --match-head-commit={SHORT}",
                        f"gh release create v1 --target {SHORT}", f"gh release create v1 --target={SHORT} -n notes"):
            self.assertIsNone(self.judge(command), command)
        for command in (f'gh pr merge 5 --match-head-commit {OTHER} -b "merged {SHORT}"',
                        f'gh release create v1 --target {OTHER} --notes "fixes {SHORT}"'):
            self.assertEqual(getattr(self.judge(command), "rule", None), "unseen-hash", command)

    def test_the_calendar_rule_still_reads_every_git_argument(self):
        self.registry({"rule": "calendar", "lesson": "G9"})
        with mock.patch.dict(os.environ, {"ARSENAL_NOW": "2026-11-23"}):
            self.assertEqual(self.judge('git tag -a v1 -F notes "Wed 11-26"').rule, "calendar")

    def test_seen_hashes_plain_commands_and_no_transcript_pass(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        self.assertIsNone(self.judge(f'gh pr comment 5 -b "merged {OTHER}"'))
        self.assertIsNone(self.judge(f"git show {SHORT}"))  # not outbound
        self.assertIsNone(guard_lessons.judge(f'gh pr comment 5 -b "merged {SHORT}"', str(self.project)))

    def test_the_entrys_programs_and_window_apply(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014", "programs": ["send.sh"], "window_mb": 1})
        self.assertEqual(self.judge(f'./send.sh pm "done at {SHORT}"').rule, "unseen-hash")
        self.assertIsNone(self.judge(f'./other.sh pm "done at {SHORT}"'))

    def test_a_reason_of_its_own_replaces_the_built_in_one(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014", "reason": "Copy hashes from git."})
        self.assertEqual(self.judge(f'gh pr comment 5 -b "{SHORT}"').reason, "Copy hashes from git.")

    def test_outbound_mcp_tools_are_judged(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        hit = guard_lessons.judge_outbound("mcp__chat__send_message", {"text": f"merged {SHORT}"}, str(self.project),
                                           self.path)
        self.assertEqual(hit.rule, "unseen-hash")
        self.assertIsNone(guard_lessons.judge_outbound("Write", {"content": SHORT}, str(self.project), self.path))
        self.assertIsNone(guard_lessons.judge_outbound("mcp__chat__send_message", {"text": SHORT}, str(self.project)))

    def test_id_fields_of_an_mcp_input_are_not_judged(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        # the ids appear nowhere in the transcript: they pass only because id fields are skipped
        for tool_name, tool_input in (
                ("mcp__mail__reply", {"message_id": "18c2f4a9b1e3d5f7", "body": "Thanks, done."}),
                ("mcp__mail__reply", {"message-id": "18c2f4a9b1e3d5f7", "body": "Thanks, done."}),
                ("mcp__mail__reply", {"thread_id": "27d3a5b0c2f4e6a8", "body": "Thanks, done."}),
                ("mcp__mail__reply", {"threadId": "27d3a5b0c2f4e6a8", "body": "Thanks, done."}),
                ("mcp__tasks__update_task", {"task_id": "86c1f2a3b", "status": "done"}),
                ("mcp__tasks__update_task", {"id": "86c1f2a3b", "taskIds": ["86c1f2a3c"], "ID": "86c1f2a3d"})):
            self.assertIsNone(guard_lessons.judge_outbound(tool_name, tool_input, str(self.project), self.path),
                              tool_input)
        hit = guard_lessons.judge_outbound("mcp__mail__reply", {"message_id": "18c2f4a9b1e3d5f7",
                                                                "body": f"Fixed in {SHORT}."}, str(self.project),
                                           self.path)
        self.assertEqual(hit.rule, "unseen-hash")
        self.assertIn(SHORT, hit.reason)
        self.assertNotIn("18c2f4a9b1e3d5f7", hit.reason)
        for key in ("paid", "valid", "android"):  # words that end in "id" are text, not ids
            hit = guard_lessons.judge_outbound("mcp__chat__send_message", {key: SHORT}, str(self.project), self.path)
            self.assertEqual(getattr(hit, "rule", None), "unseen-hash", key)

    def test_the_message_of_a_send_message_call_is_judged(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        hit = guard_lessons.judge_outbound("SendMessage", {"to": "pm", "message": f"merged {SHORT}"},
                                           str(self.project), self.path)
        self.assertEqual(getattr(hit, "rule", None), "unseen-hash")
        for tool_input in ({"to": "pm", "message": f"merged {OTHER}"},
                           {"to": f"worker [{SHORT}]", "summary": f"about {SHORT}", "message": "done"},
                           {"to": "lead", "message": {"type": "shutdown_response", "request_id": SHORT,
                                                      "approve": True}},
                           {"to": "pm"}, "not a dict"):
            self.assertIsNone(guard_lessons.judge_outbound("SendMessage", tool_input, str(self.project), self.path),
                              tool_input)

    def test_the_calendar_rule_reads_a_send_message_call_too(self):
        self.registry({"rule": "calendar", "lesson": "G9"})
        with mock.patch.dict(os.environ, {"ARSENAL_NOW": "2026-11-23"}):
            hit = guard_lessons.judge_outbound("SendMessage", {"to": "pm", "message": "ready Wed 11-26"},
                                               str(self.project))
        self.assertEqual(getattr(hit, "rule", None), "calendar")

    def test_a_here_document_counts_only_when_it_reaches_the_message_command(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014", "programs": ["send.sh"]})
        for command in (f"python3 - <<'EOF'\ncolor = '{SHORT}'\nEOF\nbash .agents/bus/send.sh pm fe \"done\"",
                        f"cat > notes <<EOF\n{SHORT}\nEOF\n./send.sh pm fe done",
                        f"cat <<EOF > notes; gh pr comment 5 -b done\n{SHORT}\nEOF"):
            self.assertIsNone(self.judge(command), command)
        for command in (f"./send.sh pm fe <<EOF\nmerged {SHORT}\nEOF",
                        f"cat <<EOF | ./send.sh pm fe\nmerged {SHORT}\nEOF",
                        f"cat <<EOF | grep merged | bash send.sh pm fe\nmerged {SHORT}\nEOF",
                        f"./send.sh pm fe \"$(cat <<'EOF'\nmerged {SHORT}\nEOF\n)\"",
                        f"cat <<EOF | git commit -F -\nRevert {SHORT}\nEOF"):
            self.assertEqual(getattr(self.judge(command), "rule", None), "unseen-hash", command)

    def test_message_programs_run_by_a_shell_or_through_a_variable_are_judged(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014", "programs": ["send.sh"]})
        for command in (f'bash .agents/bus/send.sh pm dev "merged {SHORT}"', f'sh /srv/repo/send.sh pm dev "{SHORT}"',
                        f'S=./send.sh; $S pm dev "merged {SHORT}"', f'S=/srv/repo/send.sh && "$S" pm dev "{SHORT}"',
                        f'export S=/srv/repo/send.sh; ${{S}} pm dev "{SHORT}"', f'zsh -e send.sh pm "{SHORT}"',
                        f'/bin/bash .agents/bus/send.sh pm dev "merged {SHORT}"', f'bash +x send.sh pm "{SHORT}"'):
            self.assertEqual(getattr(self.judge(command), "rule", None), "unseen-hash", command)
        for command in (f"bash -c 'echo {SHORT}'", f'bash other.sh pm "{SHORT}"', f'S=./other.sh; $S pm "{SHORT}"',
                        f'bash .agents/bus/send.sh pm dev "merged {OTHER}"', f'S=./send.sh; echo $S "{SHORT}"'):
            self.assertIsNone(self.judge(command), command)

    def test_sha_named_mcp_fields_are_judged(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        for key in ("sha", "commit_sha", "headSha", "commit"):
            hit = guard_lessons.judge_outbound("mcp__chat__send_message", {key: SHORT}, str(self.project), self.path)
            self.assertEqual(getattr(hit, "rule", None), "unseen-hash", key)

    def test_calendar_still_runs_beside_it(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        with mock.patch.dict(os.environ, {"ARSENAL_NOW": "2026-11-23"}):
            self.assertEqual(self.judge(f'gh pr comment 5 -b "{OTHER} on Wed 11-26"').rule, "calendar")

    def test_window_mb_is_checked(self):
        for entry, fault in (({"rule": "calendar", "window_mb": 4}, "unseen-hash and unseen-time rules only"),
                             ({"rule": "unseen-hash", "window_mb": 0}, "above 0"),
                             ({"rule": "unseen-hash", "window_mb": -1}, "above 0"),
                             ({"rule": "unseen-hash", "window_mb": 17}, "at most 16"),
                             ({"rule": "unseen-hash", "window_mb": 64}, "at most 16"),
                             ({"rule": "calendar", "allow": ["ff00ff00"]}, "unseen-hash and unseen-time rules only"),
                             ({"rule": "unseen-hash", "allow": "ed448"}, "list of words"),
                             ({"rule": "unseen-hash", "allow": []}, "list of words"),
                             ({"rule": "unseen-hash", "allow": ["ok", " "]}, "list of words"),
                             ({"rule": "unseen-hash", "window_mb": True}, "megabytes"),
                             ({"rule": "unseen-hash", "window_mb": "8"}, "megabytes")):
            with self.assertRaisesRegex(guard_lessons.RegistryError, fault):
                guard_lessons.validate(entry, "test")
        guard_lessons.validate({"rule": "unseen-hash", "window_mb": 16, "programs": ["send.sh"]}, "test")
        guard_lessons.validate({"rule": "unseen-hash", "window_mb": 0.5, "allow": ["ff00ff00"]}, "test")

    def test_ed25519_and_allowed_words_pass_and_the_reason_says_how(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        self.assertIsNone(self.judge('git commit -m "ci: use ed25519 deploy keys"'))
        self.assertIsNone(self.judge('gh pr create --body "Generated with ed25519 signing"'))
        hit = self.judge('gh pr comment 5 -b "color ff00ff00"')
        self.assertIn('"allow"', hit.reason)
        self.registry({"rule": "unseen-hash", "lesson": "G014", "allow": ["FF00FF00"]})
        self.assertIsNone(self.judge('gh pr comment 5 -b "color ff00ff00"'))
        self.assertEqual(self.judge(f'gh pr comment 5 -b "color ff00ff00 {SHORT}"').rule, "unseen-hash")

    def test_the_refusal_names_three_and_counts_the_rest(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        hit = self.judge(f'gh pr comment 5 -b "{SHORT} b2c3d4e5f6 c3d4e5f6a7 d4e5f6a7b8"')
        self.assertIn(f"{SHORT}, b2c3d4e5f6, c3d4e5f6a7 and 1 more", hit.reason)

    def test_a_dashless_uuid_in_an_mcp_input_counts_when_printed_dashed(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        tool_input = {"page_id": "p1", "text": "page 1a2b3c4d5e6f47a8b9c0d1e2f3a4b5c6"}
        hit = guard_lessons.judge_outbound("mcp__notes__update_page", tool_input, str(self.project), self.path)
        self.assertEqual(hit.rule, "unseen-hash")
        path = self.write(tool_result("toolu_1", "id 1a2b3c4d-5e6f-47a8-b9c0-d1e2f3a4b5c6"))
        self.assertIsNone(guard_lessons.judge_outbound("mcp__notes__update_page", tool_input, str(self.project), path))

    def test_a_here_document_counts_only_when_it_carries_the_git_message(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        for command in (f"git commit -F msg.txt && cat <<EOF > notes\n{SHORT}\nEOF",
                        f"git commit --file msg.txt <<EOF\n{SHORT}\nEOF",  # git reads the file, not stdin
                        f"git commit -F msg.txt <<EOF\n{SHORT}\nEOF",
                        f"git commit -m ok; cat > f <<EOF\nlog {SHORT}\nEOF",
                        f"git tag -a v1 -m ok && tee f <<'EOF'\n{SHORT}\nEOF"):
            self.assertIsNone(self.judge(command), command)
        for command in (f"git commit --file=- <<EOF\nRevert {SHORT}\nEOF",
                        f"git commit --file - <<EOF\nRevert {SHORT}\nEOF",
                        f"git commit -F- <<EOF\nRevert {SHORT}\nEOF",
                        f"git commit -aF - <<EOF\nRevert {SHORT}\nEOF",
                        f"git commit -m \"$(cat <<'EOF'\nRevert {SHORT}\nEOF\n)\"",
                        f"gh pr create --title t --body-file - <<EOF\nfixes {SHORT}\nEOF"):
            self.assertEqual(getattr(self.judge(command), "rule", None), "unseen-hash", command)

    def test_the_calendar_rule_still_reads_any_here_document_of_a_commit_call(self):
        self.registry({"rule": "calendar", "lesson": "G9"})
        with mock.patch.dict(os.environ, {"ARSENAL_NOW": "2026-11-23"}):
            self.assertEqual(self.judge("git commit -F msg.txt && cat <<EOF > notes\nWed 11-26\nEOF").rule,
                             "calendar")

    def test_a_bad_entry_is_skipped_and_never_refuses(self):
        self.registry({"rule": "unseen-hash", "window_mb": "lots"})
        self.assertIsNone(self.judge(f'gh pr comment 5 -b "{SHORT}"'))
        self.assertTrue(guard_lessons.registry_problems(str(self.project)))

    def test_min_version_1_29_0_applies_from_that_release_only(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014", "min_version": "1.29.0"})
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 29, 0)):
            self.assertEqual(self.judge(f'gh pr comment 5 -b "{SHORT}"').rule, "unseen-hash")
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 28, 1)):
            self.assertIsNone(self.judge(f'gh pr comment 5 -b "{SHORT}"'))
            self.assertEqual(guard_lessons.registry_problems(str(self.project)), [])  # skipped quietly


class HookTests(RuleCase):
    """guard.py pre passes the hook input's transcript_path."""

    def pre(self, tool, tool_input, transcript, **fields):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
                   "cwd": str(self.project), "permission_mode": "default", **fields}
        if transcript:
            payload["transcript_path"] = transcript
        base = {k: v for k, v in os.environ.items()
                if k not in ("ARSENAL_GUARD", "ARSENAL_LESSON_GUARDS", "ARSENAL_GUARD_DESTRUCTIVE",
                             "ARSENAL_RUN_LIMITS", "CLAUDE_PROJECT_DIR", "ARSENAL_PROFILE")}
        result = subprocess.run([sys.executable, str(SCRIPT), "pre"], cwd=self.project, input=json.dumps(payload),
                                capture_output=True, text=True, env=base)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None

    def test_bash_and_mcp_calls_are_denied_with_the_transcript(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        out = self.pre("Bash", {"command": f'gh pr comment 5 -b "merged {SHORT}"'}, self.path)
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("G014 (unseen-hash)", out["permissionDecisionReason"])
        out = self.pre("mcp__chat__send_message", {"text": f"merged {SHORT}"}, self.path)
        self.assertEqual(out["permissionDecision"], "deny")

    def test_a_subagent_is_judged_on_its_own_transcript(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        agent = self.dir / "session" / "subagents" / "agent-a9.jsonl"
        agent.parent.mkdir(parents=True)
        agent.write_text(json.dumps(tool_result("toolu_1", FULL)) + "\n", encoding="utf-8")
        for tool, tool_input in (("Bash", {"command": f'git commit -m "Revert {SHORT}"'}),
                                 ("mcp__chat__send_message", {"text": f"merged {SHORT}"})):
            self.assertIsNone(self.pre(tool, tool_input, self.path, agent_id="a9"), tool)
            out = self.pre(tool, {"command": f'git commit -m "Revert {OTHER}"'} if tool == "Bash" else
                           {"text": f"merged {OTHER}"}, self.path, agent_id="a9")
            self.assertEqual(out["permissionDecision"], "deny", tool)  # the parent's results are not the agent's

    def test_without_a_transcript_the_call_passes(self):
        self.registry({"rule": "unseen-hash", "lesson": "G014"})
        self.assertIsNone(self.pre("Bash", {"command": f'gh pr comment 5 -b "merged {SHORT}"'}, None))
        self.assertIsNone(self.pre("Bash", {"command": f'gh pr comment 5 -b "{SHORT}"'},
                                   str(self.dir / "missing.jsonl")))


if __name__ == "__main__":
    unittest.main()
