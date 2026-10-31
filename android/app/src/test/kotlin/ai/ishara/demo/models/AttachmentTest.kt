package ai.ishara.demo.models

import ai.ishara.demo.core.call.Document
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** iOS `AttachmentReader.attachment(name:thumbnail:text:)`: what text goes with the brief. */
class AttachmentTest {
    @Test
    fun readTextIsTrimmedAndGoesAsADocument() {
        val attachment = Attachment.read("Health history.pdf", null, "\n  Allergic to penicillin.\n ")

        assertEquals("Allergic to penicillin.", attachment.text)
        assertNull(attachment.problem)
        assertEquals(Document("Health history.pdf", "Allergic to penicillin."), attachment.document)
        assertEquals("Read on this phone · Ishara can quote it when asked", attachment.summary)
    }

    @Test
    fun textIsCappedAtTwentyThousandCharacters() {
        val long = "a".repeat(Attachment.TEXT_LIMIT) + "TAIL"

        val attachment = Attachment.read("long.pdf", null, "  $long")

        assertEquals(20_000, attachment.text.length)
        assertEquals("a".repeat(20_000), attachment.text)
    }

    @Test
    fun theCapCountsAfterTrimming() {
        val attachment = Attachment.read("spaced.pdf", null, " ".repeat(50) + "b".repeat(Attachment.TEXT_LIMIT))

        assertEquals("b".repeat(20_000), attachment.text)
    }

    @Test
    fun noTextIsAProblemAndSendsNothing() {
        val attachment = Attachment.read("blank.jpg", null, " \n\t ")

        assertEquals("No text found in it.", attachment.problem)
        assertEquals("No text found in it.", attachment.summary)
        assertNull(attachment.document)
    }

    @Test
    fun anUnreadableFileSaysSoAndSendsNothing() {
        val attachment = Attachment.unreadable("notes.docx")

        assertEquals("Couldn't open this file.", attachment.summary)
        assertNull(attachment.document)
        assertEquals("notes.docx", attachment.name)
    }

    @Test
    fun eachAttachmentHasItsOwnId() {
        val first = Attachment.read("card.jpg", null, "Policy 42")
        val second = Attachment.read("card.jpg", null, "Policy 42")

        assert(first.id != second.id) { "the same photo attached twice is removable one at a time" }
    }
}
