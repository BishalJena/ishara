# Gemini 4 Argon vs SignCLIP on the same ISL sign clips

Executed 24–25 October 2026 on the development Mac. One question, one experiment:
**if the same silent clip of one ISL word goes to Gemini 4 Argon and to our SignCLIP
recognizer, which one names the word more often, and how often is each wrong?**
This is a cross-signer test on public dictionary-style clips. It is not demo accuracy:
the demo recognizer is personalised to the presenting signer's own Sign Lab takes
(see [video-pipeline-eval.md](video-pipeline-eval.md)).
[Evidence](evidence/gemini-video-probe/README.md) · Code: `spikes/gemini_probe`, removed on 30 October (see git history)

```
                     same file, same sha256
public ISL clip ──▶ cut, silent, re-encoded, ──┬──▶ Gemini 4 Argon ─────────────▶ word | unsure ─┐
(INCLUDE, YouTube)   text OCR'd + pixelated    │    video + instruction + shuffled 93-word list    │
                                               │                                                   ├──▶ score.py ◀── answer key
                                               └──▶ SignCLIP embedding ─▶ nearest reference ─▶ top-1 / cut-off ┘
                                                    references: ISLRTC + Bridgeconn dictionaries only
```

## Headline

284 test clips, 93 words, 216 reference clips (SignCLIP only). Chance is 1 in 93 (1.1%).

| Clips | System | Correct (top-1) | Wrong | Unsure / abstain |
|---|---|---|---|---|
| **All 93 words** (284) | Gemini 4 Argon | **105 / 284 (37%)**, CI 32–43% | 179 / 284 (63%) | 0 / 284 (0%) |
| | SignCLIP raw top-1 | **35 / 284 (12%)**, CI 9–17% | 249 / 284 (88%) | 0 (always answers) |
| | SignCLIP with frozen cut-off | 0 / 284 | 0 / 284 | 284 / 284 (100%) |
| **12 demo words** (47) | Gemini 4 Argon | **25 / 47 (53%)**, CI 39–67% | 22 / 47 (47%) | 0 / 47 |
| | SignCLIP raw top-1 | **2 / 47 (4%)**, CI 1–14% | 45 / 47 (96%) | 0 |
| | SignCLIP with frozen cut-off | 0 / 47 | 0 / 47 | 47 / 47 (100%) |

CI = Wilson 95% interval. The 12-word rows are the same predictions, restricted to clips
whose true word is a demo sign; the list Gemini chose from was still all 93 words.

- **Gemini was clearly better at naming signs from strangers**: about 3× SignCLIP's
  top-1 on all words and 12× on the demo words. It got every clip right for hello (8/8),
  thank you (5/5), today (4/4), yes (2/2) and no (2/2).
- **Gemini never said "unsure"** (0 of 284) even though the prompt and the schema allowed
  it, and its confidence doesn't separate right from wrong: 168 of its 179 wrong answers
  came with confidence ≥ 0.9 (mean 0.94 wrong vs 0.97 right). A confidence cut-off of 0.9
  would remove 11 wrong answers and 2 right ones; 168 wrong would remain.
- **SignCLIP's frozen cut-off accepted nothing**, the same safe-but-silent result as the
  earlier cross-signer run. Raw top-1 collapsed onto a few words (pink 29×, tall 25×,
  god 22×).
- **Live-call cost of Gemini**: p50 **5.4 s**, p95 **15.8 s**, max 66 s per clip, and
  **$0.013** per clip (~₹1.1). SignCLIP: p50 1.6 s, p95 2.3 s on the Mac CPU for a whole
  clip, free and offline.
- Money spent: **$3.81** of the $10 budget.

## Sources and acknowledgements

Media was downloaded on 24–25 October 2026 for local research evaluation only, under the
gitignored `spikes/recognition/artifacts/gemini_probe/`. Nothing was committed or
redistributed. Every source URL that reached the probe is in
[`evidence/gemini-video-probe/sources.json`](evidence/gemini-video-probe/sources.json).

