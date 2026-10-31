package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.CameraPermission
import ai.ishara.demo.recognition.RecognitionTestAssets
import android.Manifest
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The front camera feed: no frames until the screens report the permission, then frames or, on a
 * device without a front camera (the emulator), the unavailable state and a failure. Never
 * revokes the permission: that would kill the test process.
 */
@RunWith(AndroidJUnit4::class)
class CameraFeedTest {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    @After
    fun tearDown() = scope.cancel()

    @Test
    fun startsOnlyOnceThePermissionIsReportedGranted() = runBlocking {
        val context = RecognitionTestAssets.app
        val feed = withContext(Dispatchers.Main) { CameraFeed(context, scope) }
        val failures = mutableListOf<Throwable>()
        feed.onFailure = { failures += it }
        val items = withContext(Dispatchers.Main) {
            feed.camera.onPermissionResult(false)
            feed.items()
        }

        delay(500)
        assertEquals(CameraPermission.DENIED, feed.camera.permission.value)
        assertTrue("a refusal is explained by the camera card, not reported as a failure", failures.isEmpty())
        assertNull("no frames without permission", items.tryReceive().getOrNull())
        assertFalse(items.isClosedForReceive)

        InstrumentationRegistry.getInstrumentation().uiAutomation.grantRuntimePermission(context.packageName, Manifest.permission.CAMERA)
        withContext(Dispatchers.Main) { feed.camera.onPermissionResult(true) }

        // Either frames come, or (the emulator: no front camera) the camera is marked unavailable.
        val first = withTimeoutOrNull(10_000) { items.receiveCatching().getOrNull() }
        if (first != null) {
            val frame = (first as FeedItem.Frame).frame
            val second = (withTimeoutOrNull(5_000) { items.receive() } as FeedItem.Frame).frame
            assertTrue("time moves forward", second.timestamp > frame.timestamp)
            assertTrue("frames are upright for a portrait device", frame.bitmap.height > frame.bitmap.width)
            assertFalse(feed.camera.isUnavailable.value)
        } else {
            assertTrue("the feed ended without frames", items.isClosedForReceive)
            assertTrue("no front camera marks the camera unavailable", feed.camera.isUnavailable.value)
            assertTrue(failures.single() is CameraUnavailableException)
        }
        withContext(Dispatchers.Main) { feed.stop() }
    }
}
