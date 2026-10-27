# Ishara workflow: what the user does and what the app does

Updated 27 October 2026 (decisions D8 and D9). Decisions and tasks live in
[PLAN.md](../PLAN.md); the visual version is the [architecture board](architecture/README.md).
This is the demo flow, not a validated product: no Deaf participant has reviewed it.

**Built so far (27 Oct):** every screen below exists and is tested in the iOS simulator, on a
scripted demo call and against the real backend code with a scripted receptionist. Nothing has
run on an iPhone or on a real Bolna call yet.

## Two ways to call

```
                 ┌─CALL──────▶ [3 Call: signing] ──SEND──▶ [4 Call: speaking] ──┐   (next turn)
 [1 Home] ─▶ [2 Get ready]                    ▲                                 │
                 │                            └─────────────────────────────────┘
                 └─CALL FOR ME─▶ [5 Brief] ──approve──▶ [6 Call: agent] ──ends──▶ [7 Notes]
```

| Screen | What the user sees and does | What happens underneath |
|---|---|---|
| **1 Home** | Picks who to call (e.g. City Clinic), the purpose (doctor's appointment), their name and preferred time; then **CALL** (they sign each reply) or **CALL FOR ME** (the agent calls from a brief). Both say the call comes from Ishara's number, not theirs | Contacts are ids; the numbers live only on the backend's allowlist |
| **2 Get ready** | Props the phone about an arm away. Checklist: face, both hands, light. Rests their hands for 2 s | The rest position calibrates the start/stop detector. Recognition starts here |
| **3 Call: signing** | Reads the receptionist's caption, signs, checks the chips and the draft, taps **SEND**. Quick replies: Yes, No, Wait, Repeat | Each finished sign becomes a chip (or a "did you mean" tile, or [?]); every chip change recomposes the draft (Groq + validator, templates as fallback) |
| **4 Call: speaking** | "Speaking now…" with the exact sentence; SEND becomes **STOP**; then "✓ Delivered" | The backend sends a Bolna event; Bolna speaks it with the Sarvam voice; chips and draft are wiped so old text can't replay |
| **5 Brief** | Signs or taps what they need (TOMORROW · MORNING), checks their name, an optional callback number and reason, taps **Prepare the request**, reads the brief, chooses **I'll stay and answer questions** or not, taps **Approve and call** | The backend builds the brief only from those chips and fields. Editing anything hides the brief until it is rebuilt, so the approval always matches what is on screen |
| **6 Call: agent** | Captions of both sides. No draft or SEND. If they stayed: a question card with YES / NO / WAIT, each showing exactly what the agent will say; they sign or tap one | The agent opens with the brief, answers from it, and pauses ("one moment, please") when the receptionist offers something that needs the user. Unattended, it says it will call back |
| **7 Notes** | Outcome (booked, needs a callback, declined, unclear), what they offered, what is still open, the brief, the full transcript, and Bolna's own summary marked as possibly wrong | Built from the transcript; the summary quotes it |

Camera pill: **green** = watching (hands at rest), **yellow** = sign in progress,
**red** = can't see you. Chips: **green** = recognised (✕ removes one), **red [?]**
= unsure and never spoken.

## How a sign becomes a chip

All on the phone; nothing is uploaded.

```
hands rise ──▶ sign ──▶ hands back at rest ~0.4 s ──▶ landmarks of that sign ──▶ ASL model (250 signs)
   ──▶ top sign one of our words, p ≥ 0.6 and 0.3 ahead of the next ──▶ chip
   ──▶ one of our words, p ≥ 0.35                                    ──▶ "Did you mean …?" (counts only if tapped)
   ──▶ anything else                                                  ──▶ [?]  (nothing spoken)
```

The model scores all 250 signs it knows and is never narrowed to our words first: a confident
"something else" stays [?] instead of becoming the nearest word on our list. These cut-offs are
provisional until the phone-camera clips are measured.

## One live-call turn, step by step

```
receptionist speaks ─▶ caption on screen (Bolna's Deepgram transcript via our backend)
user reads ─────────▶ hands at rest: nothing happens, however long the pause
user signs "no" ────▶ hands drop ~0.4 s ─▶ ASL model ─▶ chip [no] ─▶ draft updates
user signs "tomorrow"▶ fairly sure only ─▶ "Did you mean TOMORROW?" ─▶ user taps ─▶ chip ─▶ draft updates
user taps SEND ─────▶ backend ─▶ Bolna event ─▶ custom LLM returns the exact text ─▶ voice in the call
```

Two kinds of "end": the end of one sign is automatic (hands back at rest); the end of the
message is the user tapping **SEND**. The app never guesses.

## One "Call for me" call, step by step

```
user signs TOMORROW · MORNING ─▶ brief: "…book a doctor's appointment. Preferred: tomorrow in the morning…"
user approves (stays)         ─▶ Bolna dials; the agent says it calls for a Deaf caller, then states the request
receptionist: "4 pm tomorrow?" ─▶ agent: "One moment, please." ─▶ app: YES / NO / WAIT
user signs YES                ─▶ agent: "Yes, 4 pm tomorrow works. Thank you." ─▶ hangs up shortly after
notes                         ─▶ outcome booked, the offer quoted, the transcript
```

## Edge cases

| Situation | What the app does |
|---|---|
| Long pause or reading captions | Hands at rest, so nothing happens. On a live call Bolna says "One moment please, I'm signing my reply" after a long silence |
| Scratching nose, adjusting the phone | Too short, or not one of our words: ignored or [?] |
| Sign not recognised | [?], nothing spoken; sign again |
| Fairly sure, not certain | "Did you mean …?" tile; only a tap makes it a chip (or an answer) |
| A hand leaves the picture during a sign or as it ends | [?] with "A hand left the picture", never a chip, even for a one-handed sign whose hand left the side (that ends the sign, so the check also reads the rest frames right after it). A hand dropped below the rest line counts as resting |
| Wrong word recognised | User taps ✕ on the chip before SEND |
| Out of frame | Red pill: "can't see you" |
| Receptionist asks something with no sign | Quick replies on a live call; on a delegated call the agent asks the user or says it will call back |
| Receptionist talks while the user signs | New caption appears; the draft is kept and the user decides |
| SEND tapped twice | The approval is single use, so nothing is spoken twice |
| SEND while the receptionist is still talking | If Bolna doesn't confirm it spoke, the app shows "not delivered, tap SEND again". It never resends by itself |
| Stop mid-sentence | Not yet spoken: cancelled. Already speaking: words heard can't be unsaid; the user sends a correction |
| Agent's question unanswered for 10 s | The agent says "I'll need to check that and call back" instead of deciding |
| User signs WAIT to the agent's question | The agent holds the line and the question stays open |
| Receptionist offers something outside the brief | The agent never agrees to it: it asks the user (attended) or promises a callback (unattended) |
| Network drops or the call ends | "Nothing will be sent"; pending drafts are wiped; the next call starts clean |
| Receptionist says "booked" | Shown as their words. Neither the draft nor the agent claims a booking that wasn't said on the call |

## What the app knows and doesn't know

| Known | Not known |
|---|---|
| Its own camera frames, chips, drafts, approvals and playback state | Whether the receptionist understood |
| The receptionist's words (Bolna's transcript via the backend) | Path A: anything the receptionist says (iOS Live Captions are visible to the user only) |
| The purpose and details the user entered, and the brief they approved | Whether a booking actually happened beyond what was said |

## Honest limits

ASL only, from a published model used as is; 8 rehearsed signs, one at a time with the hands
at rest between signs; thresholds provisional until measured on the phone camera. Calls come
from a Bolna number (Path A, the bonus mode, keeps the user's number but has no captions). The
draft and the agent can reword but never add facts. ISL is the goal and is blocked by data. See
[PLAN.md §9](../PLAN.md#9-honest-limits-say-these-in-the-pitch).

History: [23 October workflow (personalised ISL)](archive/2026-10-23-workflow.md),
[20 October](archive/2026-10-20-workflow.md), [18 October](archive/2026-10-18-workflow.md).
