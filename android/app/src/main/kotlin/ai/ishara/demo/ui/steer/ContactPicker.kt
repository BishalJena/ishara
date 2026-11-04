package ai.ishara.demo.ui.steer

import ai.ishara.demo.models.Contact
import android.app.Activity
import android.content.ContentResolver
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.ContactsContract.CommonDataKinds.Phone
import androidx.activity.result.contract.ActivityResultContract

/**
 * The system contact picker, showing phone numbers (iOS `ContactPicker`). Picking from the
 * phone-number list hands back that one number's row with a temporary read grant, so the app
 * needs no contacts permission and never sees the rest of the address book.
 */
class PickPhoneNumber : ActivityResultContract<Unit, Uri?>() {
    override fun createIntent(context: Context, input: Unit): Intent =
        Intent(Intent.ACTION_PICK).setType(Phone.CONTENT_TYPE)

    override fun parseResult(resultCode: Int, intent: Intent?): Uri? =
        intent?.data.takeIf { resultCode == Activity.RESULT_OK }
}

/** Who was picked: the name to show (empty when the contact has none) and the 10 national digits. */
data class PickedContact(val name: String, val digits: String) {
    companion object {
        /** The picked row's name and number, read through the picker's grant; null if it has no number. */
        fun read(resolver: ContentResolver, uri: Uri): PickedContact? =
            resolver.query(uri, arrayOf(Phone.DISPLAY_NAME, Phone.NUMBER), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) of(cursor.getString(0), cursor.getString(1)) else null
            }

        /**
         * Like iOS: the name as the address book has it and the number in its 10 national digits
         * (Home then says if they aren't an Indian mobile number). Android names a contact
         * without one by its number, which iOS leaves empty.
         */
        fun of(name: String?, number: String?): PickedContact? {
            if (number.isNullOrBlank()) return null
            val shown = name?.trim().orEmpty().takeUnless(Contact::isNumberName).orEmpty()
            return PickedContact(shown, Contact.indianDigits(number))
        }
    }
}
