# SignCLIP encoder for Core ML (PLAN P1)

Converts the frozen multilingual SignCLIP pose encoder used by
[`spikes/recognition/signclip.py`](../../spikes/recognition/signclip.py) to
`SignCLIPEncoder.mlpackage` (ML Program, iOS 17+, FP16) and checks it against PyTorch.
Weights, clips, packages and evidence stay in ignored `ml/coreml/artifacts/`.
[Plan](../../PLAN.md) · [Measured ML results](../../docs/experiments/recognition.md)

> **Use `.cpuAndGPU` (or `.cpuOnly`) for the FP16 package.** On the Neural Engine
> (`.all`, `.cpuAndNeuralEngine`) it returns wrong embeddings (cosine 0.63–0.89 on
> this Mac). See [Neural Engine result](#neural-engine-result).

## Set up and run

Commands run from `ml/coreml` with Python 3.11 and `uv`. One venv holds the SignCLIP
pins plus coremltools, so the reference embeddings and conversion share one torch.

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
# SignCLIP source, ~2.6 GB checkpoint and the 11-clip public corpus (see its README):
(cd ../../spikes/recognition && ../../ml/coreml/.venv/bin/python setup_signclip.py \
  && ../../ml/coreml/.venv/bin/python fetch_clips.py)
.venv/bin/python fetch_parity_clips.py              # 36 more public INCLUDE clips
.venv/bin/python convert_signclip.py --precision fp16 fp32
.venv/bin/python parity.py                          # writes artifacts/parity.json
.venv/bin/python -m unittest -v test_contract
```

`fetch_clips.py` can leave an empty clip after a network error and then skip it on
rerun (issue #19); delete zero-byte files before retrying. The default list's
`Doctor/MVI_8875.MOV` is not in the published zips, so the corpus is 11 clips.

## I/O contract

| Name | Type | Meaning |
|---|---|---|
| input `features` | Float32 [1, 256, 609] | SignCLIP pose features per frame, after the same `preprocess_pose` normalization `signclip.extract` applies; zero-padded at the end |
| input `mask` | Float32 [1, 256] | 1 = real frame, 0 = padding |
| output `embedding` | Float32 [1, 768] | Raw pooled video embedding; L2-normalize before cosine matching |

Clips over 256 frames are rejected, never truncated; fewer than 4 frames are rejected
too, as in `signclip.embed`. [`contract.pad`](contract.py) builds both inputs.
Metadata records the SignCLIP source revision, checkpoint SHA-256 and precision.

The wrapper ([`convert_signclip.py`](convert_signclip.py)) reuses the loaded MMPT
modules and reproduces `MMFusionSeparate.forward_video`: video MLP → `[CLS] video
[SEP]` embeddings → 12 BERT layers → mean over real frames plus the video `[SEP]`.
Two deliberate details:

- Upstream always pads to 256 frames, so the video `[SEP]` sits at position 257 for every
  clip. The padded input *is* the original pipeline. A literally unpadded sequence
  moves `[SEP]` and is a different embedding (min cosine 0.9976), so it is not the reference.
- transformers builds the attention mask with float32 min, which overflows to −inf in
  FP16 and makes real-frame terms NaN. The wrapper uses −1e4. That still underflows
  `exp` to exactly 0, so PyTorch results are unchanged.

## Measured results

Run on 23 Oct 2026: Apple M4 Pro, macOS 26.5.1, Python 3.11.15, torch 2.14.1,
coremltools 9.0. coremltools warns that it was tested only up to torch 2.7; conversion
and the checks below still passed. The reference is `signclip.embed` on unpadded
features. Features come from **47/47 public INCLUDE clips** (11 corpus + 36 extra, 41–74
frames; none over 256, so none skipped).

| Package | Compute units | Min cosine | Mean cosine | Clips ≥ 0.999 | Top-1 agree | p50 | p95 |
|---|---|---|---|---|---|---|---|
| FP16 | CPU+GPU+ANE (`ALL`) | 0.632 | 0.810 | **0/47** | 39/47 | 7.0 ms | 7.1 ms |
| FP16 | CPU+ANE | 0.632 | 0.810 | 0/47 | 39/47 | 7.0 ms | 7.0 ms |
| FP16 | CPU+GPU | 0.9999997 | 0.9999998 | **47/47** | 47/47 | 10.9 ms | 11.0 ms |
| FP16 | CPU only | 0.99996 | 0.99998 | **47/47** | 47/47 | 18.4 ms | 19.2 ms |
| FP32 | CPU+GPU+ANE (`ALL`) | 1.0000000 | 1.0000000 | 47/47 | 47/47 | 12.3 ms | 12.5 ms |
| FP32 | CPU+ANE | 1.0000000 | 1.0000000 | 47/47 | 47/47 | 29.4 ms | 30.6 ms |
| FP32 | CPU+GPU | 1.0000000 | 1.0000000 | 47/47 | 47/47 | 12.3 ms | 12.5 ms |
| FP32 | CPU only | 1.0000000 | 1.0000000 | 47/47 | 47/47 | 29.5 ms | 31.0 ms |

- **Gate P1 (cosine ≥ 0.999 on every clip):** passed by FP16 on CPU+GPU or CPU only, and
  by FP32 on every compute-unit setting. Failed by FP16 whenever the Neural Engine is allowed.
- **Top-1 agreement:** each clip's leave-one-out nearest neighbour among the other 46.
  The bank is embedded by the same backend, as P3 will do. Labels match PyTorch on 47/47
  for the passing rows. As a side note, PyTorch's nearest neighbour has the clip's own
  label in 41/47 cases. That is diagnostic only, not a recognition result.
- **Wrapper (PyTorch, padded) vs `signclip.embed`:** min cosine 1.0000000. Random values
  in the padded frames change the output by exactly 0 (max abs difference 0.0).
- **Latency:** `predict` of one 68-frame clip from Python, 100 runs after 5 warm-ups.
  PyTorch CPU (4 threads) took a median of 37.2 ms (p95 38.5 ms). First package load:
  about 2 s with the ANE, 0.4–0.7 s otherwise. Package sizes: FP16 165 MB, FP32 330 MB.
- **Mac replay** (`retrieval.py replay --encoder signclip`, SignCLIP venv): 11/11
  clips embedded, top-1 5/6 scorable, as recorded before. Medians: 42.7 ms embedding,
  1.73 s landmark extraction per clip.

### Neural Engine result

The FP16 error on the ANE is not one bad op. Converting truncated wrappers on a real clip:
the first linear layer matches (cosine 0.999999), the ANE GELU alone drops to 0.9995,
and the error compounds through the BERT layers. Real-frame cosine is 0.9986 after layer
1, 0.994 after layer 3, 0.86 after layer 6 and 0.65 after layer 12.

None of these fixed it:

- mask penalty −1e4, −1e3 or −100;
- keeping softmax, GELU and LayerNorm in FP32 (`op_selector`): on synthetic inputs the ANE path stays at 0.60–0.87;
- an iOS 18 target.

`MLModelComparator` flagged the attention softmaxes and one GELU, but keeping those in
FP32 did not help. The cause is probably FP16 accumulation in the ANE's matmuls; that is
a hypothesis, not proven. Options for the app:

1. **Recommended:** ship the FP16 package with `MLModelConfiguration.computeUnits = .cpuAndGPU`.
   It passed and took 11 ms here.
2. Ship the FP32 package (330 MB). It passes with every setting, but FP32 never runs on
   the ANE, so it is CPU/GPU speed (12 ms here).

## Limits

- Features were extracted on the Mac (legacy `mp.solutions.holistic`, MediaPipe 0.10.21).
  The iOS Holistic Landmarker will produce different landmarks (PLAN P3). This shows that
  the *encoder* conversion is faithful. It does not show iOS-to-Mac recognition parity.
- Latency is Mac Python `predict` on an M4 Pro, not iPhone 17. iPhone ANE behaviour
  was not tested. Re-check cosine on the device/simulator with the chosen compute units
  before trusting `.all`.
- 47 public clips of 11 labels, all 41–74 frames. The > 256 rejection is covered by unit
  tests only. Similarities are not calibrated confidences.
