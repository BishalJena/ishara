package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.recognition.Landmarks
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.recognition.ScriptedRules
import ai.ishara.demo.recognition.core.ClipQuality
import ai.ishara.demo.recognition.core.FramingFrame
import ai.ishara.demo.recognition.core.FramingHand
import ai.ishara.demo.recognition.core.LogitsMatch
import ai.ishara.demo.recognition.core.LogitsMatching
import ai.ishara.demo.recognition.core.QualityFrame
import ai.ishara.demo.recognition.landmarks.KaggleLayout
import ai.ishara.demo.recognition.landmarks.LandmarkFrame
import ai.ishara.demo.recognition.landmarks.LogitsModel
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * How the classifier wires the model, the matcher and the framing guard, with scripted
 * RecognitionCore parts. SegmentClassifierNativeTest runs ios/IsharaTests/SegmentClassifierTests'
 * ASL cases against the real matcher and bundle on the device.
 */
class SegmentClassifierTest {
    private val clip = Landmarks.run(from = 0.0, seconds = 0.8, wristY = Landmarks.SIGNING_Y)
    private val rules = ScriptedRules(quality = ClipQuality(0.9, 0.7))
    private val logits = FloatArray(250) { it.toFloat() }

    private class FixedModel(private val logits: FloatArray) : LogitsModel {
        val inputs = mutableListOf<Pair<FloatArray, Int>>()
        var failure: Exception? = null

        override fun logits(landmarks: FloatArray, frameCount: Int): FloatArray {
            inputs += landmarks to frameCount
            failure?.let { throw it }
            return logits
        }
    }

    private class FixedMatcher(private val result: LogitsMatch) : LogitsMatching {
        val calls = mutableListOf<Pair<FloatArray, ClipQuality>>()

        override fun match(logits: FloatArray, quality: ClipQuality): LogitsMatch {
            calls += logits to quality
            return result
        }
    }

    private fun classify(
        result: LogitsMatch,
        frames: List<LandmarkFrame> = clip,
        restAfter: List<LandmarkFrame> = emptyList(),
        model: FixedModel? = FixedModel(logits),
    ): RecognitionResult {
        val classifier = SegmentClassifier(model, FixedMatcher(result), rules) {}
        return classifier.classify(RecognitionSession.SignClip(frames, restAfter, Landmarks.CALIBRATED_REST_Y))
    }

    @Test
    fun chipIsTheSign() {
        assertEquals(RecognitionResult.Recognised(Sign.TOMORROW), classify(LogitsMatch.Chip("tomorrow", 0.8, 0.7, emptyList())))
    }

    @Test
    fun pickOneIsACandidateNeverAChip() {
        assertEquals(RecognitionResult.Candidate(Sign.WAIT), classify(LogitsMatch.PickOne("wait", 0.4, 0.3, emptyList())))
    }

    @Test
    fun unsureIsAQuestionMark() {
        assertEquals(RecognitionResult.Unsure, classify(LogitsMatch.Unsure("not in vocabulary: mitten 0.98", emptyList())))
    }

    @Test
    fun aLabelTheBackendDoesNotKnowIsUnsure() {
        assertEquals(RecognitionResult.Unsure, classify(LogitsMatch.Chip("mitten", 0.9, 0.8, emptyList())))
        assertEquals(RecognitionResult.Unsure, classify(LogitsMatch.PickOne("mitten", 0.5, 0.3, emptyList())))
    }

    @Test
    fun theModelReadsTheClipInKaggleLayoutAndTheMatcherItsLogitsAndQuality() {
        val model = FixedModel(logits)
        val matcher = FixedMatcher(LogitsMatch.Chip("yes", 0.8, 0.7, emptyList()))

        SegmentClassifier(model, matcher, rules) {}.classify(RecognitionSession.SignClip(clip, Landmarks.run(0.8, 0.4), 0.82))

        val (values, frameCount) = model.inputs.single()
        assertEquals("the model never reads the rest after the cut", clip.size, frameCount)
        assertArrayEquals(KaggleLayout.values(clip), values, 0f)
        val (matched, quality) = matcher.calls.single()
        assertSame(logits, matched)
        assertEquals(ClipQuality(0.9, 0.7), quality)
    }

