package ai.ishara.demo.models

import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallPurpose
import ai.ishara.demo.core.call.Detail
import ai.ishara.demo.core.call.Document
import ai.ishara.demo.core.call.Profile
import ai.ishara.demo.core.call.StartCallRequest

/**
 * Someone the user can ask Ishara to call. The phone number lives only on the backend
 * allowlist; the app refers to a saved contact by its id. [phoneNumber] (E.164) is set for a
 * typed or pasted number, which the backend dials only when its allowlist holds it.
 */
data class Contact(val id: String, val name: String, val phoneNumber: String? = null) {
    companion object {
        val cityClinic = Contact(id = "clinic", name = "City Clinic")
        val mehtaOffice = Contact(id = "mehta-office", name = "Dr. Mehta's office")

        /** Synthetic demo contacts. Real numbers stay in the backend allowlist. */
        val demoContacts = listOf(cityClinic, mehtaOffice)

        private val e164 = Regex("""^\+[1-9]\d{6,14}$""")

        /** A typed or pasted number as a contact; the name defaults to the number, spaced. */
        fun number(digits: String, name: String? = null): Contact? {
            val number = digits.filter { it.isDigit() || it == '+' }
            if (!e164.matches(number)) return null
            val given = name?.trim().orEmpty()
            val shown = if (given.isEmpty() || isNumberName(given)) display(number) else given
            return Contact(id = "number", name = shown, phoneNumber = number)
        }

        /** "+919800012345" as people write it: "+91 98000 12345". */
        fun display(e164: String): String {
            val digits = e164.filter(Char::isDigit)
            if (!e164.startsWith("+91") || digits.length != 12) return e164
            val national = digits.drop(2)
            return "+91 ${national.take(5)} ${national.takeLast(5)}"
        }

        /** A "name" that is really a number (a record of a call to a typed number). */
        fun isNumberName(name: String): Boolean {
            val first = name.firstOrNull() ?: return false
            return first == '+' || first.isDigit()
        }

        /** An Indian number from its 10 national digits (the app is India-only, so +91 is implied). */
        fun indian(digits: String, name: String? = null): Contact? {
            val national = digits.filter(Char::isDigit)
            if (national.length != 10 || national.first() == '0' || national.first() == '1') return null
            return number("+91$national", name)
        }

        /** The 10 national digits of a number typed or picked in any common Indian form. */
        fun indianDigits(raw: String): String {
            var digits = raw.filter(Char::isDigit)
            if (digits.length == 12 && digits.startsWith("91")) digits = digits.drop(2)
            if (digits.length == 11 && digits.startsWith("0")) digits = digits.drop(1)
            return digits.take(10)
        }
    }
}

val CallPurpose.title: String
    get() = when (this) {
        CallPurpose.DOCTOR_APPOINTMENT -> "Doctor's appointment"
    }

enum class PreferredTime(val title: String) { MORNINGS("Mornings"), AFTERNOONS("Afternoons"), EVENINGS("Evenings") }

enum class CallVoice(val code: String, val title: String) { INDIAN_ENGLISH("en-IN", "Indian English") }

/** Details the user saved once so quick replies and the composer can use them. */
data class SavedDetails(val name: String, val preferredTime: PreferredTime)

/**
 * Decision D9: the brief the user read and approved, and whether they stay on the call to
 * answer the agent's questions (attended). [mode] is `DELEGATED` or `STEER`.
 */
data class Delegation(val brief: Brief, val attended: Boolean, val mode: CallMode = CallMode.DELEGATED)

/** Everything chosen on the Home screen before a call starts. */
data class CallSetup(
    val contact: Contact,
    val purpose: CallPurpose,
    val details: SavedDetails,
    val voice: CallVoice,
    /** Set for a delegated or steer call; null for a live call, where every sentence is approved. */
    val delegation: Delegation? = null,
    /** Steer call: what the user typed the call is about. */
    val request: String? = null,
    /** Steer call: facts the user approved for sharing when the receptionist asks. */
    val sharedDetails: List<Detail> = emptyList(),
    /** Cards, letters or bills the user attached, as text read on the phone. */
    val documents: List<Document> = emptyList(),
    /** The user's callback number, given only if the receptionist asks how to reach them. */
    val callback: String? = null,
) {
    val isSteer: Boolean get() = delegation?.mode == CallMode.STEER

    /** The brief request for a steer call: the typed request plus the profile and details. */
    val steerBriefRequest: BriefRequest
        get() = BriefRequest(
            purpose = purpose,
            chips = emptyList(),
            profile = Profile(
                name = details.name,
                callback = callback,
                details = sharedDetails,
                documents = documents.ifEmpty { null },
            ),
            request = request,
        )

    /**
     * The `POST /calls` body. Starting a delegated call with its brief id is the user's one
     * approval of that brief.
     */
    val startRequest: StartCallRequest
        get() {
            val contactId = if (contact.phoneNumber == null) contact.id else null
            val delegation = delegation
                ?: return StartCallRequest(contactId = contactId, phoneNumber = contact.phoneNumber, purpose = purpose)
            return StartCallRequest(
                contactId = contactId,
                phoneNumber = contact.phoneNumber,
                purpose = purpose,
                mode = delegation.mode,
                briefId = delegation.brief.briefId,
                attended = delegation.attended,
            )
        }

    companion object {
        /** Synthetic details for the rehearsed clinic call (PLAN §1). */
        val demo = CallSetup(
            contact = Contact.cityClinic,
            purpose = CallPurpose.DOCTOR_APPOINTMENT,
            details = SavedDetails(name = "Riya", preferredTime = PreferredTime.MORNINGS),
            voice = CallVoice.INDIAN_ENGLISH,
        )
    }
}
