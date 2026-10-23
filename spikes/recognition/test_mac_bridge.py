"""Mac bridge turn rules, sources and client; fake transport only, no network."""
import asyncio
import itertools
import json
import unittest

import mac_bridge as mb


def ids():
    counter = itertools.count(1)
    return lambda: f"t{next(counter)}"


def chips(turn_id, *signs):
    return {"type": "chips", "turn_id": turn_id, "chips": list(signs)}


def approve(turn_id, text):
    return {"type": "approve", "turn_id": turn_id, "text": text}


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

    def test_ended_call_drops_pending_resend(self):
        turn = state("hello")
        turn.on_draft("t1", "Hello.", "llm")
        turn.approve()
        turn.on_ended()
        self.assertIsNone(turn.on_not_delivered("t1"))
        self.assertIsNone(turn.undelivered)
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
        self.bridge = mb.Bridge(self.transport, mb.TurnState(new_id=ids()), self.lines.append)

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
        self.assertIn("draft (template): Hello.   [s = SEND]", self.lines)
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
        self.assertIn("! not delivered (no confirmation), tap SEND again (s): Hello.", self.lines)
        await self.bridge.handle_line("s")
        self.assertEqual(self.transport.sent[-1], approve("t2", "Hello."))
        await self.server(type="spoken", turn_id="t2")
        self.assertEqual(self.lines[-1], "Delivered: Hello.")

    async def test_status_caption_and_error_are_shown(self):
        await self.server(type="status", state="speaking")
        await self.server(type="caption", text="We have 4 pm tomorrow.", at=1.0)
        await self.server(type="error", code="stale_turn", message="old turn")
        await self.server(type="mystery")
        self.assertEqual(self.lines, [
            "[status] speaking", "Speaking now...", "receptionist: We have 4 pm tomorrow.",
            "! backend error stale_turn: old turn", "(ignored unknown message type 'mystery')"])
        self.assertEqual(self.transport.sent, [])

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


if __name__ == "__main__":
    unittest.main()
