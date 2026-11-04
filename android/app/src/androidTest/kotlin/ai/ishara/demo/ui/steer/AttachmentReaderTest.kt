package ai.ishara.demo.ui.steer

import ai.ishara.demo.models.Attachment
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.pdf.PdfDocument
import android.net.Uri
import android.os.Build
import androidx.core.graphics.createBitmap
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * iOS `AttachmentReader` on the device: a PDF's own text, a scanned PDF and a photo through
 * on-device OCR (ML Kit's bundled Latin model), and files that can't be read.
 */
@RunWith(AndroidJUnit4::class)
class AttachmentReaderTest {
    private val context: Context = ApplicationProvider.getApplicationContext()
    private val reader = AttachmentReader(context.contentResolver)
    private val folder = File(context.cacheDir, "attachment-tests").apply { mkdirs() }

    private fun textImage(vararg lines: String): Bitmap {
        val bitmap = createBitmap(1200, 200 + 120 * lines.size)
        Canvas(bitmap).apply {
            drawColor(Color.WHITE)
            val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.BLACK
                textSize = 72f
                typeface = Typeface.DEFAULT_BOLD
            }
            lines.forEachIndexed { index, line -> drawText(line, 60f, 160f + 120f * index, paint) }
        }
        return bitmap
    }

    private fun png(name: String, bitmap: Bitmap): Uri {
        val file = File(folder, name)
        file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        return Uri.fromFile(file)
    }

    private fun pdf(name: String, draw: (Canvas) -> Unit): Uri {
        val document = PdfDocument()
        val page = document.startPage(PdfDocument.PageInfo.Builder(612, 792, 1).create())
        draw(page.canvas)
        document.finishPage(page)
        val file = File(folder, name)
        file.outputStream().use(document::writeTo)
        document.close()
        return Uri.fromFile(file)
    }

    @Test
    fun aPhotosTextIsReadOnThePhone() = runBlocking {
        val attachment = reader.read(png("card.png", textImage("PATIENT ID CCC 20417", "PENICILLIN ALLERGY")), "Photo")

        assertNull(attachment.problem)
        assertTrue(attachment.text, attachment.text.contains("CCC 20417"))
        assertTrue(attachment.text, attachment.text.contains("PENICILLIN"))
        assertEquals("Photo", attachment.name)
        assertNotNull("a thumbnail for the row", attachment.thumbnail)
        assertTrue(attachment.thumbnail!!.width <= 120 && attachment.thumbnail.height <= 120)
    }

    @Test
    fun aPdfsOwnTextIsUsed() = runBlocking {
        // Android reads a PDF's text layer from Android 15; earlier versions read it by OCR.
        val uri = pdf("history.pdf") { canvas ->
            val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 18f }
            canvas.drawText("Allergic to penicillin. Takes amlodipine 5 mg once a day.", 40f, 80f, paint)
        }

        val attachment = reader.read(uri)

        assertNull(attachment.problem)
        assertEquals("history.pdf", attachment.name)
        assertTrue(attachment.text, attachment.text.contains("penicillin"))
        assertTrue(attachment.text, attachment.text.contains("amlodipine 5 mg"))
        assertNotNull(attachment.thumbnail)
    }

    @Test
    fun aScannedPdfIsReadByOcr() = runBlocking {
        val scan = textImage("BLOOD PRESSURE 128 OVER 84")
        val uri = pdf("scan.pdf") { canvas -> canvas.drawBitmap(scan, null, android.graphics.Rect(20, 40, 592, 40 + 572 * scan.height / scan.width), null) }

        val attachment = reader.read(uri)

        assertNull(attachment.problem)
        assertTrue(attachment.text, attachment.text.contains("BLOOD PRESSURE"))
    }

    @Test
    fun aPictureWithoutTextSendsNothing() = runBlocking {
        val blank = createBitmap(400, 400).apply { eraseColor(Color.WHITE) }

        val attachment = reader.read(png("blank.png", blank), "Photo")

        assertEquals("No text found in it.", attachment.problem)
        assertNull(attachment.document)
    }

    @Test
    fun filesThatArentAPdfOrAnImageCantBeOpened() = runBlocking {
        val notPdf = File(folder, "letter.pdf").apply { writeText("not a pdf") }
        val notImage = File(folder, "photo.jpg").apply { writeText("not an image") }

        assertEquals(Attachment.UNREADABLE, reader.read(Uri.fromFile(notPdf)).problem)
        assertEquals(Attachment.UNREADABLE, reader.read(Uri.fromFile(notImage), "Photo").problem)
        assertEquals(Attachment.UNREADABLE, reader.read(Uri.fromFile(File(folder, "missing.pdf"))).problem)
    }

    @Test
    fun theTextLayerPathRunsOnAndroid15AndLater() {
        assumeTrue(Build.VERSION.SDK_INT >= Build.VERSION_CODES.VANILLA_ICE_CREAM)
        // A PDF whose text is too small for OCR at the render size is still read word for word.
        val uri = pdf("fine-print.pdf") { canvas ->
            canvas.drawText("Policy number HX-449120-77", 40f, 80f, Paint().apply { textSize = 4f })
        }

        val attachment = runBlocking { reader.read(uri) }

        assertTrue(attachment.text, attachment.text.contains("HX-449120-77"))
    }
}
