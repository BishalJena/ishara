# Video-to-voice pipeline on public ISL videos

Executed 24 October 2026 on the development Mac. This is a **cross-signer check of the
pipeline mechanics**, not a measurement of demo accuracy: the production recognizer is
personalised (its references are the presenting signer's own Sign Lab takes), while here
every reference and every test clip comes from other people.
[Runbook](../../spikes/recognition/README.md) · [Recognition record](recognition.md) ·
[Plan](../../PLAN.md)

```
silent public clip ─▶ legacy Holistic ─▶ detector cut ─▶ SignCLIP ─▶ bundle rank + decision ─▶ chip or ?
                                                                                                │ chips only
receptionist line ───────────────────────────────────────────────────────▶ production composer ◀┘
                                                                         (Groq → validator → template)
                                                                                    │ draft
                                                                                    ▼
                                                                          Sarvam Bulbul v4 WAV
```

## Headline

- **Recognition: 0 of 24 clips from other channels produced a chip** (set A). Nothing
  wrong was accepted either: 22 clips gave `?`, 2 gave no accepted segment. SignCLIP did rank the
  right sign first for **14 of 22** segments, but at similarities of 0.70–0.88, far below
  the frozen cut-off of 0.926.
- Held-out INCLUDE signers (set B, same studio as some references): **4 of 18 correct
  chips, 1 wrong chip** (today → tomorrow), 12 `?`, 1 no segment; right sign ranked first
  for 13 of 17 segments.
- **All five conversation turns stayed silent**: every sign was `?` (or rejected), so no
  chip reached the composer and nothing was spoken. That is the pipeline's safety rule
  working, not a crash.
- **Composer on the ground-truth chips (oracle)**: 9 of 12 drafts came from Groq and
  passed the validator; 2 Groq drafts were rejected and 1 timed out, and the templates
  covered them. The three demo-script turns (T1, T3, T5) read naturally and fit the
  receptionist's line. One accepted draft added an agreement nobody signed (P6).
- **Voice**: 8 Sarvam WAVs, 1.5–4.2 s long, 0.65–1.08 s to synthesise; playback with
  `afplay` worked.
- Sign end → result latency **p50 466 ms, p95 469 ms** (live-paced replay; 400 ms of that
  is the detector waiting for hands to rest).

## Sources and acknowledgements

Media was downloaded on 24 October 2026 for local evaluation only, under the ignored
`spikes/recognition/artifacts/video_eval/`. Nothing was committed or redistributed.
Per-clip records (URL, channel, title, terms, download date, label evidence) are in
[`evidence/video-pipeline-eval/sources.json`](evidence/video-pipeline-eval/sources.json).
All our own outputs (per-clip results, scores, turn results, composer drafts and the
Sarvam audio) are in [`evidence/video-pipeline-eval/`](evidence/video-pipeline-eval/README.md);
the source media and anything derived from it stays local.

| Role | Source | Terms |
|---|---|---|
| References (17 clips, all 12 signs) | **ISLRTC Indian Sign Language Dictionary** (Govt. of India, data.gov.in, till Jan 2024), via the re-encoded mirror [silentone0725/Indian_Sign_Language_Data.gov_Rencoded](https://huggingface.co/datasets/silentone0725/Indian_Sign_Language_Data.gov_Rencoded): Hello, Thank You (+ Sign 2), Yes (+ Sign 2), No (+ Sign 2), Sorry (+ Signs 2, 3), Doctor, Today, Tomorrow, Morning, Afternoon, Evening, Time | ISLRTC FAQ Q23: research, teaching and ISL technology use with acknowledgement, no resale ([ledger R15](../CLAIM-LEDGER.md)); the mirror is MIT |
| References (18) and test set B (18) | **INCLUDE** (AI4Bharat), [Zenodo 4010759](https://zenodo.org/records/4010759): folders Greetings/48. Hello, 55. Thank you; Jobs/87. Doctor; Days_and_Time/73. Today, 74. Tomorrow, 82. Morning, 83. Afternoon, 84. Evening, 86. Time (4 clips each) | CC-BY-4.0 ([ledger R16](../CLAIM-LEDGER.md)) |
| Test set A (24) | **Pragya Gupta**, [ISL 101 Basic Words 1](https://www.youtube.com/watch?v=VtbYvVDItvg) and [Basic Words 2](https://www.youtube.com/watch?v=lffGJ29IhZQ) | standard YouTube licence |
| Test set A | **Youth4Jobs Foundation**, [Basic ISL Greetings](https://www.youtube.com/watch?v=U5LSlcD8xPg) | standard YouTube licence |
| Test set A | **PHIN Deaf**: [Yes and No](https://www.youtube.com/watch?v=T9XE5O_7Bmw), [Tomorrow](https://www.youtube.com/watch?v=hTmhHDFUbTk), [Today](https://www.youtube.com/watch?v=Zb2h-pZpieY), [Morning](https://www.youtube.com/watch?v=4TuRjBpBoMM), [Afternoon](https://www.youtube.com/watch?v=m-pUXfAMixM), [Evening](https://www.youtube.com/watch?v=YPZ7o80wU9k), [Time](https://www.youtube.com/watch?v=mtjse9ZT1Fw), [Doctor](https://www.youtube.com/watch?v=qeI6-V8YAKw) | standard YouTube licence |
| Test set A | **DEAF ENABLED FOUNDATION**, [Time (ISL)](https://www.youtube.com/watch?v=F1EDartPuC8), chapters Morning, Afternoon, Evening | YouTube Creative Commons Attribution |

Thanks to ISLRTC, AI4Bharat (INCLUDE), Pragya Gupta, Youth4Jobs Foundation, PHIN Deaf
and Deaf Enabled Foundation. Looked at but not used: Satwant/Uppal Vlogs "5 Important
Words" (the signer talks and signs continuously, no rests), Arman Idreesi (side-on at a
whiteboard), Balaram Sharma (close-up, continuous), Goa Board of Education single-word
videos ("not available" to the downloader), the ISLRTC YouTube channel (likely the same
recordings as the dictionary references, so unusable as a test).

## Method

**Clips.** `video_eval.py prepare` cut 77 clips from a local spec: 35 references, 24
test clips from other channels (set A) and 18 test clips from INCLUDE signers who are not
among the references (set B). Each cut starts and ends at rest frames chosen by viewing
contact sheets, and is padded with 2.0 s of its first frame and 1.0 s of its last, the
rest a live user gives the detector. Test boundaries and exclusions were fixed before any
recognition ran. Excluded on purpose: explanatory holds longer than 4 s (Pragya's first
"sorry", her first "morning") and compound greetings ("good morning").

**Recognition**, exactly the live path, by importing `live_source`:
`replay_clips` (legacy Holistic, paced like a camera) → `LiveSource` (2 s rest
calibration, `detector` cut) → `signclip_features` + SignCLIP embedding → `Matcher`
(`recognition_data.rank` + `decision`) → `result_details`. Every detector segment,
the top 3, margin, decision, reason and latency are recorded per clip. A turn is one
`LiveSource` run over its clips in order, like `live_source.py --replay-videos`.

**References and frozen cut-offs.** Each reference clip went through the same replay;
its first accepted detector cut became the reference, like a Sign Lab take. For 5 of the
35 the detector cut nothing usable (two calibrations saw no shoulders; ISLRTC "yes" and
two INCLUDE "today" clips stay below the rest line), so their whole sign span was kept,
like `record_session.py --manual-stop`. Cut-offs came from `retrieval.leave_one_out` +
`provisional_policy` over these 35 references only, and were frozen into the bundle
before any test clip was replayed:

| Frozen value | Number |
|---|---|
| Similarity cut-off | **0.9264** |
| Margin over the runner-up | **0.0161** |
| Tracking minimums | pose ≥ 0.6, hands ≥ 0.2 (`recognition_data.QUALITY`) |
| Leave-one-out on the references | 4 of 35 accepted, 0 wrong, 31 abstained; right sign ranked first for 9 of 35 |
| References per sign | 2–4 (yes, no: 2; thankyou: 4; others 3) |

**Composition and voice.** `backend/scripts/compose_turns.py` sends each turn's chips
to `app.composer.build_composer` built from the real Groq key (`openai/gpt-oss-120b`,
1.5 s budget, validator, template fallback), purpose `doctor_appointment`,
`last_caption` = the receptionist line, and to `TemplateComposer`. An empty chip list
composes nothing. Because every recognised list was empty, the ground-truth chips
(oracle) were composed too, plus seven composition-only probes, and the oracle drafts
were voiced with `app.sarvam.SarvamTTS` into separate `-oracle` files.

## How cheating was prevented

| Rule | How it was enforced |
|---|---|
| Silent frames only | ffmpeg `-map 0:v:0 -an -sn -dn -map_metadata -1 -map_chapters -1`; `ffprobe` shows exactly one video stream in all 77 clips and no title tags. The recognizer reads MediaPipe landmarks only; no OCR, audio or transcript exists anywhere in the path. Burned-in captions (PHIN, Pragya, DEF, ISLRTC) stay in the pixels, but only the landmark tracker sees pixels. |
| No label leaks into the pipeline | Clips are `clip_001`–`clip_077` in a seeded shuffled order; the manifest refuses a `label` key or a non-neutral name (tested). Labels live in `labels.json`, read only by `bundle` (references) and `score`. `recognize` and `turns` take no labels. Turn truth sits in a separate file. |
| No clip is its own reference | References are ISLRTC dictionary entries plus five INCLUDE signers; set A comes from other channels; set B from four other INCLUDE signers. `assert_no_leakage` refuses any shared clip id, content hash, source video or signer, at `prepare` and again against the bundle's provenance before every `recognize`/`turns` run; `recognition_data.validate_records` checks session, source and hash across splits. A live query is ranked as id `live`, so `rank()`'s own exclusion can't catch a test clip inside the bundle; that's why the extra check exists. It fired once: grouping INCLUDE signers by file number put the same people on both sides, so signers were regrouped by appearance (clothing) before anything ran. |
| Cut-offs never tuned on test clips | Leave-one-out on the 35 references only, frozen into `bundle-provisional.json` before the first test replay and not changed afterwards. |
| No hand-edited chips | Chips are exactly the recognizer's accepted `sign` values; `?` never reaches the composer, so all turns composed nothing. Oracle drafts are labelled as such. |

## Recognition results

Set A, other channels and signers (24 clips):

| Sign | Clips | Correct accepted | Wrong accepted | Unsure (?) | No accepted segment |
|---|---:|---:|---:|---:|---:|
| hello | 5 | 0 | 0 | 5 | 0 |
| thankyou | 2 | 0 | 0 | 2 | 0 |
| yes | 2 | 0 | 0 | 2 | 0 |
| no | 2 | 0 | 0 | 1 | 1 |
| sorry | 2 | 0 | 0 | 2 | 0 |
| doctor | 1 | 0 | 0 | 1 | 0 |
| today | 1 | 0 | 0 | 1 | 0 |
| tomorrow | 1 | 0 | 0 | 1 | 0 |
| morning | 3 | 0 | 0 | 3 | 0 |
| afternoon | 2 | 0 | 0 | 2 | 0 |
| evening | 2 | 0 | 0 | 2 | 0 |
| time | 1 | 0 | 0 | 0 | 1 |
| **all** | **24** | **0** | **0** | **22** | **2** |

Set B, held-out INCLUDE signers (18 clips; yes, no and sorry are not in INCLUDE):

| Sign | Clips | Correct accepted | Wrong accepted | Unsure (?) | No accepted segment |
|---|---:|---:|---:|---:|---:|
| hello | 2 | 1 | 0 | 1 | 0 |
| thankyou | 2 | 0 | 0 | 2 | 0 |
| doctor | 2 | 0 | 0 | 2 | 0 |
| today | 2 | 0 | **1** | 1 | 0 |
| tomorrow | 2 | 0 | 0 | 1 | 1 |
| morning | 2 | 1 | 0 | 1 | 0 |
| afternoon | 2 | 1 | 0 | 1 | 0 |
| evening | 2 | 1 | 0 | 1 | 0 |
| time | 2 | 0 | 0 | 2 | 0 |
| **all** | **18** | **4** | **1** | **12** | **1** |

| | Set A | Set B |
|---|---|---|
| Accuracy (correct chip / clips) | 0 / 24 | 4 / 18 |
| Wrong chips | 0 | 1 (today → tomorrow, 0.933 vs 0.873) |
| Right sign ranked first (diagnostic, ignores the cut-off) | 14 / 22 segments | 13 / 17 segments |
| Top-1 similarity when right | 0.70–0.88 | 0.81–0.97 |
| Latency sign end → result, p50 / p95 | 466 / 469 ms | 464 / 468 ms |

What the misses say:

- **The cut-off is the wall, not the ranking.** With references from other signers, the
  leave-one-out procedure had to pick 0.926 to keep zero wrong accepts, and other
  signers' clips rarely reach that. This is the expected behaviour of a personalised
  recognizer fed impersonal references.
- **Near pairs:** today/tomorrow (the only wrong chip, and the closest pair in several other clips),
  doctor/time, hello/afternoon/morning, thankyou → evening for Pragya's variant.
- **Detector blind spots:** Pragya's yes/no are head-only (hands stay clasped), so her
  "no" cut nothing and her "yes" cut a small hand shift that ranked doctor. PHIN's "time"
  is the sign plus fingerspelled T-I-M-E: 4.0 s+ → `too_long`, dropped. An INCLUDE
  "tomorrow" cut nothing; two INCLUDE "today" references never rose above the rest line.
- Latency is well inside the 2 s budget on every segment.

## Turns

Turn chips came from the same clips as the isolated runs and gave the same results.

| Turn | Receptionist said | Signed (truth) | Recognizer showed (top-1 behind each ?) | Chips → draft |
|---|---|---|---|---|
| T1 | (call opening) | hello · doctor · tomorrow | ? (hello 0.88) · ? (doctor 0.71) · ? (tomorrow 0.70) | none → silent |
| T3 | "We have 4 pm tomorrow. Does that work?" | no · morning | ? (no 0.77) · ? (afternoon 0.71) | none → silent |
| T5 | "Yes, 10:30 tomorrow morning." | yes · thankyou | ? (yes 0.80) · ? (evening 0.79) | none → silent |
| X1 | "We have slots today and tomorrow. When would you like to come?" | today · evening | ? (today 0.78) · ? (evening 0.71) | none → silent |
| X2 | "Your appointment is booked for tomorrow." | sorry · time | ? (sorry 0.74) · time rejected (too long) | none → silent |

8 of 10 turn signs had the right top-1 match, but none cleared the cut-off, so the user
would have seen only `?` chips and had nothing to SEND. Contextual verdict for the
recognised path: **not applicable (silent)**; the safety rule held.

### Composer on the ground-truth chips (oracle)

| Turn | Chips | Draft (source, time) | Groq raw / validator | Keeps every chip, no invented fact? | Fits the receptionist? |
|---|---|---|---|---|---|
| T1 | hello · doctor · tomorrow | "Hello, I would like to book an appointment with the doctor tomorrow." (llm, 0.22 s) | passed | yes | **yes**: opening request |
| T3 | no · morning | "No, 4 pm doesn't work. Do you have any openings tomorrow morning?" (llm, 0.18 s) | passed | yes; 4 pm and tomorrow are hers | **yes** |
| T5 | yes · thankyou | "Yes, 10:30 tomorrow morning works. Thank you." (llm, 0.17 s) | passed | yes; 10:30 is hers | **yes**, word for word the PLAN script |
| X1 | today · evening | "Is there an appointment this evening?" (template, 1.50 s) | Groq slower than 1.5 s | "today" only implied by "this evening" | **partly**: answers "when" with a question |
| X2 | sorry · time | "Sorry, what time is available?" (template, 0.20 s) | "Sorry, I can't make that time." rejected: adds a refusal | yes | **yes**: asks for the missing time |
| P1 | hello · doctor · today · afternoon | "Hello, I'd like to see the doctor this afternoon." (llm) | passed | "today" folded into "this afternoon" | yes |
| P2 | no · evening, after "We have 11 am tomorrow…" | "No, 11 am doesn't work. Do you have any openings tomorrow evening?" (llm) | passed | yes | yes |
| P3 | yes, after "Can you come at 5:15 pm today?" | "Yes, 5:15 pm today works for me." (llm) | passed | yes | yes |
| P4 | time, after "We can see you tomorrow." | "What time can you see me tomorrow?" (llm) | passed | yes | yes |
| P5 | sorry, after "Could you repeat that, please?" | "Sorry." (template) | "Sorry, I didn't hear you clearly. Could you please repeat that?" rejected: refusal | yes | **partly**: a bare "Sorry." doesn't repeat anything (and "didn't hear you" was wrong for a Deaf caller anyway) |
| P6 | thankyou, after "You're booked for 10:30 tomorrow morning." | "Thank you, that works perfectly for me." (llm) | passed | **no**: adds an agreement nobody signed | partly |
| P7 | doctor · morning | "I'd like to book an appointment with the doctor. Do you have any openings in the morning?" (llm) | passed | yes | yes |

Template-only drafts for the demo turns: T1 "Hello, I'd like a doctor's appointment
tomorrow.", T3 "No, sorry, that doesn't work. Is there anything in the morning?", T5
"Yes, that works. Thank you." All safe; T5 loses the receptionist's 10:30.

So recognition, not composition, is what broke these turns: with correct chips, 9 of 12
drafts fit the context fully, 3 partly, and the validator stopped both Groq drafts that
added meaning, but not P6's added agreement.

## Voice

Sarvam `bulbul:v4-flash`, speaker `simran_en_customer`, 16 kHz WAV, files under
`spikes/recognition/artifacts/video_eval/audio/` (ignored). These are **oracle** drafts:
the recognised turns produced nothing to speak.

| File | Text | Length | TTS time |
|---|---|---:|---:|
| `T1-oracle.wav` | Hello, I would like to book an appointment with the doctor tomorrow. | 3.52 s | 0.98 s |
| `T3-oracle.wav` | No, 4 pm doesn't work. Do you have any openings tomorrow morning? | 3.84 s | 1.05 s |
| `T5-oracle.wav` | Yes, 10:30 tomorrow morning works. Thank you. | 4.24 s | 1.08 s |
| `X1-oracle.wav` | Is there an appointment this evening? | 1.76 s | 0.66 s |
| `X2-oracle.wav` | Sorry, what time is available? | 1.52 s | 0.65 s |
| `template-versions/T1-oracle-template.wav` | Hello, I'd like a doctor's appointment tomorrow. | 2.96 s | 0.97 s |
| `template-versions/T3-oracle-template.wav` | No, sorry, that doesn't work. Is there anything in the morning? | 4.00 s | 1.07 s |
| `template-versions/T5-oracle-template.wav` | Yes, that works. Thank you. | 2.96 s | 0.87 s |

`afplay T3-oracle.wav` played and exited 0. The three template versions come from a
first composer run in which a bug in the evaluation script's recording transport (a
gzip header passed on with an already decoded body) made every Groq call fail, so all
drafts fell back to templates. That bug is fixed with a regression test; X1 and X2 got
the same template text in both runs, so their audio is reused.

**Paid calls used:** Groq 17 of the 20 allowed (5 lost to the bug above, then 3 demo + 9
extra), Sarvam 8 of 8. No phone call, Bolna request or deploy.

## Limitations

- Tiny samples: 1–5 clips per sign; one signer stands for most of set A's time words.
  These are counts, not rates.
- The cut-offs came from leave-one-out over references by different signers, which is
  much harder than a Sign Lab session (one signer, minutes apart). They are provisional,
  not R3/Gate 2 values; no negatives (idle, transition, unsupported) were measured, so
  false chips on non-signs are unknown.
- The test boundaries and the padding (cloned first/last frames as the rest) are
  synthetic. Real users rest for real, and live camera framing differs from tutorials.
- ISL varies by region and teacher (Pragya teaches Delhi signs; her "thank you" and
  "morning" differ from ISLRTC/INCLUDE). A different variant is not an error by the
  signer, but the recognizer can't know it.
- INCLUDE signer identity was judged from clothing, and ISLRTC signers are unknown; a
  shared signer across sources can't be fully ruled out.
- No Deaf participant validated any of this; it says nothing about natural conversation.

## Next steps

1. Re-run the same harness with the founder's own takes as references (Sign Lab
   enrollment) and a separate recorded session as the test set: `video_eval.py prepare`
   accepts any local spec. That is the number that matters for the demo.
2. Keep "today" vs "tomorrow" apart on purpose in the founder's takes (the only wrong
   chip here, and the closest pair); consider a quick-reply for yes/no, since the
   hands-only detector misses head-only answers.
3. Look at the composer cases: thankyou → "that works" passed the validator (P6), and a
   Groq timeout dropped X1 to a weaker template.

## Reproduce

```sh
cd spikes/recognition
# local spec (sources, cuts, labels) at artifacts/video_eval/spec.json; media under artifacts/video_eval/raw/
artifacts/signclip/.venv/bin/python video_eval.py prepare
artifacts/signclip/.venv/bin/python video_eval.py bundle          # references only, frozen cut-offs
artifacts/signclip/.venv/bin/python video_eval.py recognize       # test sets A and B, live-paced
.venv/bin/python video_eval.py score
artifacts/signclip/.venv/bin/python video_eval.py turns --turns artifacts/video_eval/turns.json
cd ../../backend   # paid: Groq + Sarvam, capped
uv run python -m scripts.compose_turns --turns ../spikes/recognition/artifacts/video_eval/compose-input.json \
  --out ../spikes/recognition/artifacts/video_eval/compose.json \
  --audio-dir ../spikes/recognition/artifacts/video_eval/audio --env-file ../.env --voice-oracle
```
