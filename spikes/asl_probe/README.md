# ASL model probe

Tools behind [docs/experiments/asl-model-probe.md](../../docs/experiments/asl-model-probe.md):
the public Kaggle ASL Signs 1st-place model (11 MB TFLite, 250 glosses), used as is, on saved
clips and on the webcam behind the recognition spike's start/stop detector. Nothing here trains,
uploads, speaks or calls.

Two Python environments, on purpose: landmarks come from `spikes/recognition/.venv` (MediaPipe
0.10.21, uv-managed, no pip); the model runs in `spikes/recognition/artifacts/asl_signs/.venv`
(`ai-edge-litert`, `numpy`). `asl_model.AslModel` bridges them with a stdin/stdout subprocess.

| File | Runs in | What |
|---|---|---|
| `extract.py` | recognition `.venv` | clips → `[T, 543, 3]` landmarks in the Kaggle layout (face, left hand, pose, right hand; NaN = missing) |
| `infer.py` | asl_signs `.venv` | whole-clip scoring, optional sliding windows, per-word tables; never restricts the softmax to the vocabulary before thresholding |
| `model_server.py`, `asl_model.py` | asl_signs / recognition | the TFLite behind a one-request-at-a-time pipe; `kaggle_frame(result)` and `quality()` helpers |
| `live_probe.py` | recognition `.venv` | guided webcam session: banner says which word to sign, detector cuts the sign, model scores it, `.npy` + `.mp4` per cut, `records.json`, per-word summary; `--portrait` simulates a phone front camera |
| `offline_analysis.py` | asl_signs `.venv` | re-score saved cuts: TTA, repeat accumulation, 9:16 crop, 15/60 fps, latency |
| `teach.py` | any python3 | writes `artifacts/teach.html`, the lesson page (local clips only) |
| `parity.py` | recognition `.venv` | Mac path vs the app's path (from `ios/IsharaTests/ASLParityHarness`) on the same clips: top-1, decisions, landmark gaps, mirrored-hand frames, the Mac model on the app's landmarks, and for each disagreement the landmark part whose swap flips it |
| `public_clips.py` | python3 / recognition `.venv` | Run 5 data: public per-word ASL clips (Lifeprint, ASL Signbank, SignASL.org dictionaries) fetched, converted to H.264 landscape and 9:16 portrait, and rest-only negatives cut, with a manifest; local evaluation only |

Tests: `cd spikes/asl_probe && ../recognition/.venv/bin/python -m unittest test_parity test_public_clips` (numpy only).

Per-word summaries, the gate check and threshold suggestions for a labelled session (live probe
records, one clip per attempt, or the app path's output) are in
[`spikes/recognition/asl_summary.py`](../recognition/asl_summary.py), next to the bundle it freezes.

Setup and the exact commands are in the experiment record's *Reproduce* section. Everything the
scripts download or write lives under the gitignored `spikes/recognition/artifacts/`.
