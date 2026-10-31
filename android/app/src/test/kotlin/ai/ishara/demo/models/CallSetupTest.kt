package ai.ishara.demo.models

import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallPurpose
import ai.ishara.demo.core.call.Detail
import ai.ishara.demo.core.call.Profile
import ai.ishara.demo.core.call.StartCallRequest
import org.junit.Assert.assertEquals
import org.junit.Test

class CallSetupTest {
    private val brief = Brief(briefId = "b7", text = "Call on behalf of Riya.", goal = "book", constraints = emptyList())

    @Test
    fun liveCallToASavedContactSendsOnlyItsId() {
        assertEquals(
            StartCallRequest(contactId = "clinic", purpose = CallPurpose.DOCTOR_APPOINTMENT),
            CallSetup.demo.startRequest,
        )
    }

    @Test
    fun typedNumberIsSentInsteadOfTheContactId() {
        val setup = CallSetup.demo.copy(contact = Contact(id = "number", name = "Test number", phoneNumber = "+15555550100"))

        assertEquals(
            StartCallRequest(phoneNumber = "+15555550100", purpose = CallPurpose.DOCTOR_APPOINTMENT),
            setup.startRequest,
        )
    }

    @Test
    fun delegatedAndSteerCallsCarryTheBriefModeAndAttendance() {
        val delegated = CallSetup.demo.copy(delegation = Delegation(brief, attended = true))
        val steer = CallSetup.demo.copy(delegation = Delegation(brief, attended = false, mode = CallMode.STEER))

        assertEquals(
            StartCallRequest(
                contactId = "clinic", purpose = CallPurpose.DOCTOR_APPOINTMENT, mode = CallMode.DELEGATED,
                briefId = "b7", attended = true,
            ),
            delegated.startRequest,
        )
        assertEquals(CallMode.STEER, steer.startRequest.mode)
        assertEquals(false, steer.startRequest.attended)
        assertEquals(true, steer.isSteer)
        assertEquals(false, delegated.isSteer)
    }

    @Test
    fun steerBriefRequestCarriesTheTypedRequestAndProfile() {
        val setup = CallSetup.demo.copy(
            request = "Book a check-up",
            sharedDetails = listOf(Detail("Date of birth", "12 March 1998")),
            callback = "+15555550100",
        )

        assertEquals(
            BriefRequest(
                purpose = CallPurpose.DOCTOR_APPOINTMENT,
                chips = emptyList(),
                profile = Profile(name = "Riya", callback = "+15555550100", details = listOf(Detail("Date of birth", "12 March 1998"))),
                request = "Book a check-up",
            ),
            setup.steerBriefRequest,
        )
    }
}
