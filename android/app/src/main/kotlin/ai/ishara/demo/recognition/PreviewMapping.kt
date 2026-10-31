package ai.ishara.demo.recognition

import kotlin.math.max

/**
 * Maps normalized points of the upright camera image onto a view that shows that image
 * aspect-filled (PreviewView's FILL_CENTER: scaled to cover, overflow cropped evenly) and, for
 * the front camera, mirrored. Port of `PreviewMapping` in ios/Ishara/Views/Components/BodyOverlayView.swift.
 */
class PreviewMapping(
    imageWidth: Int,
    imageHeight: Int,
    private val viewWidth: Float,
    private val viewHeight: Float,
    private val mirrored: Boolean = true,
) {
    private val scale = max(viewWidth / imageWidth, viewHeight / imageHeight)
    private val shownWidth = imageWidth * scale
    private val shownHeight = imageHeight * scale

    fun x(normalizedX: Float): Float {
        val x = if (mirrored) 1 - normalizedX else normalizedX
        return (viewWidth - shownWidth) / 2 + x * shownWidth
    }

    fun y(normalizedY: Double): Float = ((viewHeight - shownHeight) / 2 + normalizedY * shownHeight).toFloat()

    /** View coordinates (x, y) of a normalized image point. */
    fun point(point: NormalizedPoint): Pair<Float, Float> = x(point.x) to y(point.y.toDouble())

    companion object {
        fun of(overlay: BodyOverlay, viewWidth: Float, viewHeight: Float, mirrored: Boolean = true) =
            PreviewMapping(overlay.imageWidth, overlay.imageHeight, viewWidth, viewHeight, mirrored)
    }
}
