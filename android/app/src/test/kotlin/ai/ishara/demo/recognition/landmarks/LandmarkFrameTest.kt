package ai.ishara.demo.recognition.landmarks

import ai.ishara.demo.recognition.NormalizedPoint
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/** Hand-built frames with easy numbers. Port of `Synthetic` in SignPipelineTests/Support/Fixtures.swift. */
object Synthetic {
    val size = ImageSize(200, 100)

    fun pose(visibility: Float? = 1f): List<Landmark> = List(LandmarkFrame.POSE_COUNT) { index ->
        Landmark(0.3f + index / 100f, 0.2f + index / 200f, index / 1000f, visibility)
    }.toMutableList().apply {
        this[LandmarkFrame.Pose.LEFT_SHOULDER] = Landmark(0.75f, 0.5f, 0f, visibility)
        this[LandmarkFrame.Pose.RIGHT_SHOULDER] = Landmark(0.25f, 0.5f, 0f, visibility)
    }

    /** Landmark `i` sits at x = i / 1000 so the selected indices are readable. */
    fun face(): List<Landmark> = List(LandmarkFrame.MINIMUM_FACE_COUNT) { Landmark(it / 1000f, 0.4f, 0.01f) }

    fun hand(x: Float): List<Landmark> = List(LandmarkFrame.HAND_COUNT) { Landmark(x + it / 500f, 0.6f, -0.02f) }

    fun frame(
        timestamp: Double = 0.0,
        pose: List<Landmark>? = pose(),
        face: List<Landmark>? = face(),
        leftHand: List<Landmark>? = hand(0.6f),
        rightHand: List<Landmark>? = hand(0.3f),
    ) = LandmarkFrame.create(timestamp, size, pose, face, leftHand, rightHand)
}

/** Mirrors SignPipelineTests' LandmarkFrameTests and FrameSignalsTests. */
class LandmarkFrameTest {
    private val size = ImageSize(640, 480)

    @Test
    fun acceptsEveryPartMissing() {
        val frame = LandmarkFrame.create(0.0, size)
        assertNull(frame.pose)
        assertNull(frame.face)
        assertNull(frame.leftHand)
        assertNull(frame.rightHand)
    }

    @Test
    fun rejectsWrongPoseCount() {
        val error = assertThrows(LandmarkFrameException::class.java) {
            LandmarkFrame.create(0.0, size, pose = Synthetic.pose().dropLast(1))
        }
        assertEquals(LandmarkFrameException.UnexpectedLandmarkCount(BodyPart.POSE, 32), error)
    }

    @Test
    fun rejectsTruncatedFaceButAcceptsIrisRefinedMesh() {
        val face = Synthetic.face()
        val error = assertThrows(LandmarkFrameException::class.java) { LandmarkFrame.create(0.0, size, face = face.dropLast(1)) }
        assertEquals(LandmarkFrameException.UnexpectedLandmarkCount(BodyPart.FACE, 467), error)
        LandmarkFrame.create(0.0, size, face = face + List(10) { Landmark(0.5f, 0.5f, 0f) })
    }

    @Test
    fun rejectsWrongHandCountOnEitherSide() {
        val hand = Synthetic.hand(0.5f) + Landmark(0f, 0f, 0f)
        assertEquals(
            LandmarkFrameException.UnexpectedLandmarkCount(BodyPart.LEFT_HAND, 22),
            assertThrows(LandmarkFrameException::class.java) { LandmarkFrame.create(0.0, size, leftHand = hand) },
        )
        assertEquals(
            LandmarkFrameException.UnexpectedLandmarkCount(BodyPart.RIGHT_HAND, 22),
            assertThrows(LandmarkFrameException::class.java) { LandmarkFrame.create(0.0, size, rightHand = hand) },
        )
    }

    @Test
    fun rejectsNonFiniteCoordinates() {
        val hand = Synthetic.hand(0.5f).toMutableList().apply { this[3] = this[3].copy(z = Float.NaN) }
        assertEquals(
            LandmarkFrameException.NonFiniteLandmark(BodyPart.RIGHT_HAND),
            assertThrows(LandmarkFrameException::class.java) { LandmarkFrame.create(0.0, size, rightHand = hand) },
        )
    }

    @Test
    fun rejectsEmptyImage() {
        val empty = ImageSize(0, 480)
        assertEquals(
            LandmarkFrameException.InvalidImageSize(empty),
            assertThrows(LandmarkFrameException::class.java) { LandmarkFrame.create(0.0, empty) },
        )
    }

    @Test
    fun holisticTreatsEmptyListsAsMissingAndKeepsOnlyPoseVisibility() {
        val scored = { points: List<Landmark> -> points.map { it.copy(visibility = 0.3f) } }
        val frame = LandmarkFrame.holistic(
            timestamp = 1.0, imageSize = size,
            pose = Synthetic.pose(visibility = 0.7f), face = scored(Synthetic.face()),
            leftHand = emptyList(), rightHand = scored(Synthetic.hand(0.3f)),
        )

        assertNull(frame.leftHand)
        assertTrue(frame.pose!!.all { it.visibility == 0.7f })
        assertTrue((frame.face!! + frame.rightHand!!).all { it.visibility == null })
    }

    @Test
    fun reportsBodyAndBothWristsInNormalizedCoordinates() {
        val left = Synthetic.hand(0.6f).toMutableList().apply { this[0] = Landmark(0.61f, 0.72f, -0.3f) }
        val right = Synthetic.hand(0.3f).toMutableList().apply { this[0] = Landmark(0.31f, 0.83f, -0.1f) }

        val signals = FrameSignals(Synthetic.frame(timestamp = 1.5, leftHand = left, rightHand = right))

        assertEquals(1.5, signals.timestamp, 0.0)
        assertTrue(signals.body)
        assertEquals(NormalizedPoint(0.61f, 0.72f), signals.leftWrist)
        assertEquals(NormalizedPoint(0.31f, 0.83f), signals.rightWrist)
    }

    @Test
    fun missingHandsGiveNoWrists() {
        val signals = FrameSignals(Synthetic.frame(leftHand = null, rightHand = null))
        assertNull(signals.leftWrist)
        assertNull(signals.rightWrist)
        assertTrue(signals.body)
    }

    @Test
    fun noBodyWithoutPose() {
        assertFalse(FrameSignals(Synthetic.frame(pose = null)).body)
    }

    @Test
    fun noBodyWhenEitherShoulderIsBelowThreshold() {
        for (shoulder in listOf(LandmarkFrame.Pose.LEFT_SHOULDER, LandmarkFrame.Pose.RIGHT_SHOULDER)) {
            val pose = Synthetic.pose().toMutableList()
            pose[shoulder] = pose[shoulder].copy(visibility = 0.49f)
            assertFalse("shoulder $shoulder", FrameSignals(Synthetic.frame(pose = pose)).body)
            pose[shoulder] = pose[shoulder].copy(visibility = 0.5f)
            assertTrue("shoulder $shoulder", FrameSignals(Synthetic.frame(pose = pose)).body)
        }
    }

    @Test
    fun poseWithoutVisibilityStillCountsAsTracked() {
        assertTrue(Synthetic.frame(pose = Synthetic.pose(visibility = null)).hasTrackedShoulders)
    }

    @Test
    fun otherLowVisibilityLandmarksDoNotHideTheBody() {
        val pose = Synthetic.pose().toMutableList()
        pose[0] = pose[0].copy(visibility = 0f)
        pose[25] = pose[25].copy(visibility = 0f)
        assertTrue(FrameSignals(Synthetic.frame(pose = pose)).body)
    }
}
