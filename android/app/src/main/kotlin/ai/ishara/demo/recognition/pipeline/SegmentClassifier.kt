package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.recognition.core.ClipQuality
import ai.ishara.demo.recognition.core.FramingFrame
import ai.ishara.demo.recognition.core.FramingHand
import ai.ishara.demo.recognition.core.LogitsCandidate
import ai.ishara.demo.recognition.core.LogitsMatch
import ai.ishara.demo.recognition.core.LogitsMatching
import ai.ishara.demo.recognition.core.QualityFrame
import ai.ishara.demo.recognition.core.RecognitionRules
import ai.ishara.demo.recognition.landmarks.KaggleLayout
import ai.ishara.demo.recognition.landmarks.Landmark
import ai.ishara.demo.recognition.landmarks.LandmarkFrame
import ai.ishara.demo.recognition.landmarks.LogitsModel
import android.util.Log

/**
 * Turns the landmark frames of one accepted sign into a chip, a "did you mean" candidate or `?`
 * (decision D8): Kaggle-layout landmarks → the public ASL Signs model → 250 logits → the
 * open-set rule in RecognitionCore's `LogitsMatcher`. Port of the ASL engine of
 * ios/Ishara/Recognition/SegmentClassifier.swift (the SignCLIP engine is not ported).
 *
 * Never guesses: without a model or matcher, or when the model fails, the result is
 * [RecognitionResult.Unsure]; when a hand left the picture during the sign or as it ended, it
 * is [RecognitionResult.HandLeftFrame].
 */
class SegmentClassifier(
    private val model: LogitsModel?,
    private val matcher: LogitsMatching?,
    private val rules: RecognitionRules,
    private val log: (String) -> Unit = { Log.i(TAG, it) },
) {
    fun classify(clip: RecognitionSession.SignClip): RecognitionResult {
        val result = classify(clip.frames)
        // The rest after the cut counts too: a hand that leaves the picture ends the sign there.
        // A sign read while a hand was out of the picture is never a chip or a tile.
        if (!rules.handLeftFrame(framing(clip.frames + clip.restAfter), clip.restY)) return result
        log("hand left the picture: $result shown as ?")
        return RecognitionResult.HandLeftFrame
    }

    private fun classify(frames: List<LandmarkFrame>): RecognitionResult {
        if (model == null || matcher == null || frames.isEmpty()) return RecognitionResult.Unsure
        val logits = try {
            model.logits(KaggleLayout.values(frames), frames.size)
        } catch (error: Exception) {
            log("model failed: $error")
            return RecognitionResult.Unsure
        }
        return when (val match = matcher.match(logits, quality(frames))) {
            is LogitsMatch.Chip -> {
                log(verdict("chip", match.label, match.p, match.top, frames.size))
                Sign.fromWire(match.label)?.let(RecognitionResult::Recognised) ?: RecognitionResult.Unsure
            }
            is LogitsMatch.PickOne -> {
                log(verdict("pick one", match.label, match.p, match.top, frames.size))
                Sign.fromWire(match.label)?.let(RecognitionResult::Candidate) ?: RecognitionResult.Unsure
            }
            is LogitsMatch.Unsure -> {
                log(verdict("unsure", match.reason, match.top.firstOrNull()?.p ?: 0.0, match.top, frames.size))
                RecognitionResult.Unsure
            }
        }
    }

    fun quality(frames: List<LandmarkFrame>): ClipQuality = rules.quality(
        frames.map { QualityFrame(body = it.hasTrackedShoulders, handCount = listOfNotNull(it.leftHand, it.rightHand).size) },
    )

    companion object {
        private const val TAG = "IsharaRecognition"

        /** The pose's wrists (15 left, 16 right) and whether each Holistic hand was tracked. */
        fun framing(frames: List<LandmarkFrame>): List<FramingFrame> = frames.map { frame ->
            fun hand(landmarks: List<Landmark>?, wrist: Int): FramingHand {
                val point = frame.pose?.get(wrist)
                return FramingHand(tracked = landmarks != null, wristX = point?.x, wristY = point?.y)
            }
            FramingFrame(
                timestamp = frame.timestamp,
                left = hand(frame.leftHand, LandmarkFrame.Pose.LEFT_WRIST),
                right = hand(frame.rightHand, LandmarkFrame.Pose.RIGHT_WRIST),
            )
        }

        private fun verdict(verdict: String, detail: String, p: Double, top: List<LogitsCandidate>, frames: Int): String {
            val ranked = top.joinToString { "${it.gloss} ${"%.2f".format(it.p)}" }
            return "asl $verdict: $detail p=${"%.2f".format(p)} [$ranked] frames=$frames"
        }
    }
}
