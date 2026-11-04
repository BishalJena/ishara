package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.BodyOverlay
import ai.ishara.demo.recognition.NormalizedPoint
import ai.ishara.demo.recognition.landmarks.FrameSignals
import ai.ishara.demo.recognition.landmarks.LandmarkFrame

/**
 * What the preview draws for one tracked frame: shoulders tracked well enough to count for the
 * body check, the Holistic wrists, and the rest line. Port of `BodyOverlay(frame:restY:)`.
 */
fun LandmarkFrame.bodyOverlay(restY: Double?): BodyOverlay {
    val signals = FrameSignals(this)
    val shoulders = pose?.let { pose ->
        listOf(LandmarkFrame.Pose.LEFT_SHOULDER, LandmarkFrame.Pose.RIGHT_SHOULDER)
            .map { pose[it] }
            .filter { it.poseConfidence >= LandmarkFrame.MINIMUM_TRACKED_SHOULDER_VISIBILITY }
            .map { NormalizedPoint(it.x, it.y) }
    }.orEmpty()
    return BodyOverlay(
        imageWidth = imageSize.width,
        imageHeight = imageSize.height,
        shoulders = shoulders,
        wrists = listOfNotNull(signals.leftWrist, signals.rightWrist),
        restY = restY,
    )
}
