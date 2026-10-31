package ai.ishara.demo.ui.steer

import ai.ishara.demo.models.Attachment
import ai.ishara.demo.models.CallHistory
import ai.ishara.demo.models.CallRecord
import ai.ishara.demo.models.Contact
import ai.ishara.demo.models.SetupDraft
import ai.ishara.demo.models.UserSettings
import ai.ishara.demo.ui.components.InitialsAvatar
import ai.ishara.demo.ui.components.IsharaButtons
import ai.ishara.demo.ui.home.outcomeText
import ai.ishara.demo.ui.home.recentCallDate
import android.Manifest
import android.content.ActivityNotFoundException
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.MutableTransitionState
import androidx.compose.animation.core.spring
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Cancel
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.DocumentScanner
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.PictureAsPdf
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedIconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import kotlinx.coroutines.launch

/**
 * Home for steer calls (port of iOS `SetupView`): who to call (a typed or pasted number, a
 * contact, or someone called before), what the call is about, and any card, letter or bill
 * Ishara may quote from, read on this phone. One tap places the call ([onCall]; the navigator
 * asks for the caller's name first if none is saved); Ishara runs it and the user steps in
 * whenever they like.
 */
@Composable
fun SetupScreen(
    draft: SetupDraft,
    settings: UserSettings,
    history: CallHistory,
    modeDescription: String,
    /** Why a call can't be placed right now (no backend configured, or the brief failed). */
    setupProblem: String?,
    onCall: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenRecent: (recordId: String) -> Unit,
) {
    val colors = steerColors()
    val call = rememberCallWithNotificationsAsked(onCall)
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.background)
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        TopBar(settings.name, onOpenSettings)
        Text(
            "Who are we\ncalling today?",
            fontSize = 36.sp,
            lineHeight = 40.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = (-0.8).sp,
            color = colors.primary,
            modifier = Modifier.semantics { heading() },
        )
        Composer(draft, history, setupProblem, onCall = call)
        Text(
            "Ishara leads the call from what you wrote and never adds anything else. It calls from Ishara's number, not yours. $modeDescription".trim(),
            style = SteerType.footnote,
            color = colors.secondary,
            modifier = Modifier.testTag("setup.disclosure"),
        )
        if (history.records.isNotEmpty()) Recent(history.records, onOpenRecent)
    }
}

/**
 * The first Call asks for notifications (Android 13+), which show the ongoing call and its End
 * button outside the app; the call is placed whatever the answer.
 */
@Composable
private fun rememberCallWithNotificationsAsked(onCall: () -> Unit): () -> Unit {
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { onCall() }
    return remember(context, launcher, onCall) {
        {
            val asks = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
            if (asks) launcher.launch(Manifest.permission.POST_NOTIFICATIONS) else onCall()
        }
    }
}