    @Test
    fun qualityCountsBodyAndHandsPerFrame() {
        val frames = listOf(Landmarks.frame(t = 0.0), Landmarks.frame(t = 0.1, body = false, hands = false), Landmarks.frame(t = 0.2, rightHand = false))

        SegmentClassifier(null, null, rules) {}.quality(frames)

        assertEquals(listOf(QualityFrame(true, 2), QualityFrame(false, 0), QualityFrame(true, 1)), rules.qualityCalls.single())
    }

    @Test
    fun modelFailureIsUnsure() {
        val model = FixedModel(logits).apply { failure = IllegalStateException("non-finite output") }

        assertEquals(RecognitionResult.Unsure, classify(LogitsMatch.Chip("yes", 0.9, 0.8, emptyList()), model = model))
    }

    @Test
    fun withoutAModelOrMatcherEverySignIsUnsure() {
        assertEquals(RecognitionResult.Unsure, SegmentClassifier(null, FixedMatcher(LogitsMatch.Chip("yes", 0.9, 0.8, emptyList())), rules) {}
            .classify(RecognitionSession.SignClip(clip, emptyList(), 0.82)))
        val model = FixedModel(logits)
        assertEquals(RecognitionResult.Unsure, SegmentClassifier(model, null, rules) {}.classify(RecognitionSession.SignClip(clip, emptyList(), 0.82)))
        assertTrue("nothing to match against, so nothing is run", model.inputs.isEmpty())
    }

    @Test
    fun anEmptyClipIsUnsureWithoutRunningTheModel() {
        val model = FixedModel(logits)

        assertEquals(RecognitionResult.Unsure, classify(LogitsMatch.Chip("yes", 0.9, 0.8, emptyList()), frames = emptyList(), model = model))
        assertTrue(model.inputs.isEmpty())
    }

    @Test
    fun aHandThatLeftTheFrameTurnsEveryResultIntoTheFramingHint() {
        rules.handLeft = true
        for (result in listOf(
            LogitsMatch.Chip("tomorrow", 0.9, 0.8, emptyList()),
            LogitsMatch.PickOne("tomorrow", 0.4, 0.3, emptyList()),
            LogitsMatch.Unsure("not in vocabulary: mitten 0.98", emptyList()),
        )) {
            assertEquals(RecognitionResult.HandLeftFrame, classify(result))
        }
        assertEquals(RecognitionResult.HandLeftFrame, classify(LogitsMatch.Chip("yes", 0.9, 0.8, emptyList()), model = null))
    }

    @Test
    fun theFramingGuardReadsTheSignAndTheRestAfterItAtTheRestLine() {
        val restAfter = Landmarks.run(from = 0.8, seconds = 0.4)

        classify(LogitsMatch.Chip("yes", 0.9, 0.8, emptyList()), restAfter = restAfter)

        val (frames, restY) = rules.framingCalls.single()
        assertEquals(clip.size + restAfter.size, frames.size)
        assertEquals(restAfter.last().timestamp, frames.last().timestamp, 0.0)
        assertEquals(Landmarks.CALIBRATED_REST_Y, restY, 0.0)
    }

    @Test
    fun framingUsesThePoseWristsAndWhetherEachHandWasTracked() {
        val frame = Landmarks.oneHandedSign(wristAfterX = -0.4f, wristAfterY = 0.6f)(1.0)[30]

        assertEquals(
            listOf(FramingFrame(frame.timestamp, FramingHand(false, 0.7f, 1.2f), FramingHand(false, -0.4f, 0.6f))),
            SegmentClassifier.framing(listOf(frame)),
        )
        val tracked = Landmarks.frame(t = 2.0)
        assertEquals(
            FramingFrame(2.0, FramingHand(true, 0.5f, 0.5f), FramingHand(true, 0.5f, 0.5f)),
            SegmentClassifier.framing(listOf(tracked)).single(),
        )
        assertEquals(
            FramingFrame(0.0, FramingHand(false), FramingHand(false)),
            SegmentClassifier.framing(listOf(LandmarkFrame.create(0.0, Landmarks.size))).single(),
        )
    }
}
