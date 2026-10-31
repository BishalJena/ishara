package ai.ishara.demo.recognition.landmarks

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Mirrors SignPipelineTests' KaggleLayoutTests, plus the real tracked frames of SignPipeline's
 * `feature_fixture.json` (read from ios/Packages, the single source) laid out independently.
 */
class KaggleLayoutTest {
    @Test
    fun layoutMatchesTheCompetitionData() {
        assertEquals(543, KaggleLayout.POINTS)
        assertEquals(468, KaggleLayout.Offset.LEFT_HAND)
        assertEquals(489, KaggleLayout.Offset.POSE)
        assertEquals(522, KaggleLayout.Offset.RIGHT_HAND)
        assertEquals(1629, KaggleLayout.VALUES_PER_FRAME)
    }

    @Test
    fun ordersFaceLeftHandPoseRightHand() {
        val frame = Synthetic.frame()
        val values = KaggleLayout.values(listOf(frame))

        assertEquals(KaggleLayout.VALUES_PER_FRAME, values.size)
        assertArrayEquals(xyz(frame.face!![0]), point(values, 0), 0f)
        assertArrayEquals(xyz(frame.face!![467]), point(values, 467), 0f)
        assertArrayEquals(xyz(frame.leftHand!![0]), point(values, KaggleLayout.Offset.LEFT_HAND), 0f)
        assertArrayEquals(xyz(frame.pose!![11]), point(values, KaggleLayout.Offset.POSE + 11), 0f)
        assertArrayEquals(xyz(frame.rightHand!![20]), point(values, KaggleLayout.Offset.RIGHT_HAND + 20), 0f)
    }

    @Test
    fun missingPartsAreNaN() {
        val values = KaggleLayout.values(listOf(Synthetic.frame(face = null, rightHand = null)))

        assertTrue(values.sliceArray(0 until 468 * 3).all { it.isNaN() })
        assertTrue(values.sliceArray(KaggleLayout.Offset.RIGHT_HAND * 3 until values.size).all { it.isNaN() })
        assertFalse(values.sliceArray(KaggleLayout.Offset.LEFT_HAND * 3 until KaggleLayout.Offset.RIGHT_HAND * 3).any { it.isNaN() })
    }

    @Test
    fun missingHandsAreNaNNotZero() {
        val values = KaggleLayout.values(listOf(Synthetic.frame(leftHand = null)))

        val leftHand = values.sliceArray(KaggleLayout.Offset.LEFT_HAND * 3 until KaggleLayout.Offset.POSE * 3)
        assertTrue("the model reads a missing hand as NaN, never as a hand at (0, 0, 0)", leftHand.all { it.isNaN() })
    }

    @Test
    fun dropsTheTenIrisPointsOfTheHolisticLandmarker() {
        val face = Synthetic.face() + List(10) { Landmark(9f, 9f, 9f) }
        val values = KaggleLayout.values(listOf(LandmarkFrame.create(0.0, Synthetic.size, face = face)))

        assertEquals(KaggleLayout.VALUES_PER_FRAME, values.size)
        assertFalse(values.any { it == 9f })
    }

    @Test
    fun framesFollowEachOther() {
        val values = KaggleLayout.values(listOf(Synthetic.frame(timestamp = 0.0), Synthetic.frame(timestamp = 1.0, leftHand = null)))

        assertEquals(2 * KaggleLayout.VALUES_PER_FRAME, values.size)
        assertFalse(point(values, KaggleLayout.Offset.LEFT_HAND)[0].isNaN())
        assertTrue(point(values, KaggleLayout.POINTS + KaggleLayout.Offset.LEFT_HAND)[0].isNaN())
    }

    @Test
    fun trackedFixtureFramesLandInCompetitionOrder() {
        val fixture = Json { ignoreUnknownKeys = true }.decodeFromString<FeatureFixture>(
            checkNotNull(javaClass.classLoader?.getResource("feature_fixture.json")) { "feature_fixture.json not on the test classpath" }.readText(),
        )
        val missing = fixture.cases.sumOf { case -> case.frames.count { it.leftHand == null || it.rightHand == null || it.face == null } }
        assertTrue("the fixture covers missing parts", missing > 0)

        for (case in fixture.cases) {
            val frames = case.frames.mapIndexed { index, frame ->
                LandmarkFrame.create(
                    timestamp = index / 30.0, imageSize = ImageSize(case.width, case.height),
                    pose = frame.pose?.map { Landmark(it[0], it[1], it[2], it[3]) },
                    face = frame.face?.map(::landmark), leftHand = frame.leftHand?.map(::landmark), rightHand = frame.rightHand?.map(::landmark),
                )
            }
            val expected = case.frames.flatMap { frame ->
                listOf(frame.face to 468, frame.leftHand to 21, frame.pose to 33, frame.rightHand to 21).flatMap { (rows, count) ->
                    rows?.take(count)?.flatMap { it.take(3) } ?: List(count * 3) { Float.NaN }
                }
            }.toFloatArray()

            assertArrayEquals(case.name, expected, KaggleLayout.values(frames), 0f)
        }
    }

    private fun landmark(row: List<Float>) = Landmark(row[0], row[1], row[2])

    private fun point(values: FloatArray, index: Int) = values.sliceArray(index * 3 until index * 3 + 3)

    private fun xyz(landmark: Landmark) = floatArrayOf(landmark.x, landmark.y, landmark.z)

    @Serializable
    private data class FeatureFixture(val cases: List<Case>)

    @Serializable
    private data class Case(val name: String, val width: Int, val height: Int, val frames: List<Frame>)

    @Serializable
    private data class Frame(
        val pose: List<List<Float>>? = null,
        val face: List<List<Float>>? = null,
        val leftHand: List<List<Float>>? = null,
        val rightHand: List<List<Float>>? = null,
    )
}
