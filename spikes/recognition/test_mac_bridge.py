"""Mac bridge turn rules, sources and client; fake transport only, no network."""
import asyncio
import io
import itertools
import json
import os
import sys
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import mac_bridge as mb


def ids():
    counter = itertools.count(1)
    return lambda: f"t{next(counter)}"


def chips(turn_id, *signs):
    return {"type": "chips", "turn_id": turn_id, "chips": list(signs)}


def approve(turn_id, text):
    return {"type": "approve", "turn_id": turn_id, "text": text}


NOON = datetime(2026, 10, 24, 12, 0, 5, 250000)


def noon():
    return NOON


def read_log(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def state(*results):
    turn = mb.TurnState(new_id=ids())
    for result in results:
        turn.add(result)
    return turn


class Chips(unittest.TestCase):
    def test_each_change_sends_all_chips_with_the_same_turn_id(self):
        turn = state()
        self.assertEqual(turn.add("hello"), {"type": "chips", "turn_id": "t1", "chips": ["hello"]})
        self.assertEqual(turn.add("doctor"),
                         {"type": "chips", "turn_id": "t1", "chips": ["hello", "doctor"]})

    def test_removal_resends_the_remaining_chips(self):
        turn = state("hello", "doctor")
        self.assertEqual(turn.remove_last(), {"type": "chips", "turn_id": "t1", "chips": ["hello"]})
        self.assertEqual(turn.remove_last(), {"type": "chips", "turn_id": "t1", "chips": []})
        self.assertIsNone(turn.remove_last())

    def test_unsure_is_shown_but_never_sent(self):
        turn = state("hello")
        self.assertIsNone(turn.add(None))
        self.assertEqual(turn.chips, ["hello", None])
        self.assertEqual(turn.add("doctor")["chips"], ["hello", "doctor"])
        self.assertEqual(turn.remove_last()["chips"], ["hello"])
        self.assertIsNone(turn.remove_last())  # dropping the "?" changes nothing sendable
        self.assertEqual(turn.chips, ["hello"])

    def test_unknown_sign_and_too_many_chips_fail(self):
        turn = state()
        with self.assertRaises(ValueError):
            turn.add("hospital")
        for _ in range(mb.MAX_CHIPS):
            turn.add("yes")
        with self.assertRaises(mb.ChipLimit):
            turn.add("no")
        turn.add(None)  # unsure entries are not sent, so they don't count
        self.assertEqual(len(turn.sendable), mb.MAX_CHIPS)

    def test_chip_change_drops_the_old_draft(self):
        turn = state("no")
        turn.on_draft("t1", "No.", "template")
        turn.add("morning")
        self.assertIsNone(turn.draft)
        self.assertIsNone(turn.approve())


class Drafts(unittest.TestCase):
    def test_only_the_current_turns_draft_is_kept(self):
        turn = state("hello")
        self.assertIsNone(turn.on_draft("t0", "Old text.", "llm"))
        self.assertIsNone(turn.draft)
        self.assertEqual(turn.on_draft("t1", "Hello.", "llm"), mb.Draft("t1", "Hello.", "llm"))

    def test_draft_without_chips_is_ignored(self):
        turn = state()
        self.assertIsNone(turn.on_draft("t1", "Hello.", "llm"))
        self.assertIsNone(turn.approve())

    def test_clear_starts_a_new_turn_and_ignores_late_drafts(self):
        turn = state("hello", None)
        turn.on_draft("t1", "Hello.", "llm")
        turn.clear()
        self.assertEqual((turn.turn_id, turn.chips, turn.draft), ("t2", [], None))
        turn.add("yes")
        self.assertIsNone(turn.on_draft("t1", "Hello.", "llm"))
        self.assertIsNone(turn.approve())


class Approve(unittest.TestCase):
    def test_send_approves_the_draft_once_and_starts_a_new_turn(self):
        turn = state("hello", None)
        turn.on_draft("t1", "Hello.", "template")
        self.assertEqual(turn.approve(), {"type": "approve", "turn_id": "t1", "text": "Hello."})
        self.assertEqual((turn.turn_id, turn.chips, turn.draft), ("t2", [], None))
        self.assertIsNone(turn.approve())
        self.assertEqual(turn.add("yes")["turn_id"], "t2")

    def test_late_draft_for_a_sent_turn_cannot_be_sent_again(self):
        turn = state("hello")
        turn.on_draft("t1", "Hello.", "llm")
        turn.approve()
        turn.add("yes")
        self.assertIsNone(turn.on_draft("t1", "Hello there.", "llm"))
        self.assertIsNone(turn.approve())

    def test_no_draft_means_nothing_to_send(self):
        self.assertIsNone(state("hello", None).approve())

    def test_quick_reply_uses_exact_text_on_a_fresh_turn(self):
        turn = state("hello")
        turn.on_draft("t1", "Hello.", "llm")
        self.assertEqual(turn.quick_reply("repeat"), {
            "type": "approve", "turn_id": "t2", "text": "Sorry, could you please repeat that?"})
        self.assertEqual((turn.turn_id, turn.chips, turn.draft), ("t3", [], None))
        self.assertIsNone(turn.approve())

    def test_quick_reply_texts(self):
        self.assertEqual(mb.QUICK_REPLIES, {
            "yes": "Yes.", "no": "No.",
            "wait": "Please wait a moment, I'm signing my reply.",
            "repeat": "Sorry, could you please repeat that?"})


class Delivery(unittest.TestCase):
    def sent(self):
        turn = state("hello")
        turn.on_draft("t1", "Hello.", "llm")
        turn.approve()
        return turn

    def test_spoken_confirms_the_text_once(self):
        turn = self.sent()
        self.assertIsNone(turn.on_spoken("t9"))
        self.assertEqual(turn.on_spoken("t1"), "Hello.")
        self.assertIsNone(turn.on_spoken("t1"))

    def test_not_delivered_waits_and_resend_uses_a_new_turn_id(self):
        turn = self.sent()
        self.assertEqual(turn.on_not_delivered("t1"), "Hello.")
        self.assertEqual(turn.undelivered, ("t1", "Hello."))
        self.assertEqual(turn.approve(), {"type": "approve", "turn_id": "t2", "text": "Hello."})
        self.assertIsNone(turn.undelivered)
        self.assertIsNone(turn.approve())

    def test_unknown_not_delivered_is_ignored(self):
        turn = self.sent()
        self.assertIsNone(turn.on_not_delivered("t9"))
        self.assertIsNone(turn.undelivered)
        self.assertIsNone(turn.approve())

    def test_late_spoken_cancels_the_pending_resend(self):
        turn = self.sent()
        turn.on_not_delivered("t1")
        self.assertEqual(turn.on_spoken("t1"), "Hello.")
        self.assertIsNone(turn.approve())

    def test_a_new_draft_wins_over_the_undelivered_text(self):
        turn = self.sent()
        turn.on_not_delivered("t1")
        turn.add("yes")
        turn.on_draft("t2", "Yes.", "template")
        self.assertEqual(turn.approve()["text"], "Yes.")
        self.assertIsNone(turn.undelivered)


class End(unittest.TestCase):
    def test_stop_never_queues_text(self):
        turn = state("hello")
        turn.on_draft("t1", "Hello.", "llm")
        self.assertEqual(turn.stop(), {"type": "stop"})
        self.assertEqual((turn.turn_id, turn.draft), ("t1", mb.Draft("t1", "Hello.", "llm")))

    def test_end_is_sent_once_and_blocks_everything_after(self):
        turn = state("hello")
        turn.on_draft("t1", "Hello.", "llm")
        self.assertEqual(turn.end(), {"type": "end"})
        self.assertIsNone(turn.end())
        self.assertEqual((turn.chips, turn.draft), ([], None))
        for action in (lambda: turn.add("yes"), lambda: turn.add(None), turn.remove_last,
                       turn.approve, turn.stop, lambda: turn.quick_reply("yes"),
                       lambda: turn.on_draft(turn.turn_id, "Yes.", "llm")):
            self.assertIsNone(action())
        self.assertEqual(turn.chips, [])

    def test_ended_call_drops_pending_and_awaited_resends(self):
        turn = state("hello")
        turn.on_draft("t1", "Hello.", "llm")
        turn.approve()
        turn.quick_reply("yes")  # sent on t3
        turn.on_not_delivered("t1")
        turn.on_ended()
        self.assertIsNone(turn.undelivered)
        self.assertIsNone(turn.approve())
        self.assertIsNone(turn.on_not_delivered("t3"))
        self.assertIsNone(turn.approve())
        self.assertIsNone(turn.end())


async def collect(source):
    return [result async for result in source.results()]


class Sources(unittest.IsolatedAsyncioTestCase):
    def test_parse_result(self):
        self.assertEqual(mb.parse_result(" Doctor "), "doctor")
        self.assertIsNone(mb.parse_result("?"))
        for bad in ("hospital", "", "q"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                mb.parse_result(bad)

    async def test_manual_source_yields_fed_results_until_closed(self):
        source = mb.ManualSource()
        for result in ("hello", None, "doctor"):
            source.feed(result)
        source.close()
        self.assertEqual(await collect(source), ["hello", None, "doctor"])

    async def test_replay_waits_before_each_delayed_step(self):
        events = []

        async def sleep(seconds):
            events.append(seconds)

        source = mb.ReplaySource.from_json(
            '["hello", "?", null, {"sign": "doctor", "delay": 1.5}, {"sign": null}]', sleep)
        async for result in source.results():
            events.append(result)
        self.assertEqual(events, ["hello", None, None, 1.5, "doctor", None])

    def test_replay_rejects_bad_steps(self):
        for text in ('["hospital"]', '[{"delay": 1}]', '[{"sign": "yes", "delay": -1}]',
                     '[{"sign": "yes", "pause": 1}]'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                mb.ReplaySource.from_json(text)

    async def test_blocking_source_drains_the_iterator(self):
        source = mb.BlockingSource(lambda: iter(["yes", None, "thankyou"]))
        self.assertEqual(await collect(source), ["yes", None, "thankyou"])


def child(code):
    """argv for a throwaway recognizer process that runs `code`."""
    return [sys.executable, "-c", "import json, os, sys, time\n" + code]


class DescribeResult(unittest.TestCase):
    TOP = [{"sign": "doctor", "similarity": 0.8312}, {"sign": "hello", "similarity": 0.6149},
           {"sign": "time", "similarity": 0.55}]

    def test_accepted_sign_shows_top3_margin_and_latency(self):
        details = {"sign": "doctor", "reason": None, "top": self.TOP, "margin": 0.2163,
                   "latency_ms": 462.0, "failed_checks": [], "provisional": False}
        self.assertEqual(mb.describe_result(details),
                         "✓ doctor  (doctor 0.83 | hello 0.61 | time 0.55; margin 0.22; 0.46 s)")

    def test_unsure_sign_says_which_checks_failed_instead_of_the_long_reason(self):
        details = {"sign": None, "reason": "insufficient evidence (best morning 0.580, ...)",
                   "top": [{"sign": "morning", "similarity": 0.58}, {"sign": "evening", "similarity": 0.56}],
                   "margin": 0.02, "latency_ms": 470.0, "failed_checks": ["similarity", "margin", "pose", "hands"]}
        self.assertEqual(mb.describe_result(details),
                         "? unsure  (morning 0.58 | evening 0.56; margin 0.02; 0.47 s; low similarity, "
                         "low margin, body seen in too few frames, hands seen in too few frames)")

    def test_unsure_without_failed_checks_shows_the_reason(self):
        self.assertEqual(mb.describe_result({"sign": None, "reason": "no recognition bundle",
                                             "top": [], "margin": None, "latency_ms": 450.0,
                                             "failed_checks": []}),
                         "? unsure  (0.45 s; no recognition bundle)")

    def test_old_recognizer_lines_still_read(self):
        self.assertEqual(mb.describe_result({"sign": "doctor"}), "✓ doctor")
        self.assertEqual(mb.describe_result({"sign": None}), "? unsure")
        self.assertEqual(mb.describe_result({"sign": None, "reason": "low similarity", "latency_ms": 500}),
                         "? unsure  (0.50 s; low similarity)")
        self.assertEqual(mb.describe_result({"sign": None, "failed_checks": ["new_check"]}),
                         "? unsure  (new_check)")

    def test_a_reason_is_never_shown_for_an_accepted_sign(self):
        self.assertEqual(mb.describe_result({"sign": "yes", "reason": "stray", "failed_checks": ["margin"]}),
                         "✓ yes")

    def test_provisional_results_are_tagged(self):
        self.assertEqual(mb.describe_result({"sign": "yes", "provisional": True}), "✓ yes  [PROVISIONAL]")
        self.assertEqual(mb.describe_result({"sign": "yes", "provisional": False}), "✓ yes")

    def test_parse_result_details_keeps_every_key_and_checks_the_sign(self):
        line = mb.result_line("doctor", margin=0.2, top=self.TOP)
        self.assertEqual(mb.parse_result_details(line), {"sign": "doctor", "margin": 0.2, "top": self.TOP})
        with self.assertRaises(ValueError):
            mb.parse_result_details('{"sign": "hospital", "margin": 0.2}')


class SessionLogTests(unittest.TestCase):
    def test_show_prefixes_the_time_and_record_without_a_path_writes_nothing(self):
        lines = []
        log = mb.SessionLog(lines.append, None, noon)
        log.show("receptionist: Hello")
        log.record("backend", {"type": "caption", "text": "Hello"})
        self.assertEqual(lines, ["12:00:05 receptionist: Hello"])

    def test_records_append_as_json_lines_and_keep_unicode(self):
        with TemporaryDirectory() as folder:
            path = Path(folder, "lab", "nested", "s.jsonl")
            log = mb.SessionLog(print, path, noon)
            self.assertTrue(path.parent.is_dir())
            log.record("recognizer", {"sign": None, "reason": "café"})
            log.record("bridge", {"type": "end"})
            self.assertIn("café", path.read_text())
            self.assertEqual(read_log(path), [
                {"time": "2026-10-24T12:00:05.250", "from": "recognizer",
                 "message": {"sign": None, "reason": "café"}},
                {"time": "2026-10-24T12:00:05.250", "from": "bridge", "message": {"type": "end"}}])

    def test_a_failing_write_stops_the_log_once_without_raising(self):
        with TemporaryDirectory() as folder:
            lines = []
            path = Path(folder, "s.jsonl")
            log = mb.SessionLog(lines.append, path, noon)
            path.mkdir()  # opening a directory for append fails like a full or removed disk
            log.record("bridge", {"type": "end"})
            log.record("bridge", {"type": "end"})
            self.assertIsNone(log.path)
            self.assertEqual(len(lines), 1)
            self.assertTrue(lines[0].startswith("! session log stopped:"))

    def test_log_path_defaults_to_a_timestamped_file_under_artifacts_lab(self):
        with TemporaryDirectory() as folder, patch.object(mb, "ARTIFACTS", Path(folder)):
            self.assertEqual(mb.session_log_path("", noon),
                             Path(folder, "lab", "session-20261024-120005.jsonl"))
            self.assertEqual(mb.session_log_path(f"{folder}/lab/mine.jsonl"),
                             Path(folder, "lab", "mine.jsonl"))
            for outside in ("/tmp/session.jsonl", f"{folder}/../escape.jsonl"):
                with self.subTest(outside=outside), self.assertRaises(ValueError):
                    mb.session_log_path(outside)


class SubprocessSourceTests(unittest.IsolatedAsyncioTestCase):
    def test_result_lines_round_trip_and_reject_unknown_signs(self):
        line = mb.result_line("doctor", latency_ms=812.5)
        self.assertEqual(json.loads(line), {"sign": "doctor", "latency_ms": 812.5})
        self.assertEqual(mb.parse_result_line(line), "doctor")
        self.assertIsNone(mb.parse_result_line(mb.result_line(None, reason="low similarity")))
        for bad in ('{"sign": "hospital"}', '{"sign": "?"}', '{"sign": 3}', '{"sign": ""}'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                mb.parse_result_line(bad)
        with self.assertRaises(KeyError):
            mb.parse_result_line('{"latency_ms": 1}')

    async def test_yields_child_results_with_stdin_closed(self):
        lines = []
        source = mb.SubprocessSource(child(
            'assert sys.stdin.read() == ""\n'
            'for sign in ("hello", None, "doctor"):\n'
            '    print(json.dumps({"sign": sign, "latency_ms": 5}), flush=True)\n'), lines.append)
        self.assertEqual(await asyncio.wait_for(collect(source), 30), ["hello", None, "doctor"])
        self.assertEqual([line[9:] for line in lines],
                         ["✓ hello  (0.01 s)", "? unsure  (0.01 s)", "✓ doctor  (0.01 s)"])

    async def test_results_are_timestamped_and_logged_whole(self):
        lines = []
        with TemporaryDirectory() as folder:
            path = Path(folder, "s.jsonl")
            row = {"sign": "time", "top": [{"sign": "time", "similarity": 0.91}], "margin": 0.3}
            source = mb.SubprocessSource(child(f'print(json.dumps({row!r}), flush=True)'),
                                         lines.append, mb.SessionLog(lines.append, path, noon))
            self.assertEqual(await asyncio.wait_for(collect(source), 30), ["time"])
            self.assertEqual(lines, ["12:00:05 ✓ time  (time 0.91; margin 0.30)"])
            self.assertEqual(read_log(path), [{"time": "2026-10-24T12:00:05.250",
                                               "from": "recognizer", "message": row}])

    async def test_each_result_is_shown_and_a_provisional_bundle_is_announced_once(self):
        lines = []
        rows = [{"sign": "doctor", "provisional": True, "top": [{"sign": "doctor", "similarity": 0.9}]},
                {"sign": None, "provisional": True, "failed_checks": ["margin"]}]
        source = mb.SubprocessSource(child(
            f'for row in {rows!r}:\n    print(json.dumps(row), flush=True)\n'), lines.append)
        self.assertEqual(await asyncio.wait_for(collect(source), 30), ["doctor", None])
        self.assertEqual([line[9:] for line in lines], [f"!!! {mb.PROVISIONAL_BANNER} !!!",
                                 "✓ doctor  (doctor 0.90)  [PROVISIONAL]",
                                 "? unsure  (low margin)  [PROVISIONAL]"])

    async def test_a_crashed_child_is_reported_after_its_results(self):
        lines = []
        source = mb.SubprocessSource(child('print(json.dumps({"sign": "yes"}))\nsys.exit(3)'),
                                     lines.append)
        self.assertEqual(await asyncio.wait_for(collect(source), 30), ["yes"])
        self.assertEqual([lines[0][9:], lines[1]],
                         ["✓ yes", "! live recognizer stopped (exit 3); type signs instead"])

    async def test_an_unknown_sign_from_the_child_fails_loudly(self):
        source = mb.SubprocessSource(child('print(json.dumps({"sign": "hospital"}))'))
        with self.assertRaises(ValueError):
            await asyncio.wait_for(collect(source), 30)

    async def test_stopping_the_bridge_terminates_the_child(self):
        with TemporaryDirectory() as directory:
            pid_file = Path(directory) / "pid"
            source = mb.SubprocessSource(child(
                f'open({str(pid_file)!r}, "w").write(str(os.getpid()))\n'
                'print(json.dumps({"sign": "hello"}), flush=True)\ntime.sleep(60)'), [].append)
            results = source.results()
            self.assertEqual(await asyncio.wait_for(anext(results), 30), "hello")
            pid = int(pid_file.read_text())
            os.kill(pid, 0)  # still running while the bridge listens
            await asyncio.wait_for(results.aclose(), 10)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)


class FakeTransport:
    def __init__(self):
        self.sent, self.closed = [], False
        self.incoming = asyncio.Queue()

    async def send(self, message):
        if self.closed:
            raise ConnectionError("send after close")
        self.sent.append(json.loads(message))

    def push(self, **message):
        self.incoming.put_nowait(json.dumps(message))

    def hang_up(self):
        self.incoming.put_nowait(None)

    def __aiter__(self):
        return self._messages()

    async def _messages(self):
        while (raw := await self.incoming.get()) is not None:
            yield raw

    async def close(self):
        self.closed = True


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.transport, self.lines = FakeTransport(), []
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.log_path = Path(self.folder.name, "lab", "session.jsonl")
        self.log = mb.SessionLog(self.lines.append, self.log_path, noon)
        self.bridge = mb.Bridge(self.transport, mb.TurnState(new_id=ids()), self.lines.append, self.log)

    async def signs(self, *results):
        for result in results:
            await self.bridge.on_result(result)

    async def server(self, **message):
        await self.bridge.on_server(json.dumps(message))

    def types(self):
        return [message["type"] for message in self.transport.sent]

    async def test_signs_send_chips_without_unsure_entries(self):
        await self.signs("hello", None, "doctor")
        self.assertEqual(self.transport.sent, [
            chips("t1", "hello"),
            chips("t1", "hello", "doctor")])
        self.assertIn("chips: [hello] [?] [doctor]", self.lines)

    async def test_typed_tokens_go_through_the_manual_source(self):
        self.assertTrue(await self.bridge.handle_line("hello ? doctor"))
        self.assertTrue(await self.bridge.handle_line("doctor hospital"))
        self.bridge.manual.close()
        await self.bridge._pump_source(self.bridge.manual)
        self.assertEqual(self.bridge.state.chips, ["hello", None, "doctor"])
        self.assertTrue(any("unknown sign 'hospital'" in line for line in self.lines))

    async def test_remove_resends_and_clear_starts_a_new_turn(self):
        await self.signs("hello", "doctor")
        await self.bridge.handle_line("x")
        self.assertEqual(self.transport.sent[-1], chips("t1", "hello"))
        await self.bridge.handle_line("c")
        await self.signs("yes")
        self.assertEqual(self.transport.sent[-1], chips("t2", "yes"))

    async def test_chip_limit_is_reported_not_raised(self):
        await self.signs(*["yes"] * mb.MAX_CHIPS)
        await self.signs("no")
        self.assertEqual(len(self.transport.sent), mb.MAX_CHIPS)
        self.assertTrue(self.lines[-1].startswith("! at most"))

    async def test_send_uses_only_the_current_draft_once(self):
        await self.signs("hello")
        await self.bridge.handle_line("s")
        self.assertEqual(self.types(), ["chips"])
        await self.server(type="draft", turn_id="t0", text="Stale.", source="llm")
        await self.bridge.handle_line("s")
        self.assertEqual(self.types(), ["chips"])
        await self.server(type="draft", turn_id="t1", text="Hello.", source="template")
        self.assertIn("12:00:05 draft (template): Hello.   [s = SEND]", self.lines)
        await self.bridge.handle_line("s")
        await self.bridge.handle_line("s")
        self.assertEqual(self.transport.sent[1:], [approve("t1", "Hello.")])
        self.assertIn("nothing to send yet: wait for a draft", self.lines)

    async def test_quick_reply_sends_exact_text_on_a_fresh_turn(self):
        await self.signs("hello")
        await self.bridge.handle_line("q Wait")
        self.assertEqual(self.transport.sent[-1],
                         approve("t2", "Please wait a moment, I'm signing my reply."))
        for bad in ("q", "q maybe", "q yes no"):
            await self.bridge.handle_line(bad)
        self.assertEqual(len(self.transport.sent), 2)

    async def test_not_delivered_waits_for_a_manual_resend_on_a_new_turn(self):
        await self.signs("hello")
        await self.server(type="draft", turn_id="t1", text="Hello.", source="llm")
        await self.bridge.handle_line("s")
        await self.server(type="not_delivered", turn_id="t1", reason="no confirmation")
        self.assertEqual(self.types(), ["chips", "approve"])
        self.assertIn("12:00:05 ! not delivered (no confirmation), tap SEND again (s): Hello.", self.lines)
        await self.bridge.handle_line("s")
        self.assertEqual(self.transport.sent[-1], approve("t2", "Hello."))
        await self.server(type="spoken", turn_id="t2")
        self.assertEqual(self.lines[-1], "12:00:05 Delivered: Hello.")

    async def test_status_caption_and_error_are_shown(self):
        await self.server(type="status", state="speaking")
        await self.server(type="caption", text="We have 4 pm tomorrow.", at=1.0)
        await self.server(type="error", code="stale_turn", message="old turn")
        await self.server(type="mystery")
        self.assertEqual(self.lines, [
            "12:00:05 [status] speaking", "12:00:05 Speaking now...",
            "12:00:05 receptionist: We have 4 pm tomorrow.",
            "12:00:05 ! backend error stale_turn: old turn",
            "12:00:05 (ignored unknown message type 'mystery')"])
        self.assertEqual(self.transport.sent, [])

    async def test_session_log_keeps_every_message_in_order(self):
        await self.server(type="caption", text="When would you like to come?", at=1.0)
        await self.signs("tomorrow", None)
        await self.server(type="draft", turn_id="t1", text="Tomorrow, please.", source="llm")
        await self.bridge.handle_line("s")
        self.assertIn("12:00:05 SEND: Tomorrow, please.", self.lines)
        await self.server(type="spoken", turn_id="t1")
        await self.bridge.handle_line("e")
        entries = read_log(self.log_path)
        self.assertEqual({e["time"] for e in entries}, {"2026-10-24T12:00:05.250"})
        self.assertEqual([(e["from"], e["message"]) for e in entries], [
            ("backend", {"type": "caption", "text": "When would you like to come?", "at": 1.0}),
            ("bridge", chips("t1", "tomorrow")),
            ("backend", {"type": "draft", "turn_id": "t1", "text": "Tomorrow, please.", "source": "llm"}),
            ("bridge", approve("t1", "Tomorrow, please.")),
            ("backend", {"type": "spoken", "turn_id": "t1"}),
            ("bridge", {"type": "end"})])

    async def test_end_stops_further_sends(self):
        await self.signs("hello")
        await self.server(type="draft", turn_id="t1", text="Hello.", source="llm")
        self.assertFalse(await self.bridge.handle_line("e"))
        for line in ("s", "q yes", "x", "stop", "e", "yes"):
            await self.bridge.handle_line(line)
        await self.signs("no")
        self.assertEqual(self.types(), ["chips", "end"])

    async def test_backend_ended_status_blocks_sends(self):
        await self.signs("hello")
        await self.server(type="draft", turn_id="t1", text="Hello.", source="llm")
        await self.server(type="status", state="ended")
        await self.bridge.handle_line("s")
        await self.bridge.handle_line("stop")
        self.assertEqual(self.types(), ["chips"])
        self.assertIn("call ended; nothing will be sent", self.lines)
        self.assertIn("12:00:05 call ended; nothing more will be sent", self.lines)

    async def test_run_ends_when_the_user_ends_the_call(self):
        lines = asyncio.Queue()

        async def terminal():
            while (line := await lines.get()) is not None:
                yield line

        replay = mb.ReplaySource.from_json('["hello", "?"]')
        task = asyncio.create_task(self.bridge.run(terminal(), (replay,)))
        await asyncio.sleep(0.01)
        self.transport.push(type="draft", turn_id="t1", text="Hello.", source="llm")
        await asyncio.sleep(0.01)
        lines.put_nowait("s")
        lines.put_nowait("e")
        await asyncio.wait_for(task, 1)
        self.assertEqual(self.types(), ["chips", "approve", "end"])
        self.assertTrue(self.transport.closed)

    async def test_run_stops_silently_when_the_backend_hangs_up(self):
        never = asyncio.Event()

        async def terminal():
            await never.wait()
            yield "s"

        task = asyncio.create_task(self.bridge.run(terminal()))
        await asyncio.sleep(0.01)
        self.transport.hang_up()
        await asyncio.wait_for(task, 1)
        self.assertTrue(self.bridge.state.ended)
        self.assertEqual(self.lines[-1], "connection closed; nothing will be sent")
        self.assertEqual(self.transport.sent, [])


TOKEN = "test-token-123"


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.posts, self.connects, self.lines = [], [], []
        self.transport = FakeTransport()
        self.reply = {"call_id": "c42", "state": "dialing"}

    def post(self, url, body, headers):
        self.posts.append((url, body, headers))
        return self.reply

    async def connect(self, url, headers):
        self.connects.append((url, headers))
        return self.transport

    def main(self, *argv, after=0, env=None):
        async def terminal():
            while len(self.transport.sent) < after:
                await asyncio.sleep(0)
            yield "e"

        stdout, stderr = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                return mb.main(list(argv), {"APP_TOKEN": TOKEN} if env is None else env,
                               self.post, self.connect, terminal, self.lines.append)
        finally:
            printed = "\n".join(self.lines) + stdout.getvalue() + stderr.getvalue()
            self.assertNotIn(TOKEN, printed)

    def test_start_call_needs_confirm_cost_before_any_request(self):
        with self.assertRaises(SystemExit):
            mb.start_call("https://b", "clinic", TOKEN, False, self.post, self.lines.append)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.lines, [mb.COST_HEADS_UP])
        self.assertIn("5.5/min", mb.COST_HEADS_UP)

    def test_start_call_posts_contact_and_purpose_with_the_token(self):
        call_id = mb.start_call("https://b", "clinic", TOKEN, True, self.post, self.lines.append)
        self.assertEqual(call_id, "c42")
        self.assertEqual(self.posts, [("https://b/calls",
                                       {"contact_id": "clinic", "purpose": "doctor_appointment"},
                                       {"Authorization": f"Bearer {TOKEN}"})])
        self.assertEqual(self.lines[0], mb.COST_HEADS_UP)

    def test_main_refuses_to_dial_without_confirm_cost(self):
        with self.assertRaises(SystemExit):
            self.main("--base-url", "https://b", "--contact", "clinic")
        self.assertEqual((self.posts, self.connects), ([], []))

    def test_main_attaches_to_an_existing_call_without_dialing(self):
        self.assertEqual(self.main("--base-url", "https://b.example/api/", "--call-id", "c7"), 0)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.connects, [("wss://b.example/api/calls/c7/ws",
                                          {"Authorization": f"Bearer {TOKEN}"})])
        self.assertEqual(self.transport.sent, [{"type": "end"}])
        self.assertTrue(self.transport.closed)

    def test_main_starts_a_confirmed_call_then_replays_into_it(self):
        with TemporaryDirectory() as folder:
            replay = Path(folder, "script.json")
            replay.write_text('["hello", "?", "doctor"]')
            self.main("--base-url", "http://127.0.0.1:8000", "--contact", "clinic",
                      "--confirm-cost", "--replay", str(replay), after=2)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.connects[0][0], "ws://127.0.0.1:8000/calls/c42/ws")
        turn_id = self.transport.sent[0]["turn_id"]
        self.assertEqual(self.transport.sent, [chips(turn_id, "hello"),
                                               chips(turn_id, "hello", "doctor"), {"type": "end"}])

    def test_live_command_runs_live_source_with_the_chosen_input(self):
        def command(*argv):
            return mb.live_command(mb.parse_args(["--base-url", "https://b", "--call-id", "c7",
                                                  "--live", *argv]))
        head = [str(mb.RECOGNIZER_PYTHON), str(mb.ROOT / "live_source.py")]
        self.assertEqual(command(), [*head, "--camera", "0"])
        self.assertEqual(command("--camera", "2", "--bundle", "b.json", "--rest-y", "0.8"),
                         [*head, "--camera", "2", "--bundle", "b.json", "--rest-y", "0.8"])
        self.assertEqual(command("--replay-videos", "clips", "--recognizer-python", "/v/python"),
                         ["/v/python", head[1], "--replay-videos", "clips"])

    def test_live_options_need_live_and_one_input(self):
        for argv in (["--camera", "1"], ["--replay-videos", "clips"], ["--bundle", "b.json"],
                     ["--rest-y", "0.8"], ["--live", "--camera", "1", "--replay-videos", "clips"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                self.main("--base-url", "https://b", "--call-id", "c7", *argv)
        self.assertEqual((self.posts, self.connects), ([], []))

    def test_live_without_the_signclip_venv_fails_before_any_request(self):
        with self.assertRaises(SystemExit) as raised:
            self.main("--base-url", "https://b", "--call-id", "c7", "--live",
                      "--recognizer-python", "/nonexistent/python")
        self.assertIn("/nonexistent/python", str(raised.exception))
        self.assertEqual((self.posts, self.connects), ([], []))

    def test_live_signs_from_the_recognizer_become_chips(self):
        with TemporaryDirectory() as folder:
            recognizer = Path(folder, "python")
            recognizer.write_text(
                f"#!{sys.executable}\n"
                "import json, sys\n"
                "assert sys.argv[1].endswith('live_source.py'), sys.argv\n"
                "assert sys.argv[2:] == ['--camera', '3', '--bundle', 'b.json'], sys.argv\n"
                "for sign in ('hello', None, 'doctor'):\n"
                "    print(json.dumps({'sign': sign, 'latency_ms': 500}), flush=True)\n")
            recognizer.chmod(0o755)
            self.main("--base-url", "https://b", "--call-id", "c7", "--live", "--camera", "3",
                      "--bundle", "b.json", "--recognizer-python", str(recognizer), after=2)
        turn_id = self.transport.sent[0]["turn_id"]
        self.assertEqual(self.transport.sent, [chips(turn_id, "hello"),
                                               chips(turn_id, "hello", "doctor"), {"type": "end"}])

    def test_log_option_writes_the_whole_session_under_artifacts_lab(self):
        with TemporaryDirectory() as folder, patch.object(mb, "ARTIFACTS", Path(folder)):
            recognizer = Path(folder, "python")
            rows = [{"sign": "hello", "top": [{"sign": "hello", "similarity": 0.9}], "margin": 0.4},
                    {"sign": None, "failed_checks": ["margin"]}, {"sign": "doctor"}]
            recognizer.write_text(f"#!{sys.executable}\nimport json\n"
                                  f"for row in {rows!r}:\n    print(json.dumps(row), flush=True)\n")
            recognizer.chmod(0o755)
            self.transport.push(type="caption", text="Hello, clinic.", at=0.5)
            self.main("--base-url", "https://b", "--call-id", "c7", "--live",
                      "--recognizer-python", str(recognizer), "--log", after=2)
            [path] = Path(folder, "lab").glob("session-*.jsonl")
            entries = read_log(path)
        self.assertIn(f"session log: {path}", self.lines)
        self.assertEqual((entries[0]["from"], entries[0]["message"]),
                         ("bridge", {"type": "connected", "call_id": "c7"}))
        by_source = {}
        for entry in entries:
            by_source.setdefault(entry["from"], []).append(entry["message"])
        self.assertEqual(by_source["recognizer"], rows)
        self.assertEqual(by_source["backend"], [{"type": "caption", "text": "Hello, clinic.", "at": 0.5}])
        self.assertEqual([m["type"] for m in by_source["bridge"]], ["connected", "chips", "chips", "end"])
        self.assertTrue(any(line.endswith("? unsure  (low margin)") for line in self.lines))

    def test_log_outside_artifacts_is_refused_before_any_request(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self.main("--base-url", "https://b", "--call-id", "c7", "--log", "/tmp/session.jsonl")
        self.assertEqual((self.posts, self.connects), ([], []))

    def test_without_log_nothing_is_written(self):
        with TemporaryDirectory() as folder, patch.object(mb, "ARTIFACTS", Path(folder)):
            self.main("--base-url", "https://b", "--call-id", "c7")
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_backend_errors_exit_nonzero_without_the_token(self):
        def refuse(url, body, headers):
            raise mb.BackendError("POST /calls returned HTTP 403: not on allowlist")

        self.post = refuse
        code = self.main("--base-url", "https://b", "--contact", "clinic", "--confirm-cost")
        self.assertEqual(code, 1)
        self.assertEqual(self.lines[-1], "! POST /calls returned HTTP 403: not on allowlist")
        self.assertEqual(self.connects, [])

    def test_missing_token_and_bad_url_fail_before_any_request(self):
        with self.assertRaises(SystemExit):
            self.main("--base-url", "https://b", "--call-id", "c7", env={})
        with self.assertRaises(SystemExit):
            self.main("--base-url", "https://b", "--call-id", "c7", env={"APP_TOKEN": ""})
        for url in ("ftp://b", "b.example", "https://b?x=1"):
            with self.subTest(url=url), self.assertRaises(SystemExit):
                self.main("--base-url", url, "--call-id", "c7")
        self.assertEqual((self.posts, self.connects), ([], []))

    def test_http_error_is_reported_without_the_auth_header(self):
        error = urllib.error.HTTPError("https://b/calls", 401, "Unauthorized", {},
                                       io.BytesIO(b'{"detail":"invalid token"}'))
        with patch("urllib.request.urlopen", side_effect=error) as urlopen, \
                self.assertRaises(mb.BackendError) as caught:
            mb.post_json("https://b/calls", {}, mb.auth_headers(TOKEN))
        self.assertEqual(urlopen.call_args.args[0].get_header("Authorization"), f"Bearer {TOKEN}")
        self.assertEqual(str(caught.exception),
                         'POST /calls returned HTTP 401: {"detail":"invalid token"}')


if __name__ == "__main__":
    unittest.main()
