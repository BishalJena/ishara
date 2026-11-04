package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.BodyOverlay
import ai.ishara.demo.recognition.Landmarks
import ai.ishara.demo.recognition.NormalizedPoint
import ai.ishara.demo.recognition.PreviewMapping
import ai.ishara.demo.recognition.landmarks.ImageSize
import ai.ishara.demo.recognition.landmarks.LandmarkFrame
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** Mirrors ios/IsharaTests/BodyOverlayTests and the preview mapping of BodyOverlayView. */
class BodyOverlayTest {
    @Test
    fun takesTrackedShouldersWristsAndTheRestLine() {
        val overlay = Landmarks.frame(t = 0.0, wristY = 0.7f).bodyOverlay(restY = 0.8)

        assertEquals(720, overlay.imageWidth)
        assertEquals(1280, overlay.imageHeight)
        assertEquals(listOf(NormalizedPoint(0.6f, 0.4f), NormalizedPoint(0.4f, 0.4f)), overlay.shoulders)
        assertEquals(listOf(NormalizedPoint(0.6f, 0.7f), NormalizedPoint(0.4f, 0.7f)), overlay.wrists)
        assertEquals(0.8, overlay.restY!!, 0.0)
    }

    @Test
    fun leavesOutShouldersAndHandsTheTrackerLost() {
        val overlay = Landmarks.frame(t = 0.0, body = false, rightHand = false).bodyOverlay(restY = null)

        assertEquals("low-visibility shoulders would draw dots in the wrong place", emptyList<NormalizedPoint>(), overlay.shoulders)
        assertEquals(listOf(NormalizedPoint(0.6f, Landmarks.REST_Y)), overlay.wrists)
        assertNull(overlay.restY)
    }

    @Test
    fun noPoseMeansNoShoulders() {
        val overlay = LandmarkFrame.create(0.0, ImageSize(10, 20)).bodyOverlay(restY = null)

        assertEquals(BodyOverlay(10, 20), overlay)
    }

    @Test
    fun mirroredPreviewPutsTheImagesLeftOnTheRight() {
        // A 720×1280 image in a 360×640 view: same aspect, scale 0.5, nothing cropped.
        val mapping = PreviewMapping(720, 1280, 360f, 640f)

        assertEquals(360f, mapping.x(0f), 1e-4f)
        assertEquals(0f, mapping.x(1f), 1e-4f)
        assertEquals(270f, mapping.x(0.25f), 1e-4f)
        assertEquals(320f, mapping.y(0.5), 1e-4f)
    }

    @Test
    fun fillCenterCropsTheOverflowEvenly() {
        // A 1280×720 landscape image filling a 400×400 square: scale 400/720, shown 711.1 wide, 155.6 cut each side.
        val mapping = PreviewMapping(1280, 720, 400f, 400f)
        val shownWidth = 1280 * (400f / 720)

        assertEquals(200f, mapping.x(0.5f), 1e-3f)
        assertEquals((400 - shownWidth) / 2 + 0.9f * shownWidth, mapping.x(0.1f), 1e-3f)
        assertEquals(0f, mapping.y(0.0), 1e-3f)
        assertEquals(400f, mapping.y(1.0), 1e-3f)
    }

    @Test
    fun unmirroredMappingKeepsSides() {
        val mapping = PreviewMapping(720, 1280, 360f, 640f, mirrored = false)

        assertEquals(90f to 480f, mapping.point(NormalizedPoint(0.25f, 0.75f)))
    }

    @Test
    fun mappingFollowsTheOverlaysImage() {
        val overlay = BodyOverlay(imageWidth = 720, imageHeight = 1280, restY = 0.82)

        assertEquals(0.82f * 640, PreviewMapping.of(overlay, 360f, 640f).y(overlay.restY!!), 1e-3f)
    }
}
