# LocalAssets

Files the app loads for on-device recognition. They are personal recordings or large
models, so only this README is in Git (see `ios/.gitignore`). Xcode copies the whole
folder into the app; anything missing just turns that part off.

| File | From | Without it |
|---|---|---|
| `holistic_landmarker.task` | `ios/Packages/SignPipelineMediaPipe/Scripts/download_holistic_model.sh ios/Ishara/LocalAssets` | The recognition pipeline can't start (Get ready says why). Use `-IsharaRecognition scripted` |
| `asl-signs.tflite` | `ios/Packages/SignPipelineLiteRT/Scripts/download_asl_model.sh ios/Ishara/LocalAssets` (the public ASL Signs 1st-place model, decision D8; its thresholds are the committed `Resources/asl-bundle.json`) | The app falls back to the SignCLIP files below |
| `SignCLIPEncoder.mlmodelc` or `SignCLIPEncoder.mlpackage` | `ml/coreml` conversion (PR #21). Compile once with `xcrun coremlcompiler compile SignCLIPEncoder.mlpackage .` to skip the first-launch compile | Without the ASL model too: every sign shows [?] |
| `recognition-bundle.json` | `retrieval.py export-bundle --encoder signclip` (PR #12), re-embedded with the iOS extractor for P3. The Sign Lab's `--provisional` try bundle is refused | Without the ASL model too: every sign shows [?] |
| `SampleSigns/rest.mov` | Both hands in view at some point, then at least 2 s of hands at rest (see below) | The simulator can't calibrate on Get ready |
| `SampleSigns/<name>.mov` (`.mp4`, `.m4v`) | Saved sign recordings, e.g. `hello_01.mov` | Nothing to replay in the simulator |
| `SampleSigns/expected.csv`, `app-expected.csv` | The labels for `RecognitionReplayUITests` (see below) | That opt-in UI test can't run |

The Core ML encoder always runs on CPU+GPU: the FP16 package gives wrong embeddings
on the Neural Engine.

## Building a sample set from public ASL clips

For simulator checks of the whole in-app chain (Get ready → detector → ASL model → chip,
"Did you mean …?" or `?`). Third-party clips are for local evaluation only: never commit them.

1. **Clips.** Lifeprint / ASL University (Bill Vicars) per-word videos: the YouTube ids on each
   `lifeprint.com/asl101/pages-signs/<letter>/<word>.htm` page, and the Lifeprint dictionary
   channel ("Signs") for words a page lacks, such as HELLO. No ASL Citizen. Fetch at ≤ 480p:
   `yt-dlp -f "bv*[height<=480][vcodec^=avc1]/bv*[height<=480]" -o "<word>_<id>.%(ext)s" <url>`.
2. **Convert** to H.264 without audio (the simulator can't decode VP9):
   `ffmpeg -i in.mp4 -c:v libx264 -pix_fmt yuv420p -an <word>_<n>.mp4`. For phone-like framing
   add a 9:16 centre crop: `-vf "scale=-2:480,crop=270:480"`. Name clips `<word>_<anything>`
   and negatives `none_<anything>`: the first word is the label `asl_summary.py` reads.
3. **Negatives:** ASL signs outside the bundle's `vocabulary` (it has 29 glosses, including
   drink, finish and sick, so those are not negatives) and a hands-down stretch.
4. **`rest.mov`.** Get ready needs a face, both hands in one frame and both shoulders before it
   records the 2 s calibration, and it sets the rest line just above the median wrist height
   it sees during those 2 s. So: both hands visible, then lowered, then ≥ 2 s of rest. In
   Lifeprint videos resting hands are below the picture, so wrists seen while they drop set the
   line (about 0.82); a clip whose hands linger mid-frame during the 2 s sets it far too high.
5. **Expected results.** Run the parity harness on the same folder, then write
   `expected.csv` next to the clips:

   ```sh
   TEST_RUNNER_ISHARA_PARITY_CLIPS=<clips> TEST_RUNNER_ISHARA_PARITY_OUT=/tmp/parity xcodebuild test \
     -project ios/Ishara.xcodeproj -scheme Ishara -destination 'id=<your simulator>' \
     -only-testing:IsharaTests/ASLParityHarness
   cd spikes/recognition && .venv/bin/python asl_summary.py --app /tmp/parity --csv <clips>/expected.csv
   ```

   The parity harness scores the whole clip; the app scores only what the detector cuts, so a
   few clips land elsewhere for a known reason (the cut drops hands-down frames, an attempt over
   4 s is rejected, a hand that is never tracked never starts a sign). List each one in
   `app-expected.csv` (`clip,app,reason`, app = `chip:<sign>`, `pick:<sign>`, `?` or `nothing`).
6. **Run.** Copy the folder to `SampleSigns/`, rebuild, play clips from **Replay a sign** with
   `-IsharaRecognition pipeline`, or run the opt-in UI test:

   ```sh
   TEST_RUNNER_ISHARA_REPLAY_CLIPS=$PWD/ios/Ishara/LocalAssets/SampleSigns xcodebuild test \
     -project ios/Ishara.xcodeproj -scheme Ishara -destination 'id=<your simulator>' \
     -only-testing:IsharaUITests/RecognitionReplayUITests
   ```

   It checks every clip against the expected result, that one sign gives one result, that no
   negative becomes a chip, and that replayed signs feed the Call-for-me brief and answer the
   agent's question. Export the screenshots with
   `xcrun xcresulttool export attachments --path <result>.xcresult --output-path <dir>`.
