# Evidence: public ASL Signs model on ISL clips, Lifeprint ASL clips and the presenter (25 Oct 2026)

Our own outputs only. Clips, landmarks and the model file stay under the gitignored
`spikes/recognition/artifacts/`. Report: [../../asl-model-probe.md](../../asl-model-probe.md).

| File | What it is | Written by |
|---|---|---|
| `sign_to_prediction_index_map.json` | the model's 250 glosses (from the Hugging Face mirror, CC-BY corpus vocabulary) | copied |
| `manifest.json` | the 79 ISL clips: id, label, source (INCLUDE, ISLRTC, presenter webcam 20 Oct); paths relative to the artifacts dir | by hand |
| `isl-clips-results.json` | per clip: top-5 glosses with softmax probability, margin, and the demo-10-restricted top-1 (diagnostic only) for `raw` and `portrait` variants | `spikes/asl_probe/infer.py` |
| `manifest-lifeprint.json`, `lifeprint-results.json` | the 18 Lifeprint clips (11 YouTube videos, 7 GIFs; GIFs are 3–10 frames and not scorable) and their results incl. best 2 s window | `infer.py --window 2.0` |
| `parity-simulator-lifeprint.json` | 27 Oct: the 18 Lifeprint clips through the Mac path and the app's path in the iOS simulator: top-1, p, decision, tracking fractions, hand gaps, the Mac model on the app's landmarks | `spikes/asl_probe/parity.py` after `ios/IsharaTests/ASLParityHarness.swift` |
| `presenter-session-20261025.json` | the presenter's 55 live cuts: detector segment, latency, top-3, quality; `labels_inferred` are **not ground truth** (the session was free-form; labels inferred from page order and model output) | `spikes/asl_probe/live_probe.py` + by hand |