| Role | Source | Clips | Terms |
|---|---|---|---|
| Test (both systems) | **INCLUDE** (AI4Bharat), [Zenodo 4010759](https://zenodo.org/records/4010759), category zips read by range requests | 263 | CC-BY-4.0 ([ledger R16](../../CLAIM-LEDGER.md)) |
| Test (both systems) | YouTube single-word videos from the [earlier probe](video-pipeline-eval.md#sources-and-acknowledgements): **Pragya Gupta** ([1](https://www.youtube.com/watch?v=VtbYvVDItvg), [2](https://www.youtube.com/watch?v=lffGJ29IhZQ)), **Youth4Jobs Foundation** ([greetings](https://www.youtube.com/watch?v=U5LSlcD8xPg)), **PHIN Deaf** ([yes/no](https://www.youtube.com/watch?v=T9XE5O_7Bmw), [tomorrow](https://www.youtube.com/watch?v=hTmhHDFUbTk), [today](https://www.youtube.com/watch?v=Zb2h-pZpieY), [morning](https://www.youtube.com/watch?v=4TuRjBpBoMM), [afternoon](https://www.youtube.com/watch?v=m-pUXfAMixM), [evening](https://www.youtube.com/watch?v=YPZ7o80wU9k), [time](https://www.youtube.com/watch?v=mtjse9ZT1Fw), [doctor](https://www.youtube.com/watch?v=qeI6-V8YAKw)) | 21 | standard YouTube licence |
| References (SignCLIP only) | **ISLRTC Indian Sign Language Dictionary** (Govt. of India) via the re-encoded mirror [silentone0725/Indian_Sign_Language_Data.gov_Rencoded](https://huggingface.co/datasets/silentone0725/Indian_Sign_Language_Data.gov_Rencoded) | 117 | ISLRTC FAQ Q23: research, teaching, ISL technology with acknowledgement, no resale ([ledger R15](../../CLAIM-LEDGER.md)); mirror MIT |
| References (SignCLIP only) | **Bridgeconn ISL Bible (ISLV) Dictionary**, [bridgeconn/sign-dictionary-isl](https://huggingface.co/datasets/bridgeconn/sign-dictionary-isl) | 99 | CC-BY-SA-4.0 |

Thanks to AI4Bharat (INCLUDE), ISLRTC, Bridgeconn, Pragya Gupta, Youth4Jobs Foundation and
PHIN Deaf. Not used: the Deaf Enabled Foundation "Time" video (its sun, clock and sky
pictures show the time of day, which Gemini could read instead of the sign). Models:
Gemini 4 Argon (Google, Gemini API, `gemini-4-argon`) and SignCLIP (the pinned
multilingual checkpoint and MediaPipe Holistic features of the
[recognition spike](../../../spikes/recognition/README.md)).

## Method

**Words and splits** (`build_spec.py`, seed 20261025). A word qualifies when it has test
clips in INCLUDE or the YouTube set *and* reference clips in ISLRTC or Bridgeconn, and
isn't an English homograph whose dictionary entry may show another sense. Up to 3 test
clips per word, spread over INCLUDE file numbers to mix recording sessions; the 24
YouTube clips of the earlier probe were kept, minus the 3 Deaf Enabled Foundation ones. Result: **93 words** (all 12 demo words
included), **291 test cuts, 221 reference cuts**. Five reference cuts longer than 10 s
(SignCLIP's 256-frame limit) were skipped and 7 test clips were dropped for text (below):
**284 test clips** (76 words with 3, 9 with 2, 8 with 4–8; yes, no, sorry have 2 each,
YouTube only) and **216 references** (1–7 per word, every word has at least one).
Test clips are 1.5–5.0 s (median 2.5 s).

**Clips** (`prepare.py`). Each cut is re-encoded by ffmpeg to silent H.264 at 25 fps,
at most 720p, with `-an -sn -dn -map_metadata -1 -map_chapters -1` and bit-exact
headers, and named `c_` + 12 random hex characters. Two YouTube cuts were cropped and
the Deaf Enabled Foundation clips dropped because pictures next to the signer showed the
meaning. Then every frame of every test clip goes through Apple Vision OCR (below).

**Gemini 4 Argon** (`gemini_run.py`). One request per clip: the clip as inline video
(8 fps sampling, high resolution, about 5,600 video tokens), then the fixed instruction
with all 93 words in a fresh order per clip, and a JSON schema that only allows a list
word or `"unsure"` plus a confidence. Thinking level **low**, `store: false`, no system
prompt, no examples, 4 requests in parallel. The exact template is in
[`prompt_template.json`](evidence/gemini-video-probe/prompt_template.json):

> The video shows one person signing a single word in Indian Sign Language (ISL). The video
> has no sound. Which word is being signed? Choose exactly one word from the candidate list
> below. If you cannot tell, answer "unsure". Reply with JSON only: {"word": <one candidate
> exactly as written, or "unsure">, "confidence": <probability from 0 to 1 that your word is
> correct>}. Candidate words: …

**SignCLIP** (`signclip_adapter.py`, the recognition spike's code unchanged). MediaPipe
Holistic landmarks → SignCLIP embedding of the whole clip → cosine similarity to every
reference → per-word best → top-1. The cut-off rule (`recognition_data.decision`:
similarity, margin over the runner-up, tracking quality) was frozen by leave-one-out over
the 216 references only (208 queries, 4 accepted, 0 wrong): **similarity ≥ 0.713 and
margin ≥ 0.194**, written to `policy.json` before any test clip was embedded.

**Pilot and thinking level.** 5 test clips at thinking low ($0.065) and the same 5 at
thinking high ($0.114): both 2 of 5 right with identical outcomes per clip, while high
took 1.8× the money and up to 28 s per clip. So the full run stayed at low. (The pilot
clips are test clips; that choice was made on 5 of them and they stayed in the run.)
Gemini reported 0 thinking tokens at low on every request.

**Scoring** (`score.py`, stdlib only). The only code that opens the answer key. Outcome
per clip: correct, wrong, unsure (Gemini's "unsure" or SignCLIP below its cut-off), or
error (no valid answer: none happened). Rates come with counts, denominators and Wilson
95% intervals.

## Leakage checks

| Rule | How it was enforced / verified |
|---|---|
| Identical file to both systems | Both read the same `manifest.json` entry; each prediction carries the clip's sha256 and `score.py` refuses one that differs. 284/284 matched for both. |
| Silent, no metadata, re-encoded | ffmpeg flags above; `ffprobe` after the cut and again after blurring must show one video stream and only container boilerplate tags (`check_probe`), else `prepare.py` stops. |
| Neutral names, shuffled order | Random hex ids; the manifest order is a seeded shuffle; `load_manifest` refuses any label, word, source, url, title or dataset field (tested). |
| Burned-in text | Apple Vision read **every frame of all 291 test clips**: text in 205 of them (all 21 YouTube clips had their caption, e.g. "Hello", "Thank you", "PHIN DEAF"; INCLUDE clips showed background posters, and 15 of them had a token matching a candidate word, mostly "Time" on a poster, "you", "war"). Each text region was pixelated in every frame and the clip **re-read**; text that survived was added and blurred again, up to 3 rounds. **86 none, 198 blurred, 7 dropped** (text still readable after 3 rounds), **2 cropped** (pictures, before OCR). After blurring, no clip had text at confidence ≥ 0.5 or any candidate word. Audit: [`ocr_audit.json`](evidence/gemini-video-probe/ocr_audit.json). |
| Gemini sees only clip + instruction + list | `request_body` holds the video bytes, the template and the shuffled list; a test serializes the request and checks no id, `.mp4`, path, hash or answer appears. No uploads were needed (all clips < 15 MB, sent inline; the account had 0 files after the run). |
| No few-shot, closed list, strict JSON | No examples in the request; schema `{"word": enum[93 words + "unsure"], "confidence": 0–1}`; 284/284 answers parsed, 0 off-list. |
| Answer key read only by the scorer | Labels and provenance live in `key/`; `test_a_whole_query_never_opens_the_answer_key` patches `open` and fails if a Gemini query touches it. SignCLIP reads only `manifest.json` for test clips. |
| SignCLIP references from other signers and videos | References only from ISLRTC and Bridgeconn; tests only from INCLUDE and YouTube. `prepare.assert_disjoint` refuses any shared clip id, clip hash, source video, signer group, dataset, URL or raw-file hash, and `signclip_adapter.check_separation` checks ids, hashes and reference datasets again. |
| Cut-offs frozen on references only | Leave-one-out over references, written to `policy.json` before the first test embedding; raw top-1 and the cut-off result are both reported. |

## Results

### By dataset

| Clips | Gemini correct | SignCLIP top-1 correct |
|---|---|---|
| INCLUDE (263, 90 words) | 91 (35%, CI 29–41%) | 33 (13%, CI 9–17%) |
| YouTube (21, 12 demo words) | 14 (67%, CI 45–83%) | 2 (10%, CI 3–29%) |
| Demo words in INCLUDE (26) | 11 (42%) | 0 |

### The 12 demo words

| Word | Clips | Gemini correct | Gemini's wrong answers | SignCLIP top-1 correct |
|---|---:|---:|---|---:|
| hello | 8 | **8** | | 0 |
| thank you | 5 | **5** | | 0 |
| yes | 2 | **2** | | 0 |
| no | 2 | **2** | | 0 |
| today | 4 | **4** | | 0 |
| sorry | 2 | 1 | shirt | 0 |
| time | 3 | 2 | friday | 0 |
| afternoon | 4 | 1 | tall, hot, dream | 1 |
| doctor | 4 | 0 | time ×3, black | 0 |
| tomorrow | 4 | 0 | today ×2, red, you | 1 |
| morning | 5 | 0 | hello ×2, beautiful, ball, evening | 0 |
| evening | 4 | 0 | hello, green, wet, hot | 0 |
| **all** | **47** | **25** | | **2** |

Gemini also answered a demo word for 22 clips of other words, e.g. "hello" for king, new,
green, monday and god (it said "hello" 16 times, 8 of them right). In an app that turns
chips into speech, those are confident wrong chips.

### Described examples

- **Doctor → "time", 3 of 3 INCLUDE clips, confidence 0.95–0.99.** The ISL sign for
  doctor is commonly made at the wrist (taking a pulse), which looks like tapping a watch:
  a plausible, confident and wrong reading of the movement.
- **Father → mother and son → daughter, 3 times each.** Gemini picked the other member
  of the pair every time: it got the family relation and missed the detail that tells the
  two apart.
- **Tomorrow → today twice.** The same pair the earlier SignCLIP run confused.
- **Hello, thank you, yes, no: all right.** These are also widely used gestures outside
  ISL, so "Gemini knows ISL" is a stronger claim than this shows.
- **SignCLIP**: the right word's similarity was rarely the highest; top-1 similarities
  were 0.64–0.97 (median 0.86) with margins of at most 0.11, below the frozen 0.194, so the
  cut-off could never fire.

### Agreement (for a hybrid)

| | SignCLIP right | SignCLIP wrong |
|---|---:|---:|
| **Gemini right** | 15 | 90 |
| **Gemini wrong** | 20 | 159 |

Both gave the same word on 18 clips, 15 of them right; on the 47 demo-word clips they
never agreed. A "speak only when both agree" rule would have been 83% right but silent
on 266 of 284 clips and on every demo-word clip.

### Latency and cost

| | Gemini 4 Argon | SignCLIP |
|---|---|---|
| Per clip p50 / p95 / max | 5.4 s / 15.8 s / 65.8 s (26 clips > 10 s) | 1.6 s / 2.3 s / 3.2 s |
| What the time covers | request → answer over the internet, 4 requests in parallel, any retry inside | landmarks + embedding of the whole clip on the Mac CPU, offline |
| Money | $0.0130 per clip mean, $0.0237 max; $3.68 for 284 clips | free |
| Tokens | ~6,300 input per clip (5,600 video), ~32 output, 0 thinking | – |

Total spent on this experiment: **$3.81** (smoke $0.0096, full run incl. pilot $3.6838,
thinking-high pilot $0.1138), per request in
[`gemini_cost_log.jsonl`](evidence/gemini-video-probe/gemini_cost_log.jsonl).

## Limitations

- **Cross-signer, isolated words, mostly one studio.** 263 of 284 test clips are INCLUDE
  studio recordings; only 1–8 clips per word (yes, no and sorry: 2 each, YouTube only).
  Intervals are wide, especially per word.
- **SignCLIP is handicapped here the same way as in production it is not**: its
  references are other people from dictionaries, one to seven per word, and it embeds the
  whole clip instead of a detector cut. The demo uses the presenting signer's own takes;
  that number (L10) is still unmeasured. Don't read 12% as demo accuracy.
- **Possible training-data overlap.** INCLUDE has been public since 2020 and the YouTube
  videos are public; Gemini may have seen them. That can't be ruled out from outside.
- **Pixelated captions still have a shape.** On the YouTube clips the blurred caption
  block shows roughly how long the word is. OCR could not read any of them after
  blurring. Gemini did better on YouTube (67%) than on INCLUDE (35%); the YouTube clips
  are all demo words and include every yes, no and sorry clip and 5 of the 8 hello
  clips, so the two sets aren't comparable word for word.
- **93 words in the list.** The app would ask about 12; both systems would likely do
  better with a 12-word list. That condition was not run.
- One Gemini run at the default sampling; answers may vary between runs. Latency was
  measured with 4 parallel requests from the development Mac's connection in India.
- The thinking level was chosen on 5 test clips (identical results at low and high).
- No Deaf participant validation; isolated-sign results say nothing about natural
  conversation or usability.

## Recommendation for Ishara

**Keep SignCLIP (personalised) as the live recognizer for the demo. Don't put Gemini in
the live call path.** Reasons, from this run:

1. **It breaks the "unsure stays silent" rule.** Gemini never abstained and its
   confidence doesn't tell right from wrong, so there is no safe gate: 63% of its answers
   were wrong, almost all at ≥ 0.9 confidence, and it produced demo-word chips for
   non-demo signs ("hello" for king, monday, god). SEND still guards speech, but the user
   would be correcting wrong chips mid-call.
2. **Too slow for turn-taking.** 5.4 s median and 15.8 s p95 per sign, on top of the
   composer and voice, versus a sub-second live SignCLIP path ([466 ms p50](video-pipeline-eval.md#headline)).
   Asked one sign at a time, a 3-sign turn would wait about 16 s at the median, ~47 s at p95.
3. **Internet and money on every sign.** ~₹1.1 per sign and a dependency on a second
   cloud API during a call that already depends on Bolna; a network drop means no chips.

**Where Gemini is worth it**: it is far better than SignCLIP *across signers* (37% vs
12%; 25 vs 2 of 47 demo-word clips). That makes it a good **offline helper**: checking
or labelling Sign Lab takes and public clips, or suggesting which public clips to use as
extra references. A **hybrid** (Gemini only when SignCLIP is unsure, shown as a
suggestion the user must tap) is possible after the demo, but this run argues against
it for now: the agreement rule never fired on demo words, and Gemini's own confidence
can't be used as the gate. If tried, test it with a 12-word list on the presenting
signer's own clips, measure latency on the phone's network, and keep the suggestion
off by default.
