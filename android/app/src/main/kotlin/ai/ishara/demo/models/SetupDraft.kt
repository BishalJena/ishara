package ai.ishara.demo.models

import ai.ishara.demo.core.call.CallPurpose
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/**
 * What the user has typed on the steer Home, kept while they're on a call so "Back to the
 * request" finds it as they left it; cleared once a call has been through and they're done.
 */
class SetupDraft {
    /** The 10 national digits (India only; +91 is implied). */
    var number: String by mutableStateOf("")
    var pickedName: String by mutableStateOf("")
    var request: String by mutableStateOf("")

    /** Cards, letters or bills read on this phone; the readable ones go as text Ishara may quote from. */
    var attachments: List<Attachment> by mutableStateOf(emptyList())

    fun clear() {
        number = ""
        pickedName = ""
        request = ""
        attachments = emptyList()
    }

    val typedContact: Contact? get() = Contact.indian(number, pickedName)

    /** Why CALL can't be tapped yet; null when it can. */
    fun problem(setupProblem: String?): String? = when {
        setupProblem != null -> setupProblem
        number.isEmpty() -> "Enter a number, or pick someone."
        typedContact == null -> "Enter the 10-digit number."
        request.isBlank() -> "Say what the call is about."
        else -> null
    }

    /**
     * The call to place, or null while there is a [problem] or no name is saved (Settings
     * asks for it first: Ishara introduces the caller by name).
     */
    fun callSetup(settings: UserSettings, setupProblem: String?): CallSetup? {
        val contact = typedContact
        val name = settings.name.trim()
        if (problem(setupProblem) != null || contact == null || name.isEmpty()) return null
        return CallSetup(
            contact = contact,
            purpose = CallPurpose.DOCTOR_APPOINTMENT,
            details = SavedDetails(name = name, preferredTime = PreferredTime.MORNINGS),
            voice = CallVoice.INDIAN_ENGLISH,
            request = request.trim(),
            documents = attachments.mapNotNull(Attachment::document),
            // Said only when they ask how to reach the caller ("You can reach me on ...").
            callback = settings.callbackForCall,
        )
    }

    companion object {
        /** People called before from this phone, newest first, one each. */
        fun recentPeople(records: List<CallRecord>): List<Contact> {
            val seen = mutableSetOf<String>()
            return records.mapNotNull { record ->
                val number = record.contactNumber ?: return@mapNotNull null
                if (!seen.add(number)) null else Contact.number(number, record.contactName)
            }
        }
    }
}
