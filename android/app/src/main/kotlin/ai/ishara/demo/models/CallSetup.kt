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
    }
}

enum class PreferredTime { MORNINGS, AFTERNOONS, EVENINGS }

enum class CallVoice(val code: String) { INDIAN_ENGLISH("en-IN") }

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
