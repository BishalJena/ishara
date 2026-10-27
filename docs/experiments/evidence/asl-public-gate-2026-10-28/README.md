# Evidence: Gate 2 on public ASL clips, Mac path vs app path (28 Oct 2026)

Backs [Run 5 of the ASL model record](../../asl-model-probe.md#run-5-gate-2-on-public-asl-clips-mac-path-vs-app-path-28-oct).
No clips are committed: they are third-party videos kept in the gitignored
`spikes/recognition/artifacts/T03/` for local evaluation only. Shipped rule throughout: the
provisional `ios/Ishara/Resources/asl-bundle.json` (p ≥ 0.6, margin ≥ 0.3, pick-one ≥ 0.35,
29-word vocabulary), which this run did not change.

| File | What | Made by |
|---|---|---|
| `manifest.json` | all 148 fetched clips: id (the clip's file stem), label, kind (`sign`, `negative-sign`, `negative-rest`), gloss, source, source key (YouTube id, Signbank gloss, dictionary file name), licence note, cut times for rest stretches, and the reason for the 6 set aside | `spikes/asl_probe/public_clips.py fetch / prep / rest` |
| `mac-landscape.json`, `mac-portrait.json` | the Mac path (legacy Holistic, a fresh tracker per clip → `asl-signs.tflite`): per-word rows, gate, single-run suggestion, and every attempt's top 5 and tracking quality | `asl_summary.py --clips … --name … --json` |
| `app-landscape.json`, `app-portrait.json` | the app path (Holistic Landmarker task → `KaggleLayout` → LiteRT on iOS, in the simulator) on the same clips | `IsharaTests/ASLParityHarness`, then `asl_summary.py --app … --json` |
| `combined.json` | the four runs judged together under the shipped rule: per-run rows, gates and totals, and one suggestion fitted on all of them | `asl_summary.py --combine` |
| `combined-candidate.json` | the same four runs under the candidate thresholds (global 0.65; per word hello 0.5, no 0.45, now 0.45, thankyou 0.6, tomorrow 0.45, wait 0.45, yes 0.5) | `asl_summary.py --combine --bundle <candidate>` |
| `combined-rehearsed.json` | what-if: the shipped thresholds with the vocabulary cut to the 9 rehearsed words | `asl_summary.py --combine --vocabulary …` |
| `parity-landscape.json`, `parity-portrait.json` | per clip: both paths' top-1, p and decision, the Mac model on the app's landmarks (runtime check), tracking fractions, face / hand / pose gaps, mirrored-hand frames, and for each disagreement the part swap that explains it | `spikes/asl_probe/parity.py` |

Counts: 110 sign clips (hello 9, thankyou 12, yes 16, no 16, now 10, please 10, tomorrow 12,
morning 10, wait 15; 6–10 sources per word) and 32 negatives (22 Signbank signs outside the
vocabulary, 10 rest stretches). Sources: Lifeprint / ASL University, ASL Signbank (CC BY-NC-SA
4.0), and the per-word dictionaries aggregated by SignASL.org (Start ASL, ASLsearch, Elemental ASL
Concepts, ASL Bricks, Marie Katzenbach School, Sign Language Student, TSD, Dictio, YouTube
channels). The portrait set is a centred 9:16 crop of the same frames, scaled to 360×640.

Not committed: the candidate bundle itself (it lives at
`spikes/recognition/artifacts/T03/asl-bundle-candidate.json`, `provisional: true`), the
landmark files, and the first Mac runs made before the per-clip tracker fix (they differed on
7 / 13 of 142 decisions in landscape / portrait).

Tracker experiment behind the fix (portrait `tomorrow_tsdvideo-684`): fresh tracker → tomorrow
0.8022, fresh tracker again → 0.8022 with identical landmarks, after `tomorrow_tsdvideo-1203` in
the same tracker → 0.3709 with all 109 frames different.
