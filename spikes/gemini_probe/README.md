# Gemini 4 Argon vs SignCLIP probe

One experiment: the same silent ISL word clips go to Gemini 4 Argon (video + a closed
word list, answer one word or "unsure") and to SignCLIP (embedding + nearest reference
from other datasets). Both are scored against a hidden answer key.
Report: [docs/experiments/gemini-video-probe.md](../../docs/experiments/gemini-video-probe.md).

```
sources.py ──▶ build_spec.py ──▶ prepare.py ──┬──▶ gemini_run.py ──────┐
(index/fetch)  (words, splits)   (cut, OCR,   │    (paid, budget cap)  ├──▶ score.py
                                  manifests)  └──▶ signclip_adapter.py ┘    (reads the key)
```

Everything local goes to `spikes/recognition/artifacts/gemini_probe/` (gitignored):
raw media, clips, manifests, the answer key and run outputs. Only our own outputs are
copied to `docs/experiments/evidence/gemini-video-probe/`.

## Setup

```sh
cd spikes/gemini_probe
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.lock
```

SignCLIP runs in the recognition spike's SignCLIP venv
(`../recognition/artifacts/signclip/.venv`, see `../recognition/README.md`).
OCR uses Apple Vision, so `prepare.py` needs macOS.

## Run

```sh
.venv/bin/python sources.py index                       # INCLUDE zip listings, ISLRTC mirror tree (~3 min)
.venv/bin/python sources.py bridgeconn --words <json>   # streams ~5 GB once, keeps wanted words
.venv/bin/python build_spec.py --tests-per-word 3 --max-words 500
.venv/bin/python sources.py fetch                       # ISLRTC files + INCLUDE members (Zenodo is slow)
.venv/bin/python prepare.py --workers 6                 # cut, re-encode, OCR every frame (~15 min), manifests
../recognition/artifacts/signclip/.venv/bin/python signclip_adapter.py   # free, ~1 s per clip
.venv/bin/python gemini_run.py --limit 5 --cap-usd 10   # PAID pilot: read the cost log first
.venv/bin/python gemini_run.py --cap-usd 10             # PAID full run, resumes after the pilot
python3 score.py --out-dir ../../docs/experiments/evidence/gemini-video-probe
python3 evidence.py --out ../../docs/experiments/evidence/gemini-video-probe   # our outputs only
```

`gemini_run.py` reads `GEMINI_API_KEY` from the repo root `.env` (in a worktree without
one, set `ISHARA_ENV_FILE` to the main checkout's) into its own process only. It
refuses to start a call when spent money plus the worst case of the calls in flight
would pass `--cap-usd`, and the cap counts earlier runs in the same `--out-dir` (from
`cost_log.jsonl`). The cap is per `--out-dir`: a pilot in another folder (e.g.
`--thinking high --out-dir .../runs/pilot_high`) needs its own small cap.

## Leakage rules (enforced in code)

- Gemini's manifest has neutral ids, paths and hashes only (`load_manifest` refuses label
  or source fields); the answer key and provenance live in `key/`, read only by `score.py`.
  `test_gemini_run` fails if a query opens the key.
- `prompt.py` has no file access; the request is the clip, the fixed instruction and a
  freshly shuffled word list (tested field by field), structured JSON output, no examples.
- Clips: ffmpeg `-an -sn -dn -map_metadata -1`, bit-exact headers, 25 fps, ≤ 720p,
  random hex names, shuffled order; `ffprobe` must show one video stream and no
  descriptive tags. Apple Vision OCR reads every frame of every test clip; text is
  pixelated and re-read; a clip whose text survives is dropped.
- SignCLIP references come only from ISLRTC and Bridgeconn; test clips only from INCLUDE
  and YouTube (`prepare.assert_disjoint` on id, hashes, source, signer group, dataset,
  url). Cut-offs are frozen from references before any test clip is embedded.

## Tests

```sh
.venv/bin/python -m unittest test_prepare test_gemini_run test_score test_evidence
.venv/bin/python -m unittest test_signclip_adapter
```

No network, no key, no money: the Gemini client runs against a fake. The ffmpeg and
Apple Vision tests build synthetic clips and skip when the tool is missing.
