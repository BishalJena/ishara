package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.RecognitionTestAssets
import ai.ishara.demo.recognition.landmarks.ImageSize
import ai.ishara.demo.recognition.landmarks.Landmark
import ai.ishara.demo.recognition.landmarks.LandmarkFrame
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The real Holistic Landmarker on MediaPipe's own Holistic test photo, checked against MediaPipe's
 * expected result for it (as SignPipelineMediaPipe's HolisticLandmarkProviderTests does on iOS).
 */
@RunWith(AndroidJUnit4::class)
class HolisticLandmarkProviderTest {
    /** MediaPipe's own Holistic tests use the same tolerance for x and y. */
    private val tolerance = 0.03f
    private lateinit var provider: HolisticLandmarkProvider
    private lateinit var photo: Bitmap

    @Before
    fun load() {
        RecognitionTestAssets.assumeAppAsset(HolisticLandmarkProvider.MODEL_ASSET, "run download_holistic_model.sh ios/Ishara/LocalAssets")
        assumeTrue(
            "male_full_height_hands.jpg is missing: run SignPipelineMediaPipe/Scripts/download_holistic_test_assets.sh",
            RecognitionTestAssets.hasFixture(RecognitionTestAssets.HOLISTIC_PHOTO),
        )
        photo = RecognitionTestAssets.openFixture(RecognitionTestAssets.HOLISTIC_PHOTO).use {
            BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inPreferredConfig = Bitmap.Config.ARGB_8888 })!!
        }
        provider = HolisticLandmarkProvider(RecognitionTestAssets.app, HolisticLandmarkProvider.MODEL_ASSET)
    }

    @After
    fun close() {
        if (::provider.isInitialized) provider.close()
    }

    @Test
    fun mapsBodyFaceAndHandsOfTheReferencePhoto() {
        val frame = provider.landmarks(BitmapFrame(photo, 0.0))

        assertEquals(ImageSize(638, 1000), frame.imageSize)
        val pose = checkNotNull(frame.pose) { "pose not detected" }
        val face = checkNotNull(frame.face) { "face not detected" }
        val leftHand = checkNotNull(frame.leftHand) { "left hand not detected" }
        val rightHand = checkNotNull(frame.rightHand) { "right hand not detected" }
        assertEquals("face mesh plus 10 iris points", 478, face.size)

        assertMatchesExpectedResult(pose, leftHand, rightHand)
        assertTrue(frame.hasTrackedShoulders)
        pose.forEachIndexed { index, point ->
            val visibility = checkNotNull(point.visibility) { "pose $index lost its visibility" }
            assertTrue("pose $index visibility $visibility is not a probability", visibility in 0f..1f)
        }
        assertTrue((face + leftHand + rightHand).all { it.visibility == null })
    }

    @Test
    fun rejectsTimestampsThatDoNotIncrease() {
        provider.landmarks(BitmapFrame(photo, 1.0))

        val error = assertThrows(HolisticLandmarkProvider.NonIncreasingTimestampException::class.java) {
            provider.landmarks(BitmapFrame(photo, 1.0))
        }
        assertEquals(1000L, error.milliseconds)
        provider.landmarks(BitmapFrame(photo, 1.033))
    }

    /**
     * Values from mediapipe/tasks/testdata/vision/male_full_height_hands_result_cpu.pbtxt. The
     * subject's left side is on the image's right, so the left hand sits at the left wrist (pose 15).
     */
    private fun assertMatchesExpectedResult(pose: List<Landmark>, leftHand: List<Landmark>, rightHand: List<Landmark>) {
        val expectedPose = mapOf(
            0 to (0.51091266f to 0.15435366f), // nose
            11 to (0.6355789f to 0.26930806f), // left shoulder
            12 to (0.40269345f to 0.2746424f), // right shoulder
            15 to (0.6036924f to 0.39559665f), // left wrist
            16 to (0.2462176f to 0.49226165f), // right wrist
        )
        for ((index, expected) in expectedPose) assertNear(pose[index], expected, "pose $index")
        assertNear(leftHand[LandmarkFrame.WRIST_INDEX], 0.6030236f to 0.39878464f, "left hand wrist")
        assertNear(rightHand[LandmarkFrame.WRIST_INDEX], 0.24741295f to 0.49643737f, "right hand wrist")
    }

    private fun assertNear(point: Landmark, expected: Pair<Float, Float>, name: String) {
        assertEquals("$name x", expected.first, point.x, tolerance)
        assertEquals("$name y", expected.second, point.y, tolerance)
    }
}
