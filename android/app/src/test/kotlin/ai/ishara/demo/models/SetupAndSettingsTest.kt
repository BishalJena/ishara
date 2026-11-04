package ai.ishara.demo.models

import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.Document
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** The steer Home's draft, Settings storage and the Indian number rules (iOS `SetupView`, `SettingsSheet`, `Contact`). */
class SetupAndSettingsTest {
    private val values = mutableMapOf<String, String>()
    private val settings = UserSettings(UserSettings.InMemory(values))

    @Test
    fun settingsAreKeptUnderTheIosKeys() {
        settings.updateName("Riya")
        settings.updateCallback("+91 98000 12345")

        assertEquals(mapOf("ishara.name" to "Riya", "ishara.callback" to "9800012345"), values)
        assertEquals("Riya", UserSettings(UserSettings.InMemory(values)).name)
        assertEquals("+91 98000 12345", settings.callbackForCall)
    }

    @Test
    fun callbackKeepsOnlyDigitsAndIsGivenOnlyWhenComplete() {
        settings.updateCallback("98a00")
        assertEquals("9800", settings.callback)
        assertNull(settings.callbackForCall)
        settings.updateCallback("098000 12345")
        assertEquals("9800012345", settings.callback)
    }

    @Test
    fun aUiTestNameIsPresetOnlyWhenNoneIsSaved() {
        settings.presetNameIfEmpty("Riya")
        assertEquals("Riya", settings.name)
        settings.presetNameIfEmpty("Asha")
        assertEquals("Riya", settings.name)
        UserSettings(UserSettings.InMemory()).apply { presetNameIfEmpty(" ") }.also { assertEquals("", it.name) }
    }

    @Test
    fun indianNumbersInEveryCommonForm() {
        assertEquals("9845012345", Contact.indianDigits("+91 98450 12345"))
        assertEquals("9845012345", Contact.indianDigits("098450 12345"))
        assertEquals("9845012345", Contact.indianDigits("9845012345"))
        assertNull("a national number never starts with 0 or 1", Contact.indian("1845012345"))
        assertNull(Contact.indian("984501234"))
        assertEquals("+919845012345", Contact.indian("9845012345")?.phoneNumber)
        assertEquals("number", Contact.indian("9845012345")?.id)
        assertNull(Contact.number("12345"))
        assertEquals("+15551234567", Contact.display("+15551234567"))
    }

    @Test
    fun theDraftSaysWhatIsMissingInOrder() {
        val draft = SetupDraft()
        assertEquals("No backend.", draft.problem("No backend."))
        assertEquals("Enter a number, or pick someone.", draft.problem(null))
        draft.number = "98450"
        assertEquals("Enter the 10-digit number.", draft.problem(null))
        draft.number = "9845012345"
        assertEquals("Say what the call is about.", draft.problem(null))
        draft.request = "  Book a check-up  "
        assertNull(draft.problem(null))
    }

    @Test
    fun aSteerCallNeedsTheCallersNameAndCarriesTheRequest() {
        val draft = SetupDraft().apply {
            number = "9845012345"
            pickedName = "Dr Mehta"
            request = "  Book a check-up  "
            attachments = listOf(Document("card.jpg", "Policy 42"))
        }
        assertNull("Settings asks for the name first", draft.callSetup(settings, null))

        settings.updateName(" Riya ")
        settings.updateCallback("9800012345")
        val setup = draft.callSetup(settings, null)!!

        assertEquals(Contact("number", "Dr Mehta", "+919845012345"), setup.contact)
        assertEquals("Riya", setup.details.name)
        assertEquals("Book a check-up", setup.request)
        assertEquals(listOf(Document("card.jpg", "Policy 42")), setup.documents)
        assertEquals("+91 98000 12345", setup.callback)
        assertNull(draft.callSetup(settings, "No backend."))

        draft.clear()
        assertEquals(listOf("", "", ""), listOf(draft.number, draft.pickedName, draft.request))
    }

    @Test
    fun recentPeopleAreThoseCalledByNumberOnceEach() {
        fun record(name: String, number: String?, date: Double) =
            CallRecord(id = "$name$date", date = date, contactName = name, contactNumber = number, mode = CallMode.STEER, captions = emptyList())
        val people = SetupDraft.recentPeople(
            listOf(record("Dr Mehta", "+919845012345", 3.0), record("City Clinic", null, 2.0), record("Mehta again", "+919845012345", 1.0)),
        )
        assertEquals(listOf(Contact("number", "Dr Mehta", "+919845012345")), people)
    }
}
