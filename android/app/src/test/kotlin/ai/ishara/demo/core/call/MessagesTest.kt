package ai.ishara.demo.core.call

import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.double
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Golden strings from ios/Packages/CallSession/Tests/CallSessionTests/MessagesTests.swift
 * (the backend's `model_dump_json()` output). JSON is compared as trees, so key order doesn't matter.
 */
class MessagesTest {
    @Test
    fun canonicalPresentationRoundTripsAndOldNotesDecode() {
        val presentation = CallPresentation(title = "Appointment with Dr. Rao", overview = "Registration is still needed.",
            keyPoints = listOf("No booking confirmed."), nextStep = "Provide the registration ID.")
        val notes = CallNotes(callId = "synthetic", mode = CallMode.STEER, ready = true, outcome = "unclear", presentation = presentation)
        assertEquals(notes, CoreJson.decodeFromString(CallNotes.serializer(), CoreJson.encodeToString(CallNotes.serializer(), notes)))
        val old = CoreJson.decodeFromString(CallNotes.serializer(), """{"call_id":"legacy","mode":"steer","ready":true}""")
        assertEquals(null, old.presentation)
        assertEquals("The call ended without a confirmed outcome.", old.summaryOverview)
        assertEquals(false, old.summaryComplete)
    }

    @Test
    fun legacyGeneralBriefUsesRequestClauseAndPreservesDoctorAbbreviation() {
        for (context in listOf("Preferred: tomorrow.", "Reason, if asked: a check-up.", "May share: supplied report.", "Will not agree to unrelated requests.")) {
            val brief = "Call on behalf of Asha, to carry out their approved request. Request: Book an appointment with Dr. Rao. $context"
            assertEquals("Book an appointment with Dr. Rao", requestTitle(brief))
        }
    }

    private fun <T> assertWire(serializer: KSerializer<T>, value: T, golden: String) {
        assertEquals(value, CoreJson.decodeFromString(serializer, golden))
        assertEquals(normalized(Json.parseToJsonElement(golden)), normalized(CoreJson.encodeToJsonElement(serializer, value)))
    }

    /** Numbers as doubles, so `1793430000.25` and Kotlin's `1.79343000025E9` compare equal. */
    private fun normalized(element: JsonElement): Any? = when (element) {
        is JsonObject -> element.mapValues { normalized(it.value) }
        is JsonArray -> element.map(::normalized)
        is JsonNull -> null
        is JsonPrimitive -> if (element.isString) element.content else element.booleanOrNull ?: element.double
    }

    @Test
    fun appMessagesMatchTheBackendModels() {
        val app = AppMessage.serializer()
        assertWire(
            app,
            AppMessage.Chips("t1", listOf(Sign.HELLO, Sign.DOCTOR, Sign.TOMORROW)),
            """{"type":"chips","turn_id":"t1","chips":["hello","doctor","tomorrow"]}""",
        )
        assertWire(
            app,
            AppMessage.Approve("t1", "Hello, I'd like a doctor's appointment tomorrow."),
            """{"type":"approve","turn_id":"t1","text":"Hello, I'd like a doctor's appointment tomorrow."}""",
        )
        assertWire(app, AppMessage.Stop, """{"type":"stop"}""")
        assertWire(app, AppMessage.End, """{"type":"end"}""")
        assertWire(app, AppMessage.Answer("a1", AskChoice.NO), """{"ask_id":"a1","choice":"no","type":"answer"}""")
    }

    @Test
    fun everySignIsTheBackendLiteralInItsOrder() {
        val names = Sign.entries.map { CoreJson.encodeToString(Sign.serializer(), it).trim('"') }
        assertEquals(
            "hello,thankyou,yes,no,sorry,doctor,today,tomorrow,morning,afternoon,evening,time,please,now,wait,night," +
                "yesterday,later,can,where,who,why,have,finish,callonphone,sick,hungry,drink,water,home,go,see,hear,read",
            names.joinToString(","),
        )
    }

    @Test
    fun restBodiesMatchTheBackendModels() {
        assertWire(
            StartCallRequest.serializer(),
            StartCallRequest(contactId = "city_clinic", purpose = CallPurpose.DOCTOR_APPOINTMENT),
            """{"attended":false,"contact_id":"city_clinic","mode":"live","purpose":"doctor_appointment"}""",
        )
        assertWire(
            StartCallRequest.serializer(),
            StartCallRequest(
                contactId = "clinic", purpose = CallPurpose.DOCTOR_APPOINTMENT, mode = CallMode.DELEGATED,
                briefId = "b9", attended = true,
            ),
            """{"attended":true,"brief_id":"b9","contact_id":"clinic","mode":"delegated","purpose":"doctor_appointment"}""",
        )
        assertWire(
            BriefRequest.serializer(),
            BriefRequest(CallPurpose.DOCTOR_APPOINTMENT, listOf(Sign.TOMORROW, Sign.MORNING), Profile(name = "Asha")),
            """{"chips":["tomorrow","morning"],"profile":{"details":[],"name":"Asha"},"purpose":"doctor_appointment"}""",
        )
        assertWire(
            Brief.serializer(),
            Brief("b9", "Call on behalf of Asha.", "book a doctor's appointment", listOf("preferred time: tomorrow in the morning")),
            """{"brief_id":"b9","text":"Call on behalf of Asha.","goal":"book a doctor's appointment","constraints":["preferred time: tomorrow in the morning"]}""",
        )
    }

    @Test
    fun responsesFromOlderBackendsDecodeWithDefaults() {
        assertEquals(
            CallStart("call_123", CallState.DIALING, CallMode.LIVE),
            CoreJson.decodeFromString(CallStart.serializer(), """{"call_id":"call_123","state":"dialing"}"""),
        )
        val notes = CoreJson.decodeFromString(
            CallNotes.serializer(),
            """{"call_id":"c1","mode":"delegated","ready":true,"brief":"Call on behalf of Asha.","outcome":"booked","summary":["Goal: book a doctor's appointment for Asha."],"open_questions":[],"transcript":[{"speaker":"receptionist","text":"Booked.","at":1.0}],"bolna_summary":null}""",
        )
        assertEquals(
            CallNotes(
                callId = "c1", mode = CallMode.DELEGATED, ready = true, brief = "Call on behalf of Asha.", outcome = "booked",
                summary = listOf("Goal: book a doctor's appointment for Asha."),
                transcript = listOf(TranscriptEntry(CaptionSpeaker.RECEPTIONIST, "Booked.", 1.0)),
            ),
            notes,
        )
    }

    @Test
    fun serverMessagesMatchTheBackendModels() {
        val server = ServerMessage.serializer()
        assertWire(server, ServerMessage.Status(CallState.IN_CALL), """{"type":"status","state":"in_call"}""")
        assertWire(
            server,
            ServerMessage.Caption("We have 4 pm tomorrow.", 1_793_430_000.25, CaptionSpeaker.RECEPTIONIST),
            """{"type":"caption","text":"We have 4 pm tomorrow.","at":1793430000.25,"speaker":"receptionist"}""",
        )
        assertWire(
            server,
            ServerMessage.Draft("t1", "Hello.", DraftSource.TEMPLATE),
            """{"type":"draft","turn_id":"t1","text":"Hello.","source":"template"}""",
        )
        assertWire(server, ServerMessage.Spoken("t1"), """{"type":"spoken","turn_id":"t1"}""")
        assertWire(
            server,
            ServerMessage.NotDelivered("t1", "no_confirmation"),
            """{"type":"not_delivered","turn_id":"t1","reason":"no_confirmation"}""",
        )
        assertWire(
            server,
            ServerMessage.Error("stale_turn", "That turn is closed; start a new one."),
            """{"type":"error","code":"stale_turn","message":"That turn is closed; start a new one."}""",
        )
        assertWire(
            server,
            ServerMessage.Ask(
                "a1", "We have 4 pm tomorrow. Does that work?",
                listOf(
                    AskOption(AskChoice.YES, "Yes, 4 pm tomorrow works. Thank you."),
                    AskOption(AskChoice.NO, "No, sorry."),
                    AskOption(AskChoice.WAIT, "One moment."),
                ),
                "I'll call back.", 10.0,
            ),
            """{"type":"ask","ask_id":"a1","question":"We have 4 pm tomorrow. Does that work?","options":[{"choice":"yes","spoken":"Yes, 4 pm tomorrow works. Thank you."},{"choice":"no","spoken":"No, sorry."},{"choice":"wait","spoken":"One moment."}],"fallback":"I'll call back.","timeout_s":10.0}""",
        )
        assertWire(
            server,
            ServerMessage.AskResolved("a1", "Yes, 4 pm tomorrow works. Thank you.", "user"),
            """{"type":"ask_resolved","ask_id":"a1","spoken":"Yes, 4 pm tomorrow works. Thank you.","source":"user"}""",
        )
    }

    @Test
    fun captionWithoutSpeakerIsTheReceptionists() {
        assertEquals(
            ServerMessage.Caption("Hello?", 1.0, CaptionSpeaker.RECEPTIONIST),
            CoreJson.decodeFromString(ServerMessage.serializer(), """{"type":"caption","text":"Hello?","at":1.0}"""),
        )
    }

    @Test
    fun commandsUseTheBridgeShape() {
        assertWire(
            CallCommand.serializer(),
            CallCommand.Add(Chip("A1", ChipKind.Recognised(Sign.HELLO))),
            """{"op":"add","chip":{"id":"A1","kind":{"kind":"recognised","sign":"hello"}}}""",
        )
        assertWire(
            CallCommand.serializer(),
            CallCommand.Add(Chip("A2", ChipKind.Unsure)),
            """{"op":"add","chip":{"id":"A2","kind":{"kind":"unsure"}}}""",
        )
        assertWire(CallCommand.serializer(), CallCommand.Send, """{"op":"send"}""")
        assertWire(CallCommand.serializer(), CallCommand.UseQuickReply(QuickReply.REPEAT), """{"op":"useQuickReply","reply":"repeat"}""")
    }
}
