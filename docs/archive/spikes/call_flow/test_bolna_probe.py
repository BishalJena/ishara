import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import wave

from bolna_probe import ProbeFailure, audio_from_response, load_key, request_json


class ProbeTests(unittest.TestCase):
    def test_wave_metadata_comes_from_audio_not_assumed_provider_format(self):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b'\0\0' * 1600)
        payload = json.dumps({'data': base64.b64encode(buffer.getvalue()).decode()}).encode()
        data, info = audio_from_response(payload)
        self.assertEqual(data, buffer.getvalue())
        self.assertEqual(info['sample_rate'], 16000)
        self.assertAlmostEqual(info['duration_seconds'], 0.1)

    def test_rejects_error_json_and_non_audio_base64(self):
        for payload in (b'{"detail":"denied"}', b'{"data":"invalid base64"}',
                        b'{"data":"bm90IGF1ZGlv"}'):
            with self.subTest(payload=payload), self.assertRaises(ProbeFailure):
                audio_from_response(payload)

    def test_legacy_local_key_label_is_supported_without_echoing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / '.env'
            file.write_text('bolna_dev="synthetic-secret"\n')
            with patch.dict('os.environ', {}, clear=True):
                self.assertEqual(load_key(file), 'synthetic-secret')

    def test_http_error_never_includes_provider_body_or_key(self):
        secret = 'synthetic-secret'
        error = urllib.error.HTTPError('https://api.bolna.ai/user/tts_sample', 403,
                                      'Forbidden', {}, io.BytesIO(secret.encode()))
        with patch('urllib.request.OpenerDirector.open', side_effect=error):
            status, body = request_json(secret, '/user/tts_sample', {})
        self.assertEqual(status, 403)
        self.assertEqual(body, b'')

    def test_rejects_call_origination_routes(self):
        with self.assertRaises(ProbeFailure):
            request_json('synthetic-secret', '/call', {})


if __name__ == '__main__':
    unittest.main()
