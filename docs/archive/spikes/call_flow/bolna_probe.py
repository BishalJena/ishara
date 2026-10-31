"""Throwaway Bolna speech probe; never originates a call. Python standard library only.

The legacy sample API is a candidate under test, not a promised supported endpoint:
https://docs.bolna.ai/api-reference/voice/generate_tts
"""
import argparse
import base64
import binascii
import io
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(__file__).parent / 'artifacts'
PHRASES = {
    'initial': 'Hello. I would like to check an appointment time.',
    'second': 'Thank you. Please repeat the available time.',
    'long': 'Please give me a moment. I am reading your reply and signing my response. '
            'Please wait until I finish before you continue.',
}


class ProbeFailure(Exception):
    """A safe diagnostic that never contains a response body or credential."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward bearer credentials to a redirect target.
        return None


def load_key(path=ROOT / '.env'):
    key = os.environ.get('BOLNA_API_KEY')
    if not key and path.exists():
        values = {}
        for line in path.read_text().splitlines():
            name, sep, value = line.partition('=')
            if sep and not line.lstrip().startswith('#'):
                values[name.strip().removeprefix('export ')] = value.strip().strip('\"\'')
        key = values.get('BOLNA_API_KEY') or values.get('bolna_dev')
    if not key or any(character.isspace() for character in key):
        raise ProbeFailure('Missing or malformed Bolna key. No request sent.')
    return key


def request_json(key, route, payload=None):
    if (route, payload is None) not in {
        ('/me', True), ('/me/voices', True), ('/user/tts_sample', False)
    }:
        raise ProbeFailure('Route/method is outside the non-telephony probe allowlist.')
    request = urllib.request.Request(
        'https://api.bolna.ai' + route,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                 'User-Agent': 'Ishara-feasibility-spike/0.1'},
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise ProbeFailure('Response exceeds the probe size limit.')
            return response.status, raw
    except urllib.error.HTTPError as error:
        # Account/API errors can contain private identifiers. Do not print or save them.
        error.close()
        return error.code, b''
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProbeFailure('Network request failed; details withheld.') from None


def audio_from_response(raw):
    try:
        payload = json.loads(raw)
        data = base64.b64decode(payload['data'], validate=True)
        with wave.open(io.BytesIO(data)) as audio:
            frames = audio.getnframes()
            sample_rate = audio.getframerate()
            width = audio.getsampwidth()
            channels = audio.getnchannels()
            if frames <= 0 or len(audio.readframes(frames)) != frames * width * channels:
                raise ValueError('empty or truncated audio')
            info = {'format': 'wav', 'sample_rate': sample_rate, 'channels': channels,
                    'sample_width_bytes': width, 'duration_seconds': frames / sample_rate,
                    'audio_bytes': len(data)}
        return data, info
    except (KeyError, TypeError, ValueError, binascii.Error, wave.Error, EOFError):
        raise ProbeFailure('Response is not valid base64 WAV audio. No clip saved.') from None


def run(mode, phrase, destination):
    key = load_key()
    destination.mkdir(parents=True, exist_ok=True)
    report = {'mode': mode, 'native_call_tested': False, 'sign_recognition_tested': False,
              'return_captions_tested': False, 'requests': []}
    for route in ('/me', '/me/voices') if mode == 'check' else ('/user/tts_sample',):
        output = destination / (phrase + '.wav')
        # Remove a prior clip first, so a failed attempt cannot appear to have succeeded.
        if mode == 'speech':
            output.unlink(missing_ok=True)
        payload = None if mode == 'check' else {
            'text': PHRASES[phrase], 'provider': 'polly',
            'provider_config': {'voice': 'Kajal', 'engine': 'neural', 'language': 'en-IN'},
        }
        started = time.monotonic()
        status, raw = request_json(key, route, payload)
        result = {'route': route, 'status': status,
                  'response_complete_ms': round((time.monotonic() - started) * 1000)}
        if mode == 'speech' and status == 200:
            audio, info = audio_from_response(raw)
            output.write_bytes(audio)
            result.update(info)
            result['synthetic_text'] = PHRASES[phrase]
            result['cost'] = 'not supplied/verified'
        elif status != 200:
            result['blocked'] = True
        report['requests'].append(result)
    (destination / (mode + '-report.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if all(item['status'] == 200 for item in report['requests']) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('check', 'speech'))
    parser.add_argument('--phrase', choices=PHRASES, default='initial')
    parser.add_argument('--output', type=Path, default=ARTIFACTS)
    args = parser.parse_args()
    try:
        return run(args.mode, args.phrase, args.output)
    except ProbeFailure as error:
        print(json.dumps({'error': str(error)}))
        return 1
    except KeyboardInterrupt:
        print(json.dumps({'cancelled': True, 'note': 'Local wait stopped; server-side cancellation unverified.'}))
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