@Composable
private fun TopBar(name: String, onOpenSettings: () -> Unit) {
    val colors = steerColors()
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Box(
            Modifier.size(36.dp).background(colors.yellow, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Text(name.take(1).uppercase(), color = Color.Black, fontWeight = FontWeight.Bold, fontSize = 14.sp)
        }
        Text(
            if (name.isEmpty()) "Hi there" else "Hi ${name.split(" ").firstOrNull { it.isNotEmpty() } ?: name}",
            style = SteerType.headline,
            color = colors.primary,
            modifier = Modifier.weight(1f),
        )
        IconButton(
            onClick = onOpenSettings,
            modifier = Modifier
                .size(36.dp)
                .background(colors.secondaryBackground, CircleShape)
                .testTag("setup.settings"),
        ) {
            Icon(Icons.Filled.Tune, contentDescription = "Settings", tint = colors.primary, modifier = Modifier.size(20.dp))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Composer(draft: SetupDraft, history: CallHistory, setupProblem: String?, onCall: () -> Unit) {
    val colors = steerColors()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val reader = remember(context) { AttachmentReader(context.contentResolver) }
    var reading by remember { mutableIntStateOf(0) }
    var showsAttachMenu by rememberSaveable { mutableStateOf(false) }
    var pickerProblem by remember { mutableStateOf<String?>(null) }
    val usesNumber = draft.number.isNotEmpty()
    val problem = draft.problem(setupProblem)

    fun attach(uri: Uri, name: String?) {
        reading += 1
        scope.launch {
            val attachment = if (name == null) reader.read(uri) else reader.read(uri, name)
            reading -= 1
            draft.attachments = draft.attachments + attachment
        }
    }

    val photoPicker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        uri?.let { attach(it, "Photo") }
    }
    val filePicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let { attach(it, null) }
    }
    val contactPicker = rememberLauncherForActivityResult(PickPhoneNumber()) { uri ->
        val picked = uri?.let { PickedContact.read(context.contentResolver, it) } ?: return@rememberLauncherForActivityResult
        draft.pickedName = picked.name
        draft.number = picked.digits
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(colors.secondaryBackground, RoundedCornerShape(28.dp))
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("To", style = SteerType.headline, color = colors.secondary)
            Text("+91", style = SteerType.body.copy(fontFamily = FontFamily.Monospace), color = if (usesNumber) colors.primary else colors.secondary)
            PlainField(
                value = draft.number,
                onValueChange = { raw ->
                    draft.number = if (raw.length > 10) Contact.indianDigits(raw) else raw.filter(Char::isDigit)
                },
                placeholder = "10-digit number",
                style = SteerType.body.copy(fontFamily = FontFamily.Monospace),
                keyboardType = KeyboardType.Phone,
                singleLine = true,
                modifier = Modifier
                    .weight(1f)
                    .testTag("setup.number")
                    .semantics { contentDescription = "Number, +91" },
            )
            if (usesNumber) {
                if (draft.pickedName.isNotEmpty()) {
                    Text(
                        draft.pickedName,
                        style = SteerType.subheadline,
                        fontWeight = FontWeight.SemiBold,
                        color = colors.primary,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false).testTag("setup.pickedName"),
                    )
                }
                IconButton(
                    onClick = {
                        draft.number = ""
                        draft.pickedName = ""
                    },
                    modifier = Modifier.size(40.dp).testTag("setup.clear"),
                ) {
                    Icon(Icons.Filled.Cancel, contentDescription = "Clear", tint = colors.secondary, modifier = Modifier.size(20.dp))
                }
            }
        }
        val people = SetupDraft.recentPeople(history.records)
        if (!usesNumber && people.isNotEmpty()) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.horizontalScroll(rememberScrollState()).testTag("setup.recentPeople"),
            ) {
                people.forEach { person ->
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(5.dp),
                        modifier = Modifier
                            .clip(CircleShape)
                            .background(colors.tertiaryBackground)
                            .clickable {
                                draft.number = Contact.indianDigits(person.phoneNumber.orEmpty())
                                draft.pickedName = if (Contact.isNumberName(person.name)) "" else person.name
                            }
                            .padding(vertical = 6.dp, horizontal = 10.dp)
                            .testTag("setup.recentPerson"),
                    ) {
                        Icon(Icons.Filled.History, contentDescription = null, tint = colors.primary, modifier = Modifier.size(15.dp))
                        Text(person.name, style = SteerType.footnote, fontWeight = FontWeight.SemiBold, color = colors.primary)
                    }
                }
            }
        }
        HorizontalDivider(color = colors.separator, thickness = 0.5.dp)
        PlainField(
            value = draft.request,
            onValueChange = { draft.request = it },
            placeholder = "What should Ishara do? e.g. Book a check-up next week, mornings only.",
            style = SteerType.title3.copy(fontWeight = FontWeight.Medium),
            minLines = 3,
            maxLines = 8,
            modifier = Modifier.fillMaxWidth().testTag("setup.request"),
        )
        if (draft.attachments.isNotEmpty() || reading > 0) {
            AttachmentsRow(draft.attachments, reading > 0) { removed ->
                draft.attachments = draft.attachments.filter { it.id != removed.id }
            }
        }
        (pickerProblem ?: problem)?.let { text ->
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                modifier = Modifier.testTag("setup.problem").semantics(mergeDescendants = true) {},
            ) {
                Icon(Icons.Outlined.Info, contentDescription = null, tint = colors.secondary, modifier = Modifier.size(16.dp))
                Text(text, style = SteerType.footnote, color = colors.secondary)
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            CircleToolButton(Icons.Filled.AttachFile, "Attach a photo or file", "setup.attach") { showsAttachMenu = true }
            CircleToolButton(Icons.Filled.AccountCircle, "Contacts", "setup.contacts") {
                pickerProblem = try {
                    contactPicker.launch(Unit)
                    null
                } catch (_: ActivityNotFoundException) {
                    "This phone has no contacts app to pick from."
                }
            }
            Spacer(Modifier.weight(1f))
            Button(
                onClick = { if (problem == null) onCall() },
                enabled = problem == null,
                colors = ButtonDefaults.buttonColors(
                    containerColor = colors.green,
                    contentColor = Color.White,
                    disabledContainerColor = colors.tertiary.copy(alpha = 0.18f),
                    disabledContentColor = colors.tertiary,
                ),
                contentPadding = PaddingValues(horizontal = 24.dp, vertical = 10.dp),
                modifier = Modifier.heightIn(min = IsharaButtons.Height).testTag("setup.call"),
            ) {
                Icon(Icons.Filled.Call, contentDescription = null, modifier = Modifier.size(IsharaButtons.IconSize))
                Spacer(Modifier.width(8.dp))
                Text("Call", style = IsharaButtons.Label)
            }
        }
    }

    if (showsAttachMenu) {
        ModalBottomSheet(onDismissRequest = { showsAttachMenu = false }, modifier = Modifier.testTag("setup.attachMenu")) {
            Column(Modifier.padding(bottom = 24.dp)) {
                Text("Attach", style = SteerType.headline, modifier = Modifier.padding(horizontal = 24.dp))
                Text(
                    "A card, letter or bill. Ishara reads it on this phone and can quote it on the call, word for word, only when asked.",
                    style = SteerType.footnote,
                    color = colors.secondary,
                    modifier = Modifier.padding(horizontal = 24.dp, vertical = 8.dp),
                )
                ListItem(
                    headlineContent = { Text("Photo") },
                    leadingContent = { Icon(Icons.Filled.Image, contentDescription = null) },
                    colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                    modifier = Modifier.clickable {
                        showsAttachMenu = false
                        photoPicker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                    }.testTag("setup.attachPhoto"),
                )
                ListItem(
                    headlineContent = { Text("File or PDF") },
                    leadingContent = { Icon(Icons.Filled.PictureAsPdf, contentDescription = null) },
                    colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                    modifier = Modifier.clickable {
                        showsAttachMenu = false
                        filePicker.launch(arrayOf(AttachmentReader.PDF_TYPE, "image/*"))
                    }.testTag("setup.attachFile"),
                )
            }
        }
    }
}

