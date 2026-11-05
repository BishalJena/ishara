import {FilesetResolver, HolisticLandmarker} from '@mediapipe/tasks-vision';

let tracker: HolisticLandmarker | null = null;
self.onmessage = async ({data}) => {
  if (data.type === 'init') {
    try {
      const origin = self.location.origin;
      const vision = await FilesetResolver.forVisionTasks(`${origin}/mediapipe/wasm`, true);
      tracker = await HolisticLandmarker.createFromOptions(vision, {
        baseOptions: {modelAssetPath: `${origin}/models/holistic_landmarker.task`, delegate: 'CPU'},
        runningMode: 'VIDEO', outputFaceBlendshapes: false, outputPoseSegmentationMasks: false,
        minPoseDetectionConfidence: .5, minPosePresenceConfidence: .5,
        minFaceDetectionConfidence: .5, minFacePresenceConfidence: .5,
        minHandLandmarksConfidence: .5,
      });
      self.postMessage({type: 'ready'});
    } catch (error) { console.error('Camera initialization failed:', error); self.postMessage({type: 'error', message: 'The camera model couldn’t load. Reload the page or type your reply.'}); }
    return;
  }
  if (data.type === 'frame' && tracker) {
    const bitmap = data.bitmap as ImageBitmap;
    try {
      const result = tracker.detectForVideo(bitmap, data.timestamp);
      const values = new Float32Array(543 * 3).fill(Number.NaN);
      const parts = [[result.faceLandmarks[0], 0, 468], [result.leftHandLandmarks[0], 468, 21], [result.poseLandmarks[0], 489, 33], [result.rightHandLandmarks[0], 522, 21]] as const;
      for (const [points, offset, count] of parts) {
        points?.slice(0, count).forEach((point, i) => values.set([point.x, point.y, point.z], (offset + i) * 3));
      }
      const pose = result.poseLandmarks[0];
      const shoulders = Boolean(pose?.[11] && pose?.[12] && (pose[11].visibility ?? 1) >= .5 && (pose[12].visibility ?? 1) >= .5);
      self.postMessage({type: 'frame', values, shoulders, hands: Number(Boolean(result.leftHandLandmarks[0]?.length)) + Number(Boolean(result.rightHandLandmarks[0]?.length))}, {transfer: [values.buffer]});
    } catch { self.postMessage({type: 'frame-error'}); }
    finally { bitmap.close(); }
  }
};
