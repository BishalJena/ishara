package ai.ishara.demo.models

import ai.ishara.demo.core.call.Chip
import ai.ishara.demo.core.call.Draft
import ai.ishara.demo.core.call.QuickReply

// Turn state (chips, drafts, turn ids, captions, quick replies) comes from CallSession's
// TurnStore, the single source of truth for the SEND safety rules. This file only adds
// what the screens need on top.

/** The badge on the draft card, saying where the sentence came from. */
enum class DraftBadge(val title: String) {
    LLM("LLM"),
    TEMPLATE("Template"),
    QUICK_REPLY("Quick reply"),

    /** The last reply wasn't spoken; SEND offers it again on a new turn. */
    NOT_DELIVERED("Not delivered"),

    /** The user stopped the last reply before it was spoken; SEND offers it again. */
    STOPPED("Stopped"),
    ;

    companion object {
        fun of(origin: Draft.Origin): DraftBadge = when (origin) {
            Draft.Origin.LLM -> LLM
            Draft.Origin.TEMPLATE -> TEMPLATE
            Draft.Origin.QUICK_REPLY -> QUICK_REPLY
        }
    }
}

/** The sentence the draft card shows and SEND would speak. */
data class DraftDisplay(val text: String, val badge: DraftBadge)

/** The sign's word ("thankyou"), or "?" for an unsure sign. */
val Chip.label: String get() = sign?.wire ?: "?"

/** What the chip shows: the word as written ("thank you"). */
val Chip.title: String get() = if (label == "thankyou") "thank you" else label

val QuickReply.label: String
    get() = when (this) {
        QuickReply.YES -> "Yes"
        QuickReply.NO -> "No"
        QuickReply.WAIT -> "Wait"
        QuickReply.REPEAT -> "Repeat"
    }

/** The wire spelling ("repeat"), used in test tags like iOS's accessibility identifiers. */
val QuickReply.wire: String get() = name.lowercase()
