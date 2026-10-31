"""Offline lifecycle simulation. No camera, recognizer, TTS, calls or actual captions.

Phone/WhatsApp are scenario labels, not implementations of platform transports.
"""
import json

FIXTURES = {'ask_time': 'What time is available?', 'repeat': 'Please repeat that.'}


class MockSession:
    def __init__(self, app):
        if app not in ('Phone', 'WhatsApp'):
            raise ValueError('Use a supported scenario label.')
        self.app = app
        self.state = 'waiting'
        self.sequence = 0
        self.pending_text = None
        self.delivered = []
        self.captions = []
        self.partial_caption = ''
        self.events = []

    def log(self, event, **fields):
        self.events.append({'event': event, **fields})

    def sign(self, fixture):
        if self.state != 'waiting':
            return None
        text = FIXTURES.get(fixture)
        if text is None:
            self.log('unrecognized_fixture_no_speech')
            return None
        self.sequence += 1
        self.pending_text = text
        self.state = 'generating'
        self.log('synthetic_sign_resolved', turn=self.sequence, text=text)
        return self.sequence

    def audio_ready(self, turn):
        if turn != self.sequence or self.state != 'generating':
            return False
        self.state = 'playing'
        self.log('mock_audio_ready', turn=turn)
        return True

    def playback_finished(self, turn):
        if turn != self.sequence or self.state != 'playing':
            return False
        self.delivered.append(self.pending_text)
        self.pending_text = None
        self.state = 'waiting'
        self.log('mock_playback_completed', turn=turn)
        return True

    def caption(self, text, *, final):
        if self.state == 'ended':
            return False
        self.partial_caption = '' if final else text
        if final:
            self.captions.append(text)
        self.log('mock_caption', text=text, final=final)
        return True

    def cancel(self):
        if self.state == 'ended':
            return
        self.sequence += 1  # Late results from an older turn are invalid now.
        self.pending_text = None
        self.state = 'waiting'
        self.log('mock_clear')

    def provider_failed(self, turn):
        if turn == self.sequence and self.state == 'generating':
            self.cancel()
            self.log('mock_provider_error_no_speech')

    def disconnect(self):
        self.cancel()
        self.state = 'ended'
        self.partial_caption = ''
        self.log('mock_session_ended')


def demo():
    sessions = []
    for app in ('Phone', 'WhatsApp'):
        session = MockSession(app)
        turn = session.sign('ask_time')
        session.audio_ready(turn)
        session.playback_finished(turn)
        session.caption('There is a slot', final=False)
        session.caption('There is a slot at four.', final=True)
        cancelled = session.sign('repeat')
        session.cancel()
        stale_result_accepted = session.audio_ready(cancelled)
        session.disconnect()
        sessions.append({'scenario_label': app, 'events': session.events,
                         'stale_result_accepted': stale_result_accepted})
    print(json.dumps({'simulation_only': True, 'bolna_invoked': False,
                      'platform_compatibility_tested': False, 'sessions': sessions}, indent=2))


if __name__ == '__main__':
    demo()
