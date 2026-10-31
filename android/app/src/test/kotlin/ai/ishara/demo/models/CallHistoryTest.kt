package ai.ishara.demo.models

import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CallPresentation
import ai.ishara.demo.core.call.CaptionSpeaker
import ai.ishara.demo.core.call.TranscriptEntry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.util.UUID

/** Mirrors ios/IsharaTests/CallHistoryTests.swift. */
class CallHistoryTest {
    @get:Rule
    val temporary = TemporaryFolder()

    private val folder: File by lazy { File(temporary.root, "CallHistory") }
    private val now = System.currentTimeMillis() / 1000.0

    private fun record(minutesAgo: Double, contact: String = "City Clinic", notes: CallNotes? = null): CallRecord {
        val date = now - minutesAgo * 60
        return CallRecord(
            id = UUID.randomUUID().toString().uppercase(),
            date = date,
            contactName = contact,
            mode = if (notes == null) CallMode.LIVE else CallMode.DELEGATED,
            captions = listOf(
                CallRecord.Line(CallRecord.Line.Speaker.RECEPTIONIST, "We have 4 pm tomorrow.", date),
                CallRecord.Line(CallRecord.Line.Speaker.USER, "Yes, that works. Thank you.", date),
            ),
            notes = notes,
        )
    }

    private fun delegatedNotes(bolna: String? = null) = CallNotes(
        callId = "c1",
        mode = CallMode.DELEGATED,
        ready = true,
        outcome = "callback",
        summary = listOf("They offered: \"4 pm tomorrow\""),
        transcript = listOf(TranscriptEntry(CaptionSpeaker.RECEPTIONIST, "We have 4 pm tomorrow.", 1.0)),
        bolnaSummary = bolna,
    )

    private fun jsonFiles(): List<String> = folder.listFiles { file -> file.extension == "json" }.orEmpty().map { it.name }.sorted()

    @Test
    fun canonicalPresentationUpdateSurvivesRelaunchWithoutChangingRecipientOrOrder() {
        val history = CallHistory(folder)
        val call = record(5.0, notes = delegatedNotes()).copy(contactNumber = "synthetic-recipient", request = "Please book a check-up.")
        history.save(call)
        val newer = record(1.0)
        history.save(newer)
        val presentation = CallPresentation(title = "Appointment with Dr. Rao", overview = "Registration is still needed.",
            keyPoints = listOf("No booking confirmed."), nextStep = "Provide the registration ID.")
        history.update(call.id, delegatedNotes().copy(presentation = presentation))
        val loaded = CallHistory(folder).records
        assertEquals(newer.id, loaded.first().id)
        assertEquals("Appointment with Dr. Rao", loaded.last().displayTitle)
        assertEquals(call.date, loaded.last().date, 0.0)
        assertEquals(call.contactNumber, loaded.last().contactNumber)
        assertEquals(presentation, loaded.last().notes?.presentation)
        assertEquals("callback", loaded.last().notes?.outcome)
    }

    @Test
    fun savedCallsSurviveARelaunch() {
        val history = CallHistory(folder)
        val live = record(10.0)
        val delegated = record(5.0, "Dr. Mehta's office", delegatedNotes("Call back."))
        history.save(live)
        history.save(delegated)

        val relaunched = CallHistory(folder)

        assertEquals(listOf(delegated, live), relaunched.records)
        assertEquals(listOf("${live.id}.json", "${delegated.id}.json").sorted(), jsonFiles())
        assertNull(relaunched.problem)
    }

    @Test
    fun newestCallFirstWhateverTheSavingOrder() {
        val history = CallHistory(folder)
        val old = record(60.0)
        val newest = record(1.0)
        val middle = record(30.0)
        listOf(old, newest, middle).forEach(history::save)

        assertEquals(listOf(newest.id, middle.id, old.id), history.records.map { it.id })
        assertEquals(listOf(newest.id, middle.id, old.id), CallHistory(folder).records.map { it.id })
    }

