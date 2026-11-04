package ai.ishara.demo.ui.steer

import ai.ishara.demo.models.Contact
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** iOS `SetupView`'s contact pick: `pickedName = name; number = Contact.indianDigits(from: number)`. */
class PickedContactTest {
    @Test
    fun aContactsNumberInAnyIndianFormBecomesTenDigits() {
        assertEquals(PickedContact("Dr Kavita Rao", "9800012345"), PickedContact.of("Dr Kavita Rao", "+91 98000 12345"))
        assertEquals("9800012345", PickedContact.of("Clinic", "098000-12345")?.digits)
        assertEquals("9800012345", PickedContact.of("Clinic", "(+91) 98000 12345")?.digits)
    }

    @Test
    fun thePickedNumberIsReadyToCall() {
        val picked = PickedContact.of(" City Clinic ", "+91 98000 12345")!!

        assertEquals(Contact("number", "City Clinic", "+919800012345"), Contact.indian(picked.digits, picked.name))
    }

    @Test
    fun aContactWithoutANameShowsNoName() {
        assertEquals(PickedContact("", "9800012345"), PickedContact.of("+91 98000 12345", "+91 98000 12345"))
        assertEquals("", PickedContact.of(null, "9800012345")?.name)
    }

    @Test
    fun aRowWithoutANumberPicksNobody() {
        assertNull(PickedContact.of("Dr Kavita Rao", null))
        assertNull(PickedContact.of("Dr Kavita Rao", "  "))
    }

    @Test
    fun aForeignNumberIsKeptForHomeToRefuse() {
        val picked = PickedContact.of("Abroad", "+1 555 123 4567")!!

        assertNull("Home says it needs the 10-digit Indian number", Contact.indian(picked.digits, picked.name))
    }
}