@Composable
private fun AttachmentsRow(attachments: List<Attachment>, isReading: Boolean, onRemove: (Attachment) -> Unit) {
    val colors = steerColors()
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        attachments.forEach { attachment ->
            // Each row springs in (no bounce) when it is added, like iOS's `appear` transition.
            val appeared = remember(attachment.id) { MutableTransitionState(false).apply { targetState = true } }
            AnimatedVisibility(
                visibleState = appeared,
                enter = scaleIn(spring(stiffness = 600f), initialScale = 0.85f) + fadeIn(),
                exit = fadeOut(),
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    modifier = Modifier.testTag("setup.attachment"),
                ) {
                    val thumbnail = attachment.thumbnail
                    if (thumbnail != null) {
                        Image(
                            thumbnail.asImageBitmap(),
                            contentDescription = null,
                            contentScale = ContentScale.Crop,
                            modifier = Modifier.size(36.dp).clip(RoundedCornerShape(8.dp)),
                        )
                    } else {
                        Icon(Icons.Filled.Description, contentDescription = null, tint = colors.primary, modifier = Modifier.size(36.dp).padding(6.dp))
                    }
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
                        Text(
                            attachment.name,
                            style = SteerType.subheadline,
                            fontWeight = FontWeight.SemiBold,
                            color = colors.primary,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Text(attachment.summary, style = SteerType.caption, color = colors.secondary, modifier = Modifier.testTag("setup.attachmentSummary"))
                    }
                    IconButton(onClick = { onRemove(attachment) }, modifier = Modifier.size(28.dp)) {
                        Icon(Icons.Filled.Cancel, contentDescription = "Remove", tint = colors.secondary)
                    }
                }
            }
        }
        if (isReading) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Icon(Icons.Filled.DocumentScanner, contentDescription = null, tint = colors.secondary, modifier = Modifier.size(15.dp))
                Text("Reading on this phone…", style = SteerType.caption, color = colors.secondary)
            }
        }
    }
}

