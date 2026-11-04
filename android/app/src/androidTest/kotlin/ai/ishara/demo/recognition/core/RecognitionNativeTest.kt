package ai.ishara.demo.recognition.core

import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.RecognitionTestAssets
import ai.ishara.demo.recognition.RecognitionTestAssets.logits
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Round trips through the JNI layer into RecognitionCore, on the shared fixtures. */
@RunWith(AndroidJUnit4::class)
class RecognitionNativeTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun defaultParamsAreTheSharedSpec() {
        val params = NativeRecognitionRules.defaultParams

        assertEquals(2.0, params.calibrationS, 0.0)
        assertEquals(0.08, params.restMargin, 0.0)
        assertEquals(0.4, params.endRestS, 0.0)
        assertEquals(0.2, params.preRollS, 0.0)
        assertEquals(4.0, params.maxSignS, 0.0)
    }

    /** Every detector fixture (shared with the Python and Swift detectors) cuts the same clips through JNI. */
    @Test
    fun everyDetectorFixture() {
        val files = RecognitionTestAssets.fixtureNames(RecognitionTestAssets.DETECTOR_FIXTURES).filter { it.endsWith(".json") }
        assertTrue("no detector fixtures in the test APK", files.size >= 20)
        for (file in files) {
            val fixture = json.decodeFromString<DetectorFixture>(RecognitionTestAssets.fixture("${RecognitionTestAssets.DETECTOR_FIXTURES}/$file"))
            check(fixture, "$file (${fixture.name})")
        }
    }

    private fun check(fixture: DetectorFixture, label: String) {
        val defaults = Json.encodeToJsonElement(DetectorParams.serializer(), NativeRecognitionRules.defaultParams).jsonObject
        val params = Json.decodeFromJsonElement(DetectorParams.serializer(), JsonObject(defaults + fixture.params.mapValues { JsonPrimitive(it.value) }))
        val rules = NativeRecognitionRules(params)

        val restY = try {
            rules.calibrate(fixture.calibration.map(Frame::detectorFrame))
        } catch (error: CalibrationException) {
            assertEquals("$label: calibration error", fixture.expectedCalibrationError, error.error.wire)
            assertTrue("$label: a fixture that fails calibration has no frames", fixture.frames.isEmpty())
            return
        }
        assertNull("$label: calibration should have failed", fixture.expectedCalibrationError)
        fixture.expectedRestY?.let { assertEquals("$label: rest_y", it, restY, 1e-9) }

        val segments = mutableListOf<Segment>()
        val statuses = mutableListOf<String>()
        rules.detector(restY).use { detector ->
            for (frame in fixture.frames) {
                for (event in detector.update(frame.detectorFrame())) {
                    when (event) {
                        is DetectorEvent.Cut -> segments += event.segment
                        is DetectorEvent.Status -> statuses += wire(event.state)
                    }
                }
            }
        }
        assertEquals("$label: statuses", fixture.expectedStatuses, statuses)
        assertEquals("$label: segment count", fixture.expectedSegments.size, segments.size)
        for ((actual, expected) in segments.zip(fixture.expectedSegments)) {
            assertEquals("$label: segment start", expected.start, actual.start, 1e-6)
            assertEquals("$label: segment end", expected.end, actual.end, 1e-6)
            assertEquals("$label: segment accepted", expected.accepted, actual.accepted)
            assertEquals("$label: segment reason", expected.reason, actual.reason)
        }
    }

    private fun wire(state: CameraState) = when (state) {
        CameraState.WATCHING -> "watching"
        CameraState.SIGNING -> "signing"
        CameraState.CANT_SEE -> "cant_see"
    }

    @Test
    fun badInputIsAnIllegalArgument() {
        assertThrows(IllegalArgumentException::class.java) { RecognitionNative.createDetector(0.8, """{"bogus": 1}""") }
        assertThrows(IllegalArgumentException::class.java) { RecognitionNative.calibrate("not json", "{}") }
        assertThrows(IllegalArgumentException::class.java) { RecognitionNative.calibrate("""[{"t": 0, "body": true, "wrists": [[0.5]]}]""", "{}") }
        assertThrows(IllegalArgumentException::class.java) { RecognitionNative.detectorUpdate(-1, 0.0, true, DoubleArray(0)) }
        val handle = RecognitionNative.createDetector(0.8, "{}")
        try {
            assertThrows(IllegalArgumentException::class.java) { RecognitionNative.detectorUpdate(handle, 0.0, true, doubleArrayOf(0.5)) }
        } finally {
            RecognitionNative.freeDetector(handle)
        }
        assertThrows("a freed detector is gone", IllegalArgumentException::class.java) { RecognitionNative.detectorUpdate(handle, 0.0, true, DoubleArray(0)) }
        assertThrows(IllegalArgumentException::class.java) { RecognitionNative.handLeftFrame("{}", 0.8) }
        assertThrows(IllegalArgumentException::class.java) { RecognitionNative.matchLogits(-1, FloatArray(250), 1.0, 1.0) }
    }

    @Test
    fun detectorsKeepTheirOwnState() {
        val rules = NativeRecognitionRules()
        rules.detector(0.8).use { first ->
            rules.detector(0.3).use { second ->
                val up = DetectorFrame(0.0, body = true, wrists = listOf(DetectorPoint(0.5, 0.5)))
                assertEquals(listOf(DetectorEvent.Status(CameraState.WATCHING)), first.update(up))
                assertEquals(listOf(DetectorEvent.Status(CameraState.WATCHING)), second.update(up))
                val later = up.copy(t = 0.2)
                assertEquals("0.5 is above 0.8's rest line", listOf(DetectorEvent.Status(CameraState.SIGNING)), first.update(later))
                assertEquals("0.5 rests below a 0.3 line", emptyList<DetectorEvent>(), second.update(later))
            }
        }
    }

    @Test
    fun framingGuardRoundTrip() {
        val rules = NativeRecognitionRules()
        fun frames(outside: FramingHand) = List(30) { index ->
            FramingFrame(index / 30.0, FramingHand(true, 0.6f, 0.5f), if (index < 10) FramingHand(true, 0.4f, 0.5f) else outside)
        }

        assertTrue(rules.handLeftFrame(frames(FramingHand(false, 1.1f, 0.45f)), restY = 0.82))
        assertFalse("a wrist below the rest line is resting", rules.handLeftFrame(frames(FramingHand(false, 1.1f, 0.95f)), restY = 0.82))
        assertFalse("no pose wrist, no evidence", rules.handLeftFrame(frames(FramingHand(false)), restY = 0.82))
    }

    @Test
    fun clipQualityRoundTrip() {
        val quality = NativeRecognitionRules().quality(listOf(QualityFrame(true, 2), QualityFrame(false, 0), QualityFrame(true, 0), QualityFrame(false, 1)))

        assertEquals(ClipQuality(poseFraction = 0.5, handFraction = 0.5), quality)
        assertEquals(ClipQuality(0.0, 0.0), NativeRecognitionRules().quality(emptyList()))
    }

    @Test
    fun matcherReadsTheShippedBundle() {
        NativeLogitsMatcher(RecognitionTestAssets.bundleJson).use { matcher ->
            assertEquals(250, matcher.classCount)
            assertTrue(matcher.provisional)
            assertEquals(listOf("hello", "no", "now", "please", "thankyou", "tomorrow", "wait", "yes"), matcher.vocabulary)
        }
    }

    @Test
    fun matcherAppliesTheOpenSetRuleOverFloatLogits() {
        val good = ClipQuality(1.0, 0.9)
        NativeLogitsMatcher(RecognitionTestAssets.bundleJson).use { matcher ->
            val chip = matcher.match(logits("tomorrow", 0.8), good)
            assertTrue(chip is LogitsMatch.Chip)
            chip as LogitsMatch.Chip
            assertEquals("tomorrow", chip.label)
            assertEquals(0.8, chip.p, 1e-4)
            assertEquals("tomorrow", chip.top.first().gloss)

            assertEquals("pickOne", kind(matcher.match(logits("tomorrow", 0.4), good)))
            assertEquals("the open-set rule: mitten is not turned into a vocabulary word", "unsure", kind(matcher.match(logits("mitten", 0.98), good)))
            assertEquals("tracking quality gates every chip", "unsure", kind(matcher.match(logits("tomorrow", 0.9), ClipQuality(0.1, 0.9))))
            val wrongLength = matcher.match(FloatArray(10), good)
            assertEquals(LogitsMatch.Unsure("invalid evidence", emptyList()), wrongLength)
        }
    }

    @Test
    fun invalidBundleIsRejected() {
        assertThrows(IllegalArgumentException::class.java) { NativeLogitsMatcher("""{"version": 1}""") }
        val outsideBackend = Json.parseToJsonElement(RecognitionTestAssets.bundleJson).jsonObject.let { bundle ->
            JsonObject(bundle + ("vocabulary" to Json.parseToJsonElement("""["mitten"]""")))
        }
        assertThrows(IllegalArgumentException::class.java) { NativeLogitsMatcher(outsideBackend.toString()) }
    }

    private fun kind(match: LogitsMatch) = when (match) {
        is LogitsMatch.Chip -> "chip"
        is LogitsMatch.PickOne -> "pickOne"
        is LogitsMatch.Unsure -> "unsure"
    }

    @Serializable
    private data class DetectorFixture(
        val name: String,
        /** Overrides keyed by the spec's snake_case names. */
        val params: Map<String, Double> = emptyMap(),
        val calibration: List<Frame>,
        val frames: List<Frame> = emptyList(),
        @SerialName("expected_rest_y") val expectedRestY: Double? = null,
        @SerialName("expected_calibration_error") val expectedCalibrationError: String? = null,
        @SerialName("expected_segments") val expectedSegments: List<ExpectedSegment> = emptyList(),
        @SerialName("expected_statuses") val expectedStatuses: List<String> = emptyList(),
    )

    @Serializable
    private data class Frame(val t: Double, val body: Boolean, val wrists: List<List<Double>>) {
        fun detectorFrame() = DetectorFrame(t, body, wrists.map { DetectorPoint(it[0], it[1]) })
    }

    @Serializable
    private data class ExpectedSegment(val start: Double, val end: Double, val accepted: Boolean, val reason: String? = null)
}
