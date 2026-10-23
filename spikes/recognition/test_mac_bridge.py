"""Mac bridge turn rules, sources and client; fake transport only, no network."""
import itertools
import unittest

import mac_bridge as mb


def ids():
    counter = itertools.count(1)
    return lambda: f"t{next(counter)}"


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
        with self.assertRaises(ValueError):
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
    def test_end_is_sent_once_and_blocks_everything_after(self):
        turn = state("hello")
        turn.on_draft("t1", "Hello.", "llm")
        self.assertEqual(turn.end(), {"type": "end"})
        self.assertIsNone(turn.end())
        self.assertEqual((turn.chips, turn.draft), ([], None))
        for action in (lambda: turn.add("yes"), lambda: turn.add(None), turn.remove_last,
                       turn.approve, lambda: turn.quick_reply("yes"),
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


if __name__ == "__main__":
    unittest.main()
