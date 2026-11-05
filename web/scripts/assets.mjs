import {mkdir, copyFile, cp, access} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../..', import.meta.url));
const assets = path.join(root, 'web/public');
await mkdir(path.join(assets, 'models'), {recursive: true});
await mkdir(path.join(assets, 'mediapipe'), {recursive: true});
const model = path.join(root, 'ios/Ishara/LocalAssets/holistic_landmarker.task');
try {
  await access(model);
  await copyFile(model, path.join(assets, 'models/holistic_landmarker.task'));
} catch {
  // CI can build without large local weights. The camera then reports unavailability.
  console.warn('Holistic model is absent. See ios/Ishara/LocalAssets/README.md.');
}
await cp(path.join(root, 'web/node_modules/@mediapipe/tasks-vision/wasm'), path.join(assets, 'mediapipe/wasm'), {recursive: true});