@Composable
private fun Recent(records: List<CallRecord>, onOpen: (String) -> Unit) {
    val colors = steerColors()
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Recent", style = SteerType.title3, fontWeight = FontWeight.Bold, color = colors.primary)
        records.forEach { record ->
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(22.dp))
                    .background(colors.secondaryBackground)
                    .clickable { onOpen(record.id) }
                    .padding(14.dp)
                    .testTag("recentCalls.row")
                    .semantics(mergeDescendants = true) {},
            ) {
                InitialsAvatar(record.contactName, color = colors.purple)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(record.outcomeText(), style = SteerType.subheadline, fontWeight = FontWeight.SemiBold, color = colors.primary)
                    val who = if (Contact.isNumberName(record.contactName)) Contact.display(record.contactName) else record.contactName
                    Text("$who · ${recentCallDate(record.date)}", style = SteerType.caption, color = colors.secondary)
                }
                Icon(
                    Icons.AutoMirrored.Filled.KeyboardArrowRight,
                    contentDescription = null,
                    tint = colors.tertiary,
                    modifier = Modifier.size(18.dp),
                )
            }
        }
    }
}

@Composable
private fun CircleToolButton(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, tag: String, onClick: () -> Unit) {
    val colors = steerColors()
    OutlinedIconButton(
        onClick = onClick,
        border = null,
        modifier = Modifier
            .size(40.dp)
            .background(colors.tertiary.copy(alpha = 0.16f), CircleShape)
            .testTag(tag),
    ) {
        Icon(icon, contentDescription = label, tint = colors.primary, modifier = Modifier.size(22.dp))
    }
}

/** A borderless text field with a grey placeholder, like SwiftUI's plain `TextField`. */
@Composable
internal fun PlainField(
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    style: TextStyle,
    modifier: Modifier = Modifier,
    keyboardType: KeyboardType = KeyboardType.Text,
    singleLine: Boolean = false,
    minLines: Int = 1,
    maxLines: Int = if (singleLine) 1 else Int.MAX_VALUE,
    keyboardOptions: KeyboardOptions = KeyboardOptions(keyboardType = keyboardType),
    keyboardActions: androidx.compose.foundation.text.KeyboardActions = androidx.compose.foundation.text.KeyboardActions.Default,
) {
    val colors = steerColors()
    BasicTextField(
        value = value,
        onValueChange = onValueChange,
        textStyle = style.copy(color = colors.primary),
        cursorBrush = SolidColor(colors.blue),
        singleLine = singleLine,
        minLines = minLines,
        maxLines = maxLines,
        keyboardOptions = keyboardOptions,
        keyboardActions = keyboardActions,
        modifier = modifier,
        decorationBox = { inner ->
            Box {
                if (value.isEmpty()) Text(placeholder, style = style, color = colors.tertiary)
                inner()
            }
        },
    )
}
