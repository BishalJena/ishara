package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.recognition.Landmarks
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.recognition.RecognitionTestAssets
import ai.ishara.demo.recognition.RecognitionTestAssets.logits
import ai.ishara.demo.recognition.core.NativeLogitsMatcher
import ai.ishara.demo.recognition.core.NativeRecognitionRules
import ai.ishara.demo.recognition.landmarks.KaggleLayout
import ai.ishara.demo.recognition.landmarks.LandmarkFrame
import ai.ishara.demo.recognition.landmarks.LogitsModel
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The ASL cases of ios/IsharaTests/SegmentClassifierTests.swift with the real matcher, framing
 * guard and shipped bundle (D8), and a model that returns fixed logits.
 */
@RunWith(AndroidJUnit4::class)
class SegmentClassifierNativeTest {
    private val clip = Landmarks.run(from = 0.0, seconds = 0.8, wristY = Landmarks.SIGNING_Y)
    private val rules = NativeRecognitionRules()
    private val matcher = NativeLogitsMatcher(RecognitionTestAssets.bundleJson)

    @After
    fun close() = matcher.close()

    private class FixedLogitsModel(private val values: FloatArray) : LogitsModel {
        var shouldFail = false
        val frameCounts = mutableListOf<Int>()
        var lastValueCount = 0

        override fun logits(landmarks: FloatArray, frameCount: Int): FloatArray {
            frameCounts += frameCount
            lastValueCount = landmarks.size
            if (shouldFail) throw IllegalStateException("model failed")
            return values
        }
    }

    private fun asl(logits: FloatArray): Pair<SegmentClassifier, FixedLogitsModel> {
        val model = FixedLogitsModel(logits)
        return SegmentClassifier(model, matcher, rules) {} to model
    }

    private fun SegmentClassifier.classify(frames: List<LandmarkFrame>) =
        classify(RecognitionSession.SignClip(frames, emptyList(), Landmarks.CALIBRATED_REST_Y))

    @Test
    fun confidentVocabularySignIsAChip() {
        val (classifier, model) = asl(logits("tomorrow", 0.8))

        assertEquals(RecognitionResult.Recognised(Sign.TOMORROW), classifier.classify(clip))
        assertEquals(listOf(clip.size), model.frameCounts)
        assertEquals("Kaggle 543 × 3 per frame", clip.size * KaggleLayout.VALUES_PER_FRAME, model.lastValueCount)
    }

    @Test
    fun greyZoneVocabularySignIsACandidate() {
        assertEquals(RecognitionResult.Candidate(Sign.TOMORROW), asl(logits("tomorrow", 0.4)).first.classify(clip))
    }

    @Test
    fun confidentUnrehearsedSignIsUnsure() {
        // In the backend's vocabulary but not rehearsed: public YES clips read as can (Gate 2).
        for (gloss in listOf("can", "morning")) {
            assertEquals(gloss, RecognitionResult.Unsure, asl(logits(gloss, 0.9)).first.classify(clip))
        }
    }

    @Test
    fun confidentWordOutsideTheVocabularyIsUnsure() {
        // The open-set rule: "mitten" at 0.98 is not turned into the best vocabulary word.
        assertEquals(RecognitionResult.Unsure, asl(logits("mitten", 0.98)).first.classify(clip))
    }

    @Test
    fun modelFailureIsUnsure() {
        val (classifier, model) = asl(logits("tomorrow", 0.9))
        model.shouldFail = true

        assertEquals(RecognitionResult.Unsure, classifier.classify(clip))
    }

    @Test
    fun unsureSignWithAHandOffTheSideSaysSo() {
        assertEquals(RecognitionResult.HandLeftFrame, asl(logits("mitten", 0.98)).first.classify(Landmarks.rightHandLeavesMidSign))
    }

    @Test
    fun aConfidentSignFromAPartialViewIsNotAChip() {
        assertEquals(RecognitionResult.HandLeftFrame, asl(logits("tomorrow", 0.9)).first.classify(Landmarks.rightHandLeavesMidSign))
    }

    @Test
    fun aPartialViewIsNotADidYouMeanTileEither() {
        assertEquals(RecognitionResult.HandLeftFrame, asl(logits("tomorrow", 0.4)).first.classify(Landmarks.rightHandLeavesMidSign))
    }

    // Issue #58: a one-handed sign whose hand leaves the picture.

    @Test
    fun aOneHandedSignWhoseHandLeavesTheSideShowsTheFramingHint() {
        // The detector counts the vanished hand as rest and ends the sign at once, so the cut
        // itself has the hand in view; only the rest frames after it show where it went.
        val (classifier, _) = asl(logits("tomorrow", 0.9))

        val clips = cutBySession(Landmarks.oneHandedSign(wristAfterX = -0.4f, wristAfterY = 0.6f))

        assertEquals(listOf(RecognitionResult.HandLeftFrame), clips.map(classifier::classify))
    }

    @Test
    fun aOneHandedSignThatEndsAtRestKeepsItsChip() {
        val (classifier, model) = asl(logits("tomorrow", 0.9))

        val clips = cutBySession(Landmarks.oneHandedSign(wristAfterX = 0.4f, wristAfterY = 1.2f))

        assertEquals(listOf(RecognitionResult.Recognised(Sign.TOMORROW)), clips.map(classifier::classify))
        assertEquals("the model never reads the rest after the cut", clips.map { it.frames.size }, model.frameCounts)
    }

    @Test
    fun anArmRestingPastTheSideEdgeInPortraitIsNoFramingHint() {
        // 9:16 crops (issue #58): the dropped hand's pose wrist sits past the edge, below the rest line.
        val (classifier, _) = asl(logits("tomorrow", 0.9))

        val clips = cutBySession(Landmarks.oneHandedSign(wristAfterX = -0.1f, wristAfterY = 0.95f))

        assertEquals(listOf(RecognitionResult.Recognised(Sign.TOMORROW)), clips.map(classifier::classify))
    }

    /** The accepted signs [RecognitionSession] cuts from a calibrated stream. */
    private fun cutBySession(sign: (Double) -> List<LandmarkFrame>): List<RecognitionSession.SignClip> {
        val session = RecognitionSession(rules)
        return Landmarks.calibratedStream(sign).flatMap(session::process).filterIsInstance<RecognitionSession.Output.Sign>().map { it.clip }
            .also { session.close() }
    }
}