    @Test
    fun savingTheSameCallAgainReplacesIt() {
        val history = CallHistory(folder)
        val call = record(1.0)
        history.save(call)
        val longer = call.copy(captions = call.captions + CallRecord.Line(CallRecord.Line.Speaker.AGENT, "Goodbye.", now))

        history.save(longer)

        assertEquals(listOf(longer), history.records)
        assertEquals(listOf(longer), CallHistory(folder).records)
        assertEquals(1, jsonFiles().size)
    }

    @Test
    fun deletingACallRemovesItsFile() {
        val history = CallHistory(folder)
        val kept = record(10.0)
        val deleted = record(5.0)
        history.save(kept)
        history.save(deleted)

        history.delete(deleted.id)

        assertEquals(listOf(kept), history.records)
        assertEquals(listOf("${kept.id}.json"), jsonFiles())
        assertEquals(listOf(kept), CallHistory(folder).records)
        assertNull(history.problem)
    }

    @Test
    fun bolnasLateSummaryUpdatesTheSavedCall() {
        val history = CallHistory(folder)
        val call = record(1.0, notes = delegatedNotes())
        history.save(call)

        history.update(call.id, delegatedNotes("The caller will be called back."))

        assertEquals("The caller will be called back.", history.records.first().notes?.bolnaSummary)
        val relaunched = CallHistory(folder)
        assertEquals("The caller will be called back.", relaunched.records.first().notes?.bolnaSummary)
        assertEquals(call.captions, relaunched.records.first().captions)
    }

    @Test
    fun notesForAnUnknownCallAreIgnored() {
        val history = CallHistory(folder)
        history.update(UUID.randomUUID().toString(), delegatedNotes())

        assertTrue(history.records.isEmpty())
        assertTrue(jsonFiles().isEmpty())
    }

    @Test
    fun anUnreadableFileIsSkippedAndReported() {
        val good = record(1.0)
        CallHistory(folder).save(good)
        File(folder, "broken.json").writeText("not a call")
        File(folder, "notes.txt").writeText("ignored")

        val relaunched = CallHistory(folder)

        assertEquals(listOf(good), relaunched.records)
        assertEquals("1 saved call couldn't be read.", relaunched.problem)
    }

    @Test
    fun aFolderThatCantBeWrittenIsReported() {
        folder.writeText("") // a file where the folder should be
        val history = CallHistory(folder)
        assertEquals("Saved calls couldn't be read.", history.problem)
        val call = record(1.0)

        history.save(call)

        assertEquals("the call is still shown for this launch", listOf(call), history.records)
        assertEquals("The call with City Clinic couldn't be saved on this phone.", history.problem)
    }

    @Test
    fun inMemoryHistoryStartsEmptyEveryLaunch() {
        CallHistory(folder = null).save(record(1.0))
        assertTrue(CallHistory(folder = null).records.isEmpty())
    }

    @Test
    fun aSavedCallForMeHoldsNoPhoneNumber() {
        val brief = ai.ishara.demo.call.DelegatedDemo.brief(
            ai.ishara.demo.core.call.BriefRequest(
                ai.ishara.demo.core.call.CallPurpose.DOCTOR_APPOINTMENT,
                listOf(ai.ishara.demo.core.call.Sign.TOMORROW),
                ai.ishara.demo.core.call.Profile(name = "Riya", callback = "+91 98765 43210", notes = "Fever since Monday"),
            ),
        )
        val history = CallHistory(folder)
        val call = record(1.0).copy(mode = CallMode.DELEGATED)
        history.save(call)
        history.update(
            call.id,
            ai.ishara.demo.call.DelegatedDemo.notes(
                brief.goal, "Riya", brief.text,
                listOf(TranscriptEntry(CaptionSpeaker.RECEPTIONIST, ai.ishara.demo.call.DelegatedDemo.OFFER, 100.0)),
                emptyList(), ready = true,
            ),
        )

        val json = File(folder, "${call.id}.json").readText()

        assertTrue("the brief wasn't saved", json.contains("May share: name (Riya), callback number."))
        assertTrue(!json.contains("98765") && !json.contains("+91"))
    }
}
