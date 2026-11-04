package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.RecognitionController
import android.content.Context
import kotlinx.coroutines.CoroutineScope

/**
 * The real recognition pipelines. [scope] runs on the main thread and lives as long as the
 * controller (an application or view-model scope); call the controller from that thread.
 */
object RecognitionPipelines {
    /** The front camera (a device). Get ready asks the screens to request camera permission. */
    fun camera(context: Context, scope: CoroutineScope): RecognitionController {
        val assets = RecognitionAssets(context)
        return PipelineRecognitionController(
            feed = CameraFeed(context.applicationContext, scope),
            scope = scope,
            notice = assets.notice,
            makeComponents = assets::makeComponents,
        )
    }

    /**
     * Saved sign videos played in real time (the emulator). A clip named `rest` plays first for
     * Get ready; the others become replay options. Defaults to the debug build's sample clips.
     */
    fun clips(
        context: Context,
        scope: CoroutineScope,
        clips: List<ReplayClip> = RecognitionAssets(context).sampleClips(),
    ): RecognitionController {
        val assets = RecognitionAssets(context)
        return PipelineRecognitionController(
            feed = ClipFeed(clips, scope),
            scope = scope,
            notice = assets.notice,
            makeComponents = assets::makeComponents,
        )
    }
}
