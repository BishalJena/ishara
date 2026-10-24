# LocalAssets

Files the app loads for on-device recognition. They are personal recordings or large
models, so only this README is in Git (see `ios/.gitignore`). Xcode copies the whole
folder into the app; anything missing just turns that part off.

| File | From | Without it |
|---|---|---|
| `holistic_landmarker.task` | `ios/Packages/SignPipelineMediaPipe/Scripts/download_holistic_model.sh ios/Ishara/LocalAssets` | The recognition pipeline can't start (Get ready says why). Use `-IsharaRecognition scripted` |
| `SignCLIPEncoder.mlmodelc` or `SignCLIPEncoder.mlpackage` | `ml/coreml` conversion (PR #21). Compile once with `xcrun coremlcompiler compile SignCLIPEncoder.mlpackage .` to skip the first-launch compile | Every sign shows [?] |
| `recognition-bundle.json` | `retrieval.py export-bundle --encoder signclip` (PR #12), re-embedded with the iOS extractor for P3 | Every sign shows [?] |
| `SampleSigns/rest.mov` | 2–3 s of the signer's hands resting on the table | The simulator can't calibrate on Get ready |
| `SampleSigns/<name>.mov` (`.mp4`, `.m4v`) | Saved sign recordings, e.g. `hello_01.mov` | Nothing to replay in the simulator |

The Core ML encoder always runs on CPU+GPU: the FP16 package gives wrong embeddings
on the Neural Engine.
