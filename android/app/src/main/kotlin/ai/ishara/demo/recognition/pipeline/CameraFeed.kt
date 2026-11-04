package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.BodyOverlay
import ai.ishara.demo.recognition.CameraPermission
import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Matrix
import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.lifecycle.awaitInstance
import androidx.camera.view.PreviewView
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.channels.SendChannel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.Executors

/**
 * The front camera, continuously. Without permission no frames come and `camera.permission`
 * says why; that is not a failure, because the camera card explains it. Frames start as soon as
 * the screens report the permission granted ([CameraXLiveCamera.onPermissionResult]). Port of
 * `CameraFeed` in ios/Ishara/Recognition/FrameFeed.swift.
 *
 * Only the latest frames are kept (two), as on iOS: recognition runs on what the user does now.
 */
class CameraFeed(private val context: Context, private val scope: CoroutineScope) : FrameFeed {
    private val live = CameraXLiveCamera(currentPermission(context))
    override val camera: CameraXLiveCamera get() = live
    override val replayOptions: List<String> = emptyList()
    override var onFailure: ((Throwable) -> Unit)? = null
    private var pump: Job? = null

    override fun items(): ReceiveChannel<FeedItem> {
        pump?.cancel()
        val frames = Channel<FeedItem>(capacity = LATEST_FRAMES, onBufferOverflow = BufferOverflow.DROP_OLDEST)
        pump = scope.launch(Dispatchers.Main) {
            try {
                live.permission.first { it == CameraPermission.GRANTED }
                live.stream(context, frames)
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                onFailure?.invoke(error)
            } finally {
                frames.close()
            }
        }
        return frames
    }

    override fun replay(option: String) = Unit

    override fun stop() {
        pump?.cancel()
        pump = null
    }

    companion object {
        private const val LATEST_FRAMES = 2

        fun currentPermission(context: Context): CameraPermission =
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                CameraPermission.GRANTED
            } else {
                CameraPermission.NOT_DETERMINED
            }
    }
}

class CameraUnavailableException : IllegalStateException("This device has no usable front camera.")

/**
 * The front camera as the screens see it: one CameraX [Preview] (shared by every screen that
 * shows it, never rebuilt) bound together with the [ImageAnalysis] recognition reads, so both
 * show the same 16:9 picture. Analysis frames are unmirrored; the preview is mirrored.
 */
class CameraXLiveCamera(permission: CameraPermission) : FeedCamera {
    private val mutablePermission = MutableStateFlow(permission)
    override val permission: StateFlow<CameraPermission> = mutablePermission.asStateFlow()
    private val mutableUnavailable = MutableStateFlow(false)
    override val isUnavailable: StateFlow<Boolean> = mutableUnavailable.asStateFlow()
    override val overlay = MutableStateFlow<BodyOverlay?>(null)

    private val resolution = ResolutionSelector.Builder()
        .setAspectRatioStrategy(AspectRatioStrategy.RATIO_16_9_FALLBACK_AUTO_STRATEGY)
        .setResolutionStrategy(ResolutionStrategy(TARGET_SIZE, ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER))
        .build()
    private val preview = Preview.Builder().setResolutionSelector(resolution).build()

    override fun onPermissionResult(granted: Boolean) {
        mutablePermission.value = if (granted) CameraPermission.GRANTED else CameraPermission.DENIED
    }

    @Composable
    override fun Preview(modifier: Modifier) {
        AndroidView(
            factory = { context ->
                PreviewView(context).apply {
                    implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                    scaleType = PreviewView.ScaleType.FILL_CENTER
                    preview.setSurfaceProvider(surfaceProvider)
                }
            },
            modifier = modifier,
        )
    }

    /** Binds the camera and sends upright frames to [frames] until cancelled. */
    internal suspend fun stream(context: Context, frames: SendChannel<FeedItem>): Unit = withContext(Dispatchers.Main) {
        val provider = ProcessCameraProvider.awaitInstance(context)
        if (!provider.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA)) {
            mutableUnavailable.value = true
            throw CameraUnavailableException()
        }
        val analysis = ImageAnalysis.Builder()
            .setResolutionSelector(resolution)
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
            .build()
        val executor = Executors.newSingleThreadExecutor()
        analysis.setAnalyzer(executor) { image ->
            image.use { frames.trySend(FeedItem.Frame(BitmapFrame(upright(it), it.imageInfo.timestamp / 1e9))) }
        }
        val owner = CameraLifecycle()
        try {
            provider.bindToLifecycle(owner, CameraSelector.DEFAULT_FRONT_CAMERA, preview, analysis)
            awaitCancellation()
        } finally {
            provider.unbind(analysis, preview)
            owner.destroy()
            analysis.clearAnalyzer()
            executor.shutdown()
        }
    }

    private class CameraLifecycle : LifecycleOwner {
        private val registry = LifecycleRegistry(this).apply { currentState = Lifecycle.State.RESUMED }
        override val lifecycle: Lifecycle get() = registry

        fun destroy() {
            registry.currentState = Lifecycle.State.DESTROYED
        }
    }

    companion object {
        private val TARGET_SIZE = Size(1280, 720)

        /** The sensor image turned upright; front-camera analysis frames are not mirrored. */
        fun upright(image: ImageProxy): Bitmap {
            val bitmap = image.toBitmap()
            val degrees = image.imageInfo.rotationDegrees
            if (degrees == 0) return bitmap
            val matrix = Matrix().apply { postRotate(degrees.toFloat()) }
            return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true).also { bitmap.recycle() }
        }
    }
}
