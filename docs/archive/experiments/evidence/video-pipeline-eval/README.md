# Evidence: video-to-voice pipeline evaluation (24 Oct 2026)

Raw outputs behind [the report](../../video-pipeline-eval.md). Only our own outputs are
kept here; the third-party sign videos, cut clips, frame sheets and the reference
embedding bundle stay local (they derive from ISLRTC, INCLUDE and YouTube media,
which we don't redistribute). Absolute local paths were shortened.

| File | What it is |
|---|---|
| `sources.json` | Every source video: URL, channel, title, terms note, download date (no media) |
| `spec.json`, `manifest.json`, `labels.json` | How clips were cut; neutral clip ids; ground-truth labels (used only for scoring and reference building) |
| `bundle-provenance.json`, `bundle-log.txt` | Which clips formed the reference bank; frozen leave-one-out thresholds |
| `results.json`, `recognize-log.txt` | Per-clip recognition: detector segments, top-3 similarities, margin, decision, latency |
| `score.json` | Per-sign and per-set counts (correct / wrong / unsure) |
| `turns.json`, `turn-truth.json`, `turn-results.json`, `turns-log.txt` | Conversation turns: recognised chips vs ground truth |
| `compose-*.json` | Composer inputs/outputs (Groq and template), validator outcomes, oracle (ground-truth chip) drafts |
| `audio/*.wav` | Sarvam voice of the oracle drafts (`template-versions/` = template-only drafts). Play with `afplay` |
