package ai.ishara.demo.call

import ai.ishara.demo.core.call.AskChoice
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallPurpose
import ai.ishara.demo.core.call.CaptionSpeaker
import ai.ishara.demo.core.call.DraftSource
import ai.ishara.demo.core.call.Profile
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.core.call.TranscriptEntry
import ai.ishara.demo.recognition.RecognitionResult
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Mirrors ios/IsharaTests/DemoScriptTests.swift plus the fake call's brief and notes (FakeCallTests). */
class DemoScriptTest {
    @Test
    fun scriptedChipsGetTheRehearsedLlmSentence() {
        assertEquals("No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?" to DraftSource.LLM, DemoScript.draft(listOf(Sign.NO, Sign.MORNING)))
    }

    @Test
    fun wrongChipFallsBackToTemplateInSignOrder() {
        assertEquals(
            "No. In the afternoon, please. In the morning, please." to DraftSource.TEMPLATE,
            DemoScript.draft(listOf(Sign.NO, Sign.AFTERNOON, Sign.MORNING)),
        )
    }

    @Test
    fun everySignHasATemplatePhrase() {
        for (sign in Sign.entries) assertNotNull(sign.wire, DemoScript.templatePhrases[sign])
    }

    @Test
    fun scriptPlansOneWrongChipAndOneUnsureSign() {
        val signs = DemoScript.stages.flatMap { it.signs }
        assertTrue(RecognitionResult.Recognised(Sign.AFTERNOON) in signs)
        assertEquals(1, signs.count { it == RecognitionResult.Unsure })
        assertEquals(listOf(false, true, false), DemoScript.stages.map { it.losesFraming })
    }

    @Test
    fun fakeBriefSaysOnlyWhatWasSignedAndTyped() {
        val brief = DelegatedDemo.brief(
            BriefRequest(CallPurpose.DOCTOR_APPOINTMENT, listOf(Sign.NOW, Sign.AFTERNOON), Profile(name = " Riya ", callback = "123")),
        )

        assertEquals(
            "Call on behalf of Riya, who is Deaf and uses the Ishara app, to book a doctor's appointment. " +
                "Preferred: today in the afternoon. May share: name (Riya), callback number. " +
                "Will not agree to anything outside this brief; anything else comes back to you as a question.",
            brief.text,
        )
        assertEquals(listOf("preferred time: today in the afternoon"), brief.constraints)
        assertEquals("today in the afternoon", DelegatedDemo.preferredTime(brief))
    }

    @Test
    fun aBriefWithoutTimeOrCallbackSaysSo() {
        val brief = DelegatedDemo.brief(BriefRequest(CallPurpose.DOCTOR_APPOINTMENT, listOf(Sign.HELLO), Profile(name = "Riya", notes = "Fever")))

        assertEquals(
            "Call on behalf of Riya, who is Deaf and uses the Ishara app, to book a doctor's appointment. " +
                "Reason, if asked: Fever May share: name (Riya). " +
                "Will not agree to anything outside this brief; anything else comes back to you as a question.",
            brief.text,
        )
        assertTrue(brief.constraints.isEmpty())
        assertNull(DelegatedDemo.preferredTime(brief))
    }

    @Test
    fun theOpeningAndTimeLinesFollowTheBackend() {
        assertEquals("I'd like to book a doctor's appointment for Riya, tomorrow in the morning.", DelegatedDemo.opening("Riya", "book a doctor's appointment", "tomorrow in the morning"))
        assertEquals("I'd like to book a doctor's appointment for Riya.", DelegatedDemo.opening("Riya", "book a doctor's appointment", null))
        assertEquals("Tomorrow in the morning, please. What times are available?", DelegatedDemo.timeLine("tomorrow in the morning"))
        assertEquals(listOf(AskChoice.TOMORROW, AskChoice.MORNING, AskChoice.NOW, AskChoice.WAIT), DelegatedDemo.timeOptions.map { it.choice })
        assertEquals(listOf(AskChoice.YES, AskChoice.NO, AskChoice.WAIT), DelegatedDemo.options.map { it.choice })
        assertEquals("tomorrow in the morning", DelegatedDemo.`when`(listOf(Sign.MORNING, Sign.TOMORROW, Sign.MORNING)))
    }

    private fun entry(speaker: CaptionSpeaker, text: String) = TranscriptEntry(speaker, text, 1.0)

    @Test
    fun notesOutcomeComesFromTheTranscript() {
        fun outcome(transcript: List<TranscriptEntry>, answers: List<String> = emptyList()) =
            DelegatedDemo.notes("book", "Riya", "brief", transcript, answers, ready = true)

        val booked = outcome(listOf(entry(CaptionSpeaker.RECEPTIONIST, DelegatedDemo.OFFER), entry(CaptionSpeaker.RECEPTIONIST, DelegatedDemo.CONFIRMATION)), listOf("Yes."))
        assertEquals("booked", booked.outcome)
        assertEquals(
            listOf("Goal: book for Riya.", "They offered: \"${DelegatedDemo.OFFER}\"", "You answered: \"Yes.\"", "They confirmed: \"${DelegatedDemo.CONFIRMATION}\""),
            booked.summary,
        )
        assertTrue(booked.openQuestions.isEmpty())

        val callback = outcome(listOf(entry(CaptionSpeaker.AGENT, DelegatedDemo.CALLBACK_LINE)))
        assertEquals("callback", callback.outcome)
        assertEquals(1, callback.openQuestions.size)
        assertEquals("declined", outcome(emptyList(), listOf("No, thanks.")).outcome)
        assertEquals("unclear", outcome(emptyList()).outcome)
        assertNull(DelegatedDemo.notes("book", "Riya", "brief", emptyList(), emptyList(), ready = false).outcome)
    }
}
