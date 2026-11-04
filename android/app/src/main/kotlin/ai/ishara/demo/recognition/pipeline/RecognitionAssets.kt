package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.core.NativeLogitsMatcher
import ai.ishara.demo.recognition.core.NativeRecognitionRules
import android.content.Context
import android.util.Log
import java.io.FileInputStream
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.channels.FileChannel

/**
 * Model and data files the recognition pipeline loads from the APK's assets. Port of
 * ios/Ishara/Recognition/RecognitionAssets.swift (ASL path only).
 *
 * The models are large, so they're not in Git: the build copies them from the iOS app's
 * `ios/Ishara/LocalAssets/` (see the README there) when they are present. `asl-bundle.json`
 * comes from `ios/Ishara/Resources`. Debug builds also carry `LocalAssets/SampleSigns` clips for
 * the emulator. Anything missing turns its part off: no Holistic model → recognition can't start
 * (the controller's failure says why); no ASL model or an invalid bundle → every sign is `?`
 * (the notice says so).
 */
class RecognitionAssets(context: Context) {
    private val context = context.applicationContext
    private val rootAssets: Set<String> = context.assets.list("").orEmpty().toSet()

    val hasHolisticModel: Boolean get() = HolisticLandmarkProvider.MODEL_ASSET in rootAssets
    val hasAslModel: Boolean get() = LiteRTLogitsModel.MODEL_ASSET in rootAssets

    val aslBundleJson: String? by lazy {
        if (BUNDLE_ASSET !in rootAssets) null else context.assets.open(BUNDLE_ASSET).bufferedReader().use { it.readText() }
    }

    /** The clips in the `SampleSigns` asset folder (debug builds only). */
    fun sampleClips(): List<ReplayClip> = context.assets.list(SAMPLE_SIGNS).orEmpty()
        .filter { name -> ReplayClip.extensions.any { name.lowercase().endsWith(".$it") } }
        .map { ReplayClip.asset(context.assets, "$SAMPLE_SIGNS/$it") }

    /**
     * Shown on Get ready when recognition will run but can only answer `?`, or when its
     * thresholds are still provisional (never hidden).
     */
    val notice: String?
        get() {
            if (!hasAslModel) {
                return "asl-signs.tflite is missing from LocalAssets, so every sign will show [?]. " +
                    "Run the SignPipelineLiteRT download script."
            }
            val provisional = loadMatcher()?.use { it.provisional }
                ?: return "The ASL recognition bundle is missing or invalid, so every sign will show [?]."
            return if (provisional) "ASL recognition thresholds are provisional: not yet frozen on a labelled phone session." else null
        }

    /**
     * Builds the landmark provider and the classifier on the worker thread. A missing or broken
     * ASL model or bundle leaves the classifier answering `?`; a missing Holistic model throws.
     */
    fun makeComponents(): PipelineComponents {
        if (!hasHolisticModel) throw RecognitionSetupException(MISSING_HOLISTIC)
        val rules = NativeRecognitionRules()
        val matcher = loadMatcher()
        val model = if (hasAslModel) loadModel() else null
        val landmarks = try {
            HolisticLandmarkProvider(context, HolisticLandmarkProvider.MODEL_ASSET)
        } catch (error: Exception) {
            matcher?.close()
            model?.close()
            throw error
        }
        return PipelineComponents(landmarks, SegmentClassifier(model, matcher, rules), rules) {
            landmarks.close()
            model?.close()
            matcher?.close()
        }
    }

    /** null (every sign `?`) when there is no bundle or it fails validation. */
    fun loadMatcher(): NativeLogitsMatcher? {
        val json = aslBundleJson ?: return null
        return try {
            NativeLogitsMatcher(json)
        } catch (error: IllegalArgumentException) {
            Log.e(TAG, "ASL bundle rejected: ${error.message}")
            null
        }
    }

    private fun loadModel(): LiteRTLogitsModel? = try {
        LiteRTLogitsModel(mapAsset(LiteRTLogitsModel.MODEL_ASSET))
    } catch (error: Exception) {
        Log.e(TAG, "ASL model not loaded", error)
        null
    }

    /** Memory-maps an uncompressed asset. */
    fun mapAsset(name: String): ByteBuffer = context.assets.openFd(name).use { descriptor ->
        FileInputStream(descriptor.fileDescriptor).channel.use { channel ->
            channel.map(FileChannel.MapMode.READ_ONLY, descriptor.startOffset, descriptor.declaredLength)
        }
    }

    class RecognitionSetupException(message: String) : IOException(message)

    companion object {
        const val BUNDLE_ASSET = "asl-bundle.json"
        const val SAMPLE_SIGNS = "SampleSigns"
        private const val TAG = "IsharaRecognition"
        private const val MISSING_HOLISTIC =
            "holistic_landmarker.task is missing from LocalAssets. Run the SignPipelineMediaPipe download script."
    }
}
