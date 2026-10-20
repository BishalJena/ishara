import unittest

from flow_mock import MockSession


class FlowTests(unittest.TestCase):
    def test_same_conversation_logic_for_both_simulated_call_labels(self):
        for app in ('Phone', 'WhatsApp'):
            with self.subTest(app=app):
                session = MockSession(app)
                turn = session.sign('ask_time')
                session.audio_ready(turn)
                session.playback_finished(turn)
                session.caption('There is a slot at four.', final=True)
                self.assertEqual(session.delivered, ['What time is available?'])
                self.assertEqual(session.captions, ['There is a slot at four.'])

    def test_cancelled_generation_cannot_deliver_a_late_response(self):
        session = MockSession('WhatsApp')
        turn = session.sign('ask_time')
        session.cancel()
        self.assertFalse(session.audio_ready(turn))
        self.assertFalse(session.playback_finished(turn))
        self.assertEqual(session.delivered, [])

    def test_cancel_during_playback_prevents_completion_and_allows_next_turn(self):
        session = MockSession('Phone')
        first = session.sign('ask_time')
        session.audio_ready(first)
        session.cancel()
        second = session.sign('repeat')
        self.assertFalse(session.playback_finished(first))
        session.audio_ready(second)
        session.playback_finished(second)
        self.assertEqual(session.delivered, ['Please repeat that.'])

    def test_unknown_sign_emits_no_speech(self):
        session = MockSession('WhatsApp')
        self.assertIsNone(session.sign('unknown'))
        self.assertEqual(session.state, 'waiting')
        self.assertEqual(session.delivered, [])

    def test_partial_caption_updates_without_creating_duplicate_turns(self):
        session = MockSession('Phone')
        session.caption('There is', final=False)
        session.caption('There is a slot at four.', final=True)
        self.assertEqual(session.partial_caption, '')
        self.assertEqual(session.captions, ['There is a slot at four.'])

    def test_disconnect_invalidates_pending_speech_and_captions(self):
        session = MockSession('WhatsApp')
        turn = session.sign('ask_time')
        session.disconnect()
        self.assertFalse(session.audio_ready(turn))
        self.assertFalse(session.caption('late reply', final=True))
        self.assertEqual(session.state, 'ended')

    def test_duplicate_playback_ack_does_not_duplicate_speech(self):
        session = MockSession('Phone')
        turn = session.sign('repeat')
        session.audio_ready(turn)
        session.playback_finished(turn)
        self.assertFalse(session.playback_finished(turn))
        self.assertEqual(len(session.delivered), 1)

    def test_provider_failure_clears_turn_and_cannot_succeed_later(self):
        session = MockSession('WhatsApp')
        turn = session.sign('repeat')
        session.provider_failed(turn)
        self.assertFalse(session.audio_ready(turn))
        self.assertEqual(session.state, 'waiting')
        self.assertEqual(session.delivered, [])


if __name__ == '__main__':
    unittest.main()
