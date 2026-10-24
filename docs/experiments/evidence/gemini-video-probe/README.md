# Evidence: Gemini 4 Argon vs SignCLIP on the same ISL clips (25 Oct 2026)

Our own outputs only. No video, frame, thumbnail or other third-party media is here;
the clips stay under the gitignored `spikes/recognition/artifacts/gemini_probe/`.
Clip ids (`c_` + 12 hex) are random and say nothing about the sign.
Report: [../../gemini-video-probe.md](../../gemini-video-probe.md).

| File | What it is | Written by |
|---|---|---|
| `results.json` | every metric: correct / wrong / unsure / error with n, denominator and Wilson 95% CI, for all clips, the 12 demo words and each dataset; Gemini confidence cut-offs (descriptive); per-word counts; top confused pairs; latency; cost; agreement between the systems | `score.py` |
| `per_clip.csv` | one row per test clip: truth, both systems' answers, outcomes, Gemini confidence, latency and cost, SignCLIP similarity and margin | `score.py` |
| `answer_key.json` | test clip id → true word (284 clips). Read only by `score.py` | `prepare.py` |
| `candidates.json` | the closed list of 93 words Gemini chose from (sorted here; shuffled per request) | `prepare.py` |
| `prompt_template.json` | the exact instruction template, the response JSON schema, and the prompt with the list sorted | `evidence.py` from `prompt.py` |
| `gemini_predictions.jsonl` | full run, thinking low: per clip the word, confidence, raw JSON answer (≤ 300 chars), token usage, cost, latency | `gemini_run.py` |
| `gemini_cost_log.jsonl` | running cost per request with the cumulative total (includes the 5-clip pilot) | `gemini_run.py` |
| `gemini_pilot_thinking_high_*.jsonl` | the same 5 pilot clips at thinking high, to decide the thinking level | `gemini_run.py --thinking high` |
| `gemini_api_smoke.json` | the first API call (synthetic test pattern, not a sign) | by hand |
| `signclip_predictions.json` | per clip the top 5 words with similarities, margin, the cut-off decision, tracking quality and CPU time | `signclip_adapter.py` |
| `signclip_policy.json` | the cut-offs frozen from the 216 references (leave-one-out) before any test clip was embedded | `signclip_adapter.py` |
| `ocr_audit.json` | per test clip: text Apple Vision read (strings only), regions pixelated, re-read result, action (none / blurred / dropped) | `prepare.py` |
| `sources.json` | every source URL that reached the probe, grouped by dataset with its terms; clips per dataset; references skipped as too long | `evidence.py` |

Rebuild after a re-run (from `spikes/gemini_probe/`):

```sh
python3 score.py --out-dir ../../docs/experiments/evidence/gemini-video-probe
python3 evidence.py --out ../../docs/experiments/evidence/gemini-video-probe
```

Money: $3.8072 in total (smoke $0.0096 + full run incl. pilot $3.6838 + thinking-high
pilot $0.1138), at $2 / 1M input and $10 / 1M output tokens.
