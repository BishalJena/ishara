package ai.ishara.demo.ui.steer

import ai.ishara.demo.models.Attachment
import android.content.ContentResolver
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.ImageDecoder
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.Build
import android.provider.OpenableColumns
import androidx.core.graphics.createBitmap
import androidx.core.graphics.scale
import com.google.android.gms.tasks.Task
import com.google.mlkit.common.MlKitException
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.IOException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Reads the text of an attached photo or PDF on this phone (iOS `AttachmentReader`): a PDF's
 * own text where Android can read it (API 35+), otherwise its pages through on-device OCR
 * (ML Kit, bundled Latin model, like iOS's Vision fallback for scans); a photo through OCR.
 * Nothing leaves the phone here; only the text goes with the brief.
 */
class AttachmentReader(private val resolver: ContentResolver) {
    /** [name] is shown on the row; photos from the photo picker are just "Photo", as on iOS. */
    suspend fun read(uri: Uri, name: String = displayName(uri)): Attachment = withContext(Dispatchers.IO) {
        try {
            if (isPdf(uri, name)) readPdf(uri, name) else readImage(uri, name)
        } catch (_: IOException) {
            Attachment.unreadable(name)
        } catch (_: SecurityException) {
            // The picker's read grant is gone (or never covered this file).
            Attachment.unreadable(name)
        }
    }

    /** The file's name as the document picker shows it. */
    fun displayName(uri: Uri): String =
        resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getString(0) else null
        } ?: uri.lastPathSegment ?: "File"

    private fun isPdf(uri: Uri, name: String): Boolean =
        resolver.getType(uri) == PDF_TYPE || name.endsWith(".pdf", ignoreCase = true)

    private suspend fun readPdf(uri: Uri, name: String): Attachment {
        val descriptor = resolver.openFileDescriptor(uri, "r") ?: return Attachment.unreadable(name)
        return descriptor.use {
            PdfRenderer(it).use { pdf ->
                if (pdf.pageCount == 0) return@use Attachment.read(name, null, "")
                val thumbnail = pdf.render(0, THUMBNAIL_SIZE)
                var text = pdf.textLayer()
                if (text.isBlank()) text = pdf.recognisePages()
                Attachment.read(name, thumbnail, text)
            }
        }
    }

    /** The PDF's own text, page by page; empty for scans and before Android 15, which can't read it. */
    private fun PdfRenderer.textLayer(): String {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.VANILLA_ICE_CREAM) return ""
        return (0 until pageCount).joinToString("\n") { index ->
            openPage(index).use { page -> page.textContents.joinToString("\n") { it.text.orEmpty() } }
        }
    }

    /** OCR of the first pages, stopping once there is more text than the brief takes. */
    private suspend fun PdfRenderer.recognisePages(): String {
        val pages = mutableListOf<String>()
        for (index in 0 until minOf(pageCount, MAX_OCR_PAGES)) {
            pages += recognise(render(index, OCR_SIZE))
            if (pages.sumOf { it.length } >= Attachment.TEXT_LIMIT) break
        }
        return pages.joinToString("\n")
    }

    private suspend fun readImage(uri: Uri, name: String): Attachment {
        val image = try {
            ImageDecoder.decodeBitmap(ImageDecoder.createSource(resolver, uri)) { decoder, info, _ ->
                // ML Kit reads software bitmaps; very large photos are scaled down for memory.
                decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                val longest = max(info.size.width, info.size.height)
                if (longest > OCR_SIZE * 2) {
                    val factor = OCR_SIZE * 2f / longest
                    decoder.setTargetSize((info.size.width * factor).roundToInt(), (info.size.height * factor).roundToInt())
                }
            }
        } catch (_: ImageDecoder.DecodeException) {
            return Attachment.unreadable(name)
        }
        return Attachment.read(name, image.fitting(THUMBNAIL_SIZE), recognise(image))
    }

    private suspend fun recognise(bitmap: Bitmap): String {
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        return try {
            val text = recognizer.process(InputImage.fromBitmap(bitmap, 0)).await()
            text.textBlocks.flatMap { it.lines }.joinToString("\n") { it.text }
        } catch (_: MlKitException) {
            // Like iOS's Vision request: a failed recognition reads as no text ("No text found in it.").
            ""
        } finally {
            recognizer.close()
        }
    }

    companion object {
        const val PDF_TYPE = "application/pdf"
        private const val THUMBNAIL_SIZE = 120
        private const val OCR_SIZE = 1600

        /** iOS reads only a scan's first page; without a text layer below Android 15 every PDF is OCR'd, so a few more. */
        private const val MAX_OCR_PAGES = 10
    }
}

/** Renders a page on white (PDF pages are transparent) to fit a [size] × [size] box. */
private fun PdfRenderer.render(index: Int, size: Int): Bitmap = openPage(index).use { page ->
    val scale = size.toFloat() / max(page.width, page.height)
    val bitmap = createBitmap(max(1, (page.width * scale).roundToInt()), max(1, (page.height * scale).roundToInt()))
    bitmap.eraseColor(Color.WHITE)
    page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
    bitmap
}

private fun Bitmap.fitting(size: Int): Bitmap {
    val scale = size.toFloat() / max(width, height)
    if (scale >= 1f) return this
    return scale(max(1, (width * scale).roundToInt()), max(1, (height * scale).roundToInt()))
}

private suspend fun <T> Task<T>.await(): T = suspendCancellableCoroutine { continuation ->
    addOnSuccessListener { continuation.resume(it) }
    addOnFailureListener { continuation.resumeWithException(it) }
    addOnCanceledListener { continuation.cancel() }
}
